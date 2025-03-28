import os
import sys
import time
import random
import requests
import subprocess
from bilibili_api import video, Credential
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

import utils

load_dotenv()

MEDIA_DIR = utils.MEDIA_DIR
bot = utils.bot

credential = Credential(
    sessdata=os.getenv("BILI_SESSDATA"),
    bili_jct=os.getenv("BILI_BILI_JCT"),
    buvid3=os.getenv("BILI_BUVID3"),
)


async def get_video_info(video_url):
    try:
        if "b23.tv" in video_url:
            response = requests.head(video_url, allow_redirects=True)
            video_url = response.url
            print(f"Expanded URL to: {video_url}")
        bv_id = None
        av_id = None
        if "BV" in video_url:
            parts = video_url.split("BV")
            if len(parts) > 1:
                bv_id = "BV" + parts[1].split("?")[0].split("/")[0].strip()
                print(f"Extracted BV ID: {bv_id}")
        elif "av" in video_url.lower():
            parts = video_url.lower().split("av")
            if len(parts) > 1:
                av_str = parts[1].split("?")[0].split("/")[0].strip()
                if av_str.isdigit():
                    av_id = int(av_str)
                    print(f"Extracted AV ID: {av_id}")
        if not bv_id and not av_id:
            print(f"Could not extract video ID from URL: {video_url}")
            return None
        v = (
            video.Video(bvid=bv_id, credential=credential)
            if bv_id
            else video.Video(aid=av_id, credential=credential)
        )
        if v:
            print("Fetching video info...")
            info = await v.get_info()
            return {
                "id": info["bvid"],
                "title": info["title"],
                "description": info["desc"],
                "cover_url": info["pic"],
                "author": info["owner"]["name"],
                "duration": info["duration"],
                "url": f"https://www.bilibili.com/video/{info['bvid']}",
            }
        return None
    except Exception as e:
        print(f"Error getting video info: {e}")
        return None


async def download_bilibili_video(video_url):
    try:
        print(f"Getting information for video: {video_url}")
        info = await get_video_info(video_url)
        if not info:
            print("Could not get video info, aborting download")
            return None
        bv_id = info["id"]

        bili_media_dir = utils.get_user_media_dir("bilibili", info["author"])
        media_filename = utils.generate_media_filename("bilibili", bv_id, ".mp4")
        video_path = os.path.join(bili_media_dir, media_filename)

        if os.path.exists(video_path):
            print(f"Video already downloaded: {video_path}")
        else:
            print(f"Downloading video {bv_id}: {info['title']}")
            v = video.Video(bvid=bv_id, credential=credential)
            print("Getting download URL...")
            try:
                url = await v.get_download_url(0)
            except Exception as e:
                err_str = str(e)
                if "-404" in err_str or "啥都木有" in err_str:
                    print(
                        "Bilibili API download failed. Falling back to yt-dlp method."
                    )
                    ydl_opts = {
                        "outtmpl": video_path,
                        "format": "bestvideo+bestaudio/best",
                        "merge_output_format": "mp4",
                    }
                    with YoutubeDL(ydl_opts) as ydl:
                        ydl.download([f"https://www.bilibili.com/video/{bv_id}"])

                    utils.register_account("bilibili", info["author"])
                    utils.save_media_mapping(
                        f"bilibili_{info['author']}", bv_id, [video_path]
                    )
                    return {"path": video_path, "info": info}
                else:
                    raise e
            print("Download URLs obtained:")
            print(f"Video formats available: {len(url['dash']['video'])}")
            print(f"Audio formats available: {len(url['dash']['audio'])}")
            video_streams = url["dash"]["video"]
            video_streams.sort(key=lambda x: x["bandwidth"])
            video_index = min(len(video_streams) - 1, len(video_streams) // 2)
            video_url_sel = video_streams[video_index]["baseUrl"]
            audio_url = url["dash"]["audio"][0]["baseUrl"]
            print(
                f"Selected video bandwidth: {video_streams[video_index]['bandwidth']}"
            )
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"https://www.bilibili.com/video/{bv_id}",
            }

            # Create temporary file paths in the new directory structure
            temp_video_path = os.path.join(bili_media_dir, f"temp_video_{bv_id}.m4s")
            temp_audio_path = os.path.join(bili_media_dir, f"temp_audio_{bv_id}.m4s")

            print("Downloading video stream...")
            with requests.get(video_url_sel, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int(50 * downloaded / total_size)
                            sys.stdout.write(
                                f"\rVideo: [{'#'*progress}{' '*(50-progress)}] {downloaded/total_size*100:.1f}%"
                            )
                            sys.stdout.flush()
            print("\nVideo download complete!")
            print("Downloading audio stream...")
            with requests.get(audio_url, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_audio_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int(50 * downloaded / total_size)
                            sys.stdout.write(
                                f"\rAudio: [{'#'*progress}{' '*(50-progress)}] {downloaded/total_size*100:.1f}%"
                            )
                            sys.stdout.flush()
            print("\nAudio download complete!")
            try:
                print("Merging video and audio with FFmpeg...")
                cmd = [
                    "ffmpeg",
                    "-i",
                    temp_video_path,
                    "-i",
                    temp_audio_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    video_path,
                    "-y",
                ]
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()
                if process.returncode != 0:
                    print(f"Error merging: {stderr.decode()}")
                    os.rename(temp_video_path, video_path)
                else:
                    print("Successfully merged video and audio!")
            except Exception as e:
                print(f"Error during FFmpeg merge: {e}")
                os.rename(temp_video_path, video_path)
            print("Cleaning up temporary files...")
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

        # Register the account
        utils.register_account("bilibili", info["author"])

        # Save media mapping with author name
        utils.save_media_mapping(f"bilibili_{info['author']}", bv_id, [video_path])
        return {"path": video_path, "info": info}
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None


async def process_video(video_url):
    print(f"Processing video: {video_url}")
    sent_videos = utils.load_sent_videos()
    video_id = None
    if "BV" in video_url:
        video_id = "BV" + video_url.split("BV")[1].split("?")[0].split("/")[0]
    elif "av" in video_url.lower():
        video_id = "av" + video_url.lower().split("av")[1].split("?")[0].split("/")[0]
    if video_id and video_id in sent_videos["videos"]:
        print(f"Video {video_id} already sent previously.")
        return False
    result = await download_bilibili_video(video_url)
    if not result:
        print("Failed to download video")
        return False
    info = result["info"]
    caption = f"{info['title']}\n\n{info['url']}"

    success = utils.send_to_telegram(
        caption, media_paths=[result["path"]], media_types=["video"]
    )

    if success and video_id:
        sent_videos["videos"].append(video_id)
        utils.save_sent_videos(sent_videos)
        print(f"Successfully sent video {video_id} to Telegram")
        return True
    return False
