from abc import ABC, abstractmethod
from typing import List
from app.models.schema import MaterialInfo, VideoAspect

class BaseProvider(ABC):
    @abstractmethod
    def search_videos(
        self,
        search_term: str,
        minimum_duration: int,
        video_aspect: VideoAspect = VideoAspect.portrait,
    ) -> List[MaterialInfo]:
        pass
