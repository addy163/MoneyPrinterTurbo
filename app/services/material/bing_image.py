import os
from typing import List
import requests
from loguru import logger
from app.models.schema import MaterialInfo, VideoAspect
from .base import BaseProvider

class BingImageProvider(BaseProvider):
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        """
        Scrape Bing Images for a given search term.
        """
        logger.info(f"Searching Bing Images for: {search_term}")
        
        # Simple scraping often fails for Bing due to dynamic rendering, 
        # but let's try a basic approach or use a known endpoint.
        # Alternatively, we can use the official API if the user provides a key, 
        # but the prompt implies a "free" scraper approach like MoneyPrinterTurbo usually does.
        
        # We'll use a known trick or just standard scraping. 
        # A robust way without API key is parsing the HTML which is messy.
        # Let's try to mimic a simple browser request.
        
        url = f"https://www.bing.com/images/async?q={search_term}&first=0&count=35&rel=next&adlt=moderate"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
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
            
            # Bing returns HTML snippets in this async endpoint.
            # We need to extract 'murl' (media URL).
            import re
            # murl pattern in Bing's response: murl&quot;:&quot;(.*?)&quot;
            
            html = response.text
            # Find all murl matches
            matches = re.findall(r'murl&quot;:&quot;(.*?)&quot;', html)
            
            results = []
            for murl in matches:
                if murl.startswith("http"):
                    material = MaterialInfo()
                    material.provider = "bing_image"
                    material.url = murl
                    material.duration = 3 # Default duration
                    results.append(material)
            
            return results

        except Exception as e:
            logger.error(f"Failed to fetch Bing Images: {e}")
            return []
