import os
from typing import List
import requests
import re
from loguru import logger
from app.models.schema import MaterialInfo, VideoAspect
from .base import BaseProvider

class BaiduImageProvider(BaseProvider):
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        """
        Scrape Baidu Images for a given search term.
        Note: These are images, so 'minimum_duration' is ignored for fetching, 
        but we set a default duration for the slideshow effect.
        """
        logger.info(f"Searching Baidu Images for: {search_term}")
        
        # Baidu Image Search URL
        url = f"https://image.baidu.com/search/acjson?tn=resultjson_com&logid=5179920884740250626&ipn=rj&ct=201326592&is=&fp=result&queryWord={search_term}&cl=2&lm=-1&ie=utf-8&oe=utf-8&adpicid=&st=-1&z=&ic=&hd=&latest=&copyright=&word={search_term}&s=&se=&tab=&width=&height=&face=0&istype=2&qc=&nc=1&fr=&expermode=&force=&pn=0&rn=30&gsm=1e&1618127565631="
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://image.baidu.com/"
        }

        try:
            from app.config import config
            response = requests.get(
                url, 
                headers=headers, 
                proxies=config.proxy,
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            content = response.text
            results = []
            
            # Strategy 1: Standard JSON parsing with non-strict mode
            try:
                import json
                data = json.loads(content, strict=False)
                if "data" in data:
                    items = data["data"]
                    for item in items:
                        img_url = item.get("middleURL") or item.get("thumbURL") or item.get("objURL")
                        if img_url and img_url.startswith("http"):
                            material = MaterialInfo()
                            material.provider = "baidu_image"
                            material.url = img_url
                            material.duration = 3
                            results.append(material)
            except Exception as e:
                logger.warning(f"JSON parsing failed, trying regex fallback: {e}")
                
                # Strategy 2: Regex fallback to extract URLs directly
                # Patterns for middleURL, thumbURL, objURL
                # Handles both raw slashes and escaped slashes
                urls = re.findall(r'"(?:middleURL|thumbURL|objURL)":"(https?[:\\/]+.*?)"', content)
                for img_url in urls:
                    # Unescape potential escaped slashes and remove trailing quote if any
                    img_url = img_url.replace('\\/', '/').split('"')[0]
                    if img_url.startswith("http"):
                        material = MaterialInfo()
                        material.provider = "baidu_image"
                        material.url = img_url
                        material.duration = 3
                        results.append(material)

            if not results:
                logger.error("No image results found in Baidu response.")
                
            return results

        except Exception as e:
            logger.error(f"Failed to fetch Baidu Images: {e}")
            return []
        
        return []
