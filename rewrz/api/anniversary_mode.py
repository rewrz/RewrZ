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
        
        if not anniversaries_setting or not anniversaries_setting.value:
            return {"active": False}
        
        # 处理不同的数据格式
        anniversaries_data = anniversaries_setting.value
        
        # 调试：记录原始数据
        logger.info(f"原始数据类型: {type(anniversaries_data)}")
        logger.info(f"原始数据内容: {anniversaries_data}")
        
        if isinstance(anniversaries_data, str):
            # 如果是字符串，直接解析
            anniversaries = json.loads(anniversaries_data)
        elif isinstance(anniversaries_data, dict):
            if "value" in anniversaries_data:
                # 如果是包含value字段的字典
                value_data = anniversaries_data["value"]
                if isinstance(value_data, str):
                    anniversaries = json.loads(value_data)
                else:
                    anniversaries = value_data
            else:
                # 如果字典本身就是数据
                anniversaries = [anniversaries_data]
        elif isinstance(anniversaries_data, list):
            # 如果直接是列表
            anniversaries = anniversaries_data
        else:
            # 其他情况，尝试转换为字符串再解析
            try:
                anniversaries = json.loads(str(anniversaries_data))
            except:
                logger.error(f"无法解析数据: {anniversaries_data}")
                return {"active": False, "error": f"无法解析数据格式: {type(anniversaries_data)}"}
        
        if not anniversaries:
            return {"active": False}
        
        # 调试：记录解析后的数据类型和内容
        logger.info(f"解析后的纪念日数据类型: {type(anniversaries)}")
        logger.info(f"解析后的纪念日数据内容: {anniversaries}")
        
        # 确保 anniversaries 是列表
        if not isinstance(anniversaries, list):
            logger.error(f"纪念日数据不是列表格式: {type(anniversaries)}")
            return {"active": False, "error": f"数据格式错误: 期望列表，得到 {type(anniversaries)}"}
        
        # 获取当前日期
        today = datetime.now()
        current_month = today.month
        current_day = today.day
        
        # 检查是否有匹配的纪念日
        for anniversary in anniversaries:
            # 确保每个纪念日项是字典
            if not isinstance(anniversary, dict):
                logger.warning(f"跳过非字典格式的纪念日项: {anniversary} (类型: {type(anniversary)})")
                continue
                
            if (anniversary.get("month") == current_month and 
                anniversary.get("day") == current_day):
                
                # 直接使用数据库中存储的特效配置
                effects = anniversary.get("effects", [])
                
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
