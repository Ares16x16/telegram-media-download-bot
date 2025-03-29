import os
import asyncio
import sys
import random
import string
import subprocess
from yt_dlp import YoutubeDL

import utils

MEDIA_DIR = utils.MEDIA_DIR
YOUTUBE_MEDIA_DIR = os.path.join(MEDIA_DIR, "youtube")


async def process_video(video_url: str):
    if not os.path.exists(YOUTUBE_MEDIA_DIR):
        os.makedirs(YOUTUBE_MEDIA_DIR)
    random_id = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    outtmpl = os.path.join(YOUTUBE_MEDIA_DIR, f"{random_id}.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info)
        return {"path": filename, "title": info.get("title", "Untitled")}
    except Exception as e:
        print(f"Error downloading YouTube video: {e}", file=sys.stderr)
        return None
