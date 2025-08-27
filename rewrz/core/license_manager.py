"""
文章版权管理器

提供各种版权协议的定义和HTML渲染功能，支持Creative Commons等主流协议。
"""

from typing import Dict, Optional


class LicenseManager:
    """文章版权管理器"""
    
    # 预设版权类型定义
    LICENSE_TYPES = {
        "cc_by_nc_sa_4": {
            "name": "CC BY-NC-SA 4.0",
            "full_name": "知识共享署名-非商业性使用-相同方式共享 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh",
            "description": "允许他人在非商业目的下操作和修改作品，但必须署名并以相同协议共享。"
        },
        "cc_by_4": {
            "name": "CC BY 4.0", 
            "full_name": "知识共享署名 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by/4.0/deed.zh",
            "description": "允许他人以任何目的使用作品，但必须署名。"
        },
        "cc_by_sa_4": {
            "name": "CC BY-SA 4.0",
            "full_name": "知识共享署名-相同方式共享 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by-sa/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by-sa/4.0/deed.zh",
            "description": "允许他人自由使用作品，但必须署名并以相同协议共享。"
        },
        "cc_by_nc_4": {
            "name": "CC BY-NC 4.0",
            "full_name": "知识共享署名-非商业性使用 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by-nc/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by-nc/4.0/deed.zh",
            "description": "允许他人在非商业目的下使用作品，但必须署名。"
        },
        "cc_by_nd_4": {
            "name": "CC BY-ND 4.0",
            "full_name": "知识共享署名-禁止演绎 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by-nd/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by-nd/4.0/deed.zh",
            "description": "允许他人在任何目的下使用作品，但必须署名且不能修改作品。"
        },
        "cc_by_nc_nd_4": {
            "name": "CC BY-NC-ND 4.0",
            "full_name": "知识共享署名-非商业性使用-禁止演绎 4.0 国际许可协议",
            "icon": "https://licensebuttons.net/l/by-nc-nd/4.0/88x31.png",
            "url": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.zh",
            "description": "允许他人在非商业目的下使用作品，但必须署名且不能修改作品。"
        },
        "all_rights_reserved": {
            "name": "保留所有权利",
            "full_name": "保留所有权利",
            "icon": None,
            "url": None,
            "description": "著作权归作者所有，未经许可不得转载或使用。"
        },
        "public_domain": {
            "name": "公有领域",
            "full_name": "公有领域 (Public Domain)",
            "icon": "https://licensebuttons.net/p/zero/1.0/88x31.png",
            "url": "https://creativecommons.org/publicdomain/zero/1.0/deed.zh",
            "description": "作者放弃所有权利，任何人可以自由使用。"
        }
    }
    
    @classmethod
    def get_license_info(cls, license_type: str) -> Optional[Dict]:
        """获取版权协议信息"""
        return cls.LICENSE_TYPES.get(license_type)
    
    @classmethod
    def get_all_licenses(cls) -> Dict[str, Dict]:
        """获取所有可用的版权协议"""
        return cls.LICENSE_TYPES
    
    @classmethod
    def get_license_html(cls, license_type: str, author: str, site_url: str = "") -> str:
        """
        生成版权声明HTML
        
        Args:
            license_type: 版权类型
            author: 作者名称
            site_url: 网站URL（可选）
            
        Returns:
            HTML字符串
        """
        if license_type not in cls.LICENSE_TYPES:
            license_type = "cc_by_nc_sa_4"  # 默认使用CC BY-NC-SA 4.0
            
        license_info = cls.LICENSE_TYPES[license_type]
        
        html = f'''
        <div class="article-license">
            <div class="license-header">
                <i class="icon-copyright"></i>
                <span>版权声明</span>
            </div>
            <div class="license-content">
        '''
        
        # 添加协议图标
        if license_info["icon"]:
            html += f'<img src="{license_info["icon"]}" alt="{license_info["name"]}" class="license-icon" loading="lazy">'
        
        # 添加协议信息
        if license_info["url"]:
            html += f'<p>本文采用 <a href="{license_info["url"]}" target="_blank" rel="noopener">{license_info["full_name"]}</a> 许可协议。</p>'
        else:
            html += f'<p>本文版权：{license_info["full_name"]}</p>'
        
        html += f'<p>{license_info["description"]}</p>'
        html += f'<p>作者：<strong>{author}</strong>'
        
        if site_url:
            html += f' | 来源：<a href="{site_url}" rel="noopener">{site_url}</a>'
        
        html += '</p>'
        html += '''
            </div>
        </div>
        '''
        
        return html
    
    @classmethod
    def get_license_options_html(cls, selected_license: str = "cc_by_nc_sa_4") -> str:
        """
        生成版权选择下拉框的HTML选项
        
        Args:
            selected_license: 当前选中的版权类型
            
        Returns:
            HTML选项字符串
        """
        options = []
        
        for license_key, license_info in cls.LICENSE_TYPES.items():
            selected = 'selected' if license_key == selected_license else ''
            options.append(f'<option value="{license_key}" {selected}>{license_info["name"]}</option>')
        
        return '\n'.join(options)
    
    @classmethod
    def validate_license_type(cls, license_type: str) -> bool:
        """验证版权类型是否有效"""
        return license_type in cls.LICENSE_TYPES


# 提供便捷的全局函数
def get_license_manager() -> LicenseManager:
    """获取版权管理器实例"""
    return LicenseManager()


def render_license(license_type: str, author: str, site_url: str = "") -> str:
    """渲染版权声明HTML（模板函数）"""
    return LicenseManager.get_license_html(license_type, author, site_url)
