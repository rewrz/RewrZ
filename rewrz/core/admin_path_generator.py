"""
后台路径生成器模块

提供灵活的后台路径生成功能，支持多种预设模板和自定义路径格式
"""
import re
import secrets
from typing import Dict, List, Optional, Tuple
from enum import Enum

class AdminPathTemplate(Enum):
    """预设的后台路径模板"""
    CLASSIC = "classic"  # /admin_随机字符
    BRAND = "brand"      # /rewrz-admin 或类似品牌名称
    SHORT = "short"      # /ra-admin 或其他简短形式
    MIXED = "mixed"      # /brand-admin_随机字符 混合形式
    CUSTOM = "custom"    # 完全自定义

class AdminPathGenerator:
    """后台路径生成器"""
    
    # 预设模板配置
    TEMPLATE_CONFIGS = {
        AdminPathTemplate.CLASSIC: {
            "name": "经典模式",
            "description": "传统的admin加随机字符格式",
            "pattern": "/admin_{random}",
            "examples": ["/admin_a1b2c3d4", "/admin_x9y8z7w6"]
        },
        AdminPathTemplate.BRAND: {
            "name": "品牌模式", 
            "description": "使用品牌名称的固定路径",
            "pattern": "/{brand}-admin",
            "examples": ["/rewrz-admin", "/rz-admin", "/re-admin"]
        },
        AdminPathTemplate.SHORT: {
            "name": "简短模式",
            "description": "使用简短前缀的固定路径",
            "pattern": "/{prefix}-admin",
            "examples": ["/ra-admin", "/rw-admin", "/mgmt"]
        },
        AdminPathTemplate.MIXED: {
            "name": "混合模式", 
            "description": "品牌名称加随机字符的组合",
            "pattern": "/{brand}-admin_{random}",
            "examples": ["/rewrz-admin_a1b2", "/re-admin_x9y8"]
        },
        AdminPathTemplate.CUSTOM: {
            "name": "自定义模式",
            "description": "完全自定义的路径格式",
            "pattern": "用户自定义",
            "examples": ["/my-secret-panel", "/dashboard123"]
        }
    }
    
    # 安全的路径字符集
    SAFE_CHARS = re.compile(r'^[a-zA-Z0-9\-_/]+$')
    
    # 保留的系统路径（不能使用的路径）
    RESERVED_PATHS = {
        '/admin', '/api', '/static', '/media', '/installer', 
        '/feed', '/rss', '/sitemap', '/robots', '/favicon',
        '/archive', '/archives', '/category', '/tag', '/format',
        '/search', '/about', '/contact', '/login', '/logout'
    }
    
    @classmethod
    def generate_path(
        cls, 
        template: AdminPathTemplate,
        brand: str = "rewrz",
        prefix: str = "ra",
        custom_path: Optional[str] = None,
        random_length: int = 8
    ) -> str:
        """
        生成后台路径
        
        Args:
            template: 路径模板类型
            brand: 品牌名称（用于品牌模式和混合模式）
            prefix: 简短前缀（用于简短模式）
            custom_path: 自定义路径（用于自定义模式）
            random_length: 随机字符长度
            
        Returns:
            生成的后台路径
            
        Raises:
            ValueError: 当路径格式无效时
        """
        # 生成随机字符串
        random_str = secrets.token_hex(random_length // 2) if random_length > 0 else ""
        
        if template == AdminPathTemplate.CLASSIC:
            return f"/admin_{random_str}"
            
        elif template == AdminPathTemplate.BRAND:
            # 清理品牌名称
            clean_brand = cls._clean_name(brand)
            return f"/{clean_brand}-admin"
            
        elif template == AdminPathTemplate.SHORT:
            # 清理前缀
            clean_prefix = cls._clean_name(prefix)
            return f"/{clean_prefix}-admin"
            
        elif template == AdminPathTemplate.MIXED:
            # 混合模式：品牌名称 + 随机字符
            clean_brand = cls._clean_name(brand)
            short_random = secrets.token_hex(2)  # 混合模式使用较短的随机字符
            return f"/{clean_brand}-admin_{short_random}"
            
        elif template == AdminPathTemplate.CUSTOM:
            if not custom_path:
                raise ValueError("自定义模式需要提供custom_path参数")
            return cls._validate_custom_path(custom_path)
            
        else:
            raise ValueError(f"不支持的模板类型: {template}")
    
    @classmethod
    def _clean_name(cls, name: str) -> str:
        """清理名称，确保只包含安全字符"""
        if not name:
            return "rw"  # 默认前缀
        
        # 移除非安全字符，保留字母、数字、连字符
        cleaned = re.sub(r'[^a-zA-Z0-9\-]', '', name.lower())
        
        # 确保不为空且不超过10个字符
        if not cleaned:
            return "rw"
        
        return cleaned[:10]  # 限制长度
    
    @classmethod
    def _validate_custom_path(cls, path: str) -> str:
        """验证自定义路径"""
        if not path:
            raise ValueError("自定义路径不能为空")
        
        # 确保以/开头
        if not path.startswith('/'):
            path = '/' + path
        
        # 检查字符安全性
        if not cls.SAFE_CHARS.match(path):
            raise ValueError("路径包含不安全的字符，只允许字母、数字、连字符和下划线")
        
        # 检查是否为保留路径
        if path.lower() in cls.RESERVED_PATHS:
            raise ValueError(f"路径 '{path}' 是系统保留路径，请选择其他路径")
        
        # 检查长度
        if len(path) > 50:
            raise ValueError("路径长度不能超过50个字符")
        
        if len(path) < 3:
            raise ValueError("路径长度至少需要3个字符")
        
        return path
    
    @classmethod
    def validate_path(cls, path: str) -> Tuple[bool, str]:
        """
        验证路径是否有效
        
        Returns:
            (is_valid, error_message)
        """
        try:
            cls._validate_custom_path(path)
            return True, ""
        except ValueError as e:
            return False, str(e)
    
    @classmethod
    def get_template_info(cls) -> Dict:
        """获取所有模板信息"""
        return {
            template.value: {
                "name": config["name"],
                "description": config["description"], 
                "pattern": config["pattern"],
                "examples": config["examples"]
            }
            for template, config in cls.TEMPLATE_CONFIGS.items()
        }
    
    @classmethod
    def suggest_paths(cls, brand: str = "rewrz") -> List[Dict]:
        """
        为用户提供路径建议
        
        Returns:
            包含建议路径的列表
        """
        suggestions = []
        
        # 经典模式建议
        classic_path = cls.generate_path(AdminPathTemplate.CLASSIC)
        suggestions.append({
            "template": "classic",
            "path": classic_path,
            "name": "经典模式",
            "description": "传统安全模式，使用随机字符"
        })
        
        # 品牌模式建议
        brand_path = cls.generate_path(AdminPathTemplate.BRAND, brand=brand)
        suggestions.append({
            "template": "brand", 
            "path": brand_path,
            "name": "品牌模式",
            "description": "使用品牌名称，易于记忆"
        })
        
        # 简短模式建议
        short_prefixes = ["ra", "rw", "mgmt", "cp"]
        for prefix in short_prefixes[:2]:  # 只显示前两个
            short_path = cls.generate_path(AdminPathTemplate.SHORT, prefix=prefix)
            suggestions.append({
                "template": "short",
                "path": short_path, 
                "name": f"简短模式 ({prefix})",
                "description": "简短前缀，便于输入"
            })
        
        # 混合模式建议
        mixed_path = cls.generate_path(AdminPathTemplate.MIXED, brand=brand)
        suggestions.append({
            "template": "mixed",
            "path": mixed_path,
            "name": "混合模式", 
            "description": "品牌名称加随机字符，兼顾安全性和记忆性"
        })
        
        return suggestions

# 便捷函数
def generate_admin_path(
    template: str = "classic",
    brand: str = "rewrz", 
    prefix: str = "ra",
    custom_path: Optional[str] = None,
    random_length: int = 8
) -> str:
    """
    便捷的路径生成函数
    
    Args:
        template: 模板类型 ("classic", "brand", "short", "mixed", "custom")
        brand: 品牌名称
        prefix: 简短前缀
        custom_path: 自定义路径
        random_length: 随机字符长度
        
    Returns:
        生成的后台路径
    """
    template_enum = AdminPathTemplate(template)
    return AdminPathGenerator.generate_path(
        template_enum, brand, prefix, custom_path, random_length
    )

def validate_admin_path(path: str) -> Tuple[bool, str]:
    """
    验证后台路径
    
    Returns:
        (is_valid, error_message) 
    """
    return AdminPathGenerator.validate_path(path)