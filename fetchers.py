import os
import time
import random
import requests
import json
import instaloader
import traceback
import re
import uuid
from dotenv import load_dotenv

import utils

from glob import glob
from os.path import expanduser
from platform import system
from sqlite3 import OperationalError, connect
from instaloader.exceptions import QueryReturnedBadRequestException

INSTAGRAM_AVAILABLE = True


def import_session_cookies_from_firefox(sessionfile):
    try:
        default_cookiefile = {
            "Windows": "~/AppData/Roaming/Mozilla/Firefox/Profiles/*/cookies.sqlite",
            "Darwin": "~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite",
        }.get(system(), "~/.mozilla/firefox/*/cookies.sqlite")
        cookiefiles = glob(expanduser(default_cookiefile))
        if not cookiefiles:
            print("No Firefox cookies.sqlite found for Instagram.")
            return False

        cookiefile = cookiefiles[0]
        print(f"Using Firefox cookies: {cookiefile}")
        conn = connect(f"file:{cookiefile}?immutable=1", uri=True)
        try:
            cookie_data = conn.execute(
                "SELECT name, value FROM moz_cookies WHERE baseDomain='instagram.com'"
            )
        except OperationalError:
            cookie_data = conn.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE '%instagram.com'"
            )
        L.context._session.cookies.update(cookie_data)
        username = L.test_login()
        if not username:
            print("Not logged in with Firefox cookies.")
            return False
        print(f"Imported Firefox session cookies for {username}")
        L.context.username = username
        L.save_session_to_file(sessionfile)
        return True
    except Exception as e:
        print(f"Failed to import Firefox cookies: {e}")
        return False


def attempt_instagram_login(max_retries=1):
    global INSTAGRAM_AVAILABLE
    for attempt in range(max_retries):
        try:
            L.load_session_from_file(INSTAGRAM_USERNAME, "instagram_session")
            print("Successfully loaded Instagram session from file")
            return
        except FileNotFoundError:
            print(f"Session file not found - attempt {attempt+1}/{max_retries}")
            try:
                if attempt > 0:
                    # backoff = 5 * (2 ** (attempt - 1))
                    backoff = 1
                    print(f"Sleeping {backoff} seconds before retry...")
                    time.sleep(backoff)
                L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                print("Successfully logged into Instagram")
                L.save_session_to_file("instagram_session")
                return
            except instaloader.exceptions.BadCredentialsException:
                print("Error: Invalid Instagram credentials")
                INSTAGRAM_AVAILABLE = False
                return
            except instaloader.exceptions.ConnectionException as e:
                print(f"Connection error: {e}")
        except instaloader.exceptions.ConnectionException as e:
            print(f"Connection error: {e}")

    print("All regular login attempts to Instagram failed. Trying Firefox cookies.")
    if not import_session_cookies_from_firefox("instagram_session"):
        print("Cookie import also failed. Instagram features will be disabled.")
        INSTAGRAM_AVAILABLE = False


load_dotenv()

MEDIA_DIR = utils.MEDIA_DIR
SENT_POSTS_FILE = utils.SENT_POSTS_FILE
TWITTER_CACHE_FILE = utils.TWITTER_CACHE_FILE
TWITTER_CACHE_EXPIRY = utils.TWITTER_CACHE_EXPIRY
bot = utils.bot

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

L = instaloader.Instaloader()
attempt_instagram_login()

if not os.path.exists(MEDIA_DIR):
    try:
        os.makedirs(MEDIA_DIR)
        print(f"Created media directory: {MEDIA_DIR}")
    except Exception as e:
        print(f"Failed to create media directory {MEDIA_DIR}: {e}")


def download_media(url, path, retries=3, timeout=10):
    # Create parent directory if needed
    os.makedirs(os.path.dirname(path), exist_ok=True)

    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, stream=True, timeout=timeout)
            if response.status_code == 200:
                try:
                    with open(path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Downloaded media to {path}")
                    return True
                except PermissionError:
                    print(f"Permission denied to write to {path}")
                    return False
                except FileNotFoundError:
                    print(
                        f"Directory not found for {path}. Ensure {os.path.dirname(path)} exists."
                    )
                    return False
                except OSError as e:
                    print(f"OS error writing to {path}: {e}")
                    return False
            else:
                print(f"Attempt {attempt+1}: HTTP {response.status_code}")
        except (
            requests.exceptions.RequestException,
            requests.exceptions.SSLError,
        ) as e:
            print(f"Attempt {attempt+1}: Error downloading media {url}: {e}")
        time.sleep(2)
    print(f"Failed to download media {url} after {retries} attempts")
    return False


def get_twitter_user_id(username, headers, max_retries=3):
    clean_username = username.replace("@", "")
    user_url = f"https://api.twitter.com/2/users/by/username/{clean_username}"
    for attempt in range(max_retries):
        try:
            response = requests.get(user_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()["data"]["id"]
            elif response.status_code == 429:
                reset_time = int(
                    response.headers.get("x-rate-limit-reset", time.time() + 900)
                )  # Default 15 min
                wait_time = max(reset_time - time.time(), 1)
                reset_datetime = time.ctime(reset_time)
                print(
                    f"Rate limit exceeded. Waiting {wait_time:.0f} seconds until {reset_datetime}"
                )
                if CHAT_ID:
                    bot.send_message(
                        CHAT_ID,
                        f"Twitter API rate limit reached for @{clean_username}. Waiting {wait_time:.0f} seconds until {reset_datetime}.",
                    )
                time.sleep(wait_time)
            else:
                print(f"Failed to get user ID: HTTP {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: Error fetching user ID: {e}")
            time.sleep(2**attempt)
    print(f"Failed to get user ID for {clean_username} after {max_retries} attempts")
    if CHAT_ID:
        bot.send_message(
            CHAT_ID,
            f"Failed to fetch Twitter user ID for @{clean_username} after {max_retries} attempts due to rate limits or errors.",
        )
    return None


def fetch_x_posts(username):
    try:
        sent_posts = utils.load_sent_posts()
        new_posts = []
        clean_username = username.replace("@", "")
        print(f"Fetching X posts for: {clean_username}")

        # Register the account
        utils.register_account("twitter", clean_username)

        # Create user directory, properly structured
        base_twitter_dir = os.path.join(MEDIA_DIR, "twitter")
        user_media_dir = os.path.join(base_twitter_dir, clean_username)
        os.makedirs(user_media_dir, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }

        user_id = get_twitter_user_id(clean_username, headers)
        if not user_id:
            print(f"Skipping X posts fetch for {clean_username} due to user ID failure")
            return []

        tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
        params = {
            "max_results": 10,
            "expansions": "attachments.media_keys",
            "tweet.fields": "id,text,created_at",
            "media.fields": "media_key,type,url,variants",
        }
        for attempt in range(3):
            try:
                tweets_response = requests.get(
                    tweets_url, headers=headers, params=params, timeout=10
                )
                if tweets_response.status_code == 200:
                    break
                elif tweets_response.status_code == 429:
                    reset_time = int(
                        tweets_response.headers.get(
                            "x-rate-limit-reset", time.time() + 900
                        )
                    )
                    wait_time = max(reset_time - time.time(), 1)
                    reset_datetime = time.ctime(reset_time)
                    print(
                        f"Rate limit exceeded for tweets. Waiting {wait_time:.0f} seconds until {reset_datetime}"
                    )
                    if CHAT_ID:
                        bot.send_message(
                            CHAT_ID,
                            f"Twitter API rate limit reached for @{clean_username}'s tweets. Waiting {wait_time:.0f} seconds until {reset_datetime}.",
                        )
                    time.sleep(wait_time)
                else:
                    print(f"Failed to fetch tweets: HTTP {tweets_response.status_code}")
                    return []
            except requests.exceptions.RequestException as e:
                print(f"Attempt {attempt+1}: Error fetching tweets: {e}")
                time.sleep(2**attempt)
        else:
            print(f"Failed to fetch tweets for {clean_username} after retries")
            if CHAT_ID:
                bot.send_message(
                    CHAT_ID,
                    f"Failed to fetch tweets for @{clean_username} after retries due to rate limits or errors.",
                )
            return []

        tweets_data = tweets_response.json()

        media_dict = {
            m["media_key"]: m for m in tweets_data.get("includes", {}).get("media", [])
        }
        for tweet in tweets_data.get("data", []):
            tweet_id = tweet["id"]
            if tweet_id not in sent_posts["x_posts"]:
                media_paths = []
                media_types = []

                tweet_dir = os.path.join(user_media_dir, tweet_id)
                os.makedirs(tweet_dir, exist_ok=True)

                if "attachments" in tweet and "media_keys" in tweet["attachments"]:
                    for media_key in tweet["attachments"]["media_keys"]:
                        media = media_dict.get(media_key)
                        if media:
                            mtype = media["type"]
                            murl = None

                            if mtype == "photo":
                                murl = media.get("url")
                            elif mtype in ["video", "animated_gif"]:
                                variants = media.get("variants", [])
                                if variants:
                                    best_variant = max(
                                        variants,
                                        key=lambda x: x.get("bitrate", 0),
                                        default=None,
                                    )
                                    murl = (
                                        best_variant.get("url")
                                        if best_variant
                                        else None
                                    )

                            if murl:
                                ext = ".jpg" if mtype == "photo" else ".mp4"
                                media_filename = utils.generate_media_filename(
                                    "x", tweet_id, ext
                                )
                                # Save in tweet-specific directory
                                media_path = os.path.join(tweet_dir, media_filename)

                                if not os.path.exists(media_path):
                                    if download_media(murl, media_path):
                                        media_paths.append(media_path)
                                        media_types.append(mtype)
                                    else:
                                        print(
                                            f"Skipping media {murl} due to download failure"
                                        )
                                else:
                                    media_paths.append(media_path)
                                    media_types.append(mtype)
                            else:
                                print(
                                    f"No valid URL for media_key {media_key}, type {mtype}"
                                )

                new_post = {
                    "id": tweet_id,
                    "content": f"New X post from @{clean_username}:\n\n{tweet['text']}",
                    "url": f"https://twitter.com/{clean_username}/status/{tweet_id}",
                }
                if media_paths:
                    new_post["media_paths"] = media_paths
                    new_post["media_types"] = media_types
                    # Save media mapping for later retrieval
                    utils.save_media_mapping(
                        f"twitter_{clean_username}", tweet_id, media_paths
                    )
                    print(f"Added {len(media_paths)} media files to tweet {tweet_id}")
                else:
                    new_post["media_note"] = (
                        "Media unavailable due to download issues or missing URL"
                    )

                new_posts.append(new_post)
                sent_posts["x_posts"].append(tweet_id)
                print(f"Added tweet ID {tweet_id}")

        utils.save_sent_posts(sent_posts)
        return new_posts
    except Exception as e:
        print(f"Error fetching X posts: {e}")
        traceback.print_exc()
        return []


def get_instagram_posts_safely(profile, max_count=500):
    posts = []

    try:
        print("Attempting to fetch posts directly...")
        conservative_loader = instaloader.Instaloader(
            sleep=True,
            quiet=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            max_connection_attempts=3,
        )

        username = profile.username
        print(f"Getting recent posts for {username} without pagination...")

        post_count = 0

        try:
            for post in profile.get_posts():
                posts.append(post)
                post_count += 1
                if post_count >= max_count:
                    break
        except Exception as e:
            print(f"Error getting posts from profile: {e}")

    except QueryReturnedBadRequestException as e:
        print(f"Query returned bad request: {e}")

    if len(posts) < max_count:
        print("Using direct scraping method for Instagram posts")
        username = profile.username

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            url = f"https://www.instagram.com/{username}/"
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                shared_data_match = re.search(
                    r"window\._sharedData\s*=\s*(\{.+?\});</script>", response.text
                )

                if shared_data_match:
                    shared_data = json.loads(shared_data_match.group(1))
                    user_data = (
                        shared_data.get("entry_data", {})
                        .get("ProfilePage", [{}])[0]
                        .get("graphql", {})
                        .get("user", {})
                    )

                    if user_data:
                        edges = user_data.get("edge_owner_to_timeline_media", {}).get(
                            "edges", []
                        )

                        print(f"Found {len(edges)} posts via scraping")

                        for edge in edges[:max_count]:
                            node = edge.get("node", {})
                            if node:
                                shortcode = node.get("shortcode")
                                if shortcode:
                                    try:
                                        simplified_post = type("", (), {})()
                                        simplified_post.shortcode = shortcode
                                        simplified_post.caption = (
                                            node.get("edge_media_to_caption", {})
                                            .get("edges", [{}])[0]
                                            .get("node", {})
                                            .get("text", "No caption")
                                        )
                                        simplified_post.url = node.get("display_url")
                                        simplified_post.is_video = node.get(
                                            "is_video", False
                                        )
                                        simplified_post.video_url = node.get(
                                            "video_url"
                                        )

                                        try:
                                            simplified_post.date = (
                                                datetime.fromtimestamp(
                                                    node.get("taken_at_timestamp", 0)
                                                )
                                            )
                                        except:
                                            simplified_post.date = datetime.now()

                                        posts.append(simplified_post)
                                        print(
                                            f"Added post with shortcode {shortcode} via scraping"
                                        )
                                    except Exception as e:
                                        print(
                                            f"Error processing scraped post {shortcode}: {e}"
                                        )
                else:
                    print("Could not find window._sharedData in Instagram response")
            else:
                print(
                    f"Instagram profile page returned status code: {response.status_code}"
                )
        except Exception as e:
            print(f"Error in direct scraping method: {e}")

    return posts[:max_count]


def fetch_instagram_posts(username):
    if not INSTAGRAM_AVAILABLE:
        print("INSTAGRAM_AVAILABLE is False, skipping Instagram posts.")
        return []
    try:
        sent_posts = utils.load_sent_posts()
        new_posts = []
        print(f"Fetching Instagram posts for: {username}")

        # Register the account
        utils.register_account("instagram", username)

        # Create user-specific directory in the correct structure
        base_posts_dir = os.path.join(MEDIA_DIR, "instagram", "posts")
        user_media_dir = os.path.join(base_posts_dir, username)
        os.makedirs(user_media_dir, exist_ok=True)

        try:
            print(f"Attempting to fetch profile for {username}")
            profile = instaloader.Profile.from_username(L.context, username)
        except Exception as e:
            print(f"Error accessing Instagram profile '{username}': {e}")
            return []

        print(
            f"Found Instagram profile {profile.username} with {profile.mediacount} posts"
        )

        posts = get_instagram_posts_safely(profile, 500)

        if not posts:
            print(f"Could not retrieve any posts for {username}")
            return []

        for post in posts:
            if str(post.shortcode) not in sent_posts["instagram_posts"]:
                caption = post.caption if post.caption else "No caption"

                is_video = post.is_video
                media_url = post.video_url if is_video else post.url

                # Create post-specific directory
                post_dir = os.path.join(user_media_dir, str(post.shortcode))
                os.makedirs(post_dir, exist_ok=True)

                ext = ".mp4" if is_video else ".jpg"
                media_filename = utils.generate_media_filename(
                    "instagram", post.shortcode, ext
                )
                # Save in post-specific directory
                media_path = os.path.join(post_dir, media_filename)

                if not os.path.exists(media_path):
                    success = download_media(media_url, media_path)
                else:
                    success = True

                new_post = {
                    "id": post.shortcode,
                    "content": f"New Instagram post from {username}:\n\n{caption}",
                    "url": f"https://www.instagram.com/p/{post.shortcode}/",
                }
                if success and os.path.exists(media_path):
                    new_post["media_paths"] = [media_path]
                    new_post["media_types"] = ["video" if is_video else "photo"]
                    # Save media mapping for later retrieval
                    utils.save_media_mapping(
                        f"instagram_post_{username}", post.shortcode, [media_path]
                    )
                    print(f"Added media to Instagram post {post.shortcode}")
                else:
                    new_post["media_note"] = "Media unavailable due to download issues"

                new_posts.append(new_post)
                sent_posts["instagram_posts"].append(str(post.shortcode))
                print(f"Added Instagram post ID {post.shortcode}")

        utils.save_sent_posts(sent_posts)
        return new_posts
    except Exception as e:
        print(f"Error fetching Instagram posts: {e}")
        traceback.print_exc()
        return []


def fetch_instagram_stories(username):
    if not INSTAGRAM_AVAILABLE:
        print("INSTAGRAM_AVAILABLE is False, skipping Instagram stories.")
        return []
    try:
        sent_posts = utils.load_sent_posts()
        new_stories = []
        print(f"Fetching Instagram stories for: {username}")

        # Register the account
        utils.register_account("instagram", username)

        # Create user-specific directory in the correct structure
        base_stories_dir = os.path.join(MEDIA_DIR, "instagram", "stories")
        user_media_dir = os.path.join(base_stories_dir, username)
        os.makedirs(user_media_dir, exist_ok=True)

        try:
            profile = instaloader.Profile.from_username(L.context, username)
        except Exception as e:
            print(f"Error accessing Instagram profile '{username}': {e}")
            return []

        try:
            stories = L.get_stories([profile.userid])
            for story in stories:
                for item in story.get_items():
                    if str(item.mediaid) not in sent_posts["instagram_stories"]:
                        is_video = item.is_video
                        story_url = item.video_url if is_video else item.url

                        # Create story-specific directory
                        story_dir = os.path.join(user_media_dir, str(item.mediaid))
                        os.makedirs(story_dir, exist_ok=True)

                        ext = ".mp4" if is_video else ".jpg"
                        media_filename = utils.generate_media_filename(
                            "instagram_story", item.mediaid, ext
                        )
                        # Save in story-specific directory
                        media_path = os.path.join(story_dir, media_filename)

                        if not os.path.exists(media_path):
                            success = download_media(story_url, media_path)
                        else:
                            success = True

                        new_story = {
                            "id": item.mediaid,
                            "content": f"New Instagram story from {username}!",
                            "url": story_url,
                        }
                        if success and os.path.exists(media_path):
                            new_story["media_paths"] = [media_path]
                            new_story["media_types"] = [
                                "video" if is_video else "photo"
                            ]
                            # Save media mapping for later retrieval
                            utils.save_media_mapping(
                                f"instagram_story_{username}",
                                item.mediaid,
                                [media_path],
                            )
                            print(f"Added media to Instagram story {item.mediaid}")
                        else:
                            new_story["media_note"] = (
                                "Media unavailable due to download issues"
                            )

                        new_stories.append(new_story)
                        sent_posts["instagram_stories"].append(str(item.mediaid))
                        print(f"Added Instagram story ID {item.mediaid}")
        except instaloader.exceptions.LoginRequiredException:
            print("Instagram login required to fetch stories")
        except Exception as e:
            print(f"Error processing stories: {e}")

        utils.save_sent_posts(sent_posts)
        return new_stories
    except Exception as e:
        print(f"Error fetching Instagram stories: {e}")
        traceback.print_exc()
        return []
