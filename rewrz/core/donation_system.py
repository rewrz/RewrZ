"""
打赏系统管理器

提供文章打赏功能，支持二维码和链接两种方式，样式和显示位置可配置。
"""

from typing import Dict, Optional
from html import escape
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from ..crud import setting as crud_setting


class DonationSystem:
    """打赏系统管理器"""
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = self._load_donation_settings()
    
    def _load_donation_settings(self) -> dict:
        """加载打赏设置"""
        return {
            'enabled': self._get_setting('donation_enabled', False),
            'title': self._get_setting('donation_title', '如果这篇文章对您有帮助，请考虑支持作者'),
            'description': self._get_setting('donation_description', '您的支持是我创作的动力！'),
            'qr_code_url': self._get_setting('donation_qr_code_url', ''),
            'link_text': self._get_setting('donation_link_text', ''),
            'link_url': self._get_setting('donation_link_url', ''),
            'show_position': self._get_setting('donation_show_position', 'article_end'),  # article_end, sidebar
            'style_theme': self._get_setting('donation_style_theme', 'elegant')  # elegant, minimal, card
        }
    
    def _get_setting(self, key: str, default) -> any:
        """获取单个设置值"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return setting.value["value"]
        return default

    def _escape_text(self, value: str) -> str:
        return escape(str(value or ""), quote=False)

    def _escape_attr(self, value: str) -> str:
        return escape(str(value or ""), quote=True)

    def _sanitize_href(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https", "mailto"}:
            return self._escape_attr(raw)
        if not parsed.scheme and (raw.startswith("/") or raw.startswith("#") or raw.startswith("./") or raw.startswith("../")):
            return self._escape_attr(raw)
        return ""

    def _sanitize_image_src(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            return self._escape_attr(raw)
        if not parsed.scheme and (raw.startswith("/") or raw.startswith("./") or raw.startswith("../")):
            return self._escape_attr(raw)
        return ""
    
    def is_enabled(self) -> bool:
        """检查打赏功能是否启用"""
        return self.settings['enabled']
    
    def render_donation_widget(self) -> str:
        """
        渲染打赏组件HTML
        
        Returns:
            HTML字符串，如果未启用则返回空字符串
        """
        if not self.settings['enabled']:
            return ''
        
        theme = self.settings['style_theme']
        
        if theme == 'elegant':
            return self._render_elegant_style()
        elif theme == 'minimal': 
            return self._render_minimal_style()
        elif theme == 'card':
            return self._render_card_style()
        else:
            return self._render_elegant_style()  # 默认使用优雅风格
    
    def _render_elegant_style(self) -> str:
        """优雅风格的打赏组件"""
        title = self._escape_text(self.settings.get("title", "支持作者"))
        description = self._escape_text(self.settings.get("description", ""))
        qr_code_url = self._sanitize_image_src(self.settings.get("qr_code_url", ""))
        link_url = self._sanitize_href(self.settings.get("link_url", ""))
        link_text = self._escape_text(self.settings.get("link_text") or "支持作者")

        has_qr = bool(qr_code_url)
        has_link = bool(link_url)
        if not has_qr and not has_link:
            return ""

        methods_html = []
        if has_qr:
            methods_html.append(
                f"""
                <figure class="donation-qr-block">
                    <img src="{qr_code_url}" alt="打赏二维码" class="donation-qr-image" loading="lazy">
                    <figcaption class="donation-qr-hint">扫码赞赏</figcaption>
                </figure>
                """
            )
        if has_link:
            methods_html.append(
                f"""
                <a href="{link_url}" target="_blank" rel="noopener noreferrer nofollow" class="donation-action-btn">
                    <span>{link_text}</span>
                    <span class="donation-action-arrow" aria-hidden="true">↗</span>
                </a>
                """
            )

        return f"""
        <div class="donation-widget donation-theme-elegant" data-donation-theme="elegant">
            <div class="donation-shell">
                <div class="donation-header">
                    <div class="donation-mark" aria-hidden="true">赏</div>
                    <div class="donation-copy">
                        <p class="donation-kicker">Support Creator</p>
                        <h4 class="donation-title">{title}</h4>
                        <p class="donation-description">{description}</p>
                    </div>
                </div>
                <div class="donation-methods">
                    {''.join(methods_html)}
                </div>
            </div>
        </div>
        """
    
    def _render_minimal_style(self) -> str:
        """简洁风格的打赏组件"""
        title = self._escape_text(self.settings.get("title", "支持作者"))
        description = self._escape_text(self.settings.get("description", ""))
        qr_code_url = self._sanitize_image_src(self.settings.get("qr_code_url", ""))
        link_url = self._sanitize_href(self.settings.get("link_url", ""))
        link_text = self._escape_text(self.settings.get("link_text") or "支持作者")

        has_qr = bool(qr_code_url)
        has_link = bool(link_url)
        if not has_qr and not has_link:
            return ""

        methods_html = []
        if has_qr:
            methods_html.append(
                f"""
                <figure class="donation-qr-block is-minimal">
                    <img src="{qr_code_url}" alt="打赏二维码" class="donation-qr-image" loading="lazy">
                    <figcaption class="donation-qr-hint">扫码</figcaption>
                </figure>
                """
            )
        if has_link:
            methods_html.append(
                f"""
                <a href="{link_url}" target="_blank" rel="noopener noreferrer nofollow" class="donation-action-btn is-minimal">
                    {link_text}
                </a>
                """
            )

        return f"""
        <div class="donation-widget donation-theme-minimal" data-donation-theme="minimal">
            <div class="donation-shell">
                <div class="donation-header">
                    <div class="donation-copy">
                        <h4 class="donation-title">{title}</h4>
                        <p class="donation-description">{description}</p>
                    </div>
                </div>
                <div class="donation-methods">
                    {''.join(methods_html)}
                </div>
            </div>
        </div>
        """
    
    def _render_card_style(self) -> str:
        """卡片风格的打赏组件"""
        title = self._escape_text(self.settings.get("title", "支持作者"))
        description = self._escape_text(self.settings.get("description", ""))
        qr_code_url = self._sanitize_image_src(self.settings.get("qr_code_url", ""))
        link_url = self._sanitize_href(self.settings.get("link_url", ""))
        link_text = self._escape_text(self.settings.get("link_text") or "支持作者")

        has_qr = bool(qr_code_url)
        has_link = bool(link_url)
        if not has_qr and not has_link:
            return ""

        qr_html = ""
        if has_qr:
            qr_html = (
                f"""
                <figure class="donation-qr-block is-card">
                    <img src="{qr_code_url}" alt="打赏二维码" class="donation-qr-image" loading="lazy">
                    <figcaption class="donation-qr-hint">扫码支持作者</figcaption>
                </figure>
                """
            )

        link_html = ""
        if has_link:
            link_html = (
                f"""
                <a href="{link_url}" target="_blank" rel="noopener noreferrer nofollow" class="donation-action-btn is-card">
                    <span>{link_text}</span>
                    <span class="donation-action-arrow" aria-hidden="true">→</span>
                </a>
                """
            )

        card_shell_class = "donation-shell donation-card-shell"
        if not has_qr:
            card_shell_class += " is-no-qr"
        if not has_link:
            card_shell_class += " is-no-link"

        return f"""
        <div class="donation-widget donation-theme-card" data-donation-theme="card">
            <div class="{card_shell_class}">
                <div class="donation-card-main">
                    <p class="donation-kicker">Creator Support</p>
                    <h4 class="donation-title">{title}</h4>
                    <p class="donation-description">{description}</p>
                    {link_html}
                </div>
                <div class="donation-card-side">
                    {qr_html}
                </div>
            </div>
        </div>
        """
    
    def get_position(self) -> str:
        """获取打赏组件显示位置"""
        return self.settings['show_position']
    
    def get_style_theme(self) -> str:
        """获取打赏组件样式主题"""
        return self.settings['style_theme']


# 默认打赏设置配置
DEFAULT_DONATION_SETTINGS = [
    {
        "key": "donation_enabled",
        "value": {"value": False},
        "description": "启用打赏功能",
        "category": "donation",
        "type": "boolean"
    },
    {
        "key": "donation_title",
        "value": {"value": "如果这篇文章对您有帮助，请考虑支持作者"},
        "description": "打赏标题",
        "category": "donation",
        "type": "string"
    },
    {
        "key": "donation_description",
        "value": {"value": "您的支持是我创作的动力！"},
        "description": "打赏描述文字",
        "category": "donation",
        "type": "string"
    },
    {
        "key": "donation_qr_code_url",
        "value": {"value": ""},
        "description": "打赏二维码图片URL",
        "category": "donation",
        "type": "string"
    },
    {
        "key": "donation_link_text",
        "value": {"value": ""},
        "description": "打赏链接文字",
        "category": "donation",
        "type": "string"
    },
    {
        "key": "donation_link_url",
        "value": {"value": ""},
        "description": "打赏链接地址",
        "category": "donation",
        "type": "url"
    },
    {
        "key": "donation_show_position",  
        "value": {"value": "article_end"},
        "description": "打赏组件显示位置",
        "category": "donation",
        "type": "select",
        "options": ["article_end", "sidebar"]
    },
    {
        "key": "donation_style_theme",
        "value": {"value": "elegant"},
        "description": "打赏组件样式主题",
        "category": "donation", 
        "type": "select",
        "options": ["elegant", "minimal", "card"]
    }
]


def get_donation_system(db: Session) -> DonationSystem:
    """获取打赏系统实例"""
    return DonationSystem(db)


def render_donation_widget(db: Session) -> str:
    """渲染打赏组件HTML（模板函数）"""
    donation_system = get_donation_system(db)
    return donation_system.render_donation_widget()
