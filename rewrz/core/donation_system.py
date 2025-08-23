"""
打赏系统管理器

提供文章打赏功能，支持二维码和链接两种方式，样式和显示位置可配置。
"""

from typing import Dict, Optional
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
        has_qr = bool(self.settings['qr_code_url'])
        has_link = bool(self.settings['link_text'] and self.settings['link_url'])
        
        if not has_qr and not has_link:
            return ''  # 没有配置任何打赏方式
        
        html = f'''
        <div class="donation-widget elegant-style">
            <div class="donation-header">
                <div class="donation-icon">
                    <svg viewBox="0 0 24 24" class="heart-icon">
                        <path d="M12,21.35L10.55,20.03C5.4,15.36 2,12.27 2,8.5 2,5.41 4.42,3 7.5,3C9.24,3 10.91,3.81 12,5.08C13.09,3.81 14.76,3 16.5,3C19.58,3 22,5.41 22,8.5C22,12.27 18.6,15.36 13.45,20.04L12,21.35Z"/>
                    </svg>
                </div>
                <h4 class="donation-title">{self.settings['title']}</h4>
            </div>
            <p class="donation-description">{self.settings['description']}</p>
            <div class="donation-methods">
        '''
        
        if has_qr:
            html += f'''
                <div class="donation-qr">
                    <img src="{self.settings['qr_code_url']}" alt="打赏二维码" class="qr-code" loading="lazy">
                    <span class="qr-hint">扫码支持</span>
                </div>
            '''
        
        if has_link:
            html += f'''
                <div class="donation-link">
                    <a href="{self.settings['link_url']}" target="_blank" rel="noopener" class="donation-button">
                        <span>{self.settings['link_text']}</span>
                    </a>
                </div>
            '''
        
        html += '</div></div>'
        return html
    
    def _render_minimal_style(self) -> str:
        """简洁风格的打赏组件"""
        has_qr = bool(self.settings['qr_code_url'])
        has_link = bool(self.settings['link_text'] and self.settings['link_url'])
        
        if not has_qr and not has_link:
            return ''
        
        html = f'''
        <div class="donation-widget minimal-style">
            <h4 class="donation-title">{self.settings['title']}</h4>
            <div class="donation-methods">
        '''
        
        if has_qr:
            html += f'''
                <div class="donation-qr">
                    <img src="{self.settings['qr_code_url']}" alt="打赏二维码" class="qr-code" loading="lazy">
                </div>
            '''
        
        if has_link:
            html += f'''
                <div class="donation-link">
                    <a href="{self.settings['link_url']}" target="_blank" rel="noopener" class="donation-button">
                        {self.settings['link_text']}
                    </a>
                </div>
            '''
        
        html += '</div></div>'
        return html
    
    def _render_card_style(self) -> str:
        """卡片风格的打赏组件"""
        has_qr = bool(self.settings['qr_code_url'])
        has_link = bool(self.settings['link_text'] and self.settings['link_url'])
        
        if not has_qr and not has_link:
            return ''
        
        html = f'''
        <div class="donation-widget card-style">
            <div class="donation-card">
                <div class="card-header">
                    <h4 class="donation-title">{self.settings['title']}</h4>
                    <p class="donation-description">{self.settings['description']}</p>
                </div>
                <div class="card-body">
        '''
        
        if has_qr:
            html += f'''
                    <div class="donation-qr">
                        <img src="{self.settings['qr_code_url']}" alt="打赏二维码" class="qr-code" loading="lazy">
                        <span class="qr-hint">扫码支持</span>
                    </div>
            '''
        
        if has_link:
            html += f'''
                    <div class="donation-link">
                        <a href="{self.settings['link_url']}" target="_blank" rel="noopener" class="donation-button">
                            {self.settings['link_text']}
                        </a>
                    </div>
            '''
        
        html += '''
                </div>
            </div>
        </div>
        '''
        return html
    
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