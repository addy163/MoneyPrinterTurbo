from typing import List
from urllib.parse import urlencode
import requests
from loguru import logger
from app.config import config
from app.models.schema import MaterialInfo, VideoAspect
from app.utils import utils
from .base import BaseProvider

requested_count = 0

def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global requested_count
    requested_count += 1
    return api_keys[requested_count % len(api_keys)]

class PexelsProvider(BaseProvider):
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        aspect = VideoAspect(video_aspect)
        video_orientation = aspect.name
        video_width, video_height = aspect.to_resolution()
        api_key = get_api_key("pexels_api_keys")
        headers = {
            "Authorization": api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        }
        # Build URL
        params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
        query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
        logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

        try:
            r = requests.get(
                query_url,
                headers=headers,
                proxies=config.proxy,
                verify=False,
                timeout=(30, 60),
            )
            response = r.json()
            video_items = []
            if "videos" not in response:
                logger.error(f"search videos failed: {response}")
                return video_items
            videos = response["videos"]
            # loop through each video in the result
            for v in videos:
                duration = v["duration"]
                # check if video has desired minimum duration
                if duration < minimum_duration:
                    continue
                video_files = v["video_files"]
                # loop through each url to determine the best quality
                for video in video_files:
                    w = int(video["width"])
                    h = int(video["height"])
                    if w == video_width and h == video_height:
                        item = MaterialInfo()
                        item.provider = "pexels"
                        item.url = video["link"]
                        item.duration = duration
                        video_items.append(item)
                        break
            return video_items
        except Exception as e:
            logger.error(f"search videos failed: {str(e)}")

        return []
