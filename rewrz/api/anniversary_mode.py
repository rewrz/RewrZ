"""
纪念日氛围模式 API 模块
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..crud import setting as crud_setting
from ..schemas.setting import SettingUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/anniversary-mode")
async def get_anniversary_mode(db: Session = Depends(get_db)) -> Dict:
    """
    获取当前纪念日氛围模式状态
    """
    try:
        # 获取纪念日设置
        anniversaries_setting = crud_setting.get_setting(db, key="anniversaries_json")
        anniversaries_json = anniversaries_setting.value if anniversaries_setting else "[]"
        
        if not anniversaries_json or anniversaries_json == "[]":
            return {"active": False}
        
        anniversaries = json.loads(anniversaries_json)
        
        # 获取当前日期
        today = datetime.now()
        current_month = today.month
        current_day = today.day
        
        # 检查是否有匹配的纪念日
        for anniversary in anniversaries:
            if (anniversary.get("month") == current_month and 
                anniversary.get("day") == current_day):
                
                # 获取特效配置
                effects = get_anniversary_effects(anniversary.get("type", "Festive"))
                
                return {
                    "active": True,
                    "name": anniversary.get("name", "纪念日"),
                    "type": anniversary.get("type", "Festive"),
                    "effects": effects
                }
        
        return {"active": False}
        
    except Exception as e:
        return {"active": False, "error": str(e)}

@router.get("/anniversary-mode/current")
async def get_current_anniversary_mode(db: Session = Depends(get_db)) -> Dict:
    """
    获取当前纪念日氛围模式状态（兼容性端点）
    """
    return await get_anniversary_mode(db)

def get_anniversary_effects(anniversary_type: str) -> List[str]:
    """
    根据纪念日类型获取对应的特效列表
    """
    if anniversary_type == "Mourn":
        return []  # 追悼模式不需要特效，只需要灰白滤镜
    
    # 喜庆模式的特效配置
    festive_effects = {
        "春节": ["fireworks", "lanterns"],
        "国庆节": ["fireworks"],
        "中秋节": ["lanterns"],
        "樱花节": ["sakura"],
        "新年": ["fireworks"],
        "元宵节": ["lanterns"],
        "default": ["fireworks"]
    }
    
    # 这里可以根据纪念日名称或日期进一步细化特效选择
    return festive_effects.get("default", ["fireworks"])

@router.get("/custom-theme")
async def get_custom_theme(db: Session = Depends(get_db)) -> Dict:
    """
    获取自定义主题配置
    """
    try:
        # 获取主题设置
        def get_setting_value(key: str, default):
            setting = crud_setting.get_setting(db, key=key)
            if setting and isinstance(setting.value, dict) and "value" in setting.value:
                return setting.value["value"]
            return default
            
        theme_settings = {
            "primary_color": get_setting_value("theme_primary_color", "#1e293b"),
            "secondary_color": get_setting_value("theme_secondary_color", "#64748b"),
            "accent_color": get_setting_value("theme_accent_color", "#f59e0b"),
            "font_size": get_setting_value("theme_font_size", "16"),
            "active": get_setting_value("custom_theme_enabled", False)
        }
        
        return theme_settings
        
    except Exception as e:
        return {"active": False, "error": str(e)}

@router.post("/toggle-theme")
async def toggle_theme(theme_data: Dict, db: Session = Depends(get_db)) -> Dict:
    """
    切换主题设置
    """
    try:
        # 这里可以添加主题切换的逻辑
        # 目前主要通过前端JavaScript处理
        return {"success": True, "theme": theme_data.get("theme", "light")}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anniversary-mode/save")
async def save_anniversaries(
    request: Request,
    db: Session = Depends(get_db)
):
    """保存纪念日氛围设置"""
    try:
        # 获取JSON数据
        data = await request.json()
        anniversaries = data.get("anniversaries", [])
        
        # 验证数据格式
        for anniversary in anniversaries:
            if not all(key in anniversary for key in ["month", "day", "name", "type"]):
                raise HTTPException(status_code=400, detail="纪念日数据格式不正确")
            
            month = anniversary["month"]
            day = anniversary["day"]
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                raise HTTPException(status_code=400, detail="日期范围不正确")
        
        # 保存到数据库
        anniversaries_json = json.dumps(anniversaries, ensure_ascii=False)
        
        # 检查设置是否存在
        existing_setting = crud_setting.get_setting(db, key="anniversaries_json")
        if existing_setting:
            # 更新现有设置
            crud_setting.update_setting(
                db=db,
                key="anniversaries_json",
                setting_update=SettingUpdate(value={"value": anniversaries_json})
            )
        else:
            # 创建新设置
            from ..models.setting import Setting
            new_setting = Setting(
                key="anniversaries_json",
                value={"value": anniversaries_json},
                description="纪念日氛围模式设置"
            )
            db.add(new_setting)
            db.commit()
        
        logger.info(f"纪念日氛围设置已保存: {len(anniversaries)} 个纪念日")
        return {"success": True, "message": "纪念日氛围设置已保存"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存纪念日氛围设置失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="保存纪念日氛围设置失败")
