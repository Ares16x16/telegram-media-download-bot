import os
import asyncio
import telebot
import telebot.apihelper
from telebot import types
import json
from collections import defaultdict
import threading
import time
import traceback
from datetime import datetime

telebot.apihelper.CONNECT_TIMEOUT = 60
telebot.apihelper.READ_TIMEOUT = 600

import utils
import fetchers
import bilibili_downloader
import youtube_downloader
import sakurazaka_news
import hinatazaka_news

BOT_TOKEN = utils.BOT_TOKEN
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    raise ValueError("BOT_TOKEN is not set or is invalid. Please check your .env file.")

CHAT_ID = utils.CHAT_ID
X_USERNAME = "nagi_italy"
INSTAGRAM_USERNAME = "nagi.i_official"

bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}

MEDIA_DIR = utils.MEDIA_DIR
TWITTER_MEDIA_DIR = os.path.join(MEDIA_DIR, "twitter")
INSTAGRAM_POSTS_DIR = os.path.join(MEDIA_DIR, "instagram", "posts")
INSTAGRAM_STORIES_DIR = os.path.join(MEDIA_DIR, "instagram", "stories")
BILIBILI_MEDIA_DIR = os.path.join(MEDIA_DIR, "bilibili")

# Auto-fetch configuration
auto_fetch_thread = None
auto_fetch_running = False
auto_fetch_interval = 15 * 60  # 30 minutes in seconds
auto_fetch_accounts = {"x": [X_USERNAME], "instagram": [INSTAGRAM_USERNAME]}
last_fetch_time = None


def auto_fetch_worker():
    """Background worker that periodically checks for new posts"""
    global auto_fetch_running, last_fetch_time

    while auto_fetch_running:
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] Running auto fetch...")

            # Fetch X posts
            for username in auto_fetch_accounts["x"]:
                try:
                    new_posts = fetchers.fetch_x_posts(username)
                    if new_posts:
                        for post in new_posts:
                            utils.send_to_telegram(
                                f"New X post from @{username}:\n\n{post['content']}\n\n{post['url']}",
                                media_paths=post.get("media_paths"),
                                media_types=post.get("media_types"),
                            )
                        print(
                            f"[{current_time}] Fetched {len(new_posts)} new X posts from @{username}"
                        )
                except Exception as e:
                    print(f"Error fetching X posts for {username}: {e}")
                    traceback.print_exc()

            for username in auto_fetch_accounts["instagram"]:
                try:
                    # fetch post
                    insta_posts = fetchers.fetch_instagram_posts(username)
                    if insta_posts:
                        for post in insta_posts:
                            if post.get("media_paths"):
                                utils.send_to_telegram(
                                    f"New Instagram post from @{username}:\n\n{post['content']}\n\n{post['url']}",
                                    media_paths=post.get("media_paths"),
                                    media_types=post.get("media_types"),
                                )
                            else:
                                utils.send_to_telegram(
                                    f"New Instagram post from @{username}:\n\n{post['content']}\n\n{post['url']}",
                                    media_url=post.get("media_url"),
                                )
                        print(
                            f"[{current_time}] Fetched {len(insta_posts)} new Instagram posts from @{username}"
                        )

                    # Fetch stories
                    insta_stories = fetchers.fetch_instagram_stories(username)
                    if insta_stories:
                        for story in insta_stories:
                            if story.get("media_paths"):
                                utils.send_to_telegram(
                                    f"New Instagram story from @{username}:\n\n{story['content']}",
                                    media_paths=story.get("media_paths"),
                                    media_types=story.get("media_types"),
                                )
                            else:
                                utils.send_to_telegram(
                                    f" New Instagram story from @{username}:\n\n{story['content']}",
                                    media_url=story.get("url"),
                                )
                        print(
                            f"[{current_time}] Fetched {len(insta_stories)} new Instagram stories from @{username}"
                        )
                except Exception as e:
                    print(f"Error fetching Instagram content for {username}: {e}")
                    traceback.print_exc()

            last_fetch_time = current_time
        except Exception as e:
            print(f"Error in auto fetch worker: {e}")
            traceback.print_exc()

        for _ in range(auto_fetch_interval):
            if not auto_fetch_running:
                break
            time.sleep(1)


def start_auto_fetch():
    """Start the auto fetch background thread"""
    global auto_fetch_thread, auto_fetch_running

    if auto_fetch_running:
        return False

    auto_fetch_running = True
    auto_fetch_thread = threading.Thread(target=auto_fetch_worker)
    auto_fetch_thread.daemon = True
    auto_fetch_thread.start()
    return True


def stop_auto_fetch():
    """Stop the auto fetch background thread"""
    global auto_fetch_running

    if not auto_fetch_running:
        return False

    auto_fetch_running = False
    return True


@bot.message_handler(commands=["auto_start"])
def handle_auto_start(message):
    """Start automatic fetching of posts"""
    try:
        result = start_auto_fetch()
        if result:
            bot.reply_to(
                message,
                f"Auto fetch started. Will check for new posts every {auto_fetch_interval//60} minutes.",
            )
        else:
            bot.reply_to(message, "Auto fetch is already running.")
    except Exception as e:
        bot.reply_to(message, f"Error starting auto fetch: {e}")


@bot.message_handler(commands=["auto_stop"])
def handle_auto_stop(message):
    """Stop automatic fetching of posts"""
    try:
        result = stop_auto_fetch()
        if result:
            bot.reply_to(message, "Auto fetch stopped.")
        else:
            bot.reply_to(message, "Auto fetch is not running.")
    except Exception as e:
        bot.reply_to(message, f"Error stopping auto fetch: {e}")


@bot.message_handler(commands=["auto_status"])
def handle_auto_status(message):
    """Check the status of auto fetch"""
    status = "running" if auto_fetch_running else "stopped"
    accounts_info = (
        f"X accounts: {', '.join('@' + a for a in auto_fetch_accounts['x'])}\n"
        f"Instagram accounts: {', '.join('@' + a for a in auto_fetch_accounts['instagram'])}"
    )
    interval_info = f"Checking interval: {auto_fetch_interval//60} minutes"
    last_run = (
        f"Last fetch: {last_fetch_time}"
        if last_fetch_time
        else "No fetches performed yet"
    )

    status_message = (
        f"Auto fetch is {status}\n\n{accounts_info}\n{interval_info}\n{last_run}"
    )
    bot.reply_to(message, status_message)


@bot.message_handler(commands=["auto_config"])
def handle_auto_config(message):
    """Configure auto fetch settings"""
    global auto_fetch_interval, auto_fetch_accounts

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        current_config = (
            f"Current auto fetch configuration:\n\n"
            f"X accounts: {', '.join('@' + a for a in auto_fetch_accounts['x'])}\n"
            f"Instagram accounts: {', '.join('@' + a for a in auto_fetch_accounts['instagram'])}\n"
            f"Interval: {auto_fetch_interval//60} minutes\n\n"
            f"Usage: /auto_config interval=30 x=username1,username2 instagram=username1,username2"
        )
        bot.reply_to(message, current_config)
        return

    try:
        config_text = parts[1]
        config_parts = config_text.split()

        for part in config_parts:
            if "=" not in part:
                continue

            key, value = part.split("=", 1)
            key = key.lower().strip()
            value = value.strip()

            if key == "interval":
                try:
                    minutes = int(value)
                    if minutes < 5:
                        bot.reply_to(message, "Interval must be at least 5 minutes.")
                        continue
                    auto_fetch_interval = minutes * 60
                except ValueError:
                    bot.reply_to(message, f"Invalid interval value: {value}")
            elif key == "x" or key == "twitter":
                usernames = [u.strip() for u in value.split(",") if u.strip()]
                auto_fetch_accounts["x"] = usernames
            elif key == "instagram" or key == "ig":
                usernames = [u.strip() for u in value.split(",") if u.strip()]
                auto_fetch_accounts["instagram"] = usernames

        bot.reply_to(
            message,
            f"Auto fetch configuration updated:\n\n"
            f"X accounts: {', '.join('@' + a for a in auto_fetch_accounts['x'])}\n"
            f"Instagram accounts: {', '.join('@' + a for a in auto_fetch_accounts['instagram'])}\n"
            f"Interval: {auto_fetch_interval//60} minutes",
        )
    except Exception as e:
        bot.reply_to(message, f"Error configuring auto fetch: {e}")


@bot.message_handler(commands=["pick"])
def handle_pick(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    item_x = types.InlineKeyboardButton("X (Twitter)", callback_data="platform_x")
    item_ig = types.InlineKeyboardButton(
        "Instagram", callback_data="platform_instagram"
    )
    markup.add(item_x, item_ig)

    bot.send_message(
        message.chat.id, "Select a platform to fetch posts from:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("platform_"))
def platform_callback(call):
    platform = call.data.split("_")[1]
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    user_states[user_id] = {"platform": platform, "step": "wait_username"}

    bot.edit_message_text(
        f"You selected {platform.upper()}. Please enter the account username:",
        chat_id=chat_id,
        message_id=call.message.message_id,
    )
    bot.answer_callback_query(call.id)


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id].get("step") == "wait_username"
)
def handle_username_input(message):
    user_id = message.from_user.id
    platform = user_states[user_id]["platform"]
    username = message.text.strip()

    if username.startswith("@"):
        username = username[1:]

    bot.reply_to(message, f"Fetching {platform.upper()} posts for @{username}...")

    if platform == "x":
        fetch_x_content(message, username)
    elif platform == "instagram":
        fetch_instagram_content(message, username)

    user_states.pop(user_id, None)


def fetch_x_content(message, username):
    try:
        new_posts = fetchers.fetch_x_posts(username)
        count = len(new_posts)

        if count == 0:
            bot.send_message(
                message.chat.id, f"No new posts found for {username} on X."
            )
            return

        for post in new_posts:
            utils.send_to_telegram(
                f"{post['content']}\n\n{post['url']}",
                media_paths=post.get("media_paths"),
                media_types=post.get("media_types"),
            )
        bot.send_message(
            message.chat.id, f"Fetched {count} posts from X user @{username}."
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Error fetching X posts: {e}")


def fetch_instagram_content(message, username):
    try:
        insta_posts = fetchers.fetch_instagram_posts(username)
        insta_stories = fetchers.fetch_instagram_stories(username)
        count = len(insta_posts) + len(insta_stories)

        if count == 0:
            bot.send_message(
                message.chat.id, f"No new posts found for {username} on Instagram."
            )
            return

        for post in insta_posts:
            if post.get("media_paths"):
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_paths=post.get("media_paths"),
                    media_types=post.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_url=post.get("media_url"),
                )

        for story in insta_stories:
            if story.get("media_paths"):
                utils.send_to_telegram(
                    f"{story['content']}",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}",
                    media_url=story.get("url"),
                )

        bot.send_message(
            message.chat.id,
            f"Fetched {len(insta_posts)} posts and {len(insta_stories)} stories from Instagram user {username}.",
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Error fetching Instagram content: {e}")


@bot.message_handler(commands=["bili"])
def handle_bili(message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.reply_to(message, "Usage: /bili <video_link>")
            return
        link = parts[1].strip()
        bot.reply_to(message, "Processing Bilibili video...")
        result = asyncio.run(bilibili_downloader.process_video(link))
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /bili command: {e}")


@bot.message_handler(commands=["youtube"])
def handle_youtube(message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.reply_to(message, "Usage: /youtube <video_link>")
            return
        link = parts[1].strip()
        bot.reply_to(message, "Processing YouTube video...")
        result = asyncio.run(youtube_downloader.process_video(link))
        if not result:
            bot.send_message(CHAT_ID, "Failed to download YouTube video.")
            return
        caption = f"{result['title']}\n\n{link}"
        utils.send_to_telegram(
            caption,
            media_paths=[result["path"]],
            media_types=["video"],
        )
        bot.send_message(CHAT_ID, "YouTube video downloaded.")
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /youtube command: {e}")


@bot.message_handler(commands=["fetch"])
def handle_fetch(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "Usage: /fetch [x|instagram] <username>")
            return

        platform = parts[1].lower()
        username = parts[2].strip().lower()

        if username.startswith("@"):
            username = username[1:]

        bot.reply_to(message, f"Fetching {platform} posts for {username}...")

        if platform in ["x", "twitter"]:
            new_posts = fetchers.fetch_x_posts(username)
            count = len(new_posts)
            if count == 0:
                bot.send_message(CHAT_ID, f"No new posts found for {username} on X.")
                return

            for post in new_posts:
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_paths=post.get("media_paths"),
                    media_types=post.get("media_types"),
                )
            bot.send_message(CHAT_ID, f"Fetched {count} posts from X user @{username}.")

        elif platform == "instagram":
            insta_posts = fetchers.fetch_instagram_posts(username)
            insta_stories = fetchers.fetch_instagram_stories(username)
            count = len(insta_posts) + len(insta_stories)

            if count == 0:
                bot.send_message(
                    CHAT_ID, f"No new posts found for {username} on Instagram."
                )
                return

            for post in insta_posts:
                if post.get("media_paths"):
                    utils.send_to_telegram(
                        f"{post['content']}\n\n{post['url']}",
                        media_paths=post.get("media_paths"),
                        media_types=post.get("media_types"),
                    )
                else:
                    utils.send_to_telegram(
                        f"{post['content']}\n\n{post['url']}",
                        media_url=post.get("media_url"),
                    )

            for story in insta_stories:
                if story.get("media_paths"):
                    utils.send_to_telegram(
                        f"{story['content']}",
                        media_paths=story.get("media_paths"),
                        media_types=story.get("media_types"),
                    )
                else:
                    utils.send_to_telegram(
                        f"{story['content']}",
                        media_url=story.get("url"),
                    )

            bot.send_message(
                CHAT_ID,
                f"Fetched {len(insta_posts)} posts and {len(insta_stories)} stories from Instagram user {username}.",
            )
        else:
            bot.reply_to(
                message, f"Unknown platform '{platform}'. Use 'x' or 'instagram'."
            )
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /fetch command: {e}")


@bot.message_handler(commands=["fetch_nagi"])
def handle_fetch_nagi(message):
    try:
        bot.reply_to(message, "Fetching new posts for nagi...")
        new_posts = fetchers.fetch_x_posts(X_USERNAME)
        insta_posts = fetchers.fetch_instagram_posts(INSTAGRAM_USERNAME)
        insta_stories = fetchers.fetch_instagram_stories(INSTAGRAM_USERNAME)
        count = len(new_posts) + len(insta_posts) + len(insta_stories)
        if count == 0:
            bot.send_message(CHAT_ID, "No new posts found for nagi.")
            return

        for post in new_posts:
            utils.send_to_telegram(
                f"{post['content']}\n\n{post['url']}",
                media_paths=post.get("media_paths"),
                media_types=post.get("media_types"),
            )
        for post in insta_posts:
            if post.get("media_paths"):
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_paths=post.get("media_paths"),
                    media_types=post.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_url=post.get("media_url"),
                )
        for story in insta_stories:
            if story.get("media_paths"):
                utils.send_to_telegram(
                    f"{story['content']}",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}", media_url=story.get("url")
                )
        bot.send_message(CHAT_ID, f"Fetched {count} new posts for nagi_italy.")
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /fetch_nagi command: {e}")


@bot.message_handler(commands=["fetch_nagi_x"])
def handle_fetch_nagi_x(message):
    try:
        bot.reply_to(message, "Fetching X posts for nagi...")
        new_posts = fetchers.fetch_x_posts(X_USERNAME)

        if len(new_posts) == 0:
            bot.send_message(CHAT_ID, "No new X posts found for nagi.")
            return

        for post in new_posts:
            utils.send_to_telegram(
                f"{post['content']}\n\n{post['url']}",
                media_paths=post.get("media_paths"),
                media_types=post.get("media_types"),
            )

        bot.send_message(
            CHAT_ID, f"Fetched {len(new_posts)} new X posts from nagi_italy."
        )
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /fetch_nagi_x command: {e}")


@bot.message_handler(commands=["fetch_nagi_ig"])
def handle_fetch_nagi_ig(message):
    try:
        bot.reply_to(message, "Fetching Instagram posts for nagi...")
        insta_posts = fetchers.fetch_instagram_posts(INSTAGRAM_USERNAME)
        insta_stories = fetchers.fetch_instagram_stories(INSTAGRAM_USERNAME)
        count = len(insta_posts) + len(insta_stories)

        if count == 0:
            bot.send_message(
                CHAT_ID, "No new Instagram posts or stories found for nagi."
            )
            return

        for post in insta_posts:
            if post.get("media_paths"):
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_paths=post.get("media_paths"),
                    media_types=post.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{post['content']}\n\n{post['url']}",
                    media_url=post.get("media_url"),
                )

        for story in insta_stories:
            if story.get("media_paths"):
                utils.send_to_telegram(
                    f"{story['content']}",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}",
                    media_url=story.get("url"),
                )

        bot.send_message(
            CHAT_ID,
            f"Fetched {len(insta_posts)} posts and {len(insta_stories)} stories from Instagram for nagi.i_official.",
        )
    except Exception as e:
        bot.send_message(CHAT_ID, f"Error in /fetch_nagi_ig command: {e}")


@bot.message_handler(commands=["echo"])
def handle_echo(message):
    try:
        command_length = len("/echo ")
        if len(message.text) <= command_length:
            bot.reply_to(message, "Usage: /echo <your message>")
            return

        echo_text = message.text[command_length:]
        bot.reply_to(message, echo_text)
    except Exception as e:
        bot.reply_to(message, f"Error in echo function: {e}")


@bot.message_handler(commands=["history"])
def handle_history(message):
    """Browse previously fetched posts"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    item_x = types.InlineKeyboardButton(
        "X (Twitter)", callback_data="history_select_platform_twitter"
    )
    item_ig_posts = types.InlineKeyboardButton(
        "Instagram Posts", callback_data="history_select_platform_instagram_posts"
    )
    item_ig_stories = types.InlineKeyboardButton(
        "Instagram Stories", callback_data="history_select_platform_instagram_stories"
    )
    item_bili = types.InlineKeyboardButton(
        "Bilibili Videos", callback_data="history_select_platform_bilibili"
    )
    markup.add(item_x, item_ig_posts)
    markup.add(item_ig_stories, item_bili)
    bot.send_message(
        message.chat.id, "Browse history - select a platform:", reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("history_select_platform_")
)
def history_select_platform_callback(call):
    platform = call.data.replace("history_select_platform_", "")
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    accounts = utils.get_accounts_by_platform(platform)

    if not accounts:
        try:
            platform_dir_map = {
                "twitter": TWITTER_MEDIA_DIR,
                "instagram_posts": INSTAGRAM_POSTS_DIR,
                "instagram_stories": INSTAGRAM_STORIES_DIR,
                "bilibili": BILIBILI_MEDIA_DIR,
            }

            if platform in platform_dir_map:
                media_dir = platform_dir_map[platform]

                if os.path.exists(media_dir):
                    accounts = [
                        d
                        for d in os.listdir(media_dir)
                        if os.path.isdir(os.path.join(media_dir, d))
                    ]

                    if platform == "instagram_stories" and not accounts:
                        stories_pattern_dirs = [
                            os.path.join(MEDIA_DIR, "instagram", "stories"),
                            os.path.join(MEDIA_DIR, "instagram"),
                        ]

                        for dir_path in stories_pattern_dirs:
                            if os.path.exists(dir_path):
                                for d in os.listdir(dir_path):
                                    full_path = os.path.join(dir_path, d)
                                    if os.path.isdir(full_path) and (
                                        d.startswith("stories_")
                                        or "stories" in dir_path
                                    ):
                                        accounts.append(d.replace("stories_", ""))

                        if accounts:
                            seen = set()
                            accounts = [
                                x for x in accounts if not (x in seen or seen.add(x))
                            ]

                    if not accounts:
                        if platform == "instagram_stories":
                            accounts = ["nagi.i_official"]
                        elif platform == "twitter":
                            accounts = [X_USERNAME]
                        elif platform == "instagram_posts":
                            accounts = [INSTAGRAM_USERNAME]
        except Exception as e:
            import traceback

            traceback.print_exc()

    if not accounts:
        bot.edit_message_text(
            f"No accounts found for {platform.replace('_', ' ')}. Fetch some content first!\n",
            chat_id=chat_id,
            message_id=call.message.message_id,
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "Back", callback_data="history_back_to_platforms"
            )
        )
        bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup
        )
        return

    user_states[user_id] = {"platform": platform}

    markup = types.InlineKeyboardMarkup(row_width=1)
    for account in accounts:
        markup.add(
            types.InlineKeyboardButton(
                f"@{account}",
                callback_data=f"history_select_account_{platform}_{account}",
            )
        )

    markup.add(
        types.InlineKeyboardButton("Back", callback_data="history_back_to_platforms")
    )

    bot.edit_message_text(
        f"Select an account for {platform.replace('_', ' ')}:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("history_select_account_")
)
def history_select_account_callback(call):
    # print(call.data)
    parts = call.data.split("_", 4)

    if len(parts) >= 5:
        platform = parts[3]
        account = parts[4]
    else:
        bot.answer_callback_query(call.id, "Invalid selection")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if account.startswith("posts_"):
        account = account.replace("posts_", "", 1)
        platform += "_posts"
    elif account.startswith("stories_"):
        account = account.replace("stories_", "", 1)
        platform += "_stories"

    sent_posts = utils.load_sent_posts()

    if platform in ["twitter", "x"]:
        platform_type = "twitter"
        post_list_key = "x_posts"
        platform_key = f"twitter_{account}"
    elif platform == "instagram_posts":
        platform_type = "instagram_posts"
        post_list_key = "instagram_posts"
        platform_key = f"instagram_post_{account}"
    elif platform == "instagram_stories":
        platform_type = "instagram_stories"
        post_list_key = "instagram_stories"
        platform_key = f"instagram_story_{account}"
    elif platform == "instagram":
        platform_type = "instagram_posts"
        post_list_key = "instagram_posts"
        platform_key = f"instagram_post_{account}"
    elif platform == "bilibili":
        platform_type = "bilibili"
        post_list_key = None
        platform_key = f"bilibili_{account}"
    else:
        bot.answer_callback_query(call.id, f"Unknown platform: {platform}")
        return

    if platform_type == "twitter":
        posts = [
            p
            for p in sent_posts.get("x_posts", [])
            if f"twitter_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
    elif platform_type == "instagram_posts":
        posts = [
            p
            for p in sent_posts.get("instagram_posts", [])
            if f"instagram_post_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
    elif platform_type == "instagram_stories":
        posts = [
            p
            for p in sent_posts.get("instagram_stories", [])
            if f"instagram_story_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
    elif platform_type == "bilibili":
        sent_videos = utils.load_sent_videos()
        posts = [
            p
            for p in sent_videos.get("videos", [])
            if f"bilibili_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
    else:
        bot.answer_callback_query(call.id, f"Unsupported platform: {platform}")
        return

    if not posts:
        if post_list_key and post_list_key in sent_posts:
            posts = sent_posts.get(post_list_key, [])
        elif platform_type == "bilibili":
            sent_videos = utils.load_sent_videos()
            posts = sent_videos.get("videos", [])

    if not posts:
        bot.edit_message_text(
            f"No posts found for {account} on {platform.replace('_', ' ')}.",
            chat_id=chat_id,
            message_id=call.message.message_id,
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "Back", callback_data=f"history_select_platform_{platform}"
            )
        )
        bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup
        )
        return

    user_states[user_id] = {
        "platform": platform_type,
        "platform_key": platform_key,
        "account": account,
        "posts": posts,
        "current_page": 0,
        "posts_per_page": 5,
    }

    show_posts_page(user_id, chat_id, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(
    func=lambda call: call.data
    in [
        "history_prev_page",
        "history_next_page",
        "history_back_to_platforms",
        "history_back_to_accounts",
    ]
)
def history_navigation_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Session expired. Please start over.")
        return

    if call.data == "history_prev_page":
        user_states[user_id]["current_page"] -= 1
        show_posts_page(user_id, chat_id, call.message.message_id)

    elif call.data == "history_next_page":
        user_states[user_id]["current_page"] += 1
        show_posts_page(user_id, chat_id, call.message.message_id)

    elif call.data == "history_back_to_platforms":
        handle_history(call.message)

    elif call.data == "history_back_to_accounts":
        platform = user_states[user_id].get("platform")
        if platform:
            history_select_platform_callback(
                types.CallbackQuery(
                    id=call.id,
                    from_user=call.from_user,
                    message=call.message,
                    chat_instance=call.message.chat.id,
                    data=f"history_select_platform_{platform}",
                    json_string="{}",
                )
            )

    bot.answer_callback_query(call.id)


def show_posts_page(user_id, chat_id, message_id):
    state = user_states.get(user_id, {})
    platform = state.get("platform", "")
    account = state.get("account", "")
    posts = state.get("posts", [])
    current_page = state.get("current_page", 0)
    posts_per_page = state.get("posts_per_page", 5)

    start_idx = current_page * posts_per_page
    end_idx = min(start_idx + posts_per_page, len(posts))

    page_posts = posts[start_idx:end_idx]

    markup = types.InlineKeyboardMarkup(row_width=3)

    post_buttons = []
    for i, post_id in enumerate(page_posts):
        post_idx = start_idx + i
        btn_text = f"Post {post_idx + 1}"
        post_buttons.append(
            types.InlineKeyboardButton(
                btn_text, callback_data=f"view_post_{platform}_{account}_{post_id}"
            )
        )

    for i in range(0, len(post_buttons), 2):
        if i + 1 < len(post_buttons):
            markup.add(post_buttons[i], post_buttons[i + 1])
        else:
            markup.add(post_buttons[i])

    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton("⬅️ Previous", callback_data="history_prev_page")
        )

    nav_buttons.append(
        types.InlineKeyboardButton(
            "Back to Accounts", callback_data="history_back_to_accounts"
        )
    )

    if end_idx < len(posts):
        nav_buttons.append(
            types.InlineKeyboardButton("Next ➡️", callback_data="history_next_page")
        )

    markup.row(*nav_buttons)
    markup.add(
        types.InlineKeyboardButton(
            "Back to Platforms", callback_data="history_back_to_platforms"
        )
    )

    platform_name = platform.replace("_", " ").capitalize()
    message_text = (
        f"{platform_name} History for @{account}\n"
        f"Page {current_page + 1}/{(len(posts) + posts_per_page - 1) // posts_per_page}\n"
        f"Showing posts {start_idx + 1}-{end_idx} of {len(posts)}"
    )

    bot.send_message(chat_id, message_text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_post_"))
def view_post_callback(call):
    call_data = call.data[
        len("view_post_") :
    ]  # e.g. "instagram_posts_nagi.i_official_DHF-Pm3yoxf"
    parts = call_data.split("_")

    if len(parts) >= 2 and parts[0] == "instagram" and parts[1] in ["posts", "stories"]:
        platform = "_".join(parts[:2])  # "instagram_posts" or "instagram_stories"
        the_rest = parts[2:]
    else:
        platform = parts[0]  # e.g., "twitter" or "bilibili"
        the_rest = parts[1:]

    if len(the_rest) < 2:
        bot.answer_callback_query(call.id, "Invalid post data")
        return

    # The last chunk is the post_id, everything else is account
    post_id = the_rest[-1]
    account = "_".join(the_rest[:-1])

    if account.startswith("posts_"):
        account = account.replace("posts_", "", 1)
    elif account.startswith("stories_"):
        account = account.replace("stories_", "", 1)

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    platform_key = f"{user_states[user_id].get('platform_key', '')}_{post_id}"
    media_paths = utils.get_post_media_files(platform_key, post_id)

    if not media_paths:
        base_platform = ""
        if platform == "twitter":
            base_platform = "twitter"
        elif platform == "instagram_posts":
            base_platform = "instagram_post"
        elif platform == "instagram_stories":
            base_platform = "instagram_story"
        elif platform == "bilibili":
            base_platform = "bilibili"

        media_paths = utils.get_post_media_files(base_platform, post_id)

    if not media_paths:
        try:
            if platform == "twitter":
                post_dir = os.path.join(TWITTER_MEDIA_DIR, account, post_id)

                if os.path.exists(post_dir):
                    media_paths = [
                        os.path.join(post_dir, f)
                        for f in os.listdir(post_dir)
                        if os.path.isfile(os.path.join(post_dir, f))
                        and (
                            f.endswith(".jpg")
                            or f.endswith(".jpeg")
                            or f.endswith(".png")
                            or f.endswith(".mp4")
                        )
                    ]

            elif platform == "instagram_posts":
                post_dir = os.path.join(INSTAGRAM_POSTS_DIR, account, post_id)

                if os.path.exists(post_dir):
                    media_paths = [
                        os.path.join(post_dir, f)
                        for f in os.listdir(post_dir)
                        if os.path.isfile(os.path.join(post_dir, f))
                        and (
                            f.endswith(".jpg")
                            or f.endswith(".jpeg")
                            or f.endswith(".png")
                            or f.endswith(".mp4")
                        )
                    ]
                else:
                    alt_accounts = [
                        account.replace(".", "_"),
                        account.replace("_", "."),
                        f"posts_{account}",
                    ]

                    for alt_account in alt_accounts:
                        alt_dir = os.path.join(
                            INSTAGRAM_POSTS_DIR, alt_account, post_id
                        )
                        if os.path.exists(alt_dir):
                            media_paths = [
                                os.path.join(alt_dir, f)
                                for f in os.listdir(alt_dir)
                                if os.path.isfile(os.path.join(alt_dir, f))
                                and (
                                    f.endswith(".jpg")
                                    or f.endswith(".jpeg")
                                    or f.endswith(".png")
                                    or f.endswith(".mp4")
                                )
                            ]
                            if media_paths:
                                break

            elif platform == "instagram_stories":
                post_dir = os.path.join(INSTAGRAM_STORIES_DIR, account, post_id)

                if os.path.exists(post_dir):
                    media_paths = [
                        os.path.join(post_dir, f)
                        for f in os.listdir(post_dir)
                        if os.path.isfile(os.path.join(post_dir, f))
                        and (
                            f.endswith(".jpg")
                            or f.endswith(".jpeg")
                            or f.endswith(".png")
                            or f.endswith(".mp4")
                        )
                    ]
                else:
                    alt_accounts = [
                        account.replace(".", "_"),
                        account.replace("_", "."),
                        f"stories_{account}",
                    ]

                    for alt_account in alt_accounts:
                        alt_dir = os.path.join(
                            INSTAGRAM_STORIES_DIR, alt_account, post_id
                        )
                        if os.path.exists(alt_dir):
                            media_paths = [
                                os.path.join(alt_dir, f)
                                for f in os.listdir(alt_dir)
                                if os.path.isfile(os.path.join(alt_dir, f))
                                and (
                                    f.endswith(".jpg")
                                    or f.endswith(".jpeg")
                                    or f.endswith(".png")
                                    or f.endswith(".mp4")
                                )
                            ]
                            if media_paths:
                                break

            elif platform == "bilibili":
                post_dir = os.path.join(BILIBILI_MEDIA_DIR, account, post_id)

                if os.path.exists(post_dir):
                    media_paths = [
                        os.path.join(post_dir, f)
                        for f in os.listdir(post_dir)
                        if os.path.isfile(os.path.join(post_dir, f))
                        and f.endswith(".mp4")
                    ]
                # alternate account search, similar to Instagram
                else:
                    alt_accounts = [
                        account.replace(".", "_"),
                        account.replace("_", "."),
                    ]

                    for alt_account in alt_accounts:
                        alt_dir = os.path.join(BILIBILI_MEDIA_DIR, alt_account, post_id)
                        if os.path.exists(alt_dir):
                            media_paths = [
                                os.path.join(alt_dir, f)
                                for f in os.listdir(alt_dir)
                                if os.path.isfile(os.path.join(alt_dir, f))
                                and f.endswith(".mp4")
                            ]
                            if media_paths:
                                break

        except Exception as e:
            import traceback

            traceback.print_exc()

    if not media_paths:
        bot.answer_callback_query(
            call.id,
            "No media found for this post. Files may have been moved or deleted.",
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "Back to posts",
                callback_data=f"history_select_account_{platform}_{account}",
            )
        )

        bot.send_message(
            chat_id,
            f"Could not find media files for this post.\n\nPlatform: {platform}\nAccount: {account}\nPost ID: {post_id}",
            reply_markup=markup,
        )
        return

    if platform == "twitter":
        url = f"https://twitter.com/{account}/status/{post_id}"
        caption = f"X Post from @{account}:\n{url}"
    elif platform == "instagram_posts":
        url = f"https://www.instagram.com/p/{post_id}/"
        caption = f"Instagram Post from @{account}:\n{url}"
    elif platform == "instagram_stories":
        caption = f"Instagram Story from @{account}\nStory ID: {post_id}"
    elif platform == "bilibili":
        url = f"https://www.bilibili.com/video/{post_id}"
        caption = f"Bilibili Video from {account}:\n{url}"
    else:
        caption = f"Post ID: {post_id} from {account}"

    media_types = []
    for path in media_paths:
        if path.endswith(".mp4"):
            media_types.append("video")
        else:
            media_types.append("photo")

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "Back to list",
            callback_data=f"history_select_account_{platform}_{account}",
        )
    )

    try:
        if len(media_paths) == 1:
            media_path = media_paths[0]
            mtype = media_types[0]
            if mtype == "video":
                with open(media_path, "rb") as vid:
                    bot.send_video(chat_id, vid, caption=caption, reply_markup=markup)
            else:
                with open(media_path, "rb") as img:
                    bot.send_photo(chat_id, img, caption=caption, reply_markup=markup)
        else:
            media = []
            for i, path in enumerate(media_paths):
                mtype = media_types[i]
                if mtype == "video":
                    with open(path, "rb") as vid:
                        media.append(
                            telebot.types.InputMediaVideo(
                                vid, caption=caption if i == 0 else None
                            )
                        )
                else:
                    with open(path, "rb") as img:
                        media.append(
                            telebot.types.InputMediaPhoto(
                                img, caption=caption if i == 0 else None
                            )
                        )

            bot.send_media_group(chat_id, media)
            bot.send_message(
                chat_id, "Use the button below to navigate:", reply_markup=markup
            )
    except Exception as e:
        bot.send_message(chat_id, f"Error sending media: {e}\n\n{caption}")
        bot.send_message(chat_id, "Navigation:", reply_markup=markup)

    bot.answer_callback_query(call.id)


@bot.message_handler(commands=["help"])
def handle_help(message):
    help_text = """
Available commands:
/pick - Interactive menu to fetch posts (recommended)
/fetch [x|instagram] <username> - Fetch posts by platform and username
/fetch_nagi - Fetch all posts for Inoue Nagi
/fetch_nagi_x - Fetch only X/Twitter posts for Inoue Nagi
/fetch_nagi_ig - Fetch only Instagram posts for Inoue Nagi
/bili <url> - Download and send Bilibili video
/youtube <url> - Download and send YouTube video
/history - Browse previously fetched posts' media
/auto_start - Start automatically fetching new posts 
/auto_stop - Stop automatic fetching
/auto_status - Check auto fetch status
/auto_config - Configure auto fetch settings
/echo <message> - Echo back your message
/saku_news - Fetch Sakurazaka46 news by month
/hinata_news - Fetch Hinatazaka46 news by month
/help - Show this help message
"""
    bot.send_message(message.chat.id, help_text)


@bot.message_handler(commands=["saku_news"])
def handle_saku_news(message):
    """Step 1: Ask the user to pick a year."""
    now = datetime.now()
    start_year = 2020
    markup = types.InlineKeyboardMarkup()
    for year in range(start_year, now.year + 1):
        callback_data = f"sakura_year_{year}"
        markup.add(types.InlineKeyboardButton(str(year), callback_data=callback_data))
    bot.send_message(
        message.chat.id, "Choose a year to fetch news:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("sakura_year_"))
def saku_year_callback(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split("_", 2)
    selected_year = int(parts[2])
    now = datetime.now()

    # For the current year, limit the months to the current month
    max_month = now.month if (selected_year == now.year) else 12
    markup = types.InlineKeyboardMarkup()
    start_m = 10 if selected_year == 2020 else 1  # Start from October 2020
    for month in range(start_m, max_month + 1):
        callback_data = f"sakura_month_{selected_year}_{month}"
        label = f"{selected_year}-{month:02d}"
        markup.add(types.InlineKeyboardButton(label, callback_data=callback_data))
    markup.add(types.InlineKeyboardButton("Back", callback_data="sakura_back_to_years"))
    bot.edit_message_text(
        f"Selected year: {selected_year}\nChoose a month:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data == "sakura_back_to_years")
def saku_back_to_years_callback(call):
    """Go back to the year selection screen."""
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    now = datetime.now()
    start_year = 2020
    for y in range(start_year, now.year + 1):
        callback_data = f"sakura_year_{y}"
        markup.add(types.InlineKeyboardButton(str(y), callback_data=callback_data))
    bot.edit_message_text(
        "Choose a year to fetch news:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("sakura_month_"))
def saku_month_callback(call):
    parts = call.data.split("_")
    if len(parts) < 3:
        bot.send_message(call.message.chat.id, "Invalid callback data.")
        return
    # data format: sakura_month_YYYY_M
    _, _, year_str, month_str = parts
    yr, mo = int(year_str), int(month_str)

    news_items = sakurazaka_news.fetch_monthly_news(yr, mo)
    if not news_items:
        bot.send_message(call.message.chat.id, "No news found for that month.")
        return

    user_states[call.from_user.id] = {
        "saku_news": news_items,
        "saku_news_page": 0,
        "saku_year": yr,
        "saku_month": mo,
    }
    show_saku_news_page(
        call.from_user.id, call.message.chat.id, call.message.message_id
    )


@bot.callback_query_handler(
    func=lambda call: call.data in ["saku_news_prev_page", "saku_news_next_page"]
)
def saku_news_page_nav_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if uid not in user_states or "saku_news" not in user_states[uid]:
        return
    if call.data == "saku_news_prev_page":
        user_states[uid]["saku_news_page"] -= 1
    else:
        user_states[uid]["saku_news_page"] += 1
    show_saku_news_page(uid, call.message.chat.id, call.message.message_id)


def show_saku_news_page(user_id, chat_id, message_id, items_per_page=10):
    if user_id not in user_states:
        return
    all_news = user_states[user_id].get("saku_news", [])
    current_page = user_states[user_id].get("saku_news_page", 0)
    yr = user_states[user_id].get("saku_year")
    mo = user_states[user_id].get("saku_month")
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_news))
    page_news = all_news[start_idx:end_idx]

    markup = types.InlineKeyboardMarkup()
    for idx, item in enumerate(page_news):
        real_idx = start_idx + idx
        callback_data = f"sakura_detail_{real_idx}"
        markup.add(
            types.InlineKeyboardButton(item["title"], callback_data=callback_data)
        )

    nav_row = []
    if current_page > 0:
        nav_row.append(
            types.InlineKeyboardButton("Previous", callback_data="saku_news_prev_page")
        )
    if end_idx < len(all_news):
        nav_row.append(
            types.InlineKeyboardButton("Next", callback_data="saku_news_next_page")
        )
    if nav_row:
        markup.row(*nav_row)

    markup.add(types.InlineKeyboardButton("Back", callback_data="sakura_back_to_years"))
    total_pages = (len(all_news) + items_per_page - 1) // items_per_page
    text = f"Sakurazaka46 {yr}-{mo:02d} news (Page {current_page+1}/{total_pages}):"
    bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("sakura_detail_"))
def saku_detail_callback(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split("_")[2])
    if (
        call.from_user.id in user_states
        and "saku_news" in user_states[call.from_user.id]
    ):
        news_items = user_states[call.from_user.id]["saku_news"]
        if 0 <= idx < len(news_items):
            bot.send_message(call.message.chat.id, "Fetching details, please wait...")
            news_item = news_items[idx]
            detail_html = sakurazaka_news.fetch_news_detail(news_item["url"])

            if detail_html == "No detail found." or not detail_html:
                bot.send_message(
                    call.message.chat.id,
                    f"No details available for this news item.\n\nTitle: {news_item['title']}\nDate: {news_item['date']}\n\nYou can visit the original article: [View on Web]({news_item['url']})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            else:
                # Add news type if available
                news_type = f"🏷️ {news_item['type']}\n" if news_item.get("type") else ""
                # Add a divider and link to the original article
                footer = f"\n\n---\n🌐 [View original article]({news_item['url']})"
                message = f"{news_type}{detail_html}{footer}"

                try:
                    bot.send_message(
                        call.message.chat.id,
                        message,
                        parse_mode="Markdown",
                        disable_web_page_preview=False,
                    )
                except Exception as e:
                    # If Markdown parsing fails, send without formatting
                    print(f"Error sending with Markdown: {e}")
                    bot.send_message(
                        call.message.chat.id,
                        f"Error with formatted message. Here's the plain text:\n\n{detail_html}\n\nOriginal article: {news_item['url']}",
                        disable_web_page_preview=False,
                    )
    else:
        bot.send_message(call.message.chat.id, "No news items found. Please try again.")


@bot.message_handler(commands=["hinata_news"])
def handle_hinata_news(message):
    """Step 1: Ask the user to pick a year."""
    now = datetime.now()
    start_year = 2019  # Hinatazaka starts from 2019/02
    markup = types.InlineKeyboardMarkup()
    for year in range(start_year, now.year + 1):
        callback_data = f"hinata_year_{year}"
        markup.add(types.InlineKeyboardButton(str(year), callback_data=callback_data))
    bot.send_message(
        message.chat.id,
        "Choose a year to fetch Hinatazaka46 news:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("hinata_year_"))
def hinata_year_callback(call):
    """Step 2: List months for the selected year."""
    bot.answer_callback_query(call.id)
    parts = call.data.split("_", 2)
    selected_year = int(parts[2])
    now = datetime.now()

    # For the current year, limit the months to the current month
    max_month = now.month if (selected_year == now.year) else 12

    # For 2019, start from February
    start_m = 2 if selected_year == 2019 else 1

    markup = types.InlineKeyboardMarkup()
    for month in range(start_m, max_month + 1):
        callback_data = f"hinata_month_{selected_year}_{month}"
        label = f"{selected_year}-{month:02d}"
        markup.add(types.InlineKeyboardButton(label, callback_data=callback_data))
    markup.add(types.InlineKeyboardButton("Back", callback_data="hinata_back_to_years"))

    bot.edit_message_text(
        f"Selected year: {selected_year}\nChoose a month:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data == "hinata_back_to_years")
def hinata_back_to_years_callback(call):
    """Go back to the year selection screen."""
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    now = datetime.now()
    start_year = 2019  # Hinatazaka starts from 2019/02
    for y in range(start_year, now.year + 1):
        callback_data = f"hinata_year_{y}"
        markup.add(types.InlineKeyboardButton(str(y), callback_data=callback_data))
    bot.edit_message_text(
        "Choose a year to fetch Hinatazaka46 news:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("hinata_month_"))
def hinata_month_callback(call):
    """Step 3: Fetch news for the selected year-month."""
    parts = call.data.split("_")
    if len(parts) < 3:
        bot.send_message(call.message.chat.id, "Invalid callback data.")
        return
    # data format: hinata_month_YYYY_M
    _, _, year_str, month_str = parts
    yr, mo = int(year_str), int(month_str)

    bot.answer_callback_query(call.id, text="Fetching news, please wait...")

    news_items = hinatazaka_news.fetch_monthly_news(yr, mo)
    if not news_items:
        bot.send_message(call.message.chat.id, "No news found for that month.")
        return

    user_states[call.from_user.id] = {
        "hinata_news": news_items,
        "hinata_news_page": 0,
        "hinata_year": yr,
        "hinata_month": mo,
    }
    show_hinata_news_page(
        call.from_user.id, call.message.chat.id, call.message.message_id
    )


@bot.callback_query_handler(
    func=lambda call: call.data in ["hinata_news_prev_page", "hinata_news_next_page"]
)
def hinata_news_page_nav_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if uid not in user_states or "hinata_news" not in user_states[uid]:
        return
    if call.data == "hinata_news_prev_page":
        user_states[uid]["hinata_news_page"] -= 1
    else:
        user_states[uid]["hinata_news_page"] += 1
    show_hinata_news_page(uid, call.message.chat.id, call.message.message_id)


def show_hinata_news_page(user_id, chat_id, message_id, items_per_page=10):
    if user_id not in user_states:
        return
    all_news = user_states[user_id].get("hinata_news", [])
    current_page = user_states[user_id].get("hinata_news_page", 0)
    yr = user_states[user_id].get("hinata_year")
    mo = user_states[user_id].get("hinata_month")
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_news))
    page_news = all_news[start_idx:end_idx]

    markup = types.InlineKeyboardMarkup()
    for idx, item in enumerate(page_news):
        real_idx = start_idx + idx
        callback_data = f"hinata_detail_{real_idx}"
        markup.add(
            types.InlineKeyboardButton(item["title"], callback_data=callback_data)
        )

    nav_row = []
    if current_page > 0:
        nav_row.append(
            types.InlineKeyboardButton(
                "Previous", callback_data="hinata_news_prev_page"
            )
        )
    if end_idx < len(all_news):
        nav_row.append(
            types.InlineKeyboardButton("Next", callback_data="hinata_news_next_page")
        )
    if nav_row:
        markup.row(*nav_row)

    markup.add(types.InlineKeyboardButton("Back", callback_data="hinata_back_to_years"))
    total_pages = (len(all_news) + items_per_page - 1) // items_per_page
    text = f"Hinatazaka46 {yr}-{mo:02d} news (Page {current_page+1}/{total_pages}):"
    bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("hinata_detail_"))
def hinata_detail_callback(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split("_")[2])
    if (
        call.from_user.id in user_states
        and "hinata_news" in user_states[call.from_user.id]
    ):
        news_items = user_states[call.from_user.id]["hinata_news"]
        if 0 <= idx < len(news_items):
            bot.send_message(call.message.chat.id, "Fetching details, please wait...")
            news_item = news_items[idx]
            detail_html = hinatazaka_news.fetch_news_detail(news_item["url"])

            if detail_html == "No detail found." or not detail_html:
                bot.send_message(
                    call.message.chat.id,
                    f"No details available for this news item.\n\nTitle: {news_item['title']}\nDate: {news_item['date']}\n\nYou can visit the original article: [View on Web]({news_item['url']})",
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            else:
                # Add news type if available
                news_type = f"🏷️ {news_item['type']}\n" if news_item.get("type") else ""
                # Add a divider and link to the original article
                footer = f"\n\n---\n🌐 [View original article]({news_item['url']})"
                message = f"{news_type}{detail_html}{footer}"

                try:
                    bot.send_message(
                        call.message.chat.id,
                        message,
                        parse_mode="Markdown",
                        disable_web_page_preview=False,
                    )
                except Exception as e:
                    # If Markdown parsing fails, send without formatting
                    print(f"Error sending with Markdown: {e}")
                    bot.send_message(
                        call.message.chat.id,
                        f"Error with formatted message. Here's the plain text:\n\n{detail_html}\n\nOriginal article: {news_item['url']}",
                        disable_web_page_preview=False,
                    )
    else:
        bot.send_message(call.message.chat.id, "No news items found. Please try again.")


if __name__ == "__main__":
    print("Bot started. Listening for commands...")
    # start auto-fetch by default
    try:
        if start_auto_fetch():
            print(
                f"Auto fetch started. Will check for new posts every {auto_fetch_interval//60} minutes."
            )
    except Exception as e:
        print(f"Failed to start auto fetch: {e}")
    bot.polling()
