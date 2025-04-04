import os
import json
import time
import telebot
import requests
from urllib.parse import urlparse
import random
import uuid
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

# Define constants and paths
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TWITTER_CACHE_EXPIRY = 1800

# File paths
SENT_POSTS_FILE = "d:/coding_workspace/telegram/sent_posts.json"
TWITTER_CACHE_FILE = "d:/coding_workspace/telegram/twitter_cache.json"
SENT_VIDEOS_FILE = "d:/coding_workspace/telegram/sent_videos.json"
MEDIA_DIR = "d:/coding_workspace/telegram/media"

# Create bot instance
bot = telebot.TeleBot(BOT_TOKEN)


def get_user_media_dir(platform, username):
    """Create and return a directory path specific for a platform+username"""
    dir_path = os.path.join(MEDIA_DIR, f"{platform}_{username}")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def generate_media_filename(prefix, id_value, extension):
    """Generate a unique filename using UUID to prevent collisions"""
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{id_value}_{unique_id}{extension}"


def load_sent_posts():
    if os.path.exists(SENT_POSTS_FILE):
        with open(SENT_POSTS_FILE, "r") as f:
            data = json.load(f)
            # Ensure all required fields exist
            if "x_posts" not in data:
                data["x_posts"] = []
            if "instagram_posts" not in data:
                data["instagram_posts"] = []
            if "instagram_stories" not in data:
                data["instagram_stories"] = []
            if "media_mapping" not in data:
                data["media_mapping"] = {}
            if "accounts" not in data:
                data["accounts"] = {"twitter": [], "instagram": [], "bilibili": []}
            return data
    return {
        "x_posts": [],
        "instagram_posts": [],
        "instagram_stories": [],
        "media_mapping": {},  # keep track of file paths
        "accounts": {"twitter": [], "instagram": [], "bilibili": []},  # track accounts
    }


def save_sent_posts(sent_posts):
    # Ensure required fields exist
    if "media_mapping" not in sent_posts:
        sent_posts["media_mapping"] = {}
    if "accounts" not in sent_posts:
        sent_posts["accounts"] = {"twitter": [], "instagram": [], "bilibili": []}

    with open(SENT_POSTS_FILE, "w") as f:
        json.dump(sent_posts, f)


def get_post_media_files(platform, post_id):
    """Get media files associated with a specific post"""
    sent_posts = load_sent_posts()
    # Try the direct key first
    key = f"{platform}_{post_id}"
    if key in sent_posts.get("media_mapping", {}):
        paths = sent_posts["media_mapping"][key]
        # Verify the files exist
        valid_paths = [p for p in paths if os.path.exists(p)]
        if valid_paths:
            return valid_paths

    # Try a fallback search by scanning media directories
    if platform == "twitter":
        platform_dir = "twitter"
    elif platform == "instagram_post":
        platform_dir = "instagram"
    elif platform == "instagram_story":
        platform_dir = "instagram_stories"
    elif platform == "bilibili":
        platform_dir = "bilibili"
    else:
        return []

    # Search for files matching the post_id
    matching_files = []
    for root, _, files in os.walk(MEDIA_DIR):
        if platform_dir in root:
            for file in files:
                if post_id in file:
                    full_path = os.path.join(root, file)
                    matching_files.append(full_path)

    return matching_files


def save_media_mapping(platform, post_id, media_paths):
    """Save mapping between post ID and its media files"""
    sent_posts = load_sent_posts()
    if "media_mapping" not in sent_posts:
        sent_posts["media_mapping"] = {}
    # Use proper key format for consistent retrieval
    sent_posts["media_mapping"][f"{platform}_{post_id}"] = media_paths
    save_sent_posts(sent_posts)


def register_account(platform, username):
    """Register an account in the platform's account list"""
    sent_posts = load_sent_posts()
    if "accounts" not in sent_posts:
        sent_posts["accounts"] = {"twitter": [], "instagram": [], "bilibili": []}

    platform_key = platform
    if platform == "x":
        platform_key = "twitter"

    if username not in sent_posts["accounts"].get(platform_key, []):
        if platform_key not in sent_posts["accounts"]:
            sent_posts["accounts"][platform_key] = []
        sent_posts["accounts"][platform_key].append(username)
        save_sent_posts(sent_posts)


def scan_and_register_accounts():
    """Scan media directories to discover and register existing accounts"""
    if not os.path.exists(MEDIA_DIR):
        return

    # Dictionary to hold found accounts
    found_accounts = {"twitter": set(), "instagram": set(), "bilibili": set()}

    # Scan directory structure for account folders
    for item in os.listdir(MEDIA_DIR):
        path = os.path.join(MEDIA_DIR, item)
        if os.path.isdir(path):
            parts = item.split("_", 1)  # Split at first underscore
            if len(parts) == 2:
                platform, username = parts
                if platform == "twitter":
                    found_accounts["twitter"].add(username)
                elif platform == "instagram":
                    found_accounts["instagram"].add(username)
                elif platform == "instagram_stories":
                    # Extract username from instagram_stories_username
                    found_accounts["instagram"].add(username)
                elif platform == "bilibili":
                    found_accounts["bilibili"].add(username)

    # Register all found accounts
    sent_posts = load_sent_posts()
    for platform, accounts in found_accounts.items():
        for account in accounts:
            if account not in sent_posts["accounts"].get(platform, []):
                if platform not in sent_posts["accounts"]:
                    sent_posts["accounts"][platform] = []
                sent_posts["accounts"][platform].append(account)
                print(f"Registered existing {platform} account: {account}")

    save_sent_posts(sent_posts)
    return found_accounts


def get_accounts_by_platform(platform):
    """Get all accounts for a given platform"""
    # Scan for existing accounts first
    scan_and_register_accounts()

    sent_posts = load_sent_posts()
    platform_key = platform
    if platform == "x":
        platform_key = "twitter"

    return sent_posts.get("accounts", {}).get(platform_key, [])


def load_twitter_cache():
    if os.path.exists(TWITTER_CACHE_FILE):
        with open(TWITTER_CACHE_FILE, "r") as f:
            cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < TWITTER_CACHE_EXPIRY:
                return cache
    return {"timestamp": 0, "tweets": []}


def save_twitter_cache(tweets_data):
    cache = {"timestamp": time.time(), "tweets": tweets_data}
    with open(TWITTER_CACHE_FILE, "w") as f:
        json.dump(cache, f)


def load_sent_videos():
    """
    Loads a JSON with Bilibili/videos that have been processed to avoid duplicates.
    """
    if os.path.exists(SENT_VIDEOS_FILE):
        with open(SENT_VIDEOS_FILE, "r") as f:
            return json.load(f)
    return {"videos": []}


def save_sent_videos(sent_videos):
    """
    Saves the JSON that tracks which videos have been processed.
    """
    with open(SENT_VIDEOS_FILE, "w") as f:
        json.dump(sent_videos, f)


def send_to_telegram(
    message_text, media_paths=None, media_types=None, media_url=None, chat_id=None
):
    """
    Send message and/or media to Telegram.

    Args:
        message_text: Text message to send
        media_paths: List of local file paths to media files
        media_types: List of media types (photo/video) corresponding to media_paths
        media_url: Direct URL to a media file (alternative to media_paths)
        chat_id: Specific chat ID to send to (defaults to CHAT_ID)
    """
    if chat_id is None:
        chat_id = CHAT_ID

    try:
        if media_paths and len(media_paths) > 0:
            if len(media_paths) == 1:
                media_path = media_paths[0]
                mtype = media_types[0] if media_types else "photo"
                if mtype == "video":
                    with open(media_path, "rb") as vid:
                        bot.send_video(chat_id, vid, caption=message_text)
                else:
                    with open(media_path, "rb") as img:
                        bot.send_photo(chat_id, img, caption=message_text)
            else:
                media = []
                for i, path in enumerate(media_paths):
                    mtype = media_types[i] if i < len(media_types) else "photo"
                    if mtype == "video":
                        with open(path, "rb") as vid:
                            media.append(
                                telebot.types.InputMediaVideo(
                                    vid, caption=message_text if i == 0 else None
                                )
                            )
                    else:
                        with open(path, "rb") as img:
                            media.append(
                                telebot.types.InputMediaPhoto(
                                    img, caption=message_text if i == 0 else None
                                )
                            )
                bot.send_media_group(chat_id, media)
        elif media_url:
            try:
                bot.send_photo(chat_id, media_url, caption=message_text)
            except Exception:
                bot.send_message(chat_id, f"{message_text}\n\nMedia: {media_url}")
        else:
            bot.send_message(chat_id, message_text)
    except Exception as e:
        print(f"Error sending message: {e}")


def download_media(url, path, retries=3, timeout=10):
    """
    Download media from URL to specified path

    Args:
        url: URL to download from
        path: Path to save the file
        retries: Number of retry attempts
        timeout: Connection timeout in seconds

    Returns:
        bool: True if download was successful
    """
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
                except Exception as e:
                    print(f"Error writing to {path}: {e}")
                    return False
            else:
                print(f"Attempt {attempt+1}: HTTP {response.status_code}")
        except Exception as e:
            print(f"Attempt {attempt+1}: Error downloading media {url}: {e}")
        time.sleep(2)
    print(f"Failed to download media {url} after {retries} attempts")
    return False
