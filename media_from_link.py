import os
import re
import json
import requests
import traceback
import shutil
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import utils
import bot
import fetchers
from telebot import TeleBot
from dotenv import load_dotenv
from instaloader.exceptions import (
    LoginRequiredException,
    QueryReturnedBadRequestException,
)

# Get bot instance for direct message sending
BOT_TOKEN = utils.BOT_TOKEN
tgbot = TeleBot(BOT_TOKEN)


def extract_instagram_story_info(url):
    """
    Extract username and story ID from an Instagram story URL.
    Returns (username, story_id) tuple or (None, None) if extraction fails.

    Example URLs:
    - https://www.instagram.com/stories/username/12345678901234567/
    - https://instagram.com/stories/username/12345678901234567/
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.strip("/")

    # Match the path pattern for Instagram stories
    pattern = r"stories/([^/]+)/(\d+)"
    match = re.search(pattern, path)

    if match:
        username = match.group(1)
        story_id = match.group(2)
        return username, story_id

    return None, None


def fetch_specific_instagram_story(username, story_id):
    """
    Fetch a specific Instagram story based on username and story ID.
    Returns story data dict if found, None otherwise.
    """
    try:
        # First check if we already have this story saved locally
        sent_posts = utils.load_sent_posts()

        # Check if we have the story in our mapping
        story_key = f"instagram_story_{username}_{story_id}"
        if story_key in sent_posts.get("media_mapping", {}):
            media_paths = sent_posts["media_mapping"][story_key]
            # Verify files exist
            valid_paths = [p for p in media_paths if os.path.exists(p)]
            if valid_paths:
                return {
                    "media_paths": valid_paths,
                    "media_types": [
                        "photo" if not p.endswith(".mp4") else "video"
                        for p in valid_paths
                    ],
                    "content": f"Instagram story from {username}",
                    "url": f"https://www.instagram.com/stories/{username}/{story_id}/",
                }

        # Try using direct API request method with credentials from environment
        try:
            from instaloader import Instaloader, StoryItem, Profile

            L = Instaloader(
                download_videos=True,
                download_video_thumbnails=False,
                download_comments=False,
                save_metadata=False,
                quiet=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            )

            # Try to load session or login
            session_file = "instagram_session"
            INSTA_USERNAME = os.getenv("INSTA_USERNAME")
            INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")

            login_success = False
            try:
                if os.path.exists(session_file):
                    try:
                        L.load_session_from_file(INSTA_USERNAME, session_file)
                        login_success = True
                        print("Loaded Instagram session successfully")
                    except Exception as e:
                        print(f"Failed to load Instagram session: {e}")

            except Exception as e:
                print(f"Error checking for session file: {e}")

            if not login_success and INSTA_USERNAME and INSTA_PASSWORD:
                try:
                    L.login(INSTA_USERNAME, INSTA_PASSWORD)
                    L.save_session_to_file(session_file)
                    login_success = True
                    print("Logged into Instagram successfully")
                except Exception as e:
                    print(f"Failed to login to Instagram: {e}")

            # Get the profile and stories
            profile = Profile.from_username(L.context, username)

            try:
                story_items = L.get_stories([profile.userid])
                for story in story_items:
                    for item in story.get_items():
                        if str(item.mediaid) == story_id:
                            is_video = item.is_video
                            story_url = item.video_url if is_video else item.url

                            # Create a temporary directory for the media
                            import tempfile

                            temp_dir = tempfile.mkdtemp()

                            ext = ".mp4" if is_video else ".jpg"
                            filename = f"instagram_story_{username}_{story_id}{ext}"
                            media_path = os.path.join(temp_dir, filename)

                            # Download  media
                            if utils.download_media(story_url, media_path):
                                return {
                                    "media_paths": [media_path],
                                    "media_types": ["video" if is_video else "photo"],
                                    "content": f"Instagram story from {username}",
                                    "url": story_url,
                                }
            except LoginRequiredException:
                print("Login required to fetch Instagram stories")
            except Exception as e:
                print(f"Error fetching specific Instagram story using direct API: {e}")
        except ImportError:
            print("Instaloader module not available or cannot be imported correctly")
        except Exception as e:
            print(f"Error in direct Instagram API method: {e}")

        # Fallback
        try:
            all_stories = fetchers.fetch_instagram_stories(username, skip_tracking=True)

            if all_stories:
                for story in all_stories:
                    current_id = None

                    if story.get("media_paths"):
                        for path in story["media_paths"]:
                            if str(story_id) in path:
                                current_id = story_id
                                break

                    if not current_id and story.get("url"):
                        if str(story_id) in story["url"]:
                            current_id = story_id

                    if current_id:
                        return story
        except Exception as e:
            print(f"Error in fallback Instagram story fetch: {e}")

        print(f"Story ID {story_id} not found among available stories for {username}")
        return None

    except Exception as e:
        print(f"Error fetching specific Instagram story: {e}")
        traceback.print_exc()
        return None


def download_and_send_specific_instagram_story(message, url):
    """
    Download and send the specific Instagram story from the provided URL.
    Then clean up the files.
    """
    try:
        username, story_id = extract_instagram_story_info(url)

        if not username or not story_id:
            return False, "Could not extract username and story ID from URL."

        tgbot.reply_to(message, f"Looking for story from @{username}...")

        story = fetch_specific_instagram_story(username, story_id)

        if not story:
            return (
                False,
                f"Could not find story {story_id} for user @{username}. It might have expired or requires login.",
            )

        media_paths = []
        if story.get("media_paths"):
            utils.send_to_telegram(
                f"Instagram Story from @{username}",
                media_paths=story.get("media_paths"),
                media_types=story.get("media_types"),
                chat_id=message.chat.id,
            )
            media_paths = story.get("media_paths", [])
            result = True, f"Downloaded story from @{username}"

        elif story.get("url"):
            utils.send_to_telegram(
                f"Instagram Story from @{username}",
                media_url=story.get("url"),
                chat_id=message.chat.id,
            )
            result = True, f"Downloaded story from @{username}"

        else:
            return False, "Found the story but it doesn't contain media."

        cleanup_instagram_media(username, story_id, "story", media_paths)

        return result

    except Exception as e:
        error_msg = f"Error downloading Instagram story: {e}"
        print(error_msg)
        traceback.print_exc()
        return False, error_msg


def extract_instagram_post_info(url):
    """
    Extract post ID from an Instagram post or reel URL.
    Returns post_id or None if extraction fails.

    Example URLs:
    - https://www.instagram.com/p/ABC123/
    - https://instagram.com/reel/ABC123/
    - https://www.instagram.com/p/ABC123/?utm_source=ig_web_copy_link
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.strip("/")

    # Match the path pattern for Instagram posts or reels
    pattern = r"(?:p|reel)/([^/]+)"
    match = re.search(pattern, path)

    if match:
        post_id = match.group(1)
        return post_id

    return None


def fetch_specific_instagram_post(post_id):
    """
    Fetch a specific Instagram post based on post ID.
    Returns post data dict if found, None otherwise.
    """
    try:
        # We don't know the username in advance, so we need to search through posts
        # from various accounts that we monitor
        sent_posts = utils.load_sent_posts()
        instagram_accounts = utils.get_accounts_by_platform("instagram_posts")
        if not instagram_accounts:
            instagram_accounts = utils.get_accounts_by_platform("instagram")

        # Start with recent posts in sent_posts
        for post_entry in sent_posts.get("instagram_posts", []):
            if post_id in post_entry:
                for account in instagram_accounts:
                    key = f"instagram_post_{account}_{post_id}"
                    if key in sent_posts.get("media_mapping", {}):
                        # Found matching post in our history
                        media_paths = sent_posts["media_mapping"][key]
                        return {
                            "post_id": post_id,
                            "media_paths": media_paths,
                            "media_types": [
                                "photo" if not path.endswith(".mp4") else "video"
                                for path in media_paths
                            ],
                            "content": f"Instagram post found in history",
                            "url": f"https://www.instagram.com/p/{post_id}/",
                        }

        # Try to fetch from accounts we know about
        for account in instagram_accounts:
            try:
                posts = fetchers.fetch_instagram_posts(account)
                for post in posts:
                    post_url = post.get("url", "")
                    if post_id in post_url:
                        return post
            except Exception as e:
                print(f"Error fetching posts for {account}: {e}")
                continue

        print(f"Post ID {post_id} not found in any account's posts")
        return None

    except Exception as e:
        print(f"Error fetching specific Instagram post: {e}")
        traceback.print_exc()
        return None


def download_and_send_instagram_post(message, url):
    """
    Download and send the specific Instagram post from the provided URL.
    Then clean up the files.
    """
    try:
        post_id = extract_instagram_post_info(url)

        if not post_id:
            return False, "Could not extract post ID from URL."

        tgbot.reply_to(message, f"Looking for Instagram post {post_id}...")

        # Skip local history search and directly use fetch_instagram_post_by_shortcode
        # This avoids attempting to download from all previous accounts
        post = fetchers.fetch_instagram_post_by_shortcode(post_id)

        if not post:
            return False, f"Could not find Instagram post {post_id}"

        # Get username from post data or extract from URL
        username = post.get("username", extract_username_from_url(url) or "instagram")

        # Build the caption
        caption = f"Instagram Post\n\n{post.get('content', '')}\n\n{post.get('url', f'https://www.instagram.com/p/{post_id}/')}"

        # Send to Telegram
        media_paths = []
        if post.get("media_paths"):
            utils.send_to_telegram(
                caption,
                media_paths=post.get("media_paths"),
                media_types=post.get("media_types"),
                chat_id=message.chat.id,
            )
            media_paths = post.get("media_paths", [])
            result = True, f"Downloaded Instagram post {post_id}"

        elif post.get("media_url"):
            utils.send_to_telegram(
                caption, media_url=post.get("media_url"), chat_id=message.chat.id
            )
            result = True, f"Downloaded Instagram post {post_id}"

        else:
            return False, "Found the post but it doesn't contain media."

        # Clean up after sending
        cleanup_instagram_media(username, post_id, "post", media_paths)

        return result

    except Exception as e:
        error_msg = f"Error downloading Instagram post: {e}"
        print(error_msg)
        traceback.print_exc()
        return False, error_msg


def extract_username_from_url(url):
    """Extract username from an Instagram URL if possible"""
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path.strip("/")

        # Check for URL pattern like instagram.com/username/p/postid/
        path_parts = path.split("/")
        if len(path_parts) > 2:
            if path_parts[1] in ["p", "reel"]:
                return path_parts[0]
    except Exception:
        pass
    return None


def cleanup_instagram_media(username, content_id, content_type, media_paths):
    """Clean up downloaded Instagram media files and remove references from JSON"""
    try:
        # Remove files
        for path in media_paths:
            if os.path.exists(path):
                os.remove(path)
                print(f"Deleted file: {path}")

        # Remove directory if empty
        try:
            if content_type == "post":
                content_dir = os.path.join(
                    bot.INSTAGRAM_POSTS_DIR, username, content_id
                )
            else:  # story
                content_dir = os.path.join(
                    bot.INSTAGRAM_STORIES_DIR, username, content_id
                )

            if os.path.exists(content_dir) and not os.listdir(content_dir):
                os.rmdir(content_dir)
                print(f"Removed empty directory: {content_dir}")

                # Try to remove parent directory if empty
                parent_dir = os.path.dirname(content_dir)
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    print(f"Removed empty parent directory: {parent_dir}")
        except Exception as e:
            print(f"Error removing directories: {e}")

        # Remove references from JSON
        sent_posts = utils.load_sent_posts()
        key_suffix = (
            f"{'post' if content_type == 'post' else 'story'}_{username}_{content_id}"
        )

        # Remove from media mapping
        if "media_mapping" in sent_posts:
            keys_to_remove = [
                k for k in sent_posts["media_mapping"] if k.endswith(key_suffix)
            ]
            for key in keys_to_remove:
                sent_posts["media_mapping"].pop(key, None)

        # Remove from post lists if needed
        if content_type == "post" and "instagram_posts" in sent_posts:
            sent_posts["instagram_posts"] = [
                p for p in sent_posts["instagram_posts"] if content_id not in p
            ]
        elif content_type == "story" and "instagram_stories" in sent_posts:
            sent_posts["instagram_stories"] = [
                s for s in sent_posts["instagram_stories"] if content_id not in s
            ]

        utils.save_sent_posts(sent_posts)
        print(f"Cleaned up references to {content_type} {content_id}")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        traceback.print_exc()


def extract_x_post_info(url):
    """
    Extract post ID from an X/Twitter URL.
    Returns post_id or None if extraction fails.

    Example URLs:
    - https://twitter.com/username/status/12345678901234567
    - https://x.com/username/status/12345678901234567
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.strip("/")

    # Match the path pattern for Twitter/X posts
    pattern = r"(?:status|statuses)/(\d+)"
    match = re.search(pattern, path)

    if match:
        post_id = match.group(1)
        return post_id

    return None


def extract_x_username_from_url(url):
    """Extract username from an X/Twitter URL if possible"""
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path.strip("/")
        path_parts = path.split("/")

        # URL format is typically: twitter.com/username/status/id
        if len(path_parts) >= 3 and path_parts[1] in ["status", "statuses"]:
            return path_parts[0]
    except Exception:
        pass
    return None


def fetch_specific_x_post(post_id, username=None):
    """
    Fetch a specific X post based on post ID.
    Returns post data dict if found, None otherwise.
    """
    try:
        # Check if we've already downloaded this post
        sent_posts = utils.load_sent_posts()
        x_accounts = utils.get_accounts_by_platform("twitter")

        # First, try the specific username if provided
        if username:
            key = f"twitter_{username}_{post_id}"
            if key in sent_posts.get("media_mapping", {}):
                media_paths = sent_posts["media_mapping"][key]
                valid_paths = [p for p in media_paths if os.path.exists(p)]
                if valid_paths:
                    return {
                        "id": post_id,
                        "username": username,
                        "media_paths": valid_paths,
                        "media_types": [
                            "photo" if not path.endswith(".mp4") else "video"
                            for path in valid_paths
                        ],
                        "content": f"X post from @{username}",
                        "url": f"https://twitter.com/{username}/status/{post_id}",
                    }

        # Try all known accounts
        for account in x_accounts:
            key = f"twitter_{account}_{post_id}"
            if key in sent_posts.get("media_mapping", {}):
                media_paths = sent_posts["media_mapping"][key]
                valid_paths = [p for p in media_paths if os.path.exists(p)]
                if valid_paths:
                    return {
                        "id": post_id,
                        "username": account,
                        "media_paths": valid_paths,
                        "media_types": [
                            "photo" if not path.endswith(".mp4") else "video"
                            for path in valid_paths
                        ],
                        "content": f"X post from @{account}",
                        "url": f"https://twitter.com/{account}/status/{post_id}",
                    }

        # Not found in our records, try to fetch it if username is provided
        if username:
            try:
                # This will attempt to fetch recent posts from the user,
                # which may include the one we're looking for
                new_posts = fetchers.fetch_x_posts(username)

                # Check if our post_id is now in the fetched posts
                sent_posts = utils.load_sent_posts()
                key = f"twitter_{username}_{post_id}"
                if key in sent_posts.get("media_mapping", {}):
                    media_paths = sent_posts["media_mapping"][key]
                    valid_paths = [p for p in media_paths if os.path.exists(p)]
                    if valid_paths:
                        return {
                            "id": post_id,
                            "username": username,
                            "media_paths": valid_paths,
                            "media_types": [
                                "photo" if not path.endswith(".mp4") else "video"
                                for path in valid_paths
                            ],
                            "content": f"X post from @{username}",
                            "url": f"https://twitter.com/{username}/status/{post_id}",
                        }

                # Alternative: search through the returned new posts
                for post in new_posts:
                    if post.get("id") == post_id:
                        return post
            except Exception as e:
                print(f"Error fetching posts for {username}: {e}")

        # Post not found
        return None

    except Exception as e:
        print(f"Error fetching specific X post: {e}")
        traceback.print_exc()
        return None


def download_and_send_x_post(message, url):
    """
    Download and send the specific X post from the provided URL.
    Then clean up the files.
    """
    try:
        post_id = extract_x_post_info(url)

        if not post_id:
            return False, "Could not extract post ID from URL."

        # Try to extract username from URL
        username = extract_x_username_from_url(url)

        tgbot.reply_to(
            message,
            f"Looking for X post {post_id}{' from @'+username if username else ''}...",
        )

        # Try to find or fetch the post
        post = fetch_specific_x_post(post_id, username)

        if not post:
            return (
                False,
                f"Could not find X post {post_id}. The post may be private, deleted, or not contain media.",
            )

        # Build the caption
        caption = f"X Post from @{post.get('username', username or 'Twitter user')}\n\n{post.get('content', '')}\n\n{post.get('url', f'https://twitter.com/status/{post_id}')}"

        # Send to Telegram
        media_paths = []
        if post.get("media_paths"):
            utils.send_to_telegram(
                caption,
                media_paths=post.get("media_paths"),
                media_types=post.get("media_types"),
                chat_id=message.chat.id,
            )
            media_paths = post.get("media_paths", [])
            result = True, f"Downloaded X post {post_id}"
        else:
            return False, "Found the post but it doesn't contain media."

        # Clean up after sending
        post_username = post.get("username", username)
        if post_username:
            cleanup_x_media(post_username, post_id, media_paths)

        return result

    except Exception as e:
        error_msg = f"Error downloading X post: {e}"
        print(error_msg)
        traceback.print_exc()
        return False, error_msg


def cleanup_x_media(username, post_id, media_paths):
    """Clean up downloaded X media files but keep records for tracking"""
    try:
        # Remove files
        for path in media_paths:
            if os.path.exists(path):
                os.remove(path)
                print(f"Deleted file: {path}")

        # Remove directory if empty
        try:
            content_dir = os.path.join(bot.TWITTER_MEDIA_DIR, username, post_id)
            if os.path.exists(content_dir) and not os.listdir(content_dir):
                os.rmdir(content_dir)
                print(f"Removed empty directory: {content_dir}")

                # Try to remove parent directory if empty
                parent_dir = os.path.dirname(content_dir)
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    print(f"Removed empty parent directory: {parent_dir}")
        except Exception as e:
            print(f"Error removing directories: {e}")

        # Remove from media mapping in JSON
        sent_posts = utils.load_sent_posts()
        key = f"twitter_{username}_{post_id}"

        if "media_mapping" in sent_posts and key in sent_posts["media_mapping"]:
            sent_posts["media_mapping"].pop(key, None)
            utils.save_sent_posts(sent_posts)
            print(f"Removed media mapping for {key}")

        # Note: We're keeping the post ID in x_posts list to avoid re-downloading via auto-fetch

    except Exception as e:
        print(f"Error during X media cleanup: {e}")
        traceback.print_exc()
