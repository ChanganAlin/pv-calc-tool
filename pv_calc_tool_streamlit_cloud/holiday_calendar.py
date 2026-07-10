from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class DailyLoadFactor:
    date: date
    day_type: str
    is_workday: bool
    load_factor: float
    note: str


def _ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _as_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return pd.to_datetime(value).date()


def _date_range(start: Any, end: Any) -> set[date]:
    start_date = _as_date(start)
    end_date = _as_date(end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    return set(pd.date_range(start_date, end_date, freq="D").date)


def load_holiday_config(path: str | Path) -> pd.DataFrame:
    """读取可编辑的法定节假日/调休日配置。"""
    config_path = Path(path)
    if not config_path.exists():
        return pd.DataFrame(columns=["date", "type", "name", "load_factor", "is_workday"])
    df = pd.read_csv(config_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["load_factor"] = pd.to_numeric(df["load_factor"], errors="coerce").fillna(1.0).clip(0, 1)
    df["is_workday"] = df["is_workday"].astype(str).str.lower().isin(["true", "1", "yes", "是"])
    return df


def build_holiday_calendar_config(
    year: int,
    holiday_df: pd.DataFrame,
    weekend_mode: str,
    weekend_load_factor: float,
    legal_holiday_load_factor: float,
    spring_enabled: bool,
    spring_start: date | None,
    spring_end: date | None,
    spring_load_factor: float,
    maintenance_enabled: bool,
    maintenance_start: date | None,
    maintenance_end: date | None,
    maintenance_load_factor: float,
    custom_periods: list[dict] | None = None,
    force_apply_to_curve: bool = False,
) -> dict:
    """构建供消纳计算调用的节假日与停产日历配置。"""
    holiday_map: dict[date, dict] = {}
    adjusted_workday_map: dict[date, dict] = {}
    if holiday_df is not None and not holiday_df.empty:
        for _, row in holiday_df.iterrows():
            day = _as_date(row["date"])
            item = {
                "type": str(row.get("type", "")),
                "name": str(row.get("name", "")),
                "load_factor": _ratio(row.get("load_factor", legal_holiday_load_factor)),
                "is_workday": bool(row.get("is_workday", False)),
            }
            if item["type"] == "adjusted_workday" or item["is_workday"]:
                adjusted_workday_map[day] = item
            else:
                holiday_map[day] = item

    custom_ranges: list[dict] = []
    for item in custom_periods or []:
        if not item.get("enabled", True):
            continue
        try:
            days = _date_range(item["start_date"], item["end_date"])
        except Exception:
            continue
        custom_ranges.append(
            {
                "name": str(item.get("name", "自定义停产/低负荷")),
                "days": days,
                "load_factor": _ratio(item.get("load_factor", 0.1)),
                "type": str(item.get("type", "custom_stop")),
            }
        )

    spring_days = _date_range(spring_start, spring_end) if spring_enabled and spring_start and spring_end else set()
    maintenance_days = _date_range(maintenance_start, maintenance_end) if maintenance_enabled and maintenance_start and maintenance_end else set()

    return {
        "year": int(year),
        "weekend_mode": weekend_mode,
        "weekend_load_factor": _ratio(weekend_load_factor),
        "legal_holiday_load_factor": _ratio(legal_holiday_load_factor),
        "spring_days": spring_days,
        "spring_load_factor": _ratio(spring_load_factor),
        "maintenance_days": maintenance_days,
        "maintenance_load_factor": _ratio(maintenance_load_factor),
        "custom_ranges": custom_ranges,
        "holiday_map": holiday_map,
        "adjusted_workday_map": adjusted_workday_map,
        "force_apply_to_curve": bool(force_apply_to_curve),
    }


def calculate_daily_load_factor(day: date, config: dict) -> DailyLoadFactor:
    """按优先级计算某一天的负荷系数、日期类型和说明。"""
    day = _as_date(day)

    for item in config.get("custom_ranges", []):
        if day in item["days"]:
            return DailyLoadFactor(day, item.get("type", "custom_stop"), False, item["load_factor"], item["name"])

    if day in config.get("spring_days", set()):
        return DailyLoadFactor(day, "spring_festival_shutdown", False, config["spring_load_factor"], "春节停产期")

    if day in config.get("maintenance_days", set()):
        return DailyLoadFactor(day, "maintenance_shutdown", False, config["maintenance_load_factor"], "年度检修停产")

    adjusted = config.get("adjusted_workday_map", {}).get(day)
    if adjusted:
        return DailyLoadFactor(day, "adjusted_workday", True, 1.0, adjusted.get("name", "调休补班日"))

    holiday = config.get("holiday_map", {}).get(day)
    if holiday:
        return DailyLoadFactor(
            day,
            "legal_holiday",
            False,
            _ratio(holiday.get("load_factor", config["legal_holiday_load_factor"])),
            holiday.get("name", "法定节假日"),
        )

    if day.weekday() >= 5:
        return DailyLoadFactor(day, "weekend", False, config["weekend_load_factor"], config.get("weekend_mode", "周末"))

    return DailyLoadFactor(day, "workday", True, 1.0, "正常工作日")


def calculate_baseline_load_factor(day: date, config: dict) -> float:
    """理论正常生产系数：只考虑周末设置和调休补班，不考虑节假日/停产。"""
    day = _as_date(day)
    if day in config.get("adjusted_workday_map", {}):
        return 1.0
    if day.weekday() >= 5:
        return config["weekend_load_factor"]
    return 1.0


def build_calendar_table(year: int, config: dict) -> pd.DataFrame:
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D").date
    rows = []
    for day in days:
        factor = calculate_daily_load_factor(day, config)
        baseline = calculate_baseline_load_factor(day, config)
        rows.append(
            {
                "日期": day.isoformat(),
                "日期类型": factor.day_type,
                "是否工作日": factor.is_workday,
                "负荷系数": factor.load_factor,
                "基准负荷系数": baseline,
                "说明": factor.note,
                "所属月份": day.month,
            }
        )
    table = pd.DataFrame(rows)
    month_factor = table.groupby("所属月份").apply(
        lambda g: float(g["负荷系数"].sum() / g["基准负荷系数"].sum()) if g["基准负荷系数"].sum() > 0 else 1.0
    )
    table["月度修正系数"] = table["所属月份"].map(month_factor).fillna(1.0).clip(lower=0)
    return table


def monthly_adjustment_table(year: int, config: dict) -> pd.DataFrame:
    calendar = build_calendar_table(year, config)
    grouped = calendar.groupby("所属月份", as_index=False).agg(
        实际负荷系数合计=("负荷系数", "sum"),
        基准负荷系数合计=("基准负荷系数", "sum"),
        年度节假日天数=("日期类型", lambda s: int((s == "legal_holiday").sum())),
        周末停产天数=("日期类型", lambda s: int((s == "weekend").sum()) if config.get("weekend_load_factor", 1.0) < 0.2 else 0),
        春节停产天数=("日期类型", lambda s: int((s == "spring_festival_shutdown").sum())),
        检修停产天数=("日期类型", lambda s: int((s == "maintenance_shutdown").sum())),
        自定义停产天数=("日期类型", lambda s: int(s.astype(str).str.startswith("custom").sum())),
    )
    grouped["节假日修正系数"] = (grouped["实际负荷系数合计"] / grouped["基准负荷系数合计"]).fillna(1.0).clip(lower=0)
    return grouped


def calendar_summary(calendar_table: pd.DataFrame, config: dict) -> dict:
    low_load_days = int((calendar_table["负荷系数"] < 1).sum())
    return {
        "年度节假日天数": int((calendar_table["日期类型"] == "legal_holiday").sum()),
        "周末停产天数": int((calendar_table["日期类型"] == "weekend").sum()) if config.get("weekend_load_factor", 1.0) < 0.2 else 0,
        "春节停产天数": int((calendar_table["日期类型"] == "spring_festival_shutdown").sum()),
        "检修停产天数": int((calendar_table["日期类型"] == "maintenance_shutdown").sum()),
        "自定义停产天数": int(calendar_table["日期类型"].astype(str).str.startswith("custom").sum()),
        "年度停产/低负荷天数": low_load_days,
    }
