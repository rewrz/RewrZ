"""
主题调度API
处理主题调度的保存和管理功能
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, date

from ..core.database import get_db
from ..crud import setting as crud_setting
from ..core.security import ensure_admin_user, get_current_user, verify_csrf_token
from ..schemas import User, SettingUpdate  # 这里已经正确导入了SettingUpdate
from ..schemas import SettingCreate
from .themes import normalize_atmosphere_name

router = APIRouter()


class ThemeScheduleItem(BaseModel):
    start_date: str
    end_date: str
    atmosphere: str


class ThemeScheduleRequest(BaseModel):
    schedules: List[Dict[str, Any]]


async def save_theme_schedule(
    request: Request,
    schedule_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """保存主题调度设置"""
    try:
        verify_csrf_token(request, csrf_token)
        ensure_admin_user(current_user)
        # 从请求数据中获取调度列表
        schedules = schedule_data.get("schedules", [])
        
        # 验证日期格式
        validated_schedules = []
        for item in schedules:
            try:
                # 验证日期格式
                start_date = datetime.strptime(item['start_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(item['end_date'], '%Y-%m-%d').date()
                
                # 验证日期逻辑
                if end_date < start_date:
                    raise ValueError(f"结束日期不能早于开始日期: {item['start_date']} - {item['end_date']}")
                
                validated_schedules.append({
                    'start_date': item['start_date'],
                    'end_date': item['end_date'],
                    'atmosphere': item['atmosphere']
                })
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"日期格式错误: {str(e)}")
            except KeyError as e:
                raise HTTPException(status_code=400, detail=f"缺少必要字段: {str(e)}")
        
        # 保存到数据库（首次创建与更新都支持）
        existing = crud_setting.get_setting(db, key="theme_schedule")
        if existing:
            crud_setting.update_setting(
                db=db,
                key="theme_schedule",
                setting_update=SettingUpdate(value={"value": validated_schedules})
            )
        else:
            crud_setting.create_setting(
                db=db,
                setting=SettingCreate(
                    key="theme_schedule",
                    value={"value": validated_schedules},
                    description="主题自动调度配置"
                )
            )
        
        return {
            "success": True,
            "message": f"已保存 {len(validated_schedules)} 个主题调度规则",
            "schedules": validated_schedules
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存主题调度失败: {str(e)}")


@router.get("/theme-schedule/current")
async def get_current_theme_schedule(
    db: Session = Depends(get_db)
):
    """获取当前生效的主题调度"""
    try:
        # 获取所有调度规则
        schedule_setting = crud_setting.get_setting(db, key="theme_schedule")
        if schedule_setting and isinstance(schedule_setting.value, dict):
            schedules = schedule_setting.value.get("value", [])
        else:
            schedules = []
        
        if not schedules:
            return {"current_schedule": None, "message": "没有设置主题调度"}
        
        # 获取当前日期
        today = date.today()
        current_schedule = None
        
        # 查找当前生效的调度
        for schedule in schedules:
            try:
                start_date = datetime.strptime(schedule['start_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(schedule['end_date'], '%Y-%m-%d').date()
                
                if start_date <= today <= end_date:
                    current_schedule = {
                        **schedule,
                        "normalized_atmosphere": normalize_atmosphere_name(schedule.get("atmosphere"))
                    }
                    break
            except (ValueError, KeyError):
                continue
        
        return {
            "current_schedule": current_schedule,
            "all_schedules": schedules,
            "today": today.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取主题调度失败: {str(e)}")


async def clear_theme_schedule(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """清除所有主题调度设置"""
    try:
        verify_csrf_token(request, csrf_token)
        ensure_admin_user(current_user)
        existing = crud_setting.get_setting(db, key="theme_schedule")
        if existing:
            crud_setting.update_setting(
                db=db,
                key="theme_schedule",
                setting_update=SettingUpdate(value={"value": []})
            )
        else:
            crud_setting.create_setting(
                db=db,
                setting=SettingCreate(
                    key="theme_schedule",
                    value={"value": []},
                    description="主题自动调度配置"
                )
            )
        
        return {
            "success": True,
            "message": "已清除所有主题调度设置"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除主题调度失败: {str(e)}")


@router.get("/atmosphere-themes")
async def get_atmosphere_themes():
    """获取可用的氛围主题列表"""
    atmosphere_themes = {
        "spring": {
            "name": "春季氛围",
            "description": "樱花飞舞，春意盎然",
            "effects": ["sakura", "petals", "sunshine"],
            "colors": {
                "primary": "#ff69b4",
                "secondary": "#98fb98",
                "accent": "#ffd700"
            }
        },
        "summer": {
            "name": "夏季氛围", 
            "description": "阳光明媚，活力四射",
            "effects": ["sunshine"],
            "colors": {
                "primary": "#ff6347",
                "secondary": "#87ceeb",
                "accent": "#ffd700"
            }
        },
        "autumn": {
            "name": "秋季氛围",
            "description": "落叶纷飞，金桂飘香",
            "effects": ["leaves"],
            "colors": {
                "primary": "#cd853f",
                "secondary": "#daa520",
                "accent": "#ff8c00"
            }
        },
        "winter": {
            "name": "冬季氛围",
            "description": "雪花飘飘，银装素裹",
            "effects": ["snow", "clouds"],
            "colors": {
                "primary": "#4682b4",
                "secondary": "#b0c4de",
                "accent": "#87ceeb"
            }
        },
        "rainy": {
            "name": "雨季氛围",
            "description": "细雨绵绵，诗意朦胧",
            "effects": ["rain", "clouds"],
            "colors": {
                "primary": "#708090",
                "secondary": "#778899",
                "accent": "#4682b4"
            }
        },
        "stormy": {
            "name": "暴雨氛围",
            "description": "雷电交加，气势磅礴",
            "effects": ["thunder", "rain", "clouds"],
            "colors": {
                "primary": "#2f4f4f",
                "secondary": "#696969",
                "accent": "#4169e1"
            }
        },
        "festive": {
            "name": "节日氛围",
            "description": "烟花绽放，喜庆热闹",
            "effects": ["fireworks", "confetti", "lanterns"],
            "colors": {
                "primary": "#dc143c",
                "secondary": "#ffd700",
                "accent": "#ff69b4"
            }
        },
        "peaceful": {
            "name": "宁静氛围",
            "description": "云雾缭绕，静谧安详",
            "effects": ["clouds"],
            "colors": {
                "primary": "#9370db",
                "secondary": "#dda0dd",
                "accent": "#e6e6fa"
            }
        }
    }
    
    return {
        "atmosphere_themes": atmosphere_themes,
        "total_count": len(atmosphere_themes)
    }
