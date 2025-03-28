import os
import asyncio
import telebot
import telebot.apihelper
from telebot import types

telebot.apihelper.CONNECT_TIMEOUT = 60
telebot.apihelper.READ_TIMEOUT = 600

import utils
import fetchers
import bilibili_downloader

BOT_TOKEN = utils.BOT_TOKEN
if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    raise ValueError("BOT_TOKEN is not set or is invalid. Please check your .env file.")

CHAT_ID = utils.CHAT_ID
X_USERNAME = "nagi_italy"
INSTAGRAM_USERNAME = "nagi.i_official"

bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}


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
    and user_states[message.from_user.id]["step"] == "wait_username"
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
                    f"{story['content']}\n\nView it soon!",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}\n\nView it soon!",
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
                        f"{story['content']}\n\nView it soon!",
                        media_paths=story.get("media_paths"),
                        media_types=story.get("media_types"),
                    )
                else:
                    utils.send_to_telegram(
                        f"{story['content']}\n\nView it soon!",
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
                    f"{story['content']}\n\nView it soon!",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}\n\nView it soon!", media_url=story.get("url")
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
                    f"{story['content']}\n\nView it soon!",
                    media_paths=story.get("media_paths"),
                    media_types=story.get("media_types"),
                )
            else:
                utils.send_to_telegram(
                    f"{story['content']}\n\nView it soon!", media_url=story.get("url")
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
        # Get the text after "/echo "
        command_length = len("/echo ")
        if len(message.text) <= command_length:
            # If there's nothing after the command
            bot.reply_to(message, "Usage: /echo <your message>")
            return

        echo_text = message.text[command_length:]
        bot.reply_to(message, echo_text)
    except Exception as e:
        bot.reply_to(message, f"Error in echo function: {e}")


@bot.message_handler(commands=["help"])
def handle_help(message):
    help_text = """
Available commands:
/pick - Interactive menu to fetch posts (recommended)
/fetch [x|instagram] <username> - Fetch posts by platform and username
/fetch_nagi - Fetch all posts for Nagi
/fetch_nagi_x - Fetch only X/Twitter posts for Nagi
/fetch_nagi_ig - Fetch only Instagram posts for Nagi
/bili <url> - Download and send Bilibili video
/echo <message> - Echo back your message
/help - Show this help message
"""
    bot.send_message(message.chat.id, help_text)


if __name__ == "__main__":
    print("Combined bot started. Listening for commands...")
    bot.polling()
