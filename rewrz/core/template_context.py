"""
模板基础上下文构建工具

提供构建模板渲染所需的通用基础上下文字段，避免在各路由中重复注入。
"""
from fastapi import Request


def build_base_template_context(request: Request) -> dict:
    """
    构建模板通用的基础上下文，集中提供全局字段，减少重复注入。
    """
    return {
        "atmosphere_class": request.state.atmosphere_class,
        "site_title": request.state.site_title,
        "tagline": request.state.tagline,
        "noindex_site": request.state.noindex_site,
        "block_ai_crawlers": request.state.block_ai_crawlers,
    }