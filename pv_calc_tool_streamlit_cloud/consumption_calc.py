from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from modules.holiday_calendar import build_calendar_table, calendar_summary, monthly_adjustment_table

TOU_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "tou_period_config.csv"


@dataclass
class ConsumptionResult:
    annual_consumption_kwh: float
    monthly_average_kwh: float
    daytime_consumption_kwh: float
    pv_generation_kwh: float
    self_use_kwh: float
    feed_in_kwh: float
    self_use_ratio: float
    feed_in_ratio: float
    risk_note: str
    mode: str = "快速估算模式"
    annual_holiday_days: int = 0
    weekend_shutdown_days: int = 0
    spring_shutdown_days: int = 0
    maintenance_shutdown_days: int = 0
    custom_shutdown_days: int = 0
    low_load_days: int = 0
    pre_adjust_self_use_ratio: float | None = None
    post_adjust_self_use_ratio: float | None = None
    pre_adjust_feed_in_ratio: float | None = None
    post_adjust_feed_in_ratio: float | None = None
    holiday_extra_feed_in_kwh: float = 0.0
    holiday_impact_note: str = ""
    data_quality_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


PRODUCTION_CAPS = {
    "三班连续生产": 0.95,
    "连续生产": 0.95,
    "三班制": 0.95,
    "双班制": 0.85,
    "单班制": 0.75,
    "周末停产": 0.65,
    "季节性停产": 0.55,
}

MONTHLY_PV_FACTORS = np.array([0.065, 0.070, 0.085, 0.095, 0.105, 0.110, 0.110, 0.105, 0.095, 0.085, 0.075, 0.065])
MONTHLY_PV_FACTORS = MONTHLY_PV_FACTORS / MONTHLY_PV_FACTORS.sum()
MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=float)


def _ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    for col in columns:
        name = str(col).strip().lower()
        for alias in aliases:
            if alias.lower() in name:
                return col
    return None


def normalize_month_value(value) -> int | None:
    """把 1、1月、2026-01、2026年1月、日期格式等统一为 1-12。"""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return int(value.month)
    if isinstance(value, (int, np.integer)):
        month = int(value)
        return month if 1 <= month <= 12 else None
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        month = int(value)
        return month if 1 <= month <= 12 else None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        month = int(text)
        return month if 1 <= month <= 12 else None
    match = pd.Series([text]).str.extract(r"(?:\d{4}\s*年\s*)?(\d{1,2})\s*月").iloc[0, 0]
    if pd.notna(match):
        month = int(match)
        return month if 1 <= month <= 12 else None
    match = pd.Series([text]).str.extract(r"^\d{4}[-/](\d{1,2})").iloc[0, 0]
    if pd.notna(match):
        month = int(match)
        return month if 1 <= month <= 12 else None
    dt = pd.to_datetime(text, errors="coerce")
    if pd.notna(dt):
        return int(dt.month)
    return None


def infer_curve_interval_minutes(curve: pd.DataFrame) -> float:
    times = pd.to_datetime(curve["time"]).sort_values()
    if len(times) < 2:
        return 15.0
    minutes = times.diff().dropna().dt.total_seconds() / 60
    median = float(minutes.median()) if not minutes.empty else 15.0
    return median if median > 0 else 15.0


def infer_time_interval(df: pd.DataFrame, time_col: str = "time") -> dict:
    times = pd.to_datetime(df[time_col], errors="coerce").dropna().sort_values()
    if len(times) < 2:
        return {"interval_minutes": 15.0, "is_regular": True, "abnormal_interval_count": 0, "duplicate_count": 0}
    diffs = times.diff().dropna().dt.total_seconds() / 60
    median = float(diffs.median()) if not diffs.empty else 15.0
    abnormal = int(((diffs - median).abs() > max(1.0, median * 0.1)).sum())
    duplicate_count = int(pd.to_datetime(df[time_col], errors="coerce").duplicated().sum())
    return {
        "interval_minutes": median if median > 0 else 15.0,
        "is_regular": abnormal == 0,
        "abnormal_interval_count": abnormal,
        "duplicate_count": duplicate_count,
    }


def resample_energy_curve(curve: pd.DataFrame, target_minutes: float) -> pd.DataFrame:
    """把 interval_kwh 曲线重采样到目标粒度，保持总电量近似守恒。"""
    work = curve[["time", "interval_kwh"]].copy()
    work["time"] = pd.to_datetime(work["time"])
    work = work.sort_values("time").set_index("time")
    rule = f"{max(int(round(target_minutes)), 1)}min"
    resampled = work["interval_kwh"].resample(rule).sum().fillna(0).reset_index()
    return resampled.rename(columns={"interval_kwh": "interval_kwh"})


def read_curve_file(uploaded_file) -> pd.DataFrame:
    """读取负荷/PV曲线文件：支持 CSV、Excel。"""
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.read()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(BytesIO(data), encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(BytesIO(data), encoding="gbk")
    return pd.read_excel(BytesIO(data))


def load_tou_period_config(path: str | Path = TOU_CONFIG_PATH) -> pd.DataFrame:
    config_path = Path(path)
    if not config_path.exists():
        return pd.DataFrame(columns=["province", "period_name", "start_time", "end_time", "is_pv_period", "pv_weight", "note"])
    df = pd.read_csv(config_path, encoding="utf-8-sig")
    df["is_pv_period"] = df["is_pv_period"].astype(str).str.lower().isin(["true", "1", "yes", "是"])
    df["pv_weight"] = pd.to_numeric(df["pv_weight"], errors="coerce").fillna(0).clip(0, 1)
    return df


def tou_weights_for_province(province: str, config: pd.DataFrame | None = None) -> dict[str, float]:
    table = load_tou_period_config() if config is None else config
    if table.empty:
        return {"尖": 1.0, "峰": 1.0, "平": 0.6, "谷": 0.0}
    province_rows = table[table["province"] == province]
    rows = province_rows if not province_rows.empty else table[table["province"] == "默认"]
    return {str(row["period_name"]): float(row["pv_weight"]) for _, row in rows.iterrows()}


def normalize_power_or_energy_curve(df: pd.DataFrame, value_kind: str = "load") -> pd.DataFrame:
    """曲线标准化：识别时间、kW 或 kWh 字段，并统一输出 interval_kwh。"""
    work = df.dropna(how="all").copy()
    time_col = _find_column(list(work.columns), ["时间", "日期", "time", "date"])
    if time_col is None:
        raise ValueError("曲线文件缺少时间字段。")

    if value_kind == "pv":
        kw_col = _find_column(list(work.columns), ["光伏kw", "pv_kw", "出力kw", "功率kw", "kw"])
        kwh_col = _find_column(list(work.columns), ["光伏kwh", "pv_kwh", "发电量", "电量kwh", "kwh"])
    else:
        kw_col = _find_column(list(work.columns), ["负荷kw", "load_kw", "需量kw", "功率kw", "kw"])
        kwh_col = _find_column(list(work.columns), ["用电量kwh", "负荷kwh", "load_kwh", "电量kwh", "kwh"])

    if kw_col is None and kwh_col is None:
        raise ValueError("曲线文件缺少负荷kW/用电量kWh字段。")

    work["_time"] = pd.to_datetime(work[time_col])
    work = work.dropna(subset=["_time"]).sort_values("_time").reset_index(drop=True)
    interval_hours = work["_time"].diff().dt.total_seconds().median() / 3600
    if pd.isna(interval_hours) or interval_hours <= 0:
        interval_hours = 0.25

    result = pd.DataFrame({"time": work["_time"]})
    if kwh_col is not None:
        result["interval_kwh"] = pd.to_numeric(work[kwh_col], errors="coerce").fillna(0).clip(lower=0)
    else:
        kw = pd.to_numeric(work[kw_col], errors="coerce").fillna(0).clip(lower=0)
        # 该时段电量 = 该时段平均功率(kW) * 时段小时数
        result["interval_kwh"] = kw * interval_hours
    return result


def generate_pv_curve_for_timestamps(timestamps: pd.Series, annual_pv_generation_kwh: float) -> pd.DataFrame:
    """自动生成光伏逐时/15分钟出力曲线：用白天钟形曲线分配年发电量。"""
    ts = pd.to_datetime(timestamps)
    hours = ts.dt.hour + ts.dt.minute / 60
    daylight = (hours >= 6) & (hours <= 18)
    shape = np.where(daylight, np.sin((hours - 6) / 12 * np.pi), 0.0)
    shape = np.maximum(shape, 0.0)
    if shape.sum() <= 0:
        interval = np.zeros(len(ts))
    else:
        interval = shape / shape.sum() * max(float(annual_pv_generation_kwh), 0.0)
    return pd.DataFrame({"time": ts, "interval_kwh": interval})


def _holiday_load_ratio(value: float) -> float:
    return _ratio(value)


def _apply_holiday_adjustment_to_curve(
    table: pd.DataFrame,
    holiday_shutdown_days: float,
    holiday_load_ratio: float,
) -> pd.DataFrame:
    """没有具体日期时，按光伏出力较高的日期做保守节假日低负荷修正。"""
    holiday_days = int(max(float(holiday_shutdown_days), 0.0))
    load_ratio = _holiday_load_ratio(holiday_load_ratio)
    if holiday_days <= 0 or load_ratio >= 1 or table.empty:
        table["holiday_adjusted"] = False
        return table

    result = table.copy()
    result["date"] = pd.to_datetime(result["time"]).dt.date
    daily_pv = result.groupby("date")["pv_kwh"].sum().sort_values(ascending=False)
    holiday_dates = set(daily_pv.head(min(holiday_days, len(daily_pv))).index)
    result["holiday_adjusted"] = result["date"].isin(holiday_dates)
    result.loc[result["holiday_adjusted"], "load_kwh"] *= load_ratio
    result = result.drop(columns=["date"])
    return result


def _apply_calendar_to_curve(table: pd.DataFrame, calendar_table: pd.DataFrame) -> pd.DataFrame:
    if calendar_table is None or calendar_table.empty or table.empty:
        table["holiday_adjusted"] = False
        table["calendar_load_factor"] = 1.0
        return table
    factor_map = dict(zip(pd.to_datetime(calendar_table["日期"]).dt.date, calendar_table["负荷系数"]))
    result = table.copy()
    dates = pd.to_datetime(result["time"]).dt.date
    result["calendar_load_factor"] = dates.map(factor_map).fillna(1.0).astype(float)
    result["holiday_adjusted"] = result["calendar_load_factor"] < 0.999
    result["load_kwh"] = result["load_kwh"] * result["calendar_load_factor"]
    return result


def build_consumption_risks(
    self_use_ratio: float,
    feed_in_ratio: float,
    monthly_consumption: list[float] | None,
    holiday_shutdown_days: float,
    capacity_kwp: float,
    daytime_consumption_kwh: float,
    holiday_summary: dict | None = None,
    pre_adjust_self_use_ratio: float | None = None,
) -> list[str]:
    """消纳风险判断：按消纳比例、季节波动、停产天数和容量/负荷关系输出提示。"""
    risks: list[str] = []
    if self_use_ratio < 0.70:
        risks.append("自用比例低于70%，提示装机偏大或负荷不足。")
    if feed_in_ratio > 0.30:
        risks.append("余电比例高于30%，提示收益对上网电价敏感。")
    if monthly_consumption:
        positives = [v for v in monthly_consumption if v > 0]
        if positives and max(positives) / min(positives) > 2:
            risks.append("月用电量最大值/最小值大于2，提示季节性波动风险。")
    if holiday_shutdown_days > 10:
        risks.append("春节或假期停产超过10天，提示节假日余电风险。")
    daytime_avg_load_kw = daytime_consumption_kwh / (365 * 10) if daytime_consumption_kwh > 0 else 0.0
    if daytime_avg_load_kw > 0 and capacity_kwp > daytime_avg_load_kw * 0.8:
        risks.append("光伏装机容量超过企业白天平均负荷的80%，提示消纳压力较大。")
    summary = holiday_summary or {}
    if summary.get("春节停产天数", 0) > 7:
        risks.append("春节停产时间较长，春节期间可能出现较高余电上网。")
    if summary.get("周末停产天数", 0) > 0 and daytime_avg_load_kw > 0 and capacity_kwp > daytime_avg_load_kw * 0.6:
        risks.append("周末停产将显著降低光伏自用比例，建议复核周末负荷。")
    if summary.get("年度停产/低负荷天数", 0) > 30:
        risks.append("年度低负荷天数较多，消纳能力存在明显波动风险。")
    if pre_adjust_self_use_ratio is not None and pre_adjust_self_use_ratio - self_use_ratio > 0.10:
        risks.append("节假日和停产因素对消纳影响较大，建议采用15分钟负荷曲线进行复核。")
    return risks or ["消纳比例处于常规可接受区间，建议结合逐时负荷曲线继续复核。"]


def result_from_energy(
    mode: str,
    annual_consumption_kwh: float,
    daytime_consumption_kwh: float,
    pv_generation_kwh: float,
    self_use_kwh: float,
    monthly_consumption: list[float] | None,
    holiday_shutdown_days: float,
    capacity_kwp: float,
    holiday_summary: dict | None = None,
    pre_adjust_self_use_ratio: float | None = None,
    pre_adjust_feed_in_ratio: float | None = None,
    holiday_extra_feed_in_kwh: float = 0.0,
    data_quality_note: str = "",
) -> ConsumptionResult:
    """消纳结果汇总：统一计算比例和风险提示。"""
    pv_generation_kwh = max(float(pv_generation_kwh), 0.0)
    self_use_kwh = min(max(float(self_use_kwh), 0.0), pv_generation_kwh)
    feed_in_kwh = max(pv_generation_kwh - self_use_kwh, 0.0)
    self_use_ratio = _ratio(self_use_kwh / pv_generation_kwh) if pv_generation_kwh else 0.0
    feed_in_ratio = _ratio(feed_in_kwh / pv_generation_kwh) if pv_generation_kwh else 0.0
    risks = build_consumption_risks(
        self_use_ratio,
        feed_in_ratio,
        monthly_consumption,
        holiday_shutdown_days,
        capacity_kwp,
        daytime_consumption_kwh,
        holiday_summary,
        pre_adjust_self_use_ratio,
    )
    summary = holiday_summary or {}
    return ConsumptionResult(
        annual_consumption_kwh=annual_consumption_kwh,
        monthly_average_kwh=annual_consumption_kwh / 12 if annual_consumption_kwh else 0.0,
        daytime_consumption_kwh=daytime_consumption_kwh,
        pv_generation_kwh=pv_generation_kwh,
        self_use_kwh=self_use_kwh,
        feed_in_kwh=feed_in_kwh,
        self_use_ratio=self_use_ratio,
        feed_in_ratio=feed_in_ratio,
        risk_note="；".join(risks),
        mode=mode,
        annual_holiday_days=int(summary.get("年度节假日天数", 0)),
        weekend_shutdown_days=int(summary.get("周末停产天数", 0)),
        spring_shutdown_days=int(summary.get("春节停产天数", 0)),
        maintenance_shutdown_days=int(summary.get("检修停产天数", 0)),
        custom_shutdown_days=int(summary.get("自定义停产天数", 0)),
        low_load_days=int(summary.get("年度停产/低负荷天数", 0)),
        pre_adjust_self_use_ratio=pre_adjust_self_use_ratio if pre_adjust_self_use_ratio is not None else self_use_ratio,
        post_adjust_self_use_ratio=self_use_ratio,
        pre_adjust_feed_in_ratio=pre_adjust_feed_in_ratio if pre_adjust_feed_in_ratio is not None else feed_in_ratio,
        post_adjust_feed_in_ratio=feed_in_ratio,
        holiday_extra_feed_in_kwh=max(float(holiday_extra_feed_in_kwh), 0.0),
        holiday_impact_note=(
            f"节假日/停产修正使余电增加约 {max(float(holiday_extra_feed_in_kwh), 0.0):,.0f} kWh。"
            if holiday_extra_feed_in_kwh > 0
            else "节假日/停产修正对余电影响较小。"
        ),
        data_quality_note=data_quality_note,
    )


def calculate_precise_consumption(
    load_curve: pd.DataFrame,
    annual_pv_generation_kwh: float,
    pv_curve: pd.DataFrame | None,
    capacity_kwp: float,
    holiday_shutdown_days: float = 0.0,
    holiday_load_ratio: float = 0.0,
    holiday_calendar_config: dict | None = None,
    force_holiday_adjustment: bool = False,
) -> tuple[ConsumptionResult, pd.DataFrame]:
    """精确模式：逐时间点计算 min(负荷电量, 光伏发电量)。"""
    load = load_curve[["time", "interval_kwh"]].rename(columns={"interval_kwh": "load_kwh"}).copy()
    load_quality = infer_time_interval(load, "time")
    pv_quality = None
    resampled = False
    if load_quality["duplicate_count"] > 0:
        load = load.groupby("time", as_index=False)["load_kwh"].sum()
    if pv_curve is None:
        pv = generate_pv_curve_for_timestamps(load["time"], annual_pv_generation_kwh)
    else:
        pv_quality = infer_time_interval(pv_curve, "time")
        if pv_quality["duplicate_count"] > 0:
            pv_curve = pv_curve.groupby("time", as_index=False)["interval_kwh"].sum()
        load_interval = infer_curve_interval_minutes(load_curve)
        pv_interval = infer_curve_interval_minutes(pv_curve)
        target_interval = min(load_interval, pv_interval)
        if abs(load_interval - pv_interval) > max(1.0, target_interval * 0.10):
            load_curve = resample_energy_curve(load_curve, target_interval)
            pv_curve = resample_energy_curve(pv_curve, target_interval)
            load = load_curve[["time", "interval_kwh"]].rename(columns={"interval_kwh": "load_kwh"}).copy()
            resampled = True
        pv = pv_curve[["time", "interval_kwh"]].copy()
    pv = pv.rename(columns={"interval_kwh": "pv_kwh"})
    tolerance_minutes = max(infer_curve_interval_minutes(load), infer_curve_interval_minutes(pv)) * 0.51
    merged = pd.merge_asof(
        load.sort_values("time"),
        pv.sort_values("time"),
        on="time",
        direction="nearest",
        tolerance=pd.Timedelta(minutes=tolerance_minutes),
    )
    unmatched_points = int(merged["pv_kwh"].isna().sum())
    merged["pv_kwh"] = merged["pv_kwh"].fillna(0).clip(lower=0)
    merged["load_kwh"] = merged["load_kwh"].fillna(0).clip(lower=0)
    pre_adjust_self_use = float(np.minimum(merged["load_kwh"], merged["pv_kwh"]).sum())
    pre_adjust_feed_in = float(np.maximum(merged["pv_kwh"] - merged["load_kwh"], 0).sum())
    calendar_table = pd.DataFrame()
    summary = None
    if holiday_calendar_config:
        year = int(holiday_calendar_config.get("year", pd.to_datetime(merged["time"]).dt.year.mode().iloc[0]))
        calendar_table = build_calendar_table(year, holiday_calendar_config)
        summary = calendar_summary(calendar_table, holiday_calendar_config)
        if force_holiday_adjustment or holiday_calendar_config.get("force_apply_to_curve", False):
            merged = _apply_calendar_to_curve(merged, calendar_table)
        else:
            merged["holiday_adjusted"] = False
            merged["calendar_load_factor"] = 1.0
    else:
        merged = _apply_holiday_adjustment_to_curve(merged, holiday_shutdown_days, holiday_load_ratio)
    # 自用光伏电量 = min(该时段企业负荷电量, 该时段光伏发电量)
    merged["self_use_kwh"] = np.minimum(merged["load_kwh"], merged["pv_kwh"])
    # 余电上网电量 = max(该时段光伏发电量 - 企业负荷电量, 0)
    merged["feed_in_kwh"] = np.maximum(merged["pv_kwh"] - merged["load_kwh"], 0)
    monthly = merged.groupby(merged["time"].dt.month)["load_kwh"].sum().tolist()
    result = result_from_energy(
        "精确模式",
        annual_consumption_kwh=float(merged["load_kwh"].sum()),
        daytime_consumption_kwh=float(merged.loc[(merged["time"].dt.hour >= 6) & (merged["time"].dt.hour <= 18), "load_kwh"].sum()),
        pv_generation_kwh=float(merged["pv_kwh"].sum()),
        self_use_kwh=float(merged["self_use_kwh"].sum()),
        monthly_consumption=monthly,
        holiday_shutdown_days=holiday_shutdown_days,
        capacity_kwp=capacity_kwp,
        holiday_summary=summary,
        pre_adjust_self_use_ratio=_ratio(pre_adjust_self_use / float(merged["pv_kwh"].sum())) if float(merged["pv_kwh"].sum()) else None,
        pre_adjust_feed_in_ratio=_ratio(pre_adjust_feed_in / float(merged["pv_kwh"].sum())) if float(merged["pv_kwh"].sum()) else None,
        holiday_extra_feed_in_kwh=float(merged["feed_in_kwh"].sum()) - pre_adjust_feed_in,
        data_quality_note=(
            f"负荷曲线间隔约{load_quality['interval_minutes']:.1f}分钟，异常间隔{load_quality['abnormal_interval_count']}个，重复时间{load_quality['duplicate_count']}个；"
            f"光伏曲线间隔约{(pv_quality or load_quality)['interval_minutes']:.1f}分钟；"
            f"未匹配点{unmatched_points}个；{'已自动重采样。' if resampled else '未重采样。'}"
        ),
    )
    return result, merged


def normalize_monthly_tou_table(df: pd.DataFrame) -> pd.DataFrame:
    """月度分时数据标准化：识别月份、总电量、尖峰平谷电量字段。"""
    df = df.dropna(how="all").copy()
    cols = list(df.columns)
    month_col = _find_column(cols, ["月份", "账期", "month", "日期"])
    total_col = _find_column(cols, ["总电量", "总用电量", "合计电量", "用电量", "total_kwh", "total"])
    sharp_col = _find_column(cols, ["尖电量", "尖", "sharp_kwh", "sharp"])
    peak_col = _find_column(cols, ["峰电量", "峰", "peak_kwh", "high_kwh", "peak", "high"])
    flat_col = _find_column(cols, ["平电量", "平", "flat_kwh", "flat"])
    valley_col = _find_column(cols, ["谷电量", "谷", "valley_kwh", "valley"])
    out = pd.DataFrame()
    raw_months = df[month_col] if month_col is not None else range(1, len(df) + 1)
    normalized_months = [normalize_month_value(value) for value in raw_months]
    invalid_months = [str(value) for value, month in zip(raw_months, normalized_months) if month is None]
    if invalid_months:
        raise ValueError(f"存在无法解析的月份，请检查电费单月份列格式：{', '.join(invalid_months[:5])}")
    out["月份"] = normalized_months
    out["月份"] = out["月份"].astype(int)
    for name, col in [("总电量(kWh)", total_col), ("尖电量(kWh)", sharp_col), ("峰电量(kWh)", peak_col), ("平电量(kWh)", flat_col), ("谷电量(kWh)", valley_col)]:
        out[name] = pd.to_numeric(df[col], errors="coerce").fillna(0) if col is not None else 0.0
    holiday_col = _find_column(cols, ["节假日", "停产天数", "holiday_days", "shutdown_days", "holiday"])
    out["节假日/停产天数"] = pd.to_numeric(df[holiday_col], errors="coerce").fillna(0) if holiday_col is not None else 0.0
    if out["总电量(kWh)"].sum() <= 0:
        out["总电量(kWh)"] = out[["尖电量(kWh)", "峰电量(kWh)", "平电量(kWh)", "谷电量(kWh)"]].sum(axis=1)
    numeric_cols = [col for col in out.columns if col != "月份"]
    out[numeric_cols] = out[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    return out.groupby("月份", as_index=False)[numeric_cols].sum().sort_values("月份").head(12)


def calculate_monthly_tou_consumption(
    monthly_table: pd.DataFrame,
    annual_pv_generation_kwh: float,
    capacity_kwp: float,
    flat_daytime_ratio: float = 0.60,
    holiday_shutdown_days: float = 0.0,
    holiday_load_ratio: float = 0.0,
    holiday_calendar_config: dict | None = None,
    tou_weights: dict[str, float] | None = None,
) -> tuple[ConsumptionResult, pd.DataFrame]:
    """月度分时模式：优先按尖、峰、白天平段电量计算可消纳电量。"""
    table = monthly_table.copy()
    factors = MONTHLY_PV_FACTORS[: len(table)]
    factors = factors / factors.sum() if factors.sum() else factors
    table["月光伏发电量(kWh)"] = annual_pv_generation_kwh * factors
    # 月白天可消纳电量 = 尖电量 + 峰电量 + 平电量 * 白天平段比例
    weights = {"尖": 1.0, "峰": 1.0, "平": _ratio(flat_daytime_ratio), "谷": 0.0}
    if tou_weights:
        weights.update({key: _ratio(value) for key, value in tou_weights.items()})
    table["修正前月白天可消纳电量(kWh)"] = (
        table["尖电量(kWh)"] * weights.get("尖", 1.0)
        + table["峰电量(kWh)"] * weights.get("峰", 1.0)
        + table["平电量(kWh)"] * weights.get("平", _ratio(flat_daytime_ratio))
        + table["谷电量(kWh)"] * weights.get("谷", 0.0)
    )
    summary = None
    calendar_table = pd.DataFrame()
    if holiday_calendar_config:
        year = int(holiday_calendar_config.get("year", 2026))
        calendar_table = build_calendar_table(year, holiday_calendar_config)
        adjustment = monthly_adjustment_table(year, holiday_calendar_config)
        summary = calendar_summary(calendar_table, holiday_calendar_config)
        table = table.merge(
            adjustment[["所属月份", "节假日修正系数"]],
            left_on="月份",
            right_on="所属月份",
            how="left",
        ).drop(columns=["所属月份"], errors="ignore")
        table["节假日修正系数"] = table["节假日修正系数"].fillna(1.0)
    else:
        if "节假日/停产天数" not in table.columns:
            table["节假日/停产天数"] = 0.0
        total_holiday_days = float(table["节假日/停产天数"].sum())
        if total_holiday_days <= 0 and holiday_shutdown_days > 0:
            table["节假日/停产天数"] = float(holiday_shutdown_days) * factors
            total_holiday_days = float(table["节假日/停产天数"].sum())
        month_days = MONTH_DAYS[: len(table)]
        holiday_effect = np.minimum(pd.to_numeric(table["节假日/停产天数"], errors="coerce").fillna(0).to_numpy(), month_days) / month_days
        table["节假日修正系数"] = 1 - holiday_effect * (1 - _holiday_load_ratio(holiday_load_ratio))
    table["修正后月白天可消纳电量(kWh)"] = table["修正前月白天可消纳电量(kWh)"] * table["节假日修正系数"].clip(lower=0, upper=1)
    table["月白天可消纳电量(kWh)"] = table["修正后月白天可消纳电量(kWh)"]
    table["修正前月自用电量(kWh)"] = np.minimum(table["月光伏发电量(kWh)"], table["修正前月白天可消纳电量(kWh)"])
    table["修正前月余电上网电量(kWh)"] = np.maximum(table["月光伏发电量(kWh)"] - table["修正前月白天可消纳电量(kWh)"], 0)
    table["月自用电量(kWh)"] = np.minimum(table["月光伏发电量(kWh)"], table["修正后月白天可消纳电量(kWh)"])
    table["月余电上网电量(kWh)"] = np.maximum(table["月光伏发电量(kWh)"] - table["修正后月白天可消纳电量(kWh)"], 0)
    pre_self_use = float(table["修正前月自用电量(kWh)"].sum())
    pre_feed_in = float(table["修正前月余电上网电量(kWh)"].sum())
    total_pv = float(table["月光伏发电量(kWh)"].sum())
    result = result_from_energy(
        "月度分时模式",
        annual_consumption_kwh=float(table["总电量(kWh)"].sum()),
        daytime_consumption_kwh=float(table["月白天可消纳电量(kWh)"].sum()),
        pv_generation_kwh=float(table["月光伏发电量(kWh)"].sum()),
        self_use_kwh=float(table["月自用电量(kWh)"].sum()),
        monthly_consumption=table["总电量(kWh)"].tolist(),
        holiday_shutdown_days=holiday_shutdown_days,
        capacity_kwp=capacity_kwp,
        holiday_summary=summary,
        pre_adjust_self_use_ratio=_ratio(pre_self_use / total_pv) if total_pv else None,
        pre_adjust_feed_in_ratio=_ratio(pre_feed_in / total_pv) if total_pv else None,
        holiday_extra_feed_in_kwh=float(table["月余电上网电量(kWh)"].sum()) - pre_feed_in,
    )
    return result, table


def calculate_quick_consumption(
    annual_consumption_kwh: float,
    daytime_usage_ratio: float,
    pv_generation_kwh: float,
    production_mode: str,
    weekend_production: bool,
    shutdown_days: float,
    capacity_kwp: float,
    holiday_load_ratio: float = 0.0,
    holiday_calendar_config: dict | None = None,
) -> ConsumptionResult:
    """快速估算模式：按年用电量、白天用电比例、生产制度和停产情况估算消纳。"""
    annual_consumption_kwh = max(float(annual_consumption_kwh), 0.0)
    pv_generation_kwh = max(float(pv_generation_kwh), 0.0)
    daytime_usage_ratio = _ratio(daytime_usage_ratio)
    cap = PRODUCTION_CAPS.get(production_mode, 0.75)
    if not weekend_production:
        cap = min(cap, PRODUCTION_CAPS["周末停产"])
    if shutdown_days > 30:
        cap = min(cap, PRODUCTION_CAPS["季节性停产"])
    daytime_consumption_before_holiday = annual_consumption_kwh * daytime_usage_ratio
    summary = None
    if holiday_calendar_config:
        year = int(holiday_calendar_config.get("year", 2026))
        calendar_table = build_calendar_table(year, holiday_calendar_config)
        summary = calendar_summary(calendar_table, holiday_calendar_config)
        correction = float(calendar_table["负荷系数"].sum() / calendar_table["基准负荷系数"].sum())
        daytime_consumption = daytime_consumption_before_holiday * correction
    else:
        holiday_reduction = daytime_consumption_before_holiday / 365 * max(float(shutdown_days), 0.0) * (1 - _holiday_load_ratio(holiday_load_ratio))
        daytime_consumption = max(daytime_consumption_before_holiday - holiday_reduction, 0.0)
    theoretical_ratio = daytime_consumption / pv_generation_kwh if pv_generation_kwh else 0.0
    # 理论自用比例 = min(年白天可消纳电量 / 年光伏发电量, 自用比例上限)
    self_use_ratio = _ratio(min(theoretical_ratio, cap))
    return result_from_energy(
        "快速估算模式",
        annual_consumption_kwh=annual_consumption_kwh,
        daytime_consumption_kwh=daytime_consumption,
        pv_generation_kwh=pv_generation_kwh,
        self_use_kwh=pv_generation_kwh * self_use_ratio,
        monthly_consumption=None,
        holiday_shutdown_days=shutdown_days,
        capacity_kwp=capacity_kwp,
        holiday_summary=summary,
        pre_adjust_self_use_ratio=_ratio(min(daytime_consumption_before_holiday / pv_generation_kwh if pv_generation_kwh else 0.0, cap)),
        pre_adjust_feed_in_ratio=1 - _ratio(min(daytime_consumption_before_holiday / pv_generation_kwh if pv_generation_kwh else 0.0, cap)),
        holiday_extra_feed_in_kwh=max(
            pv_generation_kwh * _ratio(min(daytime_consumption_before_holiday / pv_generation_kwh if pv_generation_kwh else 0.0, cap))
            - pv_generation_kwh * self_use_ratio,
            0.0,
        ),
    )


def calculate_consumption(
    annual_consumption_kwh: float,
    daytime_usage_ratio: float,
    pv_generation_kwh: float,
    self_use_cap_ratio: float,
) -> ConsumptionResult:
    """兼容旧入口：用快速估算模式计算消纳。"""
    mode = "三班连续生产" if self_use_cap_ratio >= 0.95 else "单班制"
    return calculate_quick_consumption(
        annual_consumption_kwh,
        daytime_usage_ratio,
        pv_generation_kwh,
        mode,
        weekend_production=True,
        shutdown_days=0.0,
        capacity_kwp=0.0,
    )
