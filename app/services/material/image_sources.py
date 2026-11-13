"""百度图片 / Bing 图片 / 本地素材库：接入当前主架构的补充素材源。

这三个源返回的是**图片文件或本地路径**，不是视频片段。调用方
``task.get_video_materials`` 会在下载后用 ``video.preprocess_video`` 把图片
渲染成带动效的片段（见 task.py 的图片源预处理分支）。

实现上刻意保持自包含：只依赖标准库、requests、loguru 以及新版仍然提供的
``config`` / ``utils.task_dir`` / ``MaterialInfo``，不去调用旧版
``material.__init__`` 里的 ``get_provider``，从而与主下载逻辑解耦。
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from typing import Callable, List
from urllib.parse import quote, urlsplit

import requests
from loguru import logger

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect
from app.utils import utils

# 由本模块负责的素材源
IMAGE_SOURCES = ("baidu_image", "bing_image", "local_search")
# 其中只有远程图片需要预处理成视频片段；local_search 返回的是本地视频文件
PREPROCESS_SOURCES = ("baidu_image", "bing_image")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_IMAGE_EXTS = ("jpg", "jpeg", "png", "bmp", "webp")
# 百度 / Bing 的图片直链常带这类参数而没有 .jpg 后缀；旧版会把它们误存成
# .mp4，导致 ffmpeg 校验失败。这里按 URL 内容判定真实类型。
_IMAGE_URL_MARKERS = ("fmt=jpeg", "fmt=png", "fmt=auto", "f=jpeg", "f=png")
_SEARCH_RESULT_LIMIT = 30


def _tls_verify() -> bool:
    """遵循新版的 tls_verify 配置，而不是旧版无条件 verify=False。"""
    return bool(config.app.get("tls_verify", True))


def _get(url: str, headers: dict | None = None, timeout: int = 15):
    return requests.get(
        url,
        headers=headers or {"User-Agent": _UA},
        proxies=config.proxy,
        verify=_tls_verify(),
        timeout=timeout,
    )


def _material(provider: str, url: str, duration: int) -> MaterialInfo:
    return MaterialInfo(provider=provider, url=url, duration=duration)


def search_baidu_image(search_term: str, limit: int = _SEARCH_RESULT_LIMIT) -> List[MaterialInfo]:
    """抓取百度图片搜索结果。JSON 解析失败时回退到正则提取。"""
    logger.info(f"Searching Baidu Images for: {search_term}")
    keyword = quote(search_term)
    url = (
        "https://image.baidu.com/search/acjson?tn=resultjson_com&ipn=rj"
        "&ct=201326592&fp=result&queryWord={kw}&cl=2&lm=-1&ie=utf-8&oe=utf-8"
        "&word={kw}&istype=2&nc=1&pn=0&rn={limit}&gsm=1e"
    ).format(kw=keyword, limit=limit)
    headers = {"User-Agent": _UA, "Referer": "https://image.baidu.com/"}

    try:
        response = _get(url, headers=headers)
        response.raise_for_status()
        response.encoding = "utf-8"
        content = response.text
    except Exception as exc:
        logger.error(f"Failed to fetch Baidu Images: {exc}")
        return []

    results: List[MaterialInfo] = []
    try:
        # 百度返回结果里常混入非标准控制字符，strict=False 是必要的容错。
        data = json.loads(content, strict=False)
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            img_url = (
                item.get("middleURL")
                or item.get("thumbURL")
                or item.get("objURL")
            )
            if isinstance(img_url, str) and img_url.startswith("http"):
                results.append(_material("baidu_image", img_url, 3))
    except Exception as exc:
        logger.warning(f"Baidu JSON parsing failed, trying regex fallback: {exc}")
        urls = re.findall(
            r'"(?:middleURL|thumbURL|objURL)":"(https?[:\\/]+.*?)"', content
        )
        for raw in urls:
            img_url = raw.replace("\\/", "/").split('"')[0]
            if img_url.startswith("http"):
                results.append(_material("baidu_image", img_url, 3))

    if not results:
        logger.error("No image results found in Baidu response.")
    return results[:limit]


def search_bing_image(search_term: str, limit: int = _SEARCH_RESULT_LIMIT) -> List[MaterialInfo]:
    """抓取 Bing 图片异步端点里的 murl 直链。"""
    logger.info(f"Searching Bing Images for: {search_term}")
    url = (
        "https://www.bing.com/images/async?q={kw}&first=0&count={limit}"
        "&rel=next&adlt=moderate"
    ).format(kw=quote(search_term), limit=limit)

    try:
        response = _get(url)
        response.raise_for_status()
        html = response.text
    except Exception as exc:
        logger.error(f"Failed to fetch Bing Images: {exc}")
        return []

    results: List[MaterialInfo] = []
    for murl in re.findall(r'murl&quot;:&quot;(.*?)&quot;', html):
        if murl.startswith("http"):
            results.append(_material("bing_image", murl, 3))
    if not results:
        logger.error("No image results found in Bing response.")
    return results[:limit]


def search_local(
    search_term: str,
    minimum_duration: int,
    limit: int = _SEARCH_RESULT_LIMIT,
) -> List[MaterialInfo]:
    """按文件名关键词匹配 storage/assets 下的本地视频。"""
    assets_dir = utils.storage_dir("assets")
    if not os.path.isdir(assets_dir):
        logger.warning(f"Local assets directory does not exist: {assets_dir}")
        return []

    files: List[str] = []
    for ext in ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm"):
        files.extend(glob.glob(os.path.join(assets_dir, "**", ext), recursive=True))

    keywords = search_term.lower().split()
    results: List[MaterialInfo] = []
    for file_path in sorted(files):
        filename = os.path.basename(file_path).lower()
        if keywords and not any(kw in filename for kw in keywords):
            continue
        try:
            from moviepy import VideoFileClip

            clip = VideoFileClip(file_path)
            duration = clip.duration
            clip.close()
            if duration < minimum_duration:
                continue
            results.append(
                _material("local_search", file_path, int(duration))
            )
        except Exception as exc:
            logger.warning(f"Failed to read local video {file_path}: {exc}")
        if len(results) >= limit:
            break
    return results


def search_videos(source: str, search_term: str, minimum_duration: int) -> List[MaterialInfo]:
    if source == "baidu_image":
        return search_baidu_image(search_term)
    if source == "bing_image":
        return search_bing_image(search_term)
    if source == "local_search":
        return search_local(search_term, minimum_duration)
    return []


def _image_extension(url: str) -> str:
    """判断直链是否指向图片，返回应使用的扩展名；不是图片则返回空串。"""
    parsed = urlsplit(url)
    path = parsed.path.lower()
    ext = os.path.splitext(path)[1].lstrip(".")
    if ext in _IMAGE_EXTS:
        return ext
    query = parsed.query.lower()
    if any(marker in query or marker in path for marker in _IMAGE_URL_MARKERS):
        return "jpg"
    return ""


def _save(url: str, save_dir: str) -> str:
    """下载素材到缓存目录，返回本地路径；图片后缀按真实内容判定。"""
    if os.path.isfile(url):
        return url

    if not os.path.isdir(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    parsed = urlsplit(url)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()
    image_ext = _image_extension(url)
    if image_ext:
        filename = f"img-{digest}.{image_ext}"
    else:
        ext = os.path.splitext(parsed.path.lower())[1].lstrip(".") or "mp4"
        filename = f"vid-{digest}.{ext}"

    target = os.path.join(save_dir, filename)
    if os.path.exists(target) and os.path.getsize(target) > 0:
        logger.info(f"file already exists: {target}")
        return target

    try:
        response = _get(url, timeout=(15, 60))
        response.raise_for_status()
        with open(target, "wb") as handle:
            handle.write(response.content)
    except Exception as exc:
        logger.error(f"failed to download material: {exc}")
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError:
            pass
        return ""

    if not os.path.exists(target) or os.path.getsize(target) == 0:
        return ""
    return target


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "baidu_image",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode=None,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    clip_speed: float = 1.0,
    match_script_order: bool = False,
    progress_callback: Callable[[float], None] | None = None,
    image_motion=None,
    **generation_options,
) -> List[str]:
    """图片/本地素材源的下载入口，签名与新版 ``backup.download_videos`` 对齐。

    ``generation_options`` 是付费生成源专用的上下文，图片源不使用，仅用于
    兼容 task.py 统一传参。
    """
    material_directory = str(config.app.get("material_directory", "") or "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""
    if not material_directory:
        material_directory = utils.storage_dir("cache_videos")

    candidates: List[MaterialInfo] = []
    seen: set[str] = set()
    terms = search_terms or []
    for index, term in enumerate(terms):
        try:
            items = search_videos(source, str(term), max_clip_duration)
        except Exception as exc:
            logger.error(f"Search failed for term '{term}': {exc}")
            items = []
        if not match_script_order:
            # 打散同一关键词下的候选，保留逐词搜索结果的整体顺序
            import random

            random.shuffle(items)
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            candidates.append(item)
        if progress_callback and terms:
            progress_callback(min(1.0, (index + 1) / len(terms) * 0.2))

    if not match_script_order and video_concat_mode is not None:
        mode = getattr(video_concat_mode, "value", video_concat_mode)
        if mode == "random":
            import random

            random.shuffle(candidates)

    speed = max(0.01, float(clip_speed or 1.0))
    image_seconds = max(1, int(max_clip_duration)) / speed

    paths: List[str] = []
    total_duration = 0.0
    for index, item in enumerate(candidates):
        saved = _save(item.url, material_directory)
        if saved:
            paths.append(saved)
            is_local_video = source == "local_search"
            seconds = float(item.duration) / speed if is_local_video else image_seconds
            total_duration += seconds
            if audio_duration and total_duration > audio_duration:
                logger.info(
                    f"total duration of downloaded materials: {total_duration} seconds, "
                    "skip downloading more"
                )
                break
        if progress_callback and candidates:
            ratio = (index + 1) / len(candidates)
            progress_callback(min(1.0, 0.2 + ratio * 0.8))

    logger.success(f"downloaded {len(paths)} materials from {source}")
    return paths
