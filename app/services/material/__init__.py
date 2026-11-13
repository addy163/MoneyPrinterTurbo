"""素材源入口：上游主逻辑 + 本项目自定义的百度/Bing/本地素材源。

上游重写后的下载主逻辑在 ``.backup.download_videos``（库存源、付费生成源、
clip_speed、进度回调、image_motion 等）。本项目额外维护的三个源在
``.image_sources``。这里只按 ``source`` 做分发，不再导入旧版 provider
模块——那些模块使用 moviepy v1 的导入路径，在新版依赖下会在启动阶段
直接 ImportError。

保留 ``save_video`` 名字只是为了兼容可能存在的旧调用方。
"""
from __future__ import annotations

from . import image_sources

IMAGE_SOURCES = image_sources.IMAGE_SOURCES
# 返回图片、需要 task 层用 video.preprocess_video 渲染成片段的源
PREPROCESS_SOURCES = image_sources.PREPROCESS_SOURCES

__all__ = [
    "download_videos",
    "save_video",
    "IMAGE_SOURCES",
    "PREPROCESS_SOURCES",
]


def __getattr__(name: str):
    """透传上游 ``backup`` 模块的公共名字，保持 material 包的原有属性集合。

    ``task.py`` 的异常处理会访问 ``material.WaveSpeedUnconfirmedTaskError``、
    ``material.OpenAIImagePaidResultError``、``material.CodexImageMaterialError``
    等付费源异常类，这些类定义在 ``.backup`` 中。门面只覆盖下载入口，其余
    名字按需转发，避免精简导入时破坏异常匹配。
    """
    if name.startswith("_"):
        raise AttributeError(name)
    from . import backup

    try:
        return getattr(backup, name)
    except AttributeError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None


def download_videos(*args, **kwargs):
    """按素材源分发，参数原样转发，签名与 task.py 的调用保持一致。

    * 百度图片 / Bing 图片 / 本地素材库 -> ``image_sources``
    * 其余所有源                        -> ``.backup``（上游主逻辑）
    """
    source = kwargs.get("source")
    if source is None and len(args) >= 3:
        source = args[2]

    if source in image_sources.IMAGE_SOURCES:
        return image_sources.download_videos(*args, **kwargs)

    from .backup import download_videos as upstream_download_videos

    return upstream_download_videos(*args, **kwargs)


def save_video(video_url: str, save_dir: str = "") -> str:
    """兼容旧调用：优先交给上游保存逻辑，否则回退到图片源下载器。"""
    from app.utils import utils

    from . import backup

    upstream = getattr(backup, "save_video", None)
    if upstream is not None:
        return upstream(video_url, save_dir)
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")
    return image_sources._save(video_url, save_dir)
