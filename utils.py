import os
import json
import time
import telebot
import requests
from urllib.parse import urlparse
import random
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


def load_sent_posts():
    if os.path.exists(SENT_POSTS_FILE):
        with open(SENT_POSTS_FILE, "r") as f:
            return json.load(f)
    return {"x_posts": [], "instagram_posts": [], "instagram_stories": []}


def save_sent_posts(sent_posts):
    with open(SENT_POSTS_FILE, "w") as f:
        json.dump(sent_posts, f)


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


def send_to_telegram(message, media_url=None, media_paths=None, media_types=None):
    try:
        if media_paths and len(media_paths) > 0:
            if len(media_paths) == 1:
                media_path = media_paths[0]
                mtype = media_types[0] if media_types else "photo"
                if mtype == "video":
                    with open(media_path, "rb") as vid:
                        bot.send_video(CHAT_ID, vid, caption=message)
                else:
                    with open(media_path, "rb") as img:
                        bot.send_photo(CHAT_ID, img, caption=message)
            else:
                media = []
                for i, path in enumerate(media_paths):
                    mtype = media_types[i] if i < len(media_types) else "photo"
                    if mtype == "video":
                        with open(path, "rb") as vid:
                            media.append(
                                telebot.types.InputMediaVideo(
                                    vid, caption=message if i == 0 else None
                                )
                            )
                    else:
                        with open(path, "rb") as img:
                            media.append(
                                telebot.types.InputMediaPhoto(
                                    img, caption=message if i == 0 else None
                                )
                            )
                bot.send_media_group(CHAT_ID, media)
        elif media_url:
            try:
                bot.send_photo(CHAT_ID, media_url, caption=message)
            except Exception:
                bot.send_message(CHAT_ID, f"{message}\n\nMedia: {media_url}")
        else:
            bot.send_message(CHAT_ID, message)
    except Exception as e:
        print(f"Error sending message: {e}")
