from __future__ import annotations

import json
from math import ceil
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Form, Header, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload, selectinload

from ..core.avatar import get_avatar_service
from ..core.admin_path import get_admin_path
from ..core.config import settings
from ..core.database import get_db
from ..core.security import get_current_user
from ..models import Category, Comment, Post, Tag
from ..models.post import post_categories, post_tags
from ..crud import category as crud_category
from ..crud import format as crud_format
from ..crud import post as crud_post
from ..schemas import User
from . import (
    admin_dashboard as admin_dashboard_api,
    api_keys as api_keys_api,
    auth as auth_api,
    categories as categories_api,
    comment_settings as comment_settings_api,
    data_import_export as data_api,
    error_config as error_config_api,
    media as media_api,
    media_settings as media_settings_api,
    settings as settings_api,
    system_info as system_info_api,
    security_center as security_center_api,
    tags as tags_api,
    themes as themes_api,
    users as users_api,
)


def register_admin_primary_routes(
    app: FastAPI,
    *,
    templates,
    default_base_settings: dict,
    default_homepage_settings: dict,
    article_api_cache_enabled_default: bool,
    article_api_cache_ttl_minutes_default: int,
    article_api_cache_cleanup_minutes_default: int,
) -> None:
    """
    注册第一批后台动态路由。

    本模块只承接“薄包装 / 纯转发”为主的后台动态路由，保持行为不变，
    先把 main.py 中最容易稳定迁出的部分独立出来。
    """
    admin_path = get_admin_path()

    @app.get(f"{admin_path}", response_class=HTMLResponse)
    async def dynamic_admin_root_entry(
        request: Request,
        db: Session = Depends(get_db),
    ):
        token = (request.cookies.get("access_token") or "").strip()
        if token:
            try:
                await get_current_user(token=token, db=db)
                return RedirectResponse(url=f"{admin_path}/dashboard", status_code=303)
            except Exception:
                pass
        return RedirectResponse(url=f"{admin_path}/login", status_code=303)

    @app.get(f"{admin_path}/login", response_class=HTMLResponse)
    async def dynamic_admin_login_page(request: Request):
        return templates.TemplateResponse("admin/login.html", {"request": request, "admin_path": admin_path})

    @app.post(f"{admin_path}/auth")
    async def dynamic_admin_login(
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db),
    ):
        return await auth_api.login_for_access_token_impl(
            response,
            form_data,
            db,
            request,
            background_tasks,
        )

    @app.get(f"{admin_path}/forgot-password", response_class=HTMLResponse)
    async def dynamic_admin_forgot_password_page(request: Request):
        return auth_api.forgot_password_page(request)

    @app.post(f"{admin_path}/forgot-password", response_class=HTMLResponse)
    async def dynamic_admin_forgot_password_submit(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        identifier: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return auth_api.submit_forgot_password(
            request,
            db,
            identifier=identifier,
            csrf_token=csrf_token,
            background_tasks=background_tasks,
        )

    @app.get(f"{admin_path}/reset-password", response_class=HTMLResponse, name="dynamic_admin_reset_password_page")
    async def dynamic_admin_reset_password_page(
        request: Request,
        token: str,
        db: Session = Depends(get_db),
    ):
        return auth_api.reset_password_page(request, db, token=token)

    @app.post(f"{admin_path}/reset-password")
    async def dynamic_admin_reset_password_submit(
        request: Request,
        db: Session = Depends(get_db),
        token: str = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return auth_api.submit_reset_password(
            request,
            db,
            token=token,
            password=password,
            password_confirm=password_confirm,
            csrf_token=csrf_token,
        )

    @app.get(f"{admin_path}/dashboard", response_class=HTMLResponse)
    async def dynamic_admin_dashboard_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await admin_dashboard_api.dashboard_page(request, db, current_user)

    @app.get(f"{admin_path}/settings", response_class=HTMLResponse)
    async def dynamic_admin_settings_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await settings_api.admin_settings_page(request, db, current_user)

    @app.post(f"{admin_path}/settings", response_class=HTMLResponse)
    async def dynamic_update_admin_settings(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await settings_api.update_admin_settings(request, db, current_user)

    @app.get(f"{admin_path}/users", response_class=HTMLResponse)
    async def dynamic_admin_users_page(
        request: Request,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await users_api.admin_users_page(request, db, current_user)

    @app.post(f"{admin_path}/users", response_class=HTMLResponse)
    async def dynamic_update_admin_user_profile(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        username: str = Form(...),
        email: str = Form(...),
        display_name: Optional[str] = Form(None),
        bio: Optional[str] = Form(None),
        website: Optional[str] = Form(None),
        use_gravatar: str = Form("auto"),
        creator_profile_cover_url: Optional[str] = Form(None),
        creator_profile_micro_cover_url: Optional[str] = Form(None),
        creator_profile_poem_cover_url: Optional[str] = Form(None),
        creator_profile_headline: Optional[str] = Form(None),
        creator_profile_article_bio: Optional[str] = Form(None),
        creator_profile_micro_bio: Optional[str] = Form(None),
        creator_profile_poem_bio: Optional[str] = Form(None),
        creator_profile_location: Optional[str] = Form(None),
        creator_profile_motto: Optional[str] = Form(None),
        csrf_token: str = Form(...),
    ):
        return await users_api.update_admin_user_profile(
            request=request,
            db=db,
            current_user=current_user,
            username=username,
            email=email,
            display_name=display_name,
            bio=bio,
            website=website,
            use_gravatar=use_gravatar,
            creator_profile_cover_url=creator_profile_cover_url,
            creator_profile_micro_cover_url=creator_profile_micro_cover_url,
            creator_profile_poem_cover_url=creator_profile_poem_cover_url,
            creator_profile_headline=creator_profile_headline,
            creator_profile_article_bio=creator_profile_article_bio,
            creator_profile_micro_bio=creator_profile_micro_bio,
            creator_profile_poem_bio=creator_profile_poem_bio,
            creator_profile_location=creator_profile_location,
            creator_profile_motto=creator_profile_motto,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/users")
    async def dynamic_create_admin_user(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        username: str = Form(...),
        email: str = Form(...),
        password: str = Form(...),
        role: str = Form("admin"),
        display_name: Optional[str] = Form(None),
        csrf_token: str = Form(...),
    ):
        return await users_api.create_admin_user_action(
            request=request,
            db=db,
            current_user=current_user,
            username=username,
            email=email,
            password=password,
            role=role,
            display_name=display_name,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/users/{{user_id}}/status")
    async def dynamic_update_user_status(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        is_active: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return await users_api.update_user_status_action(
            request=request,
            db=db,
            current_user=current_user,
            user_id=user_id,
            is_active_value=is_active,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/users/{{user_id}}/role")
    async def dynamic_update_user_role(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        role: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return await users_api.update_user_role_action(
            request=request,
            db=db,
            current_user=current_user,
            user_id=user_id,
            role_value=role,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/users/{{user_id}}/password")
    async def dynamic_reset_user_password(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        password: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return await users_api.reset_user_password_action(
            request=request,
            db=db,
            current_user=current_user,
            user_id=user_id,
            password=password,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/users/{{user_id}}/force-logout")
    async def dynamic_force_logout_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Form(...),
    ):
        return await users_api.force_logout_user_action(
            request=request,
            db=db,
            current_user=current_user,
            user_id=user_id,
            csrf_token=csrf_token,
        )

    @app.get(f"{admin_path}/api-keys", response_class=HTMLResponse)
    async def dynamic_admin_api_keys_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await api_keys_api.admin_api_keys_page(request, db, current_user)

    @app.post(f"{admin_path}/api/v1/api-keys")
    async def dynamic_create_api_key(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        name: str = Form(...),
        access_level: str = Form("read_only"),
        notes: Optional[str] = Form(None),
        expires_at: Optional[str] = Form(None),
        csrf_token: str = Form(...),
    ):
        return await api_keys_api.create_api_key_action(
            request=request,
            db=db,
            current_user=current_user,
            name=name,
            access_level=access_level,
            notes=notes,
            expires_at_text=expires_at,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/api-keys/{{api_key_id}}/status")
    async def dynamic_update_api_key_status(
        api_key_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        status: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return await api_keys_api.update_api_key_status_action(
            request=request,
            db=db,
            current_user=current_user,
            api_key_id=api_key_id,
            status_value=status,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/api-keys/{{api_key_id}}/rotate")
    async def dynamic_rotate_api_key(
        api_key_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        expires_at: Optional[str] = Form(None),
        csrf_token: str = Form(...),
    ):
        return await api_keys_api.rotate_api_key_action(
            request=request,
            db=db,
            current_user=current_user,
            api_key_id=api_key_id,
            expires_at_text=expires_at,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/api-keys/{{api_key_id}}/delete")
    async def dynamic_delete_api_key(
        api_key_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Form(...),
    ):
        return await api_keys_api.delete_api_key_action(
            request=request,
            db=db,
            current_user=current_user,
            api_key_id=api_key_id,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/update-admin-path")
    @app.post(f"{admin_path}/api/update-admin-path")
    async def dynamic_update_admin_path(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await settings_api.update_admin_path(request, db, current_user)

    @app.post(f"{admin_path}/api/v1/effects/public-holidays/save")
    async def dynamic_save_public_holidays(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Header(..., alias="X-CSRF-Token"),
    ):
        return await themes_api.save_public_holiday_settings(
            request=request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/effects/public-holidays/rebuild")
    async def dynamic_rebuild_public_holidays(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Header(..., alias="X-CSRF-Token"),
    ):
        return await themes_api.rebuild_public_holiday_settings(
            request=request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/effects/custom-anniversaries/save")
    async def dynamic_save_custom_anniversaries(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Header(..., alias="X-CSRF-Token"),
    ):
        return await themes_api.save_custom_anniversary_settings(
            request=request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/api/v1/admin/themes/background")
    async def dynamic_update_background_image(
        request: Request,
        background_type: str = Form(...),
        custom_background_url: Optional[str] = Form(None),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await themes_api.update_background_image(
            request=request,
            db=db,
            current_user=current_user,
            background_type=background_type,
            custom_background_url=custom_background_url,
            csrf_token=csrf_token,
        )

    @app.get(f"{admin_path}/media", response_class=HTMLResponse)
    async def dynamic_admin_media_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await media_api.media_library_page(request, db, current_user)

    @app.get(f"{admin_path}/media/settings", response_class=HTMLResponse)
    async def dynamic_admin_media_settings_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await media_settings_api.media_settings_page(request, db, current_user)

    @app.get(f"{admin_path}/themes", response_class=HTMLResponse)
    async def dynamic_admin_themes_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await themes_api.admin_theme_system_page(request, db, current_user)

    @app.get(f"{admin_path}/effects", response_class=HTMLResponse)
    async def dynamic_admin_effects_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await themes_api.admin_effects_page(request, db, current_user)

    @app.post(f"{admin_path}/themes/update")
    async def dynamic_update_theme(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        form_data = await request.form()
        return await themes_api.update_theme_settings(
            request=request,
            db=db,
            current_user=current_user,
            current_theme=form_data.get("current_theme", "light"),
            glass_intensity=form_data.get("glass_intensity", "medium"),
            csrf_token=form_data.get("csrf_token", ""),
        )

    @app.post(f"{admin_path}/effects/update")
    async def dynamic_update_effects(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        form_data = await request.form()
        return await themes_api.update_effects_settings(
            request=request,
            db=db,
            current_user=current_user,
            effects_schedule_enabled=bool(form_data.get("effects_schedule_enabled")),
            csrf_token=form_data.get("csrf_token", ""),
        )

    @app.post(f"{admin_path}/themes/custom")
    async def dynamic_create_custom_theme(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        form_data = await request.form()
        return await themes_api.create_custom_theme(
            request=request,
            db=db,
            current_user=current_user,
            theme_name=form_data.get("theme_name", ""),
            theme_data=form_data.get("theme_data", ""),
            csrf_token=form_data.get("csrf_token", ""),
        )

    @app.delete(f"{admin_path}/themes/custom/{{theme_name}}")
    async def dynamic_delete_custom_theme(
        theme_name: str,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        csrf_token: str = Header(..., alias="X-CSRF-Token"),
    ):
        return await themes_api.delete_custom_theme(theme_name, request, db, current_user, csrf_token)

    @app.post(f"{admin_path}/themes/schedule")
    async def dynamic_schedule_themes(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        form_data = await request.form()
        themes_api.verify_csrf_token(request, form_data.get("csrf_token", ""))
        themes_api.ensure_admin_user(current_user)
        schedule_data = form_data.get("schedule_data", "")
        try:
            parsed_schedule = json.loads(schedule_data) if schedule_data else {"schedules": []}
        except json.JSONDecodeError:
            return JSONResponse({"success": False, "message": "调度配置格式错误"}, status_code=400)

        schedules = parsed_schedule if isinstance(parsed_schedule, list) else parsed_schedule.get("schedules", [])
        normalized_schedules = []
        for item in schedules:
            if not isinstance(item, dict):
                continue
            scene = themes_api.normalize_effect_scene_name(item.get("scene") or item.get("atmosphere"))
            start_date = item.get("start_date") or item.get("start_at")
            end_date = item.get("end_date") or item.get("end_at")
            if not start_date or not end_date or not scene:
                continue
            normalized_schedules.append(
                {
                    "name": str(item.get("name") or themes_api.get_effect_scene_label(scene)).strip() or "特效调度规则",
                    "start_at": start_date,
                    "end_at": end_date,
                    "start_date": start_date,
                    "end_date": end_date,
                    "scene": scene,
                    "effects": themes_api.get_scene_effects(scene, item.get("effects")),
                    "enabled": bool(item.get("enabled", True)),
                    "priority": int(item.get("priority") or 1000),
                }
            )

        themes_api.effects_engine.save_schedule_rules(db, normalized_schedules)
        return JSONResponse({"success": True, "message": "节日特效调度已更新"})

    @app.get(f"{admin_path}/posts", response_class=HTMLResponse)
    async def dynamic_admin_posts_list_page(
        request: Request,
        search: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        category: Optional[str] = None,
        format: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        search = (search or "").strip() or None
        status = (status or "").strip() or None
        visibility = (visibility or "").strip() or None
        category = (category or "").strip() or None
        format = (format or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [10, 20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        base_conditions = list(crud_post.get_public_post_conditions(published_only=False))
        filter_conditions = list(base_conditions)

        if status:
            filter_conditions.append(Post.status == status)
        if visibility in {"public", "private", "password"}:
            filter_conditions.append(Post.visibility == visibility)

        category_id: Optional[int] = None
        if category:
            try:
                category_id = int(category)
            except ValueError:
                category_id = None
            if category_id is not None:
                filter_conditions.append(Post.categories.any(id=category_id))

        format_id: Optional[int] = None
        if format:
            try:
                format_id = int(format)
            except ValueError:
                format_id = None
            if format_id is not None:
                filter_conditions.append(Post.formats.any(id=format_id))

        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Post.title.ilike(like),
                    Post.excerpt.ilike(like),
                    Post.content_markdown.ilike(like),
                    Post.content_html.ilike(like),
                )
            )

        total_articles = db.execute(
            select(func.count(Post.id)).where(*base_conditions)
        ).scalar_one()
        filtered_total = db.execute(
            select(func.count(Post.id)).where(*filter_conditions)
        ).scalar_one()

        total_pages = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * resolved_page_size
        posts = db.execute(
            select(Post)
            .options(joinedload(Post.categories), joinedload(Post.tags), joinedload(Post.formats))
            .where(*filter_conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(resolved_page_size)
        ).unique().scalars().all()

        try:
            crud_post._attach_views_metrics(db, posts)
        except Exception:
            for post in posts:
                setattr(post, "views", 0)
                setattr(post, "views_count", 0)

        comment_count_map = {}
        post_ids = [post.id for post in posts]
        if post_ids:
            comment_rows = db.execute(
                select(Comment.post_id, func.count(Comment.id))
                .where(Comment.post_id.in_(post_ids))
                .group_by(Comment.post_id)
            ).all()
            comment_count_map = {post_id: count for post_id, count in comment_rows}
        for post in posts:
            setattr(post, "comment_count", int(comment_count_map.get(post.id, 0)))

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if status:
                params["status"] = status
            if visibility:
                params["visibility"] = visibility
            if category_id is not None:
                params["category"] = str(category_id)
            if format_id is not None:
                params["format"] = str(format_id)
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_pages, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_pages,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_pages else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        categories = crud_category.get_categories(db)
        formats = [
            item for item in crud_format.get_formats(db)
            if getattr(item, "slug", None) in {"article", "micro", "poem"}
        ]

        return templates.TemplateResponse("admin/posts_list.html", {
            "request": request,
            "posts": posts,
            "categories": categories,
            "formats": formats,
            "search_query": search or "",
            "selected_status": status or "",
            "selected_visibility": visibility or "",
            "selected_category": str(category_id) if category_id is not None else "",
            "selected_format": str(format_id) if format_id is not None else "",
            "pagination": pagination,
            "total_articles": total_articles,
            "user": current_user,
            "admin_path": admin_path,
        })

    @app.get(f"{admin_path}/api/v1/categories/options")
    async def dynamic_get_category_options(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        categories = crud_category.get_categories(db)
        options_html = '<option value="">全部分类</option>'
        for category in categories:
            options_html += f'<option value="{category.id}">{category.name}</option>'
        return HTMLResponse(content=options_html)

    @app.get(f"{admin_path}/categories", response_class=HTMLResponse)
    async def dynamic_admin_categories_page(
        request: Request,
        search: Optional[str] = None,
        usage: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        search = (search or "").strip() or None
        usage = (usage or "").strip().lower() or None
        if usage not in {"used", "unused"}:
            usage = None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Category.name.ilike(like),
                    Category.slug.ilike(like),
                    Category.description.ilike(like),
                )
            )
        if usage == "used":
            filter_conditions.append(Category.posts.any())
        elif usage == "unused":
            filter_conditions.append(~Category.posts.any())

        total_categories = db.execute(select(func.count(Category.id))).scalar_one()
        used_categories = db.execute(
            select(func.count(Category.id)).where(Category.posts.any())
        ).scalar_one()
        unused_categories = max(0, total_categories - used_categories)
        total_post_bindings = db.execute(
            select(func.count()).select_from(post_categories)
        ).scalar_one()

        filtered_total_query = select(func.count(Category.id))
        if filter_conditions:
            filtered_total_query = filtered_total_query.where(*filter_conditions)
        filtered_total = db.execute(filtered_total_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        categories_query = select(Category).options(selectinload(Category.posts))
        if filter_conditions:
            categories_query = categories_query.where(*filter_conditions)
        categories = db.execute(
            categories_query
            .order_by(Category.name.asc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        for category in categories:
            setattr(category, "post_count", len(category.posts) if category.posts else 0)

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if usage:
                params["usage"] = usage
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/categories_list.html", {
            "request": request,
            "categories": categories,
            "search_query": search or "",
            "selected_usage": usage or "",
            "pagination": pagination,
            "stats": {
                "total": total_categories,
                "used": used_categories,
                "unused": unused_categories,
                "post_bindings": total_post_bindings,
            },
            "user": current_user,
            "admin_path": admin_path,
        })

    @app.get(f"{admin_path}/tags", response_class=HTMLResponse)
    async def dynamic_admin_tags_page(
        request: Request,
        search: Optional[str] = None,
        usage: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        search = (search or "").strip() or None
        usage = (usage or "").strip().lower() or None
        if usage not in {"used", "unused"}:
            usage = None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Tag.name.ilike(like),
                    Tag.slug.ilike(like),
                )
            )
        if usage == "used":
            filter_conditions.append(Tag.posts.any())
        elif usage == "unused":
            filter_conditions.append(~Tag.posts.any())

        total_tags = db.execute(select(func.count(Tag.id))).scalar_one()
        used_tags = db.execute(
            select(func.count(Tag.id)).where(Tag.posts.any())
        ).scalar_one()
        unused_tags = max(0, total_tags - used_tags)
        total_post_bindings = db.execute(
            select(func.count()).select_from(post_tags)
        ).scalar_one()

        filtered_total_query = select(func.count(Tag.id))
        if filter_conditions:
            filtered_total_query = filtered_total_query.where(*filter_conditions)
        filtered_total = db.execute(filtered_total_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        tags_query = select(Tag).options(selectinload(Tag.posts))
        if filter_conditions:
            tags_query = tags_query.where(*filter_conditions)
        tags = db.execute(
            tags_query
            .order_by(Tag.name.asc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        for tag in tags:
            setattr(tag, "post_count", len(tag.posts) if tag.posts else 0)

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if usage:
                params["usage"] = usage
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/tags_list.html", {
            "request": request,
            "tags": tags,
            "search_query": search or "",
            "selected_usage": usage or "",
            "pagination": pagination,
            "stats": {
                "total": total_tags,
                "used": used_tags,
                "unused": unused_tags,
                "post_bindings": total_post_bindings,
            },
            "user": current_user,
            "admin_path": admin_path,
        })

    @app.get(f"{admin_path}/comments", response_class=HTMLResponse)
    async def dynamic_admin_comments_page(
        request: Request,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        status = (status or "").strip() or None
        search = (search or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        filter_conditions = []
        if status:
            filter_conditions.append(Comment.status == status)
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Comment.author_name.ilike(like),
                    Comment.author_email.ilike(like),
                    Comment.content.ilike(like),
                    Post.title.ilike(like),
                    Comment.ip_address.ilike(like),
                    Comment.user_agent.ilike(like),
                )
            )

        total_comments = db.execute(select(func.count(Comment.id))).scalar_one()
        pending_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "pending")
        ).scalar_one()
        approved_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "approved")
        ).scalar_one()
        spam_count = db.execute(
            select(func.count(Comment.id)).where(Comment.status == "spam")
        ).scalar_one()

        count_query = select(func.count(Comment.id)).outerjoin(Post, Post.id == Comment.post_id)
        if filter_conditions:
            count_query = count_query.where(*filter_conditions)
        filtered_total = db.execute(count_query).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count
        offset = (page - 1) * resolved_page_size

        comments_query = (
            select(Comment)
            .outerjoin(Post, Post.id == Comment.post_id)
            .options(
                joinedload(Comment.post),
                joinedload(Comment.parent),
            )
        )
        if filter_conditions:
            comments_query = comments_query.where(*filter_conditions)
        comments = db.execute(
            comments_query.order_by(Comment.created_at.desc()).offset(offset).limit(resolved_page_size)
        ).scalars().all()

        avatar_service = get_avatar_service(db)
        comments_with_avatars = []
        for comment in comments:
            avatar_url = avatar_service.get_comment_avatar_url(
                author_email=comment.author_email,
                author_id=None,
                size=40,
            )
            comments_with_avatars.append({
                "comment": comment,
                "avatar_url": avatar_url,
            })

        def _build_page_url(target_page: int) -> str:
            params = {}
            if status:
                params["status"] = status
            if search:
                params["search"] = search
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/comments_list.html", {
            "request": request,
            "comments_with_avatars": comments_with_avatars,
            "user": current_user,
            "admin_path": admin_path,
            "current_status": status,
            "search_query": search or "",
            "pagination": pagination,
            "total_comments": total_comments,
            "status_counts": {
                "pending": pending_count,
                "approved": approved_count,
                "spam": spam_count,
            },
        })

    @app.get(f"{admin_path}/pages", response_class=HTMLResponse)
    async def dynamic_admin_pages_page(
        request: Request,
        search: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        search = (search or "").strip() or None
        status = (status or "").strip() or None
        visibility = (visibility or "").strip() or None

        page = max(1, int(page or 1))
        allowed_page_sizes = [10, 20, 50, 100]
        try:
            resolved_page_size = int(page_size) if page_size is not None else 20
        except (TypeError, ValueError):
            resolved_page_size = 20
        if resolved_page_size not in allowed_page_sizes:
            resolved_page_size = 20

        base_conditions = [Post.post_type == "page"]
        filter_conditions = list(base_conditions)
        if status:
            filter_conditions.append(Post.status == status)
        if visibility:
            filter_conditions.append(Post.visibility == visibility)
        if search:
            like = f"%{search}%"
            filter_conditions.append(
                or_(
                    Post.title.ilike(like),
                    Post.excerpt.ilike(like),
                    Post.content_markdown.ilike(like),
                    Post.content_html.ilike(like),
                    Post.slug.ilike(like),
                )
            )

        total_pages_count = db.execute(
            select(func.count(Post.id)).where(*base_conditions)
        ).scalar_one()
        filtered_total = db.execute(
            select(func.count(Post.id)).where(*filter_conditions)
        ).scalar_one()

        total_page_count = max(1, ceil(filtered_total / resolved_page_size)) if filtered_total else 1
        if page > total_page_count:
            page = total_page_count

        offset = (page - 1) * resolved_page_size
        pages = db.execute(
            select(Post)
            .where(*filter_conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(resolved_page_size)
        ).scalars().all()

        try:
            crud_post._attach_views_metrics(db, pages)
        except Exception:
            for item in pages:
                setattr(item, "views", 0)
                setattr(item, "views_count", 0)

        page_ids = [item.id for item in pages]
        comment_count_map = {}
        if page_ids:
            comment_rows = db.execute(
                select(Comment.post_id, func.count(Comment.id))
                .where(Comment.post_id.in_(page_ids))
                .group_by(Comment.post_id)
            ).all()
            comment_count_map = {post_id: count for post_id, count in comment_rows}
        for item in pages:
            setattr(item, "comment_count", int(comment_count_map.get(item.id, 0)))

        def _build_page_url(target_page: int) -> str:
            params = {}
            if search:
                params["search"] = search
            if status:
                params["status"] = status
            if visibility:
                params["visibility"] = visibility
            params["page"] = str(target_page)
            params["page_size"] = str(resolved_page_size)
            return str(request.url.replace_query_params(**params))

        page_window_start = max(1, page - 2)
        page_window_end = min(total_page_count, page_window_start + 4)
        page_window_start = max(1, page_window_end - 4)
        page_numbers = list(range(page_window_start, page_window_end + 1))

        pagination = {
            "current_page": page,
            "page_size": resolved_page_size,
            "allowed_page_sizes": allowed_page_sizes,
            "total_pages": total_page_count,
            "filtered_total": filtered_total,
            "has_prev": page > 1,
            "has_next": page < total_page_count,
            "prev_url": _build_page_url(page - 1) if page > 1 else None,
            "next_url": _build_page_url(page + 1) if page < total_page_count else None,
            "page_links": [{"page": p, "url": _build_page_url(p), "is_current": p == page} for p in page_numbers],
        }

        return templates.TemplateResponse("admin/pages_list.html", {
            "request": request,
            "pages": pages,
            "search_query": search or "",
            "selected_status": status or "",
            "selected_visibility": visibility or "",
            "pagination": pagination,
            "total_pages_count": total_pages_count,
            "user": current_user,
            "admin_path": admin_path,
        })

    @app.get(f"{admin_path}/system-info", response_class=HTMLResponse)
    async def dynamic_admin_system_info_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await system_info_api.system_info_page(request, db, current_user)

    @app.get(f"{admin_path}/api/v1/system-info")
    async def dynamic_get_system_info_api(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await system_info_api.get_system_info_api(db, current_user)

    @app.get(f"{admin_path}/error-settings", response_class=HTMLResponse)
    async def dynamic_admin_error_settings_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await error_config_api.error_settings_page(request, db, current_user)

    @app.post(f"{admin_path}/error-settings")
    async def dynamic_update_error_settings(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        enable_custom_error_pages: bool = Form(False),
        error_page_template: str = Form("default"),
        custom_error_404_title: str = Form("页面未找到"),
        custom_error_404_message: str = Form("抱歉，您访问的页面不存在。"),
        custom_error_500_title: str = Form("服务器内部错误"),
        custom_error_500_message: str = Form("抱歉，服务器遇到了一些问题，请稍后再试。"),
        custom_error_403_title: str = Form("访问被禁止"),
        custom_error_403_message: str = Form("抱歉，您没有权限访问此页面。"),
        custom_error_400_title: str = Form("请求错误"),
        custom_error_400_message: str = Form("抱歉，您的请求存在问题，请检查后重试。"),
        enable_error_caching: bool = Form(False),
        error_cache_duration: int = Form(3600),
        enable_error_logging: bool = Form(False),
        log_level: str = Form("INFO"),
        enable_performance_optimization: bool = Form(False),
        related_posts_cache_strategy: str = Form("aggressive"),
        reading_time_cache_duration: int = Form(7200),
        csrf_token: str = Form(...),
    ):
        return await error_config_api.update_error_settings(
            request,
            db,
            current_user,
            enable_custom_error_pages,
            error_page_template,
            custom_error_404_title,
            custom_error_404_message,
            custom_error_500_title,
            custom_error_500_message,
            custom_error_403_title,
            custom_error_403_message,
            custom_error_400_title,
            custom_error_400_message,
            enable_error_caching,
            error_cache_duration,
            enable_error_logging,
            log_level,
            enable_performance_optimization,
            related_posts_cache_strategy,
            reading_time_cache_duration,
            csrf_token,
        )

    @app.get(f"{admin_path}/comment-settings", response_class=HTMLResponse)
    async def dynamic_admin_comment_settings_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await comment_settings_api.comment_settings_page(request, db, current_user)

    @app.get(f"{admin_path}/security-center", response_class=HTMLResponse)
    async def dynamic_admin_security_center_page(
        request: Request,
        page: int = 1,
        page_size: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await security_center_api.security_center_page(request, db, current_user)

    @app.post(f"{admin_path}/security-center", response_class=HTMLResponse)
    async def dynamic_update_security_center(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        login_max_attempts: int = Form(3),
        login_ban_minutes: int = Form(15),
        new_ip_login_alert_enabled: bool = Form(False),
        comment_rate_limit_per_min: int = Form(30),
        login_audit_auto_cleanup_enabled: bool = Form(False),
        login_audit_retention_days: int = Form(30),
        csrf_token: str = Form(...),
    ):
        return await security_center_api.update_security_center(
            request=request,
            db=db,
            current_user=current_user,
            login_max_attempts=login_max_attempts,
            login_ban_minutes=login_ban_minutes,
            new_ip_login_alert_enabled=new_ip_login_alert_enabled,
            comment_rate_limit_per_min=comment_rate_limit_per_min,
            login_audit_auto_cleanup_enabled=login_audit_auto_cleanup_enabled,
            login_audit_retention_days=login_audit_retention_days,
            csrf_token=csrf_token,
        )

    @app.post(f"{admin_path}/security-center/audit/cleanup", response_class=HTMLResponse)
    async def dynamic_clear_security_audit_logs(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        clear_mode: str = Form(...),
        csrf_token: str = Form(...),
    ):
        return await security_center_api.clear_security_audit_logs(
            request=request,
            db=db,
            current_user=current_user,
            clear_mode=clear_mode,
            csrf_token=csrf_token,
        )

    @app.get(f"{admin_path}/data-management", response_class=HTMLResponse)
    async def dynamic_admin_data_management_page(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        return await data_api.data_management_page(request, db, current_user)

    app.include_router(data_api.router, prefix=admin_path)
    app.include_router(categories_api.router, prefix=admin_path)
    app.include_router(tags_api.router, prefix=admin_path)
    app.include_router(comment_settings_api.router)
    app.include_router(admin_dashboard_api.router)
