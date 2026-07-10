from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class SolarProfile:
    province: str
    city: str
    county: str
    latitude: float
    best_tilt_deg: float
    equivalent_hours: float
    annual_specific_yield_kwh_per_kwp: float
    resource_level: str
    data_source_note: str
    solar_data_level: str

    def to_dict(self) -> dict:
        return asdict(self)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ADMIN_CSV_PATH = DATA_DIR / "china_admin_divisions.csv"
CSV_PATH = DATA_DIR / "county_solar_data.csv"

PROVINCE_SOLAR_BASE = {
    "北京市": (39.9, 40, 1230),
    "天津市": (39.0, 39, 1220),
    "河北省": (38.0, 38, 1260),
    "山西省": (37.7, 38, 1360),
    "内蒙古自治区": (40.8, 41, 1500),
    "辽宁省": (41.8, 42, 1210),
    "吉林省": (43.9, 44, 1240),
    "黑龙江省": (45.8, 46, 1260),
    "上海市": (31.2, 31, 1040),
    "江苏省": (32.0, 32, 1080),
    "浙江省": (30.3, 30, 1020),
    "安徽省": (31.8, 32, 1100),
    "福建省": (26.1, 26, 980),
    "江西省": (28.7, 29, 1040),
    "山东省": (36.7, 37, 1240),
    "河南省": (34.8, 35, 1160),
    "湖北省": (30.5, 30, 1000),
    "湖南省": (28.2, 28, 930),
    "广东省": (23.1, 23, 1030),
    "广西壮族自治区": (22.8, 23, 980),
    "海南省": (20.0, 20, 1220),
    "重庆市": (29.7, 30, 860),
    "四川省": (30.7, 31, 850),
    "贵州省": (26.7, 27, 900),
    "云南省": (25.0, 25, 1380),
    "西藏自治区": (29.7, 30, 1650),
    "陕西省": (34.3, 34, 1180),
    "甘肃省": (36.1, 36, 1440),
    "青海省": (36.6, 37, 1580),
    "宁夏回族自治区": (38.5, 38, 1500),
    "新疆维吾尔自治区": (43.8, 44, 1520),
}

BUILTIN_ROWS = [
    ("陕西省", "西安市", "雁塔区", 34.22, 34, 1120, 1120, "较好", "内置估算值，建议用当地气象或设计院数据复核"),
    ("陕西省", "西安市", "未央区", 34.31, 34, 1125, 1125, "较好", "内置估算值，建议用当地气象或设计院数据复核"),
    ("陕西省", "榆林市", "榆阳区", 38.28, 38, 1420, 1420, "优秀", "内置估算值，陕北资源较好，建议结合遮挡和并网条件复核"),
    ("陕西省", "延安市", "宝塔区", 36.59, 36, 1320, 1320, "优秀", "内置估算值，建议结合实测辐照数据复核"),
    ("北京市", "北京市", "朝阳区", 39.92, 40, 1230, 1230, "较好", "省级代表估算值"),
    ("上海市", "上海市", "浦东新区", 31.22, 31, 1040, 1040, "一般", "省级代表估算值"),
    ("天津市", "天津市", "滨海新区", 39.00, 39, 1220, 1220, "较好", "省级代表估算值"),
    ("重庆市", "重庆市", "渝北区", 29.72, 30, 860, 860, "一般", "省级代表估算值"),
    ("河北省", "石家庄市", "长安区", 38.04, 38, 1260, 1260, "较好", "省级代表估算值"),
    ("山西省", "太原市", "小店区", 37.74, 38, 1360, 1360, "优秀", "省级代表估算值"),
    ("内蒙古自治区", "呼和浩特市", "赛罕区", 40.82, 41, 1500, 1500, "优秀", "省级代表估算值"),
    ("辽宁省", "沈阳市", "和平区", 41.80, 42, 1210, 1210, "较好", "省级代表估算值"),
    ("吉林省", "长春市", "南关区", 43.89, 44, 1240, 1240, "较好", "省级代表估算值"),
    ("黑龙江省", "哈尔滨市", "南岗区", 45.75, 46, 1260, 1260, "较好", "省级代表估算值"),
    ("江苏省", "南京市", "江宁区", 31.95, 32, 1080, 1080, "一般", "省级代表估算值"),
    ("浙江省", "杭州市", "余杭区", 30.27, 30, 1020, 1020, "一般", "省级代表估算值"),
    ("安徽省", "合肥市", "蜀山区", 31.82, 32, 1100, 1100, "较好", "省级代表估算值"),
    ("福建省", "福州市", "鼓楼区", 26.08, 26, 980, 980, "一般", "省级代表估算值"),
    ("江西省", "南昌市", "红谷滩区", 28.68, 29, 1040, 1040, "一般", "省级代表估算值"),
    ("山东省", "济南市", "历下区", 36.67, 37, 1240, 1240, "较好", "省级代表估算值"),
    ("河南省", "郑州市", "金水区", 34.75, 35, 1160, 1160, "较好", "省级代表估算值"),
    ("湖北省", "武汉市", "洪山区", 30.50, 30, 1000, 1000, "一般", "省级代表估算值"),
    ("湖南省", "长沙市", "岳麓区", 28.23, 28, 930, 930, "一般", "省级代表估算值"),
    ("广东省", "广州市", "黄埔区", 23.13, 23, 1030, 1030, "一般", "省级代表估算值"),
    ("广西壮族自治区", "南宁市", "青秀区", 22.82, 23, 980, 980, "一般", "省级代表估算值"),
    ("海南省", "海口市", "秀英区", 20.04, 20, 1220, 1220, "较好", "省级代表估算值"),
    ("四川省", "成都市", "锦江区", 30.66, 31, 860, 860, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "青羊区", 30.67, 31, 855, 855, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "金牛区", 30.70, 31, 855, 855, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "武侯区", 30.65, 31, 860, 860, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "成华区", 30.66, 31, 860, 860, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "龙泉驿区", 30.56, 31, 880, 880, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "青白江区", 30.88, 31, 875, 875, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "新都区", 30.82, 31, 865, 865, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "温江区", 30.68, 31, 850, 850, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "双流区", 30.57, 31, 870, 870, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "郫都区", 30.81, 31, 850, 850, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "新津区", 30.41, 30, 890, 890, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "金堂县", 30.86, 31, 900, 900, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "大邑县", 30.59, 31, 845, 845, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "蒲江县", 30.20, 30, 900, 900, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "都江堰市", 31.00, 31, 840, 840, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "彭州市", 30.99, 31, 850, 850, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "邛崃市", 30.42, 30, 875, 875, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "崇州市", 30.63, 31, 845, 845, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("四川省", "成都市", "简阳市", 30.39, 30, 920, 920, "一般", "成都区县估算值，建议用当地气象或设计院数据复核"),
    ("贵州省", "贵阳市", "观山湖区", 26.65, 27, 900, 900, "一般", "省级代表估算值"),
    ("云南省", "昆明市", "官渡区", 25.04, 25, 1380, 1380, "优秀", "省级代表估算值"),
    ("西藏自治区", "拉萨市", "城关区", 29.65, 30, 1650, 1650, "优秀", "省级代表估算值"),
    ("甘肃省", "兰州市", "城关区", 36.06, 36, 1440, 1440, "优秀", "省级代表估算值"),
    ("青海省", "西宁市", "城西区", 36.62, 37, 1580, 1580, "优秀", "省级代表估算值"),
    ("宁夏回族自治区", "银川市", "金凤区", 38.49, 38, 1500, 1500, "优秀", "省级代表估算值"),
    ("新疆维吾尔自治区", "乌鲁木齐市", "天山区", 43.82, 44, 1520, 1520, "优秀", "省级代表估算值"),
]


def _builtin_df() -> pd.DataFrame:
    df = pd.DataFrame(
        BUILTIN_ROWS,
        columns=[
            "province",
            "city",
            "county",
            "latitude",
            "best_tilt_deg",
            "equivalent_hours",
            "annual_specific_yield_kwh_per_kwp",
            "resource_level",
            "data_source_note",
        ],
    )
    df["solar_data_level"] = df["data_source_note"].apply(lambda x: "city_estimated" if "区县估算" in str(x) or "内置估算" in str(x) else "province_estimated")
    return df


def _resource_level(hours: float) -> str:
    if hours >= 1300:
        return "优秀"
    if hours >= 1100:
        return "较好"
    return "一般"


def theoretical_tilt_from_latitude(latitude: float) -> float:
    """理论最佳倾角：按项目所在地纬度分档估算。"""
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


def _estimated_admin_solar_df() -> pd.DataFrame:
    """全国行政区划：从本地CSV读取省-市-区县，并按省级代表值生成光照估算。"""
    if not ADMIN_CSV_PATH.exists():
        return _builtin_df()
    admin = pd.read_csv(ADMIN_CSV_PATH, dtype=str, encoding="utf-8-sig").fillna("")
    rows = []
    for item in admin.to_dict(orient="records"):
        province = item["province"]
        city = item["city"]
        county = item["county"]
        latitude, _best_tilt, hours = PROVINCE_SOLAR_BASE.get(province, (30.0, 30, 1000))
        rows.append(
            {
                "province": province,
                "city": city,
                "county": county,
                "latitude": latitude,
                "best_tilt_deg": theoretical_tilt_from_latitude(latitude),
                "equivalent_hours": hours,
                "annual_specific_yield_kwh_per_kwp": hours,
                "resource_level": _resource_level(hours),
            "data_source_note": "行政区划来自全国省市区县CSV；光照为省级代表估算值，需用当地资源报告复核",
            "solar_data_level": "province_estimated",
            }
        )
    return pd.DataFrame(rows).drop_duplicates(["province", "city", "county"], keep="first")


def load_location_solar_data() -> pd.DataFrame:
    """地区数据：行政区划优先用全国CSV，光照可由用户区县级CSV覆盖。"""
    base_df = _estimated_admin_solar_df()
    builtin_df = _builtin_df()
    base_df = base_df.set_index(["province", "city", "county"])
    builtin_df = builtin_df.set_index(["province", "city", "county"])
    base_df.update(builtin_df)
    base_df = base_df.reset_index()
    if "solar_data_level" not in base_df.columns:
        base_df["solar_data_level"] = base_df["data_source_note"].apply(lambda x: "city_estimated" if "区县估算" in str(x) or "内置估算" in str(x) else "province_estimated")

    if CSV_PATH.exists():
        csv_df = pd.read_csv(CSV_PATH)
        required = set(_builtin_df().columns) - {"solar_data_level"}
        if required.issubset(csv_df.columns):
            if "solar_data_level" not in csv_df.columns:
                csv_df["solar_data_level"] = "measured_or_verified"
            user_df = csv_df[list(_builtin_df().columns)].copy().set_index(["province", "city", "county"])
            base_idx = base_df.set_index(["province", "city", "county"])
            base_idx.update(user_df)
            base_idx = pd.concat([base_idx, user_df.loc[~user_df.index.isin(base_idx.index)]])
            return base_idx.reset_index()
    cols = list(_builtin_df().columns)
    if "solar_data_level" not in cols:
        cols.append("solar_data_level")
    return base_df[cols].copy()


def list_provinces(df: pd.DataFrame) -> list[str]:
    return df["province"].dropna().drop_duplicates().tolist()


def list_cities(df: pd.DataFrame, province: str) -> list[str]:
    return df.loc[df["province"] == province, "city"].dropna().drop_duplicates().tolist()


def list_counties(df: pd.DataFrame, province: str, city: str) -> list[str]:
    mask = (df["province"] == province) & (df["city"] == city)
    return df.loc[mask, "county"].dropna().drop_duplicates().tolist()


def get_solar_profile(df: pd.DataFrame, province: str, city: str, county: str) -> SolarProfile:
    """返回选定区县的光照参数；如没有完全匹配，则退回到同省第一条代表值。"""
    match = df[(df["province"] == province) & (df["city"] == city) & (df["county"] == county)]
    if match.empty:
        match = df[df["province"] == province]
    if match.empty:
        match = df.iloc[[0]]
    row = match.iloc[0].to_dict()
    return SolarProfile(
        province=str(row["province"]),
        city=str(row["city"]),
        county=str(row["county"]),
        latitude=float(row["latitude"]),
        best_tilt_deg=theoretical_tilt_from_latitude(float(row["latitude"])),
        equivalent_hours=float(row["equivalent_hours"]),
        annual_specific_yield_kwh_per_kwp=float(row["annual_specific_yield_kwh_per_kwp"]),
        resource_level=str(row["resource_level"]),
        data_source_note=str(row["data_source_note"]),
        solar_data_level=str(row.get("solar_data_level", "province_estimated")),
    )


def module_generation_table(profile: SolarProfile, module_powers_wp: list[float]) -> pd.DataFrame:
    """组件发电量估算：单块组件年发电量 = 组件功率(kWp) * 年等效利用小时数。"""
    rows = []
    for power_wp in module_powers_wp:
        power_kwp = max(float(power_wp), 0.0) / 1000
        rows.append(
            {
                "组件功率(Wp)": power_wp,
                "单块组件年发电量(kWh/年)": power_kwp * profile.annual_specific_yield_kwh_per_kwp,
                "每MWp年发电量(万kWh/年)": profile.annual_specific_yield_kwh_per_kwp * 1000 / 10000,
            }
        )
    return pd.DataFrame(rows)
