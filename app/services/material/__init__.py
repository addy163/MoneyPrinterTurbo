import os
import random
from typing import List
import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

from .pexels import PexelsProvider
from .pixabay import PixabayProvider
from .local import LocalProvider
from .baidu_image import BaiduImageProvider
from .bing_image import BingImageProvider

def get_provider(provider_name: str):
    if provider_name == "pexels":
        return PexelsProvider()
    elif provider_name == "pixabay":
        return PixabayProvider()
    elif provider_name == "local_search":
        return LocalProvider()
    elif provider_name == "baidu_image":
        return BaiduImageProvider()
    elif provider_name == "bing_image":
        return BingImageProvider()
    else:
        # Default fallback
        logger.warning(f"Unknown provider '{provider_name}', defaulting to Pexels")
        return PexelsProvider()

def save_video(video_url: str, save_dir: str = "") -> str:
    # If it's a local file (from LocalProvider), just return it.
    if os.path.isfile(video_url):
        return video_url

    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Clean URL to get the base path for extension parsing
    url_without_query = video_url.split("?")[0].lower()
    ext = utils.parse_extension(url_without_query)
    
    # Check if it's a known image extension or contains image markers
    valid_image_exts = ['jpg', 'jpeg', 'png', 'bmp', 'webp']
    
    is_image = False
    if ext in valid_image_exts:
        is_image = True
    elif any(img_marker in url_without_query for img_marker in ['fmt=jpeg', 'fmt=png', 'fmt=auto', 'f=jpeg', 'f=png']):
        # Common image markers in Baidu/Bing URLs
        is_image = True
        if not ext:
            ext = 'jpg' # Default to jpg if marker found but no ext
            
    url_hash = utils.md5(video_url.split("?")[0])
    
    if is_image:
        if not ext:
            ext = "jpg"
        filename = f"img-{url_hash}.{ext}"
    else:
        # Default to mp4 if unknown or video
        if not ext:
            ext = "mp4"
        filename = f"vid-{url_hash}.{ext}"

    video_path = f"{save_dir}/{filename}"

    # if file already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"file already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # download it
    try:
        response = requests.get(
            video_url,
            headers=headers,
            proxies=config.proxy,
            verify=False,
            timeout=(60, 240),
        )
        response.raise_for_status()
        with open(video_path, "wb") as f:
            f.write(response.content)

        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            # If it's a video file, check validity
            if filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                try:
                    clip = VideoFileClip(video_path)
                    duration = clip.duration
                    fps = clip.fps
                    clip.close()
                    if duration > 0 and fps > 0:
                        return video_path
                except Exception as e:
                    try:
                        os.remove(video_path)
                    except Exception:
                        pass
                    logger.warning(f"invalid video file: {video_path} => {str(e)}")
            else:
                # Assume image/other is valid if downloaded
                return video_path
        else:
            return ""
            
    except Exception as e:
        logger.error(f"save_video failed: {e}")
        return ""
    
    return video_path

def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    
    # Check if source is one of our providers
    provider = get_provider(source)
    logger.info(f"using provider: {source}")

    for search_term in search_terms:
        try:
            video_items = provider.search_videos(
                search_term=search_term,
                minimum_duration=max_clip_duration,
                video_aspect=video_aspect,
            )
            logger.info(f"found {len(video_items)} items for '{search_term}'")

            for item in video_items:
                if item.url not in valid_video_urls:
                    valid_video_items.append(item)
                    valid_video_urls.append(item.url)
                    found_duration += item.duration
        except Exception as e:
            logger.error(f"Search failed for term '{search_term}': {e}")

    logger.info(
        f"found total items: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading material: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"material saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                
                # Check if it is an image, if so, use the default duration from item or max_clip_duration
                # Note: 'item.duration' for images was set to 3 or similar in providers.
                seconds = min(max_clip_duration, item.duration)
                
                # If it's a video, item.duration is real duration.
                # If it's an image, item.duration is virtual.
                
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded materials: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download material: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} materials")
    return video_paths

if __name__ == "__main__":
    # Test
    pass