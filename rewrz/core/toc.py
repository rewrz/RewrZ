"""
文章目录（TOC）构建工具
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
from slugify import slugify


def build_toc_from_html(content_html: str, min_headings: int = 3) -> Tuple[str, List[Dict[str, str]]]:
    """
    从 HTML 内容中提取 h2/h3 作为目录，并为标题注入稳定 id。

    Returns:
        (处理后的 html, toc_items)
    """
    if not content_html:
        return "", []

    soup = BeautifulSoup(content_html, "html.parser")
    headings = soup.find_all(["h2", "h3"])
    if not headings:
        return str(soup), []

    used_ids = set()
    toc_items: List[Dict[str, str]] = []

    for idx, heading in enumerate(headings):
        title = heading.get_text(strip=True)
        if not title:
            continue

        hid = heading.get("id") or slugify(title) or f"section-{idx + 1}"
        base_hid = hid
        suffix = 1
        while hid in used_ids:
            suffix += 1
            hid = f"{base_hid}-{suffix}"
        used_ids.add(hid)
        heading["id"] = hid

        toc_items.append(
            {
                "id": hid,
                "title": title,
                "level": heading.name,  # h2 / h3
            }
        )

    if len(toc_items) < min_headings:
        return str(soup), []

    return str(soup), toc_items

