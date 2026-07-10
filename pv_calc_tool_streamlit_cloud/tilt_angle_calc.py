from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
COUNTY_TILT_DB_PATH = DATA_DIR / "county_tilt.csv"


@dataclass(frozen=True)
class TiltAngleResult:
    province: str
    city: str
    county: str
    latitude: float
    theoretical_tilt_deg: float
    rooftop_default_tilt_deg: float
    recommended_tilt_deg: float
    roof_type: str
    priority: str
    data_source: str
    layout_adjustment_ratio: float
    notes: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["notes"] = "；".join(self.notes)
        return data


def theoretical_tilt_from_latitude(latitude: float) -> float:
    """理论推荐倾角：根据项目所在地纬度分档估算。"""
    latitude = float(latitude)
    if latitude < 22:
        return 10.0
    if latitude < 25:
        return 15.0
    if latitude < 30:
        return 20.0
    if latitude < 35:
        return 25.0
    if latitude < 40:
        return 30.0
    if latitude < 45:
        return 35.0
    return 40.0


def load_county_tilt_database(path: Path = COUNTY_TILT_DB_PATH) -> pd.DataFrame:
    """读取区县倾角数据库；不存在时返回空表。"""
    columns = ["province", "city", "county", "latitude", "rooftop_default_tilt"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"county_tilt.csv 缺少字段：{', '.join(missing)}")
    return df[columns].copy()


def get_county_tilt_record(province: str, city: str, county: str, db: pd.DataFrame | None = None) -> dict | None:
    """按省市区县查找数据库倾角记录。"""
    db = load_county_tilt_database() if db is None else db
    if db.empty:
        return None
    match = db[(db["province"] == province) & (db["city"] == city) & (db["county"] == county)]
    if match.empty:
        return None
    row = match.iloc[0].to_dict()
    return {
        "latitude": float(row["latitude"]),
        "rooftop_default_tilt": float(row["rooftop_default_tilt"]),
    }


def layout_adjustment_from_tilt(recommended_tilt_deg: float) -> float:
    """倾角对屋面排布修正系数的影响：倾角越大，阵列间距和遮挡修正越高。"""
    tilt = max(float(recommended_tilt_deg), 0.0)
    if tilt <= 10:
        return 0.00
    if tilt <= 15:
        return 0.01
    if tilt <= 20:
        return 0.02
    if tilt <= 25:
        return 0.03
    if tilt <= 30:
        return 0.04
    return 0.05


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def recommend_tilt_angle(
    province: str,
    city: str,
    county: str,
    location_latitude: float,
    roof_type: str,
    roof_slope_deg: float,
    priority: str,
    manual_latitude: float | None = None,
    db: pd.DataFrame | None = None,
) -> TiltAngleResult:
    """区县最佳倾角推荐：数据库优先，其次按纬度估算，再按屋面类型和项目策略修正。"""
    db_record = get_county_tilt_record(province, city, county, db)
    notes: list[str] = []

    if manual_latitude is not None:
        latitude = float(manual_latitude)
        theoretical = theoretical_tilt_from_latitude(latitude)
        rooftop_default = theoretical
        data_source = "手动纬度估算"
        notes.append("用户选择手动纬度，优先按手动纬度估算理论推荐倾角")
    elif db_record is not None:
        latitude = db_record["latitude"]
        theoretical = theoretical_tilt_from_latitude(latitude)
        rooftop_default = db_record["rooftop_default_tilt"]
        data_source = "区县倾角数据库"
        notes.append("命中区县倾角数据库，优先采用 rooftop_default_tilt")
    else:
        latitude = float(location_latitude)
        theoretical = theoretical_tilt_from_latitude(latitude)
        rooftop_default = theoretical
        data_source = "纬度分档估算"
        notes.append("区县倾角数据库无记录，按项目纬度分档估算理论推荐倾角")

    if roof_type == "彩钢瓦屋面":
        recommended = max(float(roof_slope_deg), 0.0)
        notes.append("彩钢瓦屋面默认采用屋面坡度")
    elif roof_type == "混凝土平屋面":
        recommended = min(rooftop_default, 15.0)
        notes.append("混凝土平屋面默认采用 min(理论推荐倾角, 15°)")
    else:
        recommended = rooftop_default
        notes.append("其他屋面默认采用区县或理论推荐倾角")

    if priority == "发电量优先":
        recommended = rooftop_default
        notes.append("发电量优先：采用理论/区县推荐倾角")
    elif priority == "装机容量优先":
        recommended = _clamp(recommended, 5.0, 10.0)
        notes.append("装机容量优先：倾角控制在 5°-10°")
    elif priority == "抗风优先":
        recommended = _clamp(recommended, 5.0, 15.0)
        notes.append("抗风优先：倾角控制在 5°-15°")

    adjustment = layout_adjustment_from_tilt(recommended)
    notes.append(f"倾角排布修正系数为 {adjustment * 100:.1f}%")

    return TiltAngleResult(
        province=province,
        city=city,
        county=county,
        latitude=round(latitude, 4),
        theoretical_tilt_deg=round(theoretical, 1),
        rooftop_default_tilt_deg=round(rooftop_default, 1),
        recommended_tilt_deg=round(recommended, 1),
        roof_type=roof_type,
        priority=priority,
        data_source=data_source,
        layout_adjustment_ratio=adjustment,
        notes=notes,
    )

