"""
媒体附件检测与扩展注册

用于将文章内容按附件类型归类：
- images: 单图/多图
- gallery: 相册（多图）
- videos: 视频
- link: 外链卡片
- audio: 音频

并提供可扩展接口，便于后续二次开发新增自定义媒体类型检测器。
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, MutableMapping, Optional


MEDIA_ATTACHMENT_KEYS = ("images", "gallery", "videos", "link", "audio")

# 默认相册阈值：达到该图片数视为“相册”
DEFAULT_GALLERY_THRESHOLD = 4


@dataclass(frozen=True)
class MediaAttachmentSummary:
    has_images: bool
    has_gallery: bool
    has_videos: bool
    has_link: bool
    has_audio: bool
    image_count: int
    image_urls: List[str]
    external_links: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "images": self.has_images,
            "gallery": self.has_gallery,
            "videos": self.has_videos,
            "link": self.has_link,
            "audio": self.has_audio,
            "image_count": self.image_count,
            "image_urls": list(self.image_urls),
            "external_links": list(self.external_links),
        }


AttachmentDetector = Callable[[MediaAttachmentSummary], bool]


_IMAGE_SRC_RE = re.compile(r'<img[^>]+src=["\\\']([^"\\\']+)["\\\']', re.IGNORECASE)
_VIDEO_RE = re.compile(
    r"<video\b|youtube\.com|youtu\.be|bilibili\.com|vimeo\.com|youku\.com|tudou\.com|qq\.com/x/page",
    re.IGNORECASE,
)
_AUDIO_RE = re.compile(
    r"<audio\b|music\.163\.com|spotify\.com|soundcloud\.com|music\.qq\.com|ximalaya\.com",
    re.IGNORECASE,
)
_EXTERNAL_LINK_RE = re.compile(r'href=["\\\'](https?://[^"\\\']+)["\\\']', re.IGNORECASE)


def _uniq_keep_order(items: Iterable[str]) -> List[str]:
    seen: MutableMapping[str, bool] = OrderedDict()
    for item in items:
        key = (item or "").strip()
        if not key:
            continue
        if key in seen:
            continue
        seen[key] = True
    return list(seen.keys())


def extract_image_urls(content_html: Optional[str], featured_image_url: Optional[str] = None, max_count: int = 40) -> List[str]:
    html = (content_html or "").strip()
    if not html:
        return []

    featured = (featured_image_url or "").strip()
    urls: List[str] = []
    for match in _IMAGE_SRC_RE.finditer(html):
        src = (match.group(1) or "").strip()
        if not src:
            continue
        if featured and src == featured:
            continue
        urls.append(src)
        if len(urls) >= max_count:
            break
    return _uniq_keep_order(urls)


def extract_external_links(content_html: Optional[str], max_count: int = 20) -> List[str]:
    html = (content_html or "").strip()
    if not html:
        return []
    links = [(m.group(1) or "").strip() for m in _EXTERNAL_LINK_RE.finditer(html)]
    unique_links = _uniq_keep_order(links)
    return unique_links[:max_count]


def summarize_media_attachments(
    content_html: Optional[str],
    *,
    featured_image_url: Optional[str] = None,
    gallery_threshold: int = DEFAULT_GALLERY_THRESHOLD,
) -> MediaAttachmentSummary:
    html = (content_html or "").strip()
    image_urls = extract_image_urls(html, featured_image_url=featured_image_url)
    image_count = len(image_urls) + (1 if (featured_image_url or "").strip() else 0)
    external_links = extract_external_links(html)

    has_images = image_count > 0
    has_gallery = image_count >= max(2, int(gallery_threshold))
    has_videos = bool(_VIDEO_RE.search(html))
    has_audio = bool(_AUDIO_RE.search(html))
    has_link = len(external_links) > 0

    return MediaAttachmentSummary(
        has_images=has_images,
        has_gallery=has_gallery,
        has_videos=has_videos,
        has_link=has_link,
        has_audio=has_audio,
        image_count=image_count,
        image_urls=image_urls,
        external_links=external_links,
    )


_detectors: "OrderedDict[str, AttachmentDetector]" = OrderedDict()


def register_media_attachment_detector(media_key: str, detector: AttachmentDetector) -> None:
    """
    注册或替换媒体检测器。

    后续二开可调用该函数扩展新的媒体附件类型。
    """
    key = (media_key or "").strip().lower()
    if not key:
        raise ValueError("media_key 不能为空")
    if not callable(detector):
        raise ValueError("detector 必须可调用")
    _detectors[key] = detector


def unregister_media_attachment_detector(media_key: str) -> None:
    key = (media_key or "").strip().lower()
    _detectors.pop(key, None)


def list_registered_media_attachment_keys() -> List[str]:
    return list(_detectors.keys())


def detect_media_flags(summary: MediaAttachmentSummary) -> Dict[str, bool]:
    flags: Dict[str, bool] = {}
    for key, detector in _detectors.items():
        try:
            flags[key] = bool(detector(summary))
        except Exception:
            flags[key] = False
    return flags


def get_default_media_navigation() -> List[Dict[str, str]]:
    return [
        {"key": "images", "name": "图片", "icon": "fa-image"},
        {"key": "gallery", "name": "相册", "icon": "fa-images"},
        {"key": "videos", "name": "视频", "icon": "fa-circle-play"},
        {"key": "link", "name": "外链", "icon": "fa-link"},
        {"key": "audio", "name": "音频", "icon": "fa-music"},
    ]


# 默认检测器注册（可被后续自定义覆盖）
register_media_attachment_detector("images", lambda s: s.has_images)
register_media_attachment_detector("gallery", lambda s: s.has_gallery)
register_media_attachment_detector("videos", lambda s: s.has_videos)
register_media_attachment_detector("link", lambda s: s.has_link)
register_media_attachment_detector("audio", lambda s: s.has_audio)

