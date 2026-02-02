import os
import glob
from typing import List
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip
from app.models.schema import MaterialInfo, VideoAspect
from app.utils import utils
from .base import BaseProvider

class LocalProvider(BaseProvider):
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        
        # Define assets directory
        # We look into storage/assets
        assets_dir = utils.storage_dir("assets")
        if not os.path.exists(assets_dir):
            logger.warning(f"Local assets directory does not exist: {assets_dir}")
            return []

        # Find all video files
        # You can add more extensions if needed
        video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.webm']
        files = []
        for ext in video_extensions:
            files.extend(glob.glob(os.path.join(assets_dir, "**", ext), recursive=True))

        video_items = []
        # Filter by search_term
        # We split search_term by space to get keywords
        keywords = search_term.lower().split()
        
        for file_path in files:
            filename = os.path.basename(file_path).lower()
            
            # Simple matching strategy:
            # If ANY of the keywords match the filename (partial match), we consider it a candidate.
            # You can change this to ALL if you want stricter matching.
            # Or use fuzzy matching if you install fuzzywuzzy.
            match = False
            for keyword in keywords:
                if keyword in filename:
                    match = True
                    break
            
            if match:
                try:
                    # Get duration using moviepy
                    # Note: Opening many files can be slow. 
                    # Consider caching metadata in a database or JSON file in the future.
                    clip = VideoFileClip(file_path)
                    duration = clip.duration
                    width, height = clip.size
                    clip.close()

                    if duration < minimum_duration:
                        continue

                    # Check aspect ratio if needed?
                    # The current implementation of Pexels/Pixabay does strict checking.
                    # For local files, maybe we should be more lenient or resize later?
                    # The video processing logic (video.py) handles resizing/cropping.
                    # But Pexels provider was filtering by exact resolution.
                    # Pixabay was filtering by width >= target.
                    # Let's filter by aspect ratio similarity or just return it and let video.py handle it.
                    # Video.py does: "if clip_w != video_width or clip_h != video_height: ... resize ..."
                    # So it seems fine to return whatever we find, assuming the user put it there for a reason.
                    # But to be safe and consistent with other providers, maybe we skip completely wrong aspects?
                    # For now, I'll trust the filename match.
                    
                    item = MaterialInfo()
                    item.provider = "local_search" # distinct from "local" source which usually means direct paths provided by user
                    item.url = file_path 
                    item.duration = duration
                    video_items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to read local video {file_path}: {e}")

        return video_items
