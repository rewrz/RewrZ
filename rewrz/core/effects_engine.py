"""
节日特效引擎领域服务。

负责：
- 公共节日年度实例生成
- 自定义纪念日读取与保存
- 当前命中节日解析
- 特效优先级与去重合并
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from lunar_python import Lunar, LunarYear, Solar
from sqlalchemy.orm import Session

from ..crud import setting as crud_setting
from ..schemas import SettingCreate
from ..schemas.setting import SettingUpdate

SETTING_PUBLIC_HOLIDAYS = "effects_public_holidays"
SETTING_CUSTOM_ANNIVERSARIES = "effects_custom_anniversaries"
SETTING_MANUAL_OVERRIDE = "effects_manual_override"
SETTING_SCHEDULE_RULES = "effects_schedule_rules"

EFFECT_SCENE_ALIASES = {
    "mourn": "memorial",
    "spring_festival": "spring_festival",
    "new_year": "new_year",
    "cherry_blossom": "cherry_blossom",
    "winter": "winter",
    "autumn": "autumn",
    "valentine": "valentine",
    "christmas": "christmas",
    "national_day": "national_day",
    "rainy_day": "rainy_day",
    "stormy": "stormy",
    "sunny": "sunny",
    "cloudy": "cloudy",
    "spring": "spring",
    "summer": "summer",
    "thunderstorm": "thunderstorm",
    "festive": "festive",
    "celebration": "celebration",
    "memorial": "memorial",
}

EFFECT_SCENE_PRESETS = {
    "festive": ["fireworks", "confetti", "lanterns", "golden_dust", "stars"],
    "mourn": ["grayscale", "candles", "floating_lights"],
    "spring_festival": ["lanterns", "firecrackers", "golden_dust", "embers"],
    "new_year": ["fireworks", "confetti", "golden_dust", "stars"],
    "cherry_blossom": ["sakura", "petals"],
    "winter": ["snow", "clouds", "moonlight"],
    "autumn": ["leaves"],
    "celebration": ["fireworks", "confetti", "golden_dust", "balloons"],
    "memorial": ["grayscale", "candles", "floating_lights"],
    "valentine": ["hearts", "petals", "sakura", "stars"],
    "christmas": ["snow", "fireworks", "floating_lights", "stars"],
    "national_day": ["fireworks", "lanterns", "golden_dust", "stars"],
    "rainy_day": ["rain", "clouds"],
    "stormy": ["rain", "thunder", "clouds"],
    "sunny": ["sunshine"],
    "cloudy": ["clouds"],
    "spring": ["sakura", "petals", "sunshine"],
    "summer": ["sunshine", "bubbles", "balloons"],
    "thunderstorm": ["thunder", "rain"],
}

AVAILABLE_EFFECTS = {
    "fireworks",
    "countdown_banner",
    "lanterns",
    "firecrackers",
    "confetti",
    "golden_dust",
    "floating_lights",
    "hearts",
    "balloons",
    "bubbles",
    "moonlight",
    "stars",
    "embers",
    "rice_grains",
    "red_packets",
    "ingots",
    "tangyuan",
    "dragon_shape",
    "willow_catkins",
    "gear_icons",
    "tie_icons",
    "dragon_boats",
    "zongzi",
    "star_bridge",
    "feathers",
    "paper_charms",
    "lotus_lights",
    "chalk_writing",
    "osmanthus",
    "dumplings",
    "tree_lights",
    "grayscale",
    "candles",
    "petals",
    "sakura",
    "snow",
    "leaves",
    "rain",
    "thunder",
    "clouds",
    "sunshine",
}

SOURCE_PRIORITY = {
    "custom": 4000,
    "manual": 3000,
    "public": 2000,
    "schedule": 1000,
}

PUBLIC_HOLIDAY_PRESETS: List[Dict[str, Any]] = [
    {
        "code": "new_year_day",
        "name": "元旦",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 1, "day": 1},
        "effect_scene": "new_year",
        "effects": ["countdown_banner", "fireworks", "confetti", "golden_dust", "stars"],
        "priority": 610,
    },
    {
        "code": "valentines_day",
        "name": "情人节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 2, "day": 14},
        "effect_scene": "valentine",
        "effects": ["hearts", "sakura", "petals", "stars"],
        "priority": 520,
    },
    {
        "code": "womens_day",
        "name": "国际妇女节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 3, "day": 8},
        "effect_scene": "celebration",
        "effects": ["petals", "confetti", "hearts", "balloons"],
        "priority": 500,
    },
    {
        "code": "labor_day",
        "name": "国际劳动节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 5, "day": 1},
        "effect_scene": "festive",
        "effects": ["gear_icons", "confetti", "fireworks", "golden_dust"],
        "priority": 540,
    },
    {
        "code": "youth_day",
        "name": "青年节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 5, "day": 4},
        "effect_scene": "celebration",
        "effects": ["confetti", "sunshine"],
        "priority": 470,
    },
    {
        "code": "childrens_day",
        "name": "国际儿童节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 6, "day": 1},
        "effect_scene": "celebration",
        "effects": ["balloons", "bubbles", "sunshine", "confetti"],
        "priority": 520,
    },
    {
        "code": "teachers_day",
        "name": "教师节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 9, "day": 10},
        "effect_scene": "celebration",
        "effects": ["chalk_writing", "petals", "confetti", "golden_dust", "stars"],
        "priority": 510,
    },
    {
        "code": "national_day",
        "name": "国庆节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 10, "day": 1},
        "effect_scene": "national_day",
        "effects": ["fireworks", "lanterns", "confetti", "golden_dust", "stars"],
        "priority": 800,
    },
    {
        "code": "christmas_day",
        "name": "圣诞节",
        "calendar_type": "solar_fixed",
        "date_rule": {"month": 12, "day": 25},
        "effect_scene": "christmas",
        "effects": ["snow", "floating_lights", "stars", "tree_lights", "golden_dust"],
        "priority": 580,
    },
    {
        "code": "mothers_day",
        "name": "母亲节",
        "calendar_type": "solar_weekday",
        "date_rule": {"month": 5, "week": 2, "weekday": 6},
        "effect_scene": "valentine",
        "effects": ["hearts", "petals", "sakura", "stars"],
        "priority": 550,
    },
    {
        "code": "fathers_day",
        "name": "父亲节",
        "calendar_type": "solar_weekday",
        "date_rule": {"month": 6, "week": 3, "weekday": 6},
        "effect_scene": "celebration",
        "effects": ["tie_icons", "balloons", "sunshine", "confetti", "stars"],
        "priority": 550,
    },
    {
        "code": "laba_festival",
        "name": "腊八节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 12, "day": 8},
        "effect_scene": "celebration",
        "effects": ["rice_grains", "floating_lights", "clouds", "golden_dust"],
        "priority": 620,
    },
    {
        "code": "little_new_year",
        "name": "小年",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 12, "day": 23},
        "effect_scene": "spring_festival",
        "effects": ["lanterns", "firecrackers", "golden_dust", "embers", "floating_lights"],
        "priority": 700,
    },
    {
        "code": "new_year_eve",
        "name": "除夕",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 12, "is_last_day": True},
        "effect_scene": "spring_festival",
        "effects": ["countdown_banner", "fireworks", "lanterns", "firecrackers", "golden_dust", "embers", "red_packets"],
        "priority": 920,
    },
    {
        "code": "spring_festival",
        "name": "春节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 1, "day": 1},
        "effect_scene": "spring_festival",
        "effects": ["lanterns", "firecrackers", "confetti", "golden_dust", "embers", "red_packets"],
        "priority": 950,
    },
    {
        "code": "spring_festival_day2",
        "name": "年初二",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 1, "day": 2},
        "effect_scene": "spring_festival",
        "effects": ["lanterns", "confetti", "golden_dust", "embers"],
        "priority": 820,
    },
    {
        "code": "spring_festival_day5",
        "name": "年初五",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 1, "day": 5},
        "effect_scene": "spring_festival",
        "effects": ["firecrackers", "confetti", "golden_dust", "embers", "ingots"],
        "priority": 810,
    },
    {
        "code": "spring_festival_day7",
        "name": "年初七",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 1, "day": 7},
        "effect_scene": "celebration",
        "effects": ["confetti", "sunshine", "balloons"],
        "priority": 760,
    },
    {
        "code": "lantern_festival",
        "name": "元宵节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 1, "day": 15},
        "effect_scene": "festive",
        "effects": ["lanterns", "confetti", "fireworks", "golden_dust", "stars", "floating_lights", "tangyuan"],
        "priority": 880,
    },
    {
        "code": "dragon_heads_raising_day",
        "name": "龙抬头",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 2, "day": 2},
        "effect_scene": "spring",
        "effects": ["dragon_shape", "clouds", "sunshine", "rain"],
        "priority": 600,
    },
    {
        "code": "qingming_festival",
        "name": "清明节",
        "calendar_type": "solar_term",
        "date_rule": {"term": "清明"},
        "effect_scene": "memorial",
        "effects": ["grayscale", "willow_catkins", "clouds", "floating_lights"],
        "priority": 860,
    },
    {
        "code": "dragon_boat_festival",
        "name": "端午节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 5, "day": 5},
        "effect_scene": "festive",
        "effects": ["dragon_boats", "zongzi", "lanterns", "confetti", "golden_dust", "floating_lights"],
        "priority": 760,
    },
    {
        "code": "qixi_festival",
        "name": "七夕节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 7, "day": 7},
        "effect_scene": "valentine",
        "effects": ["star_bridge", "feathers", "hearts", "sakura", "petals", "stars"],
        "priority": 700,
    },
    {
        "code": "zhongyuan_festival",
        "name": "中元节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 7, "day": 15},
        "effect_scene": "memorial",
        "effects": ["grayscale", "candles", "paper_charms", "lotus_lights", "floating_lights"],
        "priority": 840,
    },
    {
        "code": "mid_autumn_festival",
        "name": "中秋节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 8, "day": 15},
        "effect_scene": "festive",
        "effects": ["moonlight", "lanterns", "clouds", "floating_lights", "stars", "osmanthus"],
        "priority": 790,
    },
    {
        "code": "double_ninth_festival",
        "name": "重阳节",
        "calendar_type": "lunar_fixed",
        "date_rule": {"month": 9, "day": 9},
        "effect_scene": "autumn",
        "effects": ["leaves", "clouds", "floating_lights", "golden_dust"],
        "priority": 640,
    },
    {
        "code": "winter_solstice",
        "name": "冬至",
        "calendar_type": "solar_term",
        "date_rule": {"term": "冬至"},
        "effect_scene": "winter",
        "effects": ["snow", "clouds", "floating_lights", "moonlight", "dumplings"],
        "priority": 660,
    },
]


@dataclass
class ResolvedEffectRecord:
    source: str
    name: str
    scene: Optional[str]
    effects: List[str]
    priority: int
    payload: Dict[str, Any]


def normalize_effect_scene_name(scene: Optional[str]) -> Optional[str]:
    if not scene:
        return None
    normalized = str(scene).strip().lower()
    return EFFECT_SCENE_ALIASES.get(normalized, normalized)


def normalize_effects(effects: Optional[Iterable[Any]]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for effect in effects or []:
        key = str(effect or "").strip().lower()
        if not key or key not in AVAILABLE_EFFECTS or key in seen:
            continue
        normalized.append(key)
        seen.add(key)
    return normalized


def get_scene_effects(scene: Optional[str], explicit_effects: Optional[Iterable[Any]] = None) -> List[str]:
    normalized_explicit = normalize_effects(explicit_effects)
    if normalized_explicit:
        return normalized_explicit
    normalized_scene = normalize_effect_scene_name(scene)
    return list(EFFECT_SCENE_PRESETS.get(normalized_scene or "", []))


def _upsert_json_setting(
    db: Session,
    *,
    key: str,
    value: Dict[str, Any],
    description: str,
    category: str = "effects",
    type_name: str = "json",
) -> None:
    existing = crud_setting.get_setting(db, key=key)
    payload = {"value": value}
    if existing is None:
        crud_setting.create_setting(
            db,
            SettingCreate(
                key=key,
                value=payload,
                description=description,
                category=category,
                type=type_name,
            ),
        )
        return
    crud_setting.update_setting(
        db,
        key,
        SettingUpdate(
            value=payload,
            description=description,
            category=category,
            type=type_name,
        ),
    )


def _extract_json_setting(db: Session, key: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    setting = crud_setting.get_setting(db, key=key)
    if setting is None or not isinstance(setting.value, dict):
        return dict(default or {})
    value = setting.value.get("value")
    if isinstance(value, dict):
        return dict(value)
    return dict(default or {})


def _extract_json_list_setting(db: Session, key: str) -> List[Dict[str, Any]]:
    setting = crud_setting.get_setting(db, key=key)
    if setting is None or not isinstance(setting.value, dict):
        return []
    value = setting.value.get("value")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _nth_weekday_of_month(year: int, month: int, week: int, weekday: int) -> date:
    """
    weekday 取值与 Python 一致：周一 0，周日 6。
    """
    first = date(year, month, 1)
    day_offset = (weekday - first.weekday()) % 7
    target_day = 1 + day_offset + (max(1, week) - 1) * 7
    return date(year, month, target_day)


def _resolve_lunar_fixed_date_in_year(year: int, date_rule: Dict[str, Any]) -> date:
    lunar_month = int(date_rule["month"])
    matched_dates: List[date] = []

    for lunar_year in (year - 1, year, year + 1):
        if date_rule.get("is_last_day"):
            lunar_month_data = LunarYear.fromYear(lunar_year).getMonth(lunar_month)
            if lunar_month_data is None:
                continue
            solar_date = _solar_from_lunar(lunar_year, lunar_month, lunar_month_data.getDayCount())
        else:
            solar_date = _solar_from_lunar(lunar_year, lunar_month, int(date_rule["day"]))

        if solar_date.year == year:
            matched_dates.append(solar_date)

    if len(matched_dates) != 1:
        raise ValueError(f"无法在公历 {year} 年内唯一解析农历日期: {date_rule}")

    return matched_dates[0]


def _resolve_solar_term_date_in_year(year: int, term_name: str) -> date:
    current = date(year, 1, 1)
    end = date(year, 12, 31)
    while current <= end:
        current_lunar = Lunar.fromSolar(Solar.fromYmd(current.year, current.month, current.day)).getJieQi()
        if current_lunar == term_name:
            return current
        current += timedelta(days=1)

    raise ValueError(f"无法在公历 {year} 年内解析节气: {term_name}")


def _resolve_rule_to_date(year: int, calendar_type: str, date_rule: Dict[str, Any]) -> date:
    if calendar_type == "solar_fixed":
        return date(year, int(date_rule["month"]), int(date_rule["day"]))

    if calendar_type == "solar_weekday":
        return _nth_weekday_of_month(
            year,
            int(date_rule["month"]),
            int(date_rule["week"]),
            int(date_rule["weekday"]),
        )

    if calendar_type == "lunar_fixed":
        return _resolve_lunar_fixed_date_in_year(year, date_rule)

    if calendar_type == "solar_term":
        return _resolve_solar_term_date_in_year(year, str(date_rule["term"]))

    raise ValueError(f"不支持的日期规则类型: {calendar_type}")


def _solar_from_lunar(year: int, month: int, day: int) -> date:
    solar = Lunar.fromYmd(year, month, day).getSolar()
    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def build_public_holiday_catalog(year: int) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    generated_at = datetime.now().isoformat()
    for preset in PUBLIC_HOLIDAY_PRESETS:
        start_date = _resolve_rule_to_date(year, str(preset["calendar_type"]), dict(preset["date_rule"]))
        item = {
            "id": f"public-{year}-{preset['code']}",
            "code": preset["code"],
            "name": preset["name"],
            "source_type": "public",
            "preset_source": "system",
            "target_year": year,
            "calendar_type": preset["calendar_type"],
            "date_rule": dict(preset["date_rule"]),
            "start_at": start_date.isoformat(),
            "end_at": start_date.isoformat(),
            "effect_scene": normalize_effect_scene_name(preset["effect_scene"]),
            "effects": normalize_effects(preset.get("effects", [])),
            "enabled": True,
            "allow_override": True,
            "priority": int(preset.get("priority", 500)),
            "generated_at": generated_at,
        }
        items.append(item)

    items.sort(key=lambda item: (item["start_at"], -int(item["priority"]), item["code"]))
    return {
        "year": year,
        "generated_at": generated_at,
        "preset_count": len(PUBLIC_HOLIDAY_PRESETS),
        "items": items,
    }


def load_public_holiday_catalog(db: Session) -> Dict[str, Any]:
    return _extract_json_setting(db, SETTING_PUBLIC_HOLIDAYS, default={"items": []})


def save_public_holiday_catalog(db: Session, catalog: Dict[str, Any]) -> None:
    _upsert_json_setting(
        db,
        key=SETTING_PUBLIC_HOLIDAYS,
        value=catalog,
        description="公共节日年度实例清单",
    )


def rebuild_public_holiday_catalog(db: Session, year: int) -> Dict[str, Any]:
    catalog = build_public_holiday_catalog(year)
    save_public_holiday_catalog(db, catalog)
    return catalog


def ensure_public_holiday_catalog(db: Session, year: int) -> Dict[str, Any]:
    catalog = load_public_holiday_catalog(db)
    if int(catalog.get("year") or 0) == year and isinstance(catalog.get("items"), list):
        return catalog
    catalog = build_public_holiday_catalog(year)
    save_public_holiday_catalog(db, catalog)
    return catalog


def load_custom_anniversaries(db: Session) -> List[Dict[str, Any]]:
    return _extract_json_list_setting(db, SETTING_CUSTOM_ANNIVERSARIES)


def save_custom_anniversaries(db: Session, anniversaries: List[Dict[str, Any]]) -> None:
    _upsert_json_setting(
        db,
        key=SETTING_CUSTOM_ANNIVERSARIES,
        value={"items": anniversaries},
        description="自定义纪念日特效规则",
    )


def normalize_custom_anniversary_payloads(anniversaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for anniversary in anniversaries:
        if not isinstance(anniversary, dict):
            continue
        name = str(anniversary.get("name") or "").strip()
        if not name:
            continue
        date_type = str(anniversary.get("date_type") or anniversary.get("calendar_type") or "solar_fixed").strip()
        date_rule = anniversary.get("date_rule") if isinstance(anniversary.get("date_rule"), dict) else {}
        if date_type == "solar_fixed" and (not date_rule.get("month") or not date_rule.get("day")):
            month = anniversary.get("month")
            day = anniversary.get("day")
            if month and day:
                date_rule = {"month": int(month), "day": int(day)}
        scene = normalize_effect_scene_name(anniversary.get("effect_scene") or anniversary.get("type") or anniversary.get("scene"))
        normalized.append(
            {
                "id": str(anniversary.get("id") or f"custom-{uuid4().hex[:12]}"),
                "name": name,
                "source_type": "custom",
                "date_type": date_type,
                "calendar_type": date_type,
                "date_rule": date_rule,
                "effect_scene": scene,
                "effects": get_scene_effects(scene, anniversary.get("effects")),
                "enabled": bool(anniversary.get("enabled", True)),
                "priority": int(anniversary.get("priority") or 4000),
                "is_recurring": bool(anniversary.get("is_recurring", True)),
                "notes": str(anniversary.get("notes") or "").strip(),
            }
        )
    return normalized


def load_manual_override(db: Session) -> Dict[str, Any]:
    return _extract_json_setting(db, SETTING_MANUAL_OVERRIDE, default={})


def save_manual_override(db: Session, payload: Dict[str, Any]) -> None:
    _upsert_json_setting(
        db,
        key=SETTING_MANUAL_OVERRIDE,
        value=payload,
        description="手动特效覆盖状态",
    )


def load_schedule_rules(db: Session) -> List[Dict[str, Any]]:
    return _extract_json_list_setting(db, SETTING_SCHEDULE_RULES)


def save_schedule_rules(db: Session, schedules: List[Dict[str, Any]]) -> None:
    _upsert_json_setting(
        db,
        key=SETTING_SCHEDULE_RULES,
        value={"items": schedules},
        description="节日特效调度规则",
    )


def normalize_public_holiday_payloads(year: int, holidays: List[Dict[str, Any]]) -> Dict[str, Any]:
    base_catalog = build_public_holiday_catalog(year)
    base_by_code = {
        str(item["code"]): item
        for item in base_catalog["items"]
        if isinstance(item, dict) and item.get("code")
    }
    normalized_items: List[Dict[str, Any]] = []
    for holiday in holidays:
        if not isinstance(holiday, dict):
            continue
        code = str(holiday.get("code") or "").strip()
        base_item = base_by_code.get(code)
        if base_item is None:
            continue
        scene = normalize_effect_scene_name(holiday.get("effect_scene") or base_item.get("effect_scene"))
        effects = get_scene_effects(scene, holiday.get("effects") or base_item.get("effects"))
        normalized_items.append(
            {
                **base_item,
                "name": str(holiday.get("name") or base_item.get("name") or "").strip() or base_item["name"],
                "effect_scene": scene,
                "effects": effects,
                "enabled": bool(holiday.get("enabled", base_item.get("enabled", True))),
                "priority": int(holiday.get("priority") or base_item.get("priority") or 500),
            }
        )

    normalized_items.sort(key=lambda item: (item["start_at"], -int(item["priority"]), item["code"]))
    base_catalog["items"] = normalized_items
    base_catalog["preset_count"] = len(normalized_items)
    return base_catalog


def _match_record_on_date(record: Dict[str, Any], on_date: date) -> bool:
    if not bool(record.get("enabled", True)):
        return False

    start_at = _parse_iso_date(record.get("start_at"))
    end_at = _parse_iso_date(record.get("end_at"))
    if start_at and end_at:
        return start_at <= on_date <= end_at

    date_rule = record.get("date_rule")
    calendar_type = str(record.get("calendar_type") or record.get("date_type") or "").strip()
    if isinstance(date_rule, dict) and calendar_type:
        return _resolve_rule_to_date(on_date.year, calendar_type, date_rule) == on_date

    month = record.get("month")
    day = record.get("day")
    if month and day:
        return int(month) == on_date.month and int(day) == on_date.day

    return False


def _match_manual_override(payload: Dict[str, Any], on_date: date) -> Optional[ResolvedEffectRecord]:
    if not payload or not bool(payload.get("enabled", True)):
        return None
    expires_at = _parse_iso_date(payload.get("expires_at"))
    if expires_at and on_date > expires_at:
        return None
    scene = normalize_effect_scene_name(payload.get("scene") or payload.get("value"))
    effects = get_scene_effects(scene, payload.get("effects"))
    if not scene and not effects:
        return None
    return ResolvedEffectRecord(
        source="manual",
        name=str(payload.get("name") or "手动触发"),
        scene=scene,
        effects=effects,
        priority=int(payload.get("priority") or 3000),
        payload=payload,
    )


def _match_schedule_rule(payload: Dict[str, Any], on_date: date) -> Optional[ResolvedEffectRecord]:
    start_at = _parse_iso_date(payload.get("start_date") or payload.get("start_at"))
    end_at = _parse_iso_date(payload.get("end_date") or payload.get("end_at"))
    if start_at is None or end_at is None or not (start_at <= on_date <= end_at):
        return None
    scene = normalize_effect_scene_name(payload.get("scene") or payload.get("atmosphere"))
    effects = get_scene_effects(scene, payload.get("effects"))
    if not scene and not effects:
        return None
    return ResolvedEffectRecord(
        source="schedule",
        name=str(payload.get("name") or scene or "调度规则"),
        scene=scene,
        effects=effects,
        priority=int(payload.get("priority") or 1000),
        payload=payload,
    )


def _to_effect_record(record: Dict[str, Any], *, source: str) -> ResolvedEffectRecord:
    scene = normalize_effect_scene_name(record.get("effect_scene") or record.get("scene") or record.get("type"))
    effects = get_scene_effects(scene, record.get("effects"))
    return ResolvedEffectRecord(
        source=source,
        name=str(record.get("name") or record.get("code") or "未命名节日"),
        scene=scene,
        effects=effects,
        priority=int(record.get("priority") or 0),
        payload=record,
    )


def normalize_legacy_custom_anniversaries(anniversaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for anniversary in anniversaries:
        if not isinstance(anniversary, dict):
            continue
        month = anniversary.get("month")
        day = anniversary.get("day")
        name = str(anniversary.get("name") or "").strip()
        if not month or not day or not name:
            continue
        scene = normalize_effect_scene_name(anniversary.get("effect_scene") or anniversary.get("type"))
        normalized.append(
            {
                "id": str(anniversary.get("id") or f"custom-{uuid4().hex[:12]}"),
                "name": name,
                "source_type": "custom",
                "date_type": "solar_fixed",
                "calendar_type": "solar_fixed",
                "date_rule": {"month": int(month), "day": int(day)},
                "effect_scene": scene,
                "effects": get_scene_effects(scene, anniversary.get("effects")),
                "enabled": bool(anniversary.get("enabled", True)),
                "priority": int(anniversary.get("priority") or 4000),
                "is_recurring": bool(anniversary.get("is_recurring", True)),
                "notes": str(anniversary.get("notes") or "").strip(),
            }
        )
    return normalized


def resolve_active_effects_state(
    db: Session,
    *,
    on_date: Optional[date] = None,
    include_matches: bool = False,
) -> Dict[str, Any]:
    target_date = on_date or date.today()
    public_catalog = ensure_public_holiday_catalog(db, target_date.year)
    custom_anniversaries = load_custom_anniversaries(db)
    manual_override = load_manual_override(db)
    schedule_rules = load_schedule_rules(db)

    matched_records: List[ResolvedEffectRecord] = []

    for item in public_catalog.get("items", []):
        if isinstance(item, dict) and _match_record_on_date(item, target_date):
            matched_records.append(_to_effect_record(item, source="public"))

    for item in custom_anniversaries:
        if isinstance(item, dict) and _match_record_on_date(item, target_date):
            matched_records.append(_to_effect_record(item, source="custom"))

    manual_record = _match_manual_override(manual_override, target_date)
    if manual_record is not None:
        matched_records.append(manual_record)

    for rule in schedule_rules:
        if not isinstance(rule, dict):
            continue
        schedule_record = _match_schedule_rule(rule, target_date)
        if schedule_record is not None:
            matched_records.append(schedule_record)

    if not matched_records:
        return {
            "scene": None,
            "source": "none",
            "effects": [],
            "body_classes": [],
            "label": "",
            "matched_items": [] if include_matches else None,
        }

    matched_records.sort(
        key=lambda record: (
            -SOURCE_PRIORITY.get(record.source, 0),
            -record.priority,
            record.name,
        )
    )
    primary = matched_records[0]

    merged_effects: List[str] = []
    seen_effects: set[str] = set()
    for record in matched_records:
        for effect in record.effects:
            if effect in seen_effects:
                continue
            seen_effects.add(effect)
            merged_effects.append(effect)

    payload = {
        "scene": primary.scene,
        "source": primary.source,
        "effects": merged_effects,
        "body_classes": [f"atmosphere-{primary.scene}"] if primary.scene else [],
        "label": primary.name,
    }
    if include_matches:
        payload["matched_items"] = [
            {
                "name": record.name,
                "source": record.source,
                "scene": record.scene,
                "effects": record.effects,
                "priority": record.priority,
            }
            for record in matched_records
        ]
    return payload
