"""页面模板注册与解析工具。"""

from __future__ import annotations

from typing import Dict, List

DEFAULT_PAGE_TEMPLATE = "default"

PAGE_TEMPLATE_REGISTRY: Dict[str, Dict[str, str]] = {
    "default": {
        "label": "默认页面（全宽）",
        "description": "WordPress 常见默认页风格，适合通用内容展示。",
        "usage": "用二级标题分节、正文写段落或列表即可，适合公告、说明文档和通用介绍。",
        "skeleton": "## 小节标题\n这里写这一部分的说明文字。\n\n- 要点一\n- 要点二\n\n## 另一个小节\n补充说明或结论。",
        "template_file": "page.html",
    },
    "about": {
        "label": "关于页面（Profile）",
        "description": "二次元角色档案风格，适合关于我/关于站点。",
        "usage": "开头写一段自我介绍，再用二级标题分“关于我 / 我在做什么 / 联系我”，首屏会自动展示档案信息卡片。",
        "skeleton": "你好，我是……（一段自我介绍）。\n\n## 关于我\n- 所在城市：……\n- 目前在做：……\n- 兴趣爱好：……\n\n## 我在做什么\n用几句话介绍你的工作、项目或创作方向。\n\n## 联系我\n- 邮箱：you@example.com\n- 社交主页：https://example.com",
        "template_file": "page_about.html",
    },
    "resume": {
        "label": "个人简历（Resume）",
        "description": "条目化简历版式，适合求职、个人履历与技能清单。",
        "usage": "用二级标题分区（基本信息、教育经历、工作经历、技能、项目），三级标题写公司/学校 + 时间，列表写职责与成果。",
        "skeleton": "## 基本信息\n- 姓名：你的名字\n- 求职方向：前端工程师\n- 所在城市：上海\n- 联系邮箱：you@example.com\n\n## 教育经历\n### 某某大学 · 计算机科学与技术（2018 - 2022）\n- 主修课程：数据结构、操作系统、Web 开发\n- 荣誉：校级优秀毕业生\n\n## 工作经历\n### 某某公司 · 前端工程师（2022 - 至今）\n- 负责站点前台与后台管理界面的开发维护\n- 推动页面模板系统落地，内容搭建效率提升 60%\n\n## 技能清单\n- 前端：HTML / CSS / JavaScript / TypeScript\n- 工具：Git、Figma、Linux\n\n## 项目经验\n### 个人博客系统（2025）\n- 独立完成前后端与部署，支持主题切换与页面模板",
        "template_file": "page_resume.html",
    },
    "portfolio": {
        "label": "作品集（Portfolio）",
        "description": "网格作品集版式，适合摄影、绘画、游戏与项目作品展示。",
        "usage": "用二级标题给作品分组（摄影作品 / 游戏作品 / 项目作品），每个作品写成一条列表：图片 + 一句说明，模板会自动排成网格卡片。",
        "skeleton": "## 摄影作品\n- [![城市夜景](/media/2025/04/example.jpg)](/media/2025/04/example.jpg) 雨夜街头的长曝光，摄于 2026 年夏。\n- [![山间清晨](/media/2025/04/example2.jpg)](/media/2025/04/example2.jpg) 清晨五点的山脊线与云海。\n\n## 游戏作品\n- [![作品封面](/media/2025/04/cover.jpg)](/media/2025/04/cover.jpg) 《你的作品名》· 叙事解谜 · [试玩链接](https://example.com)\n\n## 项目作品\n- [![项目截图](/media/2025/04/project.jpg)](/media/2025/04/project.jpg) 项目简介：一句话说明它解决了什么问题。",
        "template_file": "page_portfolio.html",
    },
    "gallery": {
        "label": "主题展览（Gallery）",
        "description": "沉浸式线上摄影展版式，适合主题摄影、同人图集与系列作品。",
        "usage": "用 ## 写展览章节，图片单独成段，并把作品名写进图片说明：![作品名](图片地址)。模板会放大图片、生成图注，支持滚动入场动画与点击放大浏览。",
        "skeleton": "## 序章 · 主题名\n用一两句话写展览引言或拍摄故事。\n\n![作品名](/media/2025/04/cover.jpg)\n\n## 第一章 · 章节名\n写这一章的氛围、地点或拍摄背景。\n\n![作品名](/media/2025/04/photo-1.jpg)\n\n![作品名](/media/2025/04/photo-2.jpg)\n\n## 终章 · 留白\n写一段结束语，给展览收尾。",
        "template_file": "page_gallery.html",
    },
    "timeline": {
        "label": "时间轴（Archives）",
        "description": "WordPress 常见历程/归档页风格，适合大事记与博客历史。",
        "usage": "用二级标题写年份或阶段，下面用列表列条目；时间轴会自动连线，适合博客历史、个人经历、大事记。",
        "skeleton": "## 2026 年\n- 3 月：上线新主题\n- 8 月：完成页面模板系统\n\n## 2025 年\n- 开始写博客\n- 发布第一篇文章",
        "template_file": "page_timeline.html",
    },
    "roadmap": {
        "label": "项目进度（Roadmap）",
        "description": "进度路线版式，适合开发计划、项目进度与版本规划。",
        "usage": "用二级标题写阶段或季度，任务列表用 - [x] 表示已完成、- [ ] 表示未完成，模板会自动区分状态。",
        "skeleton": "## 已完成\n- [x] 页面模板系统\n- [x] 主题切换\n\n## 进行中\n- [x] 编辑器体验优化\n- [ ] 移动端适配\n\n## 计划中\n- [ ] 多语言支持\n- [ ] 数据导出",
        "template_file": "page_roadmap.html",
    },
    "landing": {
        "label": "落地页（Landing）",
        "description": "大视觉首屏风格，适合活动页、上线页与引导页。",
        "usage": "标题与摘要决定首屏大字，正文写亮点列表和行动号召；模板顶部会自动展示返回首页与浏览归档按钮。",
        "skeleton": "## 这是什么\n一句话说明这个活动或项目。\n\n## 亮点\n- 亮点一：……\n- 亮点二：……\n\n## 现在就加入\n把参与方式或联系方式写在这里。",
        "template_file": "page_landing.html",
    },
    "links": {
        "label": "友情链接（Blogroll）",
        "description": "卡片式友链风格，适合站点导航与资源列表。",
        "usage": "每个友链写成 - [站点名](https://…) — 一句话介绍，模板会自动渲染为卡片；也适合整理常用资源导航。",
        "skeleton": "- [示例站点](https://example.com) — 一位长期写独立博客的朋友。\n- [另一个站点](https://example.org) — 设计资源与灵感收集。\n- [项目主页](https://example.net) — 我的开源项目与文档。",
        "template_file": "page_links.html",
    },
    "faq": {
        "label": "常见问题（FAQ）",
        "description": "问答卡片风格，建议用二级标题写问题、正文写回答。",
        "usage": "用二级标题写问题、正文写回答，每个问题会自动编号并生成问答卡片。",
        "skeleton": "## 这个站点主要写什么？\n这里写回答。\n\n## 可以转载你的文章吗？\n除特别注明外，均采用 CC BY-NC-SA 4.0 协议，转载前请注明出处。\n\n## 如何联系你？\n可以通过联系页留下的邮箱与我沟通。",
        "template_file": "page_faq.html",
    },
    "legal": {
        "label": "条款文档（Legal）",
        "description": "隐私政策、服务条款等长文风格，二级标题自动编号。",
        "usage": "用二级标题写条款章节，模板会自动编号，适合隐私政策、服务条款、用户协议。",
        "skeleton": "## 我们收集哪些信息\n说明收集范围与用途。\n\n## 信息如何使用\n说明使用方式与共享情况。\n\n## 你的权利\n说明查询、更正与删除方式。\n\n## 联系我们\n如需行使权利，请联系 you@example.com。",
        "template_file": "page_legal.html",
    },
    "contact": {
        "label": "联系页（Contact）",
        "description": "展示站点公开邮箱与社交入口，适合联系我/合作洽谈。",
        "usage": "公开邮箱与社交入口来自后台站点设置，正文只需补充合作说明、响应时间或留言方式。",
        "skeleton": "## 合作与反馈\n欢迎通过上方邮箱或社交入口联系我。\n\n- 合作类型：文章转载、项目合作、产品试用\n- 响应时间：通常 1-2 个工作日内回复\n\n## 留言建议\n附上项目背景与期望结果，沟通会更高效。",
        "template_file": "page_contact.html",
    },
    "changelog": {
        "label": "更新日志（Changelog）",
        "description": "版本记录风格，建议用二级标题写版本号、列表写变更内容。",
        "usage": "用二级标题写版本号（可带日期），列表写变更项；每个版本会自动显示为独立版本块。",
        "skeleton": "## v1.2.0（2026-10-20）\n- 新增页面模板系统\n- 修复空正文保存异常\n\n## v1.1.0（2026-09-12）\n- 优化移动端布局\n- 新增评论审核开关",
        "template_file": "page_changelog.html",
    },
}


def normalize_page_template(raw_value: str | None) -> str:
    candidate = str(raw_value or "").strip().lower()
    if candidate in PAGE_TEMPLATE_REGISTRY:
        return candidate
    return DEFAULT_PAGE_TEMPLATE


def resolve_page_template_file(raw_value: str | None) -> str:
    key = normalize_page_template(raw_value)
    return PAGE_TEMPLATE_REGISTRY.get(key, PAGE_TEMPLATE_REGISTRY[DEFAULT_PAGE_TEMPLATE])["template_file"]


def get_page_template_options() -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for key, meta in PAGE_TEMPLATE_REGISTRY.items():
        options.append(
            {
                "value": key,
                "label": meta.get("label", key),
                "description": meta.get("description", ""),
                "usage": meta.get("usage", ""),
                "skeleton": meta.get("skeleton", ""),
            }
        )
    return options


# 后台下拉分组：只做展示分组，不新增模板
PAGE_TEMPLATE_GROUPS: List[Dict[str, object]] = [
    {
        "label": "基础页面",
        "keys": ["default", "about", "resume", "faq", "legal", "contact", "links", "changelog"],
    },
    {
        "label": "展示型页面",
        "keys": ["portfolio", "gallery", "timeline", "roadmap", "landing"],
    },
]


def get_page_template_grouped_options() -> List[Dict[str, object]]:
    """按后台下拉分组返回页面模板选项，保持分组内原有顺序。"""
    flat_options = {item["value"]: item for item in get_page_template_options()}
    groups: List[Dict[str, object]] = []
    for group in PAGE_TEMPLATE_GROUPS:
        items = [flat_options[key] for key in group["keys"] if key in flat_options]
        if items:
            groups.append({"label": group["label"], "items": items})
    return groups


def get_page_template_label_map() -> Dict[str, str]:
    """返回模板键到展示名称的映射，供后台列表直接使用。"""
    return {
        key: meta.get("label", key)
        for key, meta in PAGE_TEMPLATE_REGISTRY.items()
    }
