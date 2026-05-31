"""
公开资料解析器

为前台模板提供统一的公开资料数据结构，便于未来扩展到多用户博客系统。
当前实现为默认单站长策略，后续可替换为多作者策略而无需改模板。
"""

from typing import Any, Dict, Optional, Protocol

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..models import User as UserModel
from .avatar import get_avatar_service
from .public_alias import resolve_public_display_name
from .template_context import DEFAULT_BASE_SETTINGS, DEFAULT_HOMEPAGE_SETTINGS
from .url_normalizer import normalize_local_asset_url, normalize_local_asset_url_lines


def _get_setting_value(db: Session, key: str, default: Any = None) -> Any:
    setting = crud_setting.get_setting(db, key=key)
    if setting and isinstance(setting.value, dict) and "value" in setting.value:
        return setting.value["value"]
    return default


def _parse_gallery_images(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    return [
        line.strip()
        for line in str(raw_value).splitlines()
        if line and line.strip()
    ]


class PublicProfileResolver(Protocol):
    def resolve_homepage_profile(self, request: Request, db: Session) -> Dict[str, Any]:
        ...

    def resolve_format_profile(self, request: Request, db: Session, format_slug: str) -> Dict[str, Any]:
        ...

    def resolve_author_profile(self, db: Session, user_id: Optional[int], fallback_name: str = "博主") -> Dict[str, str]:
        ...


class DefaultPublicProfileResolver:
    """默认实现：站点页用站点配置，格式页用个人资料配置。"""

    @staticmethod
    def _resolve_primary_user(db: Session) -> Optional[UserModel]:
        admin_email = str(_get_setting_value(db, "admin_email", "") or "").strip().lower()
        if admin_email:
            owner = crud_user.get_user_by_email(db, admin_email)
            if owner is not None:
                return owner
        return db.execute(
            select(UserModel).order_by(UserModel.id.asc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _resolve_site_cover_url(db: Session) -> str:
        explicit_cover = normalize_local_asset_url(_get_setting_value(db, "site_cover_url", ""))
        if explicit_cover:
            return explicit_cover
        homepage_mode = str(
            _get_setting_value(db, "homepage_mode", DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"])
            or DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]
        ).strip()
        gallery_images = _parse_gallery_images(
            normalize_local_asset_url_lines(_get_setting_value(db, "homepage_background_image_url", ""))
        )
        if gallery_images:
            return gallery_images[0]
        if homepage_mode == "fullscreen_video":
            return "/static/images/covers/home-video.jpg"
        return "/static/images/covers/home-default.jpg"

    @staticmethod
    def _resolve_site_avatar_url(db: Session) -> str:
        candidates = [
            normalize_local_asset_url(_get_setting_value(db, "site_logo_light", "")),
            normalize_local_asset_url(_get_setting_value(db, "site_logo_dark", "")),
            normalize_local_asset_url(_get_setting_value(db, "favicon", "")),
        ]
        for value in candidates:
            if value:
                return value
        return "/static/images/default-avatar.png"

    def resolve_homepage_profile(self, request: Request, db: Session) -> Dict[str, Any]:
        site_title = str(getattr(request.state, "site_title", DEFAULT_BASE_SETTINGS["site_title"]) or DEFAULT_BASE_SETTINGS["site_title"])
        tagline = str(getattr(request.state, "tagline", DEFAULT_BASE_SETTINGS["tagline"]) or DEFAULT_BASE_SETTINGS["tagline"])
        site_url = str(_get_setting_value(db, "site_url", str(request.base_url)) or str(request.base_url)).strip()

        return {
            "display_name": site_title,
            "username": "",
            "bio": tagline,
            "website": site_url,
            "public_email": str(_get_setting_value(db, "public_contact_email", "") or "").strip(),
            "avatar_url": self._resolve_site_avatar_url(db),
            "cover_url": self._resolve_site_cover_url(db),
            "homepage_mode": str(_get_setting_value(db, "homepage_mode", DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]) or DEFAULT_HOMEPAGE_SETTINGS["homepage_mode"]).strip(),
            "logo_light": normalize_local_asset_url(_get_setting_value(db, "site_logo_light", "")),
            "logo_dark": normalize_local_asset_url(_get_setting_value(db, "site_logo_dark", "")),
            "favicon": normalize_local_asset_url(_get_setting_value(db, "favicon", "")),
        }

    def resolve_format_profile(self, request: Request, db: Session, format_slug: str) -> Dict[str, Any]:
        owner = self._resolve_primary_user(db)
        avatar_service = get_avatar_service(db)

        site_title = str(getattr(request.state, "site_title", DEFAULT_BASE_SETTINGS["site_title"]) or DEFAULT_BASE_SETTINGS["site_title"])
        tagline = str(getattr(request.state, "tagline", DEFAULT_BASE_SETTINGS["tagline"]) or DEFAULT_BASE_SETTINGS["tagline"])
        site_url = str(_get_setting_value(db, "site_url", str(request.base_url)) or str(request.base_url)).strip()

        display_name = site_title
        username = ""
        bio_default = tagline
        website = site_url
        avatar_url = "/static/images/default-avatar.png"
        joined_text = ""

        if owner is not None:
            display_name = resolve_public_display_name(
                getattr(owner, "display_name", None),
                seed_value=getattr(owner, "id", None),
                fallback=site_title,
            )
            username = ""
            bio_default = str(getattr(owner, "bio", "") or "").strip() or tagline
            website = str(getattr(owner, "website", "") or "").strip() or site_url
            owner_email = str(getattr(owner, "email", "") or "").strip()
            avatar_url = avatar_service.get_avatar_url(owner_email, getattr(owner, "id", None), size=128)
            if getattr(owner, "created_at", None):
                joined_text = owner.created_at.strftime("%Y-%m")

        normalized_slug = str(format_slug or "article").strip().lower()
        format_cover_map = {
            "article": "creator_profile_cover_url",
            "micro": "creator_profile_micro_cover_url",
            "poem": "creator_profile_poem_cover_url",
        }
        format_cover_fallback_map = {
            "article": "/static/images/covers/format-article.jpg",
            "micro": "/static/images/covers/format-micro.jpg",
            "poem": "/static/images/covers/format-poem.jpg",
        }
        format_bio_map = {
            "article": "creator_profile_article_bio",
            "micro": "creator_profile_micro_bio",
            "poem": "creator_profile_poem_bio",
        }
        selected_cover_key = format_cover_map.get(normalized_slug, "creator_profile_cover_url")
        selected_bio_key = format_bio_map.get(normalized_slug, "creator_profile_article_bio")
        selected_cover_fallback = format_cover_fallback_map.get(
            normalized_slug,
            "/static/images/covers/format-article.jpg",
        )

        selected_cover = normalize_local_asset_url(_get_setting_value(db, selected_cover_key, ""))
        cover_url = selected_cover or selected_cover_fallback

        selected_bio = str(_get_setting_value(db, selected_bio_key, "") or "").strip()

        return {
            "display_name": display_name,
            "username": username,
            "bio": selected_bio or bio_default,
            "website": website,
            "public_email": str(_get_setting_value(db, "public_contact_email", "") or "").strip(),
            "avatar_url": avatar_url or "/static/images/default-avatar.png",
            "cover_url": cover_url,
            "headline": str(_get_setting_value(db, "creator_profile_headline", "") or "").strip(),
            "motto": str(_get_setting_value(db, "creator_profile_motto", "") or "").strip(),
            "location": str(_get_setting_value(db, "creator_profile_location", "") or "").strip(),
            "joined_text": joined_text,
            "format_slug": normalized_slug,
        }

    def resolve_author_profile(self, db: Session, user_id: Optional[int], fallback_name: str = "博主") -> Dict[str, str]:
        avatar_service = get_avatar_service(db)
        fallback_display_name = str(fallback_name or "博主").strip() or "博主"
        if not user_id:
            return {"display_name": fallback_display_name, "avatar_url": "/static/images/default-avatar.png"}

        user_obj = crud_user.get_user(db, int(user_id))
        if user_obj is None:
            return {"display_name": fallback_display_name, "avatar_url": "/static/images/default-avatar.png"}

        display_name = resolve_public_display_name(
            getattr(user_obj, "display_name", None),
            seed_value=getattr(user_obj, "id", None),
            fallback=fallback_display_name,
        )
        user_email = str(getattr(user_obj, "email", "") or "")
        avatar_url = avatar_service.get_avatar_url(user_email, getattr(user_obj, "id", None), size=96)
        return {
            "display_name": display_name,
            "avatar_url": avatar_url or "/static/images/default-avatar.png",
        }


_resolver_instance: Optional[PublicProfileResolver] = None


def get_public_profile_resolver() -> PublicProfileResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = DefaultPublicProfileResolver()
    return _resolver_instance


def set_public_profile_resolver(resolver: PublicProfileResolver) -> None:
    """
    注入自定义公开资料解析器。

    方便后续扩展到多用户博客场景时，替换默认单站长策略而无需改动业务路由。
    """
    global _resolver_instance
    _resolver_instance = resolver
