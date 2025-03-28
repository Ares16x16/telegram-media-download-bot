import os
import asyncio
import telebot
import telebot.apihelper
from telebot import types
import json
from collections import defaultdict

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

# Constants for media directory structure
MEDIA_DIR = utils.MEDIA_DIR
TWITTER_MEDIA_DIR = os.path.join(MEDIA_DIR, "twitter")
INSTAGRAM_POSTS_DIR = os.path.join(MEDIA_DIR, "instagram", "posts")
INSTAGRAM_STORIES_DIR = os.path.join(MEDIA_DIR, "instagram", "stories")
BILIBILI_MEDIA_DIR = os.path.join(MEDIA_DIR, "bilibili")


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


@bot.message_handler(commands=["history"])
def handle_history(message):
    """Command to browse previously fetched posts"""
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Platform buttons
    item_x = types.InlineKeyboardButton(
        "X (Twitter)", callback_data="history_select_platform_twitter"
    )
    item_ig = types.InlineKeyboardButton(
        "Instagram Posts", callback_data="history_select_platform_instagram_posts"
    )
    item_ig_stories = types.InlineKeyboardButton(
        "Instagram Stories", callback_data="history_select_platform_instagram_stories"
    )
    item_bili = types.InlineKeyboardButton(
        "Bilibili Videos", callback_data="history_select_platform_bilibili"
    )

    markup.add(item_x, item_ig)
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

    # Get accounts for this platform
    accounts = utils.get_accounts_by_platform(platform)

    # Fallback: If no accounts found, try scanning directories directly
    if not accounts:
        try:
            # Use the constants defined at the top of the file
            platform_dir_map = {
                "twitter": TWITTER_MEDIA_DIR,
                "instagram_posts": INSTAGRAM_POSTS_DIR,
                "instagram_stories": INSTAGRAM_STORIES_DIR,
                "bilibili": BILIBILI_MEDIA_DIR,
            }

            if platform in platform_dir_map:
                media_dir = platform_dir_map[platform]
                print(f"Looking for {platform} accounts in directory: {media_dir}")

                if os.path.exists(media_dir):
                    # List subdirectories (account names)
                    accounts = [
                        d
                        for d in os.listdir(media_dir)
                        if os.path.isdir(os.path.join(media_dir, d))
                    ]

                    # Special handling for Instagram stories which might follow different patterns
                    if platform == "instagram_stories" and not accounts:
                        # Try looking directly in the instagram directory for stories
                        stories_pattern_dirs = [
                            os.path.join(MEDIA_DIR, "instagram", "stories"),
                            os.path.join(MEDIA_DIR, "instagram"),
                        ]

                        for dir_path in stories_pattern_dirs:
                            if os.path.exists(dir_path):
                                # Look for "stories_" prefixed dirs or any dirs in stories/
                                for d in os.listdir(dir_path):
                                    full_path = os.path.join(dir_path, d)
                                    if os.path.isdir(full_path) and (
                                        d.startswith("stories_")
                                        or "stories" in dir_path
                                    ):
                                        accounts.append(d.replace("stories_", ""))

                        if accounts:
                            # Remove duplicates but preserve order
                            seen = set()
                            accounts = [
                                x for x in accounts if not (x in seen or seen.add(x))
                            ]
                            print(
                                f"Found story accounts via pattern matching: {accounts}"
                            )

                    # Register hardcoded accounts if still no accounts found
                    if not accounts:
                        if platform == "instagram_stories":
                            accounts = ["nagi.i_official"]
                            print(
                                f"Using hardcoded Instagram story account: {accounts}"
                            )
                        elif platform == "twitter":
                            accounts = [X_USERNAME]
                            print(f"Using hardcoded Twitter account: {accounts}")
                        elif platform == "instagram_posts":
                            accounts = [INSTAGRAM_USERNAME]
                            print(f"Using hardcoded Instagram account: {accounts}")
                    else:
                        print(
                            f"Found accounts via directory scanning for {platform}: {accounts}"
                        )
        except Exception as e:
            print(f"Error in directory scanning fallback: {e}")
            import traceback

            traceback.print_exc()

    if not accounts:
        bot.edit_message_text(
            f"No accounts found for {platform.replace('_', ' ')}. Fetch some content first!\n"
            f"Check if media files are in expected locations:\n"
            f"- Instagram posts: {INSTAGRAM_POSTS_DIR}\n"
            f"- Instagram stories: {INSTAGRAM_STORIES_DIR}\n"
            f"- Twitter: {TWITTER_MEDIA_DIR}",
            chat_id=chat_id,
            message_id=call.message.message_id,
        )
        # Add back button
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

    # Store the selected platform in user state
    user_states[user_id] = {"platform": platform}

    # Create account selection buttons
    markup = types.InlineKeyboardMarkup(row_width=1)
    for account in accounts:
        markup.add(
            types.InlineKeyboardButton(
                f"@{account}",
                callback_data=f"history_select_account_{platform}_{account}",
            )
        )

    # Add back button
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
    # Parse the platform and account from the callback data
    parts = call.data.split("_", 4)
    if len(parts) >= 5:
        platform = parts[3]
        account = parts[4]
    else:
        bot.answer_callback_query(call.id, "Invalid selection")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    # Load sent posts data
    sent_posts = utils.load_sent_posts()

    if platform == "twitter":
        posts = [
            p
            for p in sent_posts.get("x_posts", [])
            if f"twitter_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
        platform_key = f"twitter_{account}"
    elif platform == "instagram_posts":
        posts = [
            p
            for p in sent_posts.get("instagram_posts", [])
            if f"instagram_post_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
        platform_key = f"instagram_post_{account}"
    elif platform == "instagram_stories":
        posts = [
            p
            for p in sent_posts.get("instagram_stories", [])
            if f"instagram_story_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
        platform_key = f"instagram_story_{account}"
    elif platform == "bilibili":
        # Get videos from sent_videos.json
        sent_videos = utils.load_sent_videos()
        posts = [
            p
            for p in sent_videos.get("videos", [])
            if f"bilibili_{account}_{p}" in sent_posts.get("media_mapping", {})
        ]
        platform_key = f"bilibili_{account}"
    else:
        bot.answer_callback_query(call.id, "Unknown platform")
        return

    if not posts:
        # If we didn't find posts with the detailed mapping, fall back to all posts for this account
        if platform == "twitter":
            posts = sent_posts.get("x_posts", [])
        elif platform == "instagram_posts":
            posts = sent_posts.get("instagram_posts", [])
        elif platform == "instagram_stories":
            posts = sent_posts.get("instagram_stories", [])
        elif platform == "bilibili":
            sent_videos = utils.load_sent_videos()
            posts = sent_videos.get("videos", [])

    if not posts:
        bot.edit_message_text(
            f"No posts found for {account} on {platform.replace('_', ' ')}.",
            chat_id=chat_id,
            message_id=call.message.message_id,
        )
        # Add back button
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

    # Store user state for pagination
    user_states[user_id] = {
        "platform": platform,
        "platform_key": platform_key,
        "account": account,
        "posts": posts,
        "current_page": 0,
        "posts_per_page": 5,
    }

    # Show the first page
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
        # Go back to platform selection
        handle_history(call.message)

    elif call.data == "history_back_to_accounts":
        # Go back to account selection
        platform = user_states[user_id].get("platform")
        if platform:
            history_select_platform_callback(
                types.CallbackQuery(
                    id=call.id,
                    from_user=call.from_user,
                    message=call.message,
                    data=f"history_select_platform_{platform}",
                )
            )

    bot.answer_callback_query(call.id)


def show_posts_page(user_id, chat_id, message_id):
    """Display a page of posts with pagination controls"""
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

    # Add buttons for each post on this page
    post_buttons = []
    for i, post_id in enumerate(page_posts):
        post_idx = start_idx + i
        btn_text = f"Post {post_idx + 1}"
        post_buttons.append(
            types.InlineKeyboardButton(
                btn_text, callback_data=f"view_post_{platform}_{account}_{post_id}"
            )
        )

    # Add post buttons in rows of 2
    for i in range(0, len(post_buttons), 2):
        if i + 1 < len(post_buttons):
            markup.add(post_buttons[i], post_buttons[i + 1])
        else:
            markup.add(post_buttons[i])

    # Navigation buttons
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

    # Create message text
    platform_name = platform.replace("_", " ").capitalize()
    message_text = (
        f"{platform_name} History for @{account}\n"
        f"Page {current_page + 1}/{(len(posts) + posts_per_page - 1) // posts_per_page}\n"
        f"Showing posts {start_idx + 1}-{end_idx} of {len(posts)}"
    )

    bot.edit_message_text(
        message_text, chat_id=chat_id, message_id=message_id, reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_post_"))
def view_post_callback(call):
    parts = call.data.split("_")
    if len(parts) < 5:  # Format: view_post_platform_account_postid
        bot.answer_callback_query(call.id, "Invalid post data")
        return

    platform = parts[2]
    account = parts[3]
    post_id = "_".join(parts[4:])  # In case the ID contains underscores

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Session expired. Please start over.")
        return

    platform_key = f"{user_states[user_id].get('platform_key', '')}_{post_id}"

    # First try using the platform_key
    media_paths = utils.get_post_media_files(platform_key, post_id)

    # If no media found, try with just basic platform type
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

    # If still no media, try scanning directories with our new structure
    if not media_paths:
        print(
            f"No media mapping found for {platform_key}_{post_id}, trying to scan directories"
        )
        try:
            # Try to locate media based on expected directory structure
            if platform == "twitter":
                account_dir = os.path.join(TWITTER_MEDIA_DIR, account)
                post_dir = os.path.join(account_dir, post_id)
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
                account_dir = os.path.join(INSTAGRAM_POSTS_DIR, account)
                post_dir = os.path.join(account_dir, post_id)
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

            elif platform == "instagram_stories":
                # Try multiple patterns for stories
                possible_paths = [
                    os.path.join(INSTAGRAM_STORIES_DIR, account, post_id),
                    os.path.join(INSTAGRAM_STORIES_DIR, f"stories_{account}", post_id),
                    os.path.join(MEDIA_DIR, "instagram", f"stories_{account}", post_id),
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        media_paths = [
                            os.path.join(path, f)
                            for f in os.listdir(path)
                            if os.path.isfile(os.path.join(path, f))
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
                account_dir = os.path.join(BILIBILI_MEDIA_DIR, account)
                post_dir = os.path.join(account_dir, post_id)
                if os.path.exists(post_dir):
                    media_paths = [
                        os.path.join(post_dir, f)
                        for f in os.listdir(post_dir)
                        if os.path.isfile(os.path.join(post_dir, f))
                        and f.endswith(".mp4")
                    ]

            print(
                f"Directory scan found {len(media_paths)} files for {platform}/{account}/{post_id}"
            )

        except Exception as e:
            print(f"Error in directory scanning fallback: {e}")
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

    # Send the post with its media
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

    # Send media with caption
    media_types = []
    for path in media_paths:
        if path.endswith(".mp4"):
            media_types.append("video")
        else:
            media_types.append("photo")

    # Create navigation buttons for this view
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "Back to list",
            callback_data=f"history_select_account_history_{platform}_{account}",
        )
    )

    # Attempt to send the media
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
            # Send media group
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

            # Send media group first, then send a message with the navigation buttons
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
/fetch_nagi - Fetch all posts for Nagi
/fetch_nagi_x - Fetch only X/Twitter posts for Nagi
/fetch_nagi_ig - Fetch only Instagram posts for Nagi
/bili <url> - Download and send Bilibili video
/history - Browse previously fetched posts and media
/echo <message> - Echo back your message
/help - Show this help message
"""
    bot.send_message(message.chat.id, help_text)


if __name__ == "__main__":
    print("Combined bot started. Listening for commands...")
    bot.polling()
