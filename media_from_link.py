import os
import re
import json
import requests
import traceback
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import utils
import fetchers


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
        # First fetch all stories for the user - we need to filter from these
        all_stories = fetchers.fetch_instagram_stories(username)

        # Check if we have stories and if the specific ID matches
        if all_stories:
            for story in all_stories:
                # Try to get story ID from media paths or URL
                current_id = None

                # Try to extract ID from media paths
                if story.get("media_paths"):
                    for path in story["media_paths"]:
                        if str(story_id) in path:
                            current_id = story_id
                            break

                # Try to extract ID from URL
                if not current_id and story.get("url"):
                    if str(story_id) in story["url"]:
                        current_id = story_id

                # If this is the story we want, return it
                if current_id:
                    return story

        print(f"Story ID {story_id} not found among available stories for {username}")
        return None

    except Exception as e:
        print(f"Error fetching specific Instagram story: {e}")
        traceback.print_exc()
        return None


def download_and_send_specific_instagram_story(message, url):
    """
    Download and send the specific Instagram story from the provided URL.
    """
    try:
        username, story_id = extract_instagram_story_info(url)

        if not username or not story_id:
            return False, "Could not extract username and story ID from URL."

        story = fetch_specific_instagram_story(username, story_id)

        if not story:
            return False, f"Could not find story {story_id} for user @{username}."

        # Send the story to Telegram
        if story.get("media_paths"):
            utils.send_to_telegram(
                f"Instagram Story from @{username}",
                media_paths=story.get("media_paths"),
                media_types=story.get("media_types"),
                chat_id=message.chat.id,
            )
            return True, f"Downloaded story from @{username}"

        elif story.get("url"):
            utils.send_to_telegram(
                f"Instagram Story from @{username}",
                media_url=story.get("url"),
                chat_id=message.chat.id,
            )
            return True, f"Downloaded story from @{username}"

        else:
            return False, "Found the story but it doesn't contain media."

    except Exception as e:
        error_msg = f"Error downloading Instagram story: {e}"
        print(error_msg)
        traceback.print_exc()
        return False, error_msg
