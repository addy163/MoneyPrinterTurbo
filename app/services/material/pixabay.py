from typing import List
from urllib.parse import urlencode
import requests
from loguru import logger
from app.config import config
from app.models.schema import MaterialInfo, VideoAspect
from .base import BaseProvider

requested_count = 0

def get_api_key(cfg_key: str):
    from app.utils import utils # Local import to avoid potential circular dependency issues if any
    
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

class PixabayProvider(BaseProvider):
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        aspect = VideoAspect(video_aspect)

        video_width, video_height = aspect.to_resolution()

        api_key = get_api_key("pixabay_api_keys")
        # Build URL
        params = {
            "q": search_term,
            "video_type": "all",  # Accepted values: "all", "film", "animation"
            "per_page": 50,
            "key": api_key,
        }
        query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
        logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

        try:
            r = requests.get(
                query_url, proxies=config.proxy, verify=False, timeout=(30, 60)
            )
            response = r.json()
            video_items = []
            if "hits" not in response:
                logger.error(f"search videos failed: {response}")
                return video_items
            videos = response["hits"]
            # loop through each video in the result
            for v in videos:
                duration = v["duration"]
                # check if video has desired minimum duration
                if duration < minimum_duration:
                    continue
                video_files = v["videos"]
                # loop through each url to determine the best quality
                for video_type in video_files:
                    video = video_files[video_type]
                    w = int(video["width"])
                    # h = int(video["height"])
                    if w >= video_width:
                        item = MaterialInfo()
                        item.provider = "pixabay"
                        item.url = video["url"]
                        item.duration = duration
                        video_items.append(item)
                        break
            return video_items
        except Exception as e:
            logger.error(f"search videos failed: {str(e)}")

        return []
