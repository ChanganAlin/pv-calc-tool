from __future__ import annotations

import base64
import hashlib
import html
import sys
from io import BytesIO
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from components.ui_helpers import energy, labeled_table, money, ratio, years
from config.default_params import (
    CAPACITY_DEFAULTS,
    CONSUMPTION_DEFAULTS,
    CUSTOM_STOP_LOAD_FACTOR,
    COST_DEFAULTS,
    LEGAL_HOLIDAY_LOAD_FACTOR,
    MAINTENANCE_LOAD_FACTOR,
    REVENUE_DEFAULTS,
    SENSITIVITY_STEPS,
    SPRING_FESTIVAL_LOAD_FACTOR,
    WEEKEND_LOAD_FACTOR_LOW,
    WEEKEND_LOAD_FACTOR_NORMAL,
    WEEKEND_LOAD_FACTOR_STOP,
)
from modules.bill_parser import parse_bill_file
from modules.capacity_calc import calculate_capacity
from modules.consumption_calc import (
    calculate_monthly_tou_consumption,
    calculate_precise_consumption,
    calculate_quick_consumption,
    load_tou_period_config,
    normalize_monthly_tou_table,
    normalize_power_or_energy_curve,
    read_curve_file,
    tou_weights_for_province,
)
from modules.cost_calc import calculate_cost
from modules.export_excel import build_excel_report
from modules.holiday_calendar import build_calendar_table, build_holiday_calendar_config, load_holiday_config
from modules.grid_connection_config import (
    CONNECTION_POINT_TYPES,
    GRID_MODES,
    VOLTAGE_LEVELS,
    GridConnection,
    adjust_consumption_for_grid,
    apply_capacity_limit,
    grid_analysis_summary,
    grid_cost_items_yuan,
    grid_risk_suggestions,
    normalize_grid_connection,
    recommend_capacity_scenarios,
    validate_grid_connection,
)
from modules.image_area_estimator import (
    DetectedRegion,
    detect_pv_candidate_regions,
    detect_scale_bar_pixels,
    draw_polygon_overlay,
    draw_regions_overlay,
    estimate_map_region_area,
    estimate_polygon_area,
    estimate_rect_area,
    load_rgb_image,
    open_image_size,
)
from modules.location_solar_data import (
    get_solar_profile,
    list_cities,
    list_counties,
    list_provinces,
    load_location_solar_data,
    module_generation_table,
)
from modules.revenue_calc import calculate_revenue
from modules.sensitivity_calc import build_risk_suggestions, sensitivity_analysis
from modules.tilt_angle_calc import recommend_tilt_angle


LOGO_PATH = BASE_DIR / "assets" / "broad_sun_logo.png"
POLYGON_SELECTOR_DIR = BASE_DIR / "components" / "polygon_selector"
HOLIDAY_CONFIG_PATH = BASE_DIR / "data" / "holiday_config.csv"
polygon_selector_component = components.declare_component("polygon_selector_image_v5", path=str(POLYGON_SELECTOR_DIR))

st.set_page_config(page_title="博阳能源光伏项目自动测算工具", layout="wide", initial_sidebar_state="expanded")


def inject_brand_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --broad-sun-orange: #F05A1A;
            --broad-sun-red: #D62019;
            --broad-sun-amber: #FFB11B;
            --broad-sun-brown: #3A2B2B;
            --broad-sun-muted: #7A6A66;
            --broad-sun-warm-bg: #FFF9F2;
            --broad-sun-line: rgba(240, 90, 26, 0.16);
            --broad-sun-soft: rgba(240, 90, 26, 0.075);
            --apple-glass: rgba(255, 255, 255, 0.72);
            --apple-glass-strong: rgba(255, 255, 255, 0.88);
            --apple-shadow: 0 18px 48px rgba(58, 43, 43, 0.08);
            --apple-shadow-soft: 0 8px 28px rgba(58, 43, 43, 0.055);
        }

        html, body, [class*="css"], [class*="st-"], button, input, textarea, select {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", "Microsoft YaHei", sans-serif;
            letter-spacing: 0;
        }

        #MainMenu, footer, header [data-testid="stToolbar"] {
            visibility: hidden;
        }

        header[data-testid="stHeader"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
        }

        .block-container {
            padding-top: 0.35rem;
            padding-bottom: 3rem;
            max-width: 1480px;
            padding-left: 2.35rem;
            padding-right: 2.35rem;
        }

        [data-testid="stAppViewContainer"] {
            margin-left: 300px !important;
            width: calc(100% - 300px) !important;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(255, 177, 27, 0.16), transparent 24%),
                radial-gradient(circle at 86% 6%, rgba(240, 90, 26, 0.10), transparent 22%),
                linear-gradient(180deg, rgba(255, 250, 245, 0.96) 0%, rgba(255, 255, 255, 0.98) 42%, #ffffff 100%),
                var(--broad-sun-warm-bg);
            color: var(--broad-sun-brown);
        }

        section[data-testid="stSidebar"],
        [data-testid="stSidebar"] {
            background: rgba(255, 247, 239, 0.82) !important;
            border-right: 1px solid var(--broad-sun-line) !important;
            backdrop-filter: blur(22px) saturate(1.28);
            -webkit-backdrop-filter: blur(22px) saturate(1.28);
            min-width: 300px !important;
            width: 300px !important;
            max-width: 300px !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            transform: translateX(0) !important;
            position: fixed !important;
            left: 0 !important;
            top: 0 !important;
            bottom: 0 !important;
            height: 100vh !important;
            z-index: 1000 !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
        }

        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebar"] > div {
            background: rgba(255, 247, 239, 0.64) !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"][aria-expanded="false"],
        [data-testid="stSidebar"][aria-expanded="false"],
        section[data-testid="stSidebar"][aria-expanded="true"],
        [data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 300px !important;
            width: 300px !important;
            max-width: 300px !important;
            margin-left: 0 !important;
            left: 0 !important;
            transform: translateX(0) !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebarContent"] {
            min-width: 300px !important;
            width: 300px !important;
            max-width: 300px !important;
            margin-left: 0 !important;
            left: 0 !important;
            transform: translateX(0) !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            height: 100vh !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
        }

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebar"] button[title*="sidebar"],
        [data-testid="stSidebar"] button[aria-label*="sidebar"],
        [data-testid="stSidebar"] button[aria-label*="Sidebar"],
        button[kind="header"][aria-label*="sidebar"],
        button[kind="header"][aria-label*="Sidebar"] {
            display: none !important;
        }

        @media (max-width: 900px) {
            section[data-testid="stSidebar"],
            [data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div:first-child,
            [data-testid="stSidebar"] > div:first-child,
            [data-testid="stSidebarContent"] {
                min-width: 280px !important;
                width: 280px !important;
                max-width: 280px !important;
            }

            [data-testid="stAppViewContainer"] {
                margin-left: 280px !important;
                width: calc(100% - 280px) !important;
            }
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.65rem;
        }

        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--broad-sun-brown);
            font-weight: 760;
        }

        .brand-header {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 24px;
            padding: 14px 26px 14px 28px;
            margin: 0 0 18px;
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.96) 0%, rgba(255, 249, 242, 0.84) 100%);
            border: 1px solid rgba(240, 90, 26, 0.16);
            border-left: 5px solid var(--broad-sun-orange);
            border-radius: 8px;
            box-shadow: var(--apple-shadow);
            backdrop-filter: blur(18px) saturate(1.18);
            -webkit-backdrop-filter: blur(18px) saturate(1.18);
            min-height: 104px;
            overflow: hidden;
        }

        .brand-copy {
            flex: 1 1 auto;
            min-width: 0;
            padding-left: 2px;
        }

        .brand-title {
            margin: 0;
            color: var(--broad-sun-brown);
            font-size: 34px;
            line-height: 1.12;
            font-weight: 780;
        }

        .brand-subtitle {
            margin: 8px 0 0;
            color: var(--broad-sun-muted);
            font-size: 14px;
            font-weight: 450;
        }

        .brand-accent {
            height: 3px;
            width: 168px;
            background: linear-gradient(90deg, var(--broad-sun-orange), var(--broad-sun-red), var(--broad-sun-amber));
            border-radius: 999px;
            margin-top: 14px;
            box-shadow: 0 0 20px rgba(240, 90, 26, 0.22);
        }

        .brand-logo-panel {
            flex: 0 0 255px;
            align-self: stretch;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px 24px 6px 0;
            border-right: 1px solid rgba(240, 90, 26, 0.14);
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.28), rgba(255, 236, 222, 0.20));
        }

        .brand-logo-panel img {
            display: block;
            width: min(210px, 100%);
            height: auto;
            object-fit: contain;
        }

        .brand-logo-fallback {
            color: var(--broad-sun-brown);
            font-weight: 780;
            font-size: 20px;
            letter-spacing: 0.08em;
        }

        .summary-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 4px 0 18px;
        }

        .summary-item {
            background: var(--apple-glass);
            border: 1px solid rgba(240, 90, 26, 0.13);
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 78px;
            box-shadow: var(--apple-shadow-soft);
            backdrop-filter: blur(14px) saturate(1.15);
            -webkit-backdrop-filter: blur(14px) saturate(1.15);
        }

        .summary-label {
            color: var(--broad-sun-muted);
            font-size: 12px;
            margin-bottom: 6px;
        }

        .summary-value {
            color: var(--broad-sun-brown);
            font-weight: 740;
            font-size: 18px;
            line-height: 1.25;
        }

        .section-heading {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 12px 0 14px;
            padding-top: 4px;
        }

        .section-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 999px;
            color: #fff;
            background: linear-gradient(135deg, var(--broad-sun-orange), var(--broad-sun-red));
            font-weight: 700;
            font-size: 13px;
            box-shadow: 0 8px 20px rgba(240, 90, 26, 0.24);
        }

        .section-title {
            margin: 0;
            color: var(--broad-sun-brown);
            font-size: 24px;
            line-height: 1.25;
            font-weight: 780;
        }

        .section-subtitle {
            margin: 2px 0 0;
            color: var(--broad-sun-muted);
            font-size: 13px;
        }

        .data-note {
            padding: 11px 13px;
            margin: 8px 0 14px;
            background: rgba(255, 247, 237, 0.76);
            border: 1px solid rgba(240, 90, 26, 0.16);
            border-left: 3px solid var(--broad-sun-orange);
            border-radius: 8px;
            color: var(--broad-sun-muted);
            font-size: 13px;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }

        div[data-testid="stMetric"] {
            background: var(--apple-glass-strong);
            border: 1px solid rgba(240, 90, 26, 0.13);
            border-radius: 8px;
            padding: 16px 18px;
            min-height: 98px;
            height: 100%;
            box-shadow: var(--apple-shadow-soft);
            backdrop-filter: blur(16px) saturate(1.16);
            -webkit-backdrop-filter: blur(16px) saturate(1.16);
            transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
        }

        div[data-testid="stMetric"]:hover {
            border-color: rgba(240, 90, 26, 0.26);
            transform: translateY(-1px);
            box-shadow: 0 14px 34px rgba(58, 43, 43, 0.08);
        }

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: var(--broad-sun-muted);
        }

        div[data-testid="stMetricValue"] {
            color: var(--broad-sun-brown);
            font-size: 1.7rem;
            font-weight: 700;
            letter-spacing: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 3px;
            border-bottom: 1px solid rgba(240, 90, 26, 0.14);
            background: rgba(255,255,255,0.68);
            border-radius: 8px;
            padding: 5px;
            backdrop-filter: blur(16px) saturate(1.18);
            -webkit-backdrop-filter: blur(16px) saturate(1.18);
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 7px;
            color: var(--broad-sun-brown);
            padding: 9px 13px;
            font-weight: 520;
        }

        .stTabs [aria-selected="true"] {
            color: var(--broad-sun-orange);
            background: rgba(240, 90, 26, 0.105);
            font-weight: 720;
            box-shadow: inset 0 0 0 1px rgba(240, 90, 26, 0.10);
        }

        [data-testid="stDataFrame"] {
            border: 1px solid rgba(240, 90, 26, 0.13);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: var(--apple-shadow-soft);
            background: rgba(255, 255, 255, 0.84);
        }

        div[data-baseweb="input"],
        div[data-baseweb="select"] > div,
        textarea {
            border-radius: 8px;
        }

        [data-testid="stNumberInput"],
        [data-testid="stTextInput"],
        [data-testid="stSelectbox"],
        [data-testid="stFileUploader"],
        [data-testid="stRadio"],
        [data-testid="stCheckbox"] {
            background: rgba(255, 255, 255, 0.70);
            border: 1px solid rgba(240, 90, 26, 0.10);
            border-radius: 8px;
            padding: 10px 12px;
            box-shadow: 0 3px 12px rgba(58, 43, 43, 0.025);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }

        [data-testid="stNumberInput"]:hover,
        [data-testid="stTextInput"]:hover,
        [data-testid="stSelectbox"]:hover,
        [data-testid="stFileUploader"]:hover,
        [data-testid="stRadio"]:hover,
        [data-testid="stCheckbox"]:hover {
            border-color: rgba(240, 90, 26, 0.24);
            background: rgba(255, 255, 255, 0.92);
        }

        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stFileUploader"] label,
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label {
            color: var(--broad-sun-brown);
            font-weight: 620;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
            border-color: var(--broad-sun-orange);
            color: #ffffff;
            background: linear-gradient(135deg, var(--broad-sun-orange), var(--broad-sun-red));
            box-shadow: 0 10px 24px rgba(240, 90, 26, 0.20);
            font-weight: 680;
            transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--broad-sun-red);
            color: #ffffff;
            filter: brightness(0.97);
            transform: translateY(-1px);
            box-shadow: 0 14px 30px rgba(240, 90, 26, 0.24);
        }

        h1, h2, h3 {
            color: var(--broad-sun-brown);
            font-weight: 760;
        }

        hr {
            border-color: rgba(240, 90, 26, 0.12);
        }

        [data-testid="stAlert"] {
            border-radius: 8px;
            border: 1px solid rgba(240, 90, 26, 0.14);
            box-shadow: 0 8px 24px rgba(58, 43, 43, 0.04);
        }

        div[data-testid="stExpander"] {
            border: 1px solid rgba(240, 90, 26, 0.13);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.70);
            box-shadow: var(--apple-shadow-soft);
        }

        @media (max-width: 900px) {
            .summary-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .brand-header {
                align-items: flex-start;
                flex-direction: column;
                min-height: auto;
                padding: 22px;
            }
            .brand-title {
                font-size: 24px;
            }
            .brand-logo-panel {
                width: 100%;
                flex-basis: auto;
                border-right: 0;
                border-bottom: 1px solid rgba(240, 90, 26, 0.12);
                justify-content: flex-start;
                padding: 0 0 14px;
                background: transparent;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand_header() -> None:
    if LOGO_PATH.exists():
        logo_src = f"data:image/png;base64,{base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')}"
        logo_html = f'<img src="{logo_src}" alt="博阳能源 BROAD SUN logo">'
    else:
        logo_html = '<div class="brand-logo-fallback">BROAD SUN</div>'

    st.markdown(
        f"""
        <div class="brand-header">
          <div class="brand-logo-panel">
            {logo_html}
          </div>
          <div class="brand-copy">
            <h1 class="brand-title">博阳能源光伏项目自动测算工具</h1>
            <p class="brand-subtitle">工商业分布式光伏项目容量、消纳、造价、收益与敏感性一体化测算</p>
            <div class="brand-accent"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(index: int, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-heading">
          <div class="section-index">{index}</div>
          <div>
            <h2 class="section-title">{title}</h2>
            <p class="section-subtitle">{subtitle}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_summary_strip(items: list[tuple[str, str]]) -> None:
    cards = "".join(
        f'<div class="summary-item"><div class="summary-label">{html.escape(str(label))}</div>'
        f'<div class="summary-value">{html.escape(str(value))}</div></div>'
        for label, value in items
    )
    st.markdown(f'<div class="summary-strip">{cards}</div>', unsafe_allow_html=True)


def render_note(text: str) -> None:
    st.markdown(f'<div class="data-note">{text}</div>', unsafe_allow_html=True)


def resized_for_selector(image, max_width: int = 980) -> tuple[object, float]:
    width, height = image.size
    if width <= max_width:
        return image.copy(), 1.0
    ratio = max_width / float(width)
    resized = image.resize((max_width, max(1, int(height * ratio))))
    return resized, ratio


def polygon_selector_image_asset(image) -> tuple[str, str]:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=72, optimize=True)
    payload = buffer.getvalue()
    digest = hashlib.sha1(payload).hexdigest()[:16]
    cache_dir = POLYGON_SELECTOR_DIR / "_cache"
    cache_dir.mkdir(exist_ok=True)
    asset_path = cache_dir / f"map_{digest}.jpg"
    if not asset_path.exists():
        asset_path.write_bytes(payload)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"_cache/{asset_path.name}", f"data:image/jpeg;base64,{encoded}"


def polygon_selector(image, default_points: list[dict], image_id: str, closed: bool = False, key: str | None = None) -> dict:
    image_src, fallback_data_uri = polygon_selector_image_asset(image)
    return polygon_selector_component(
        image_src=image_src,
        image_data=fallback_data_uri,
        default_points=default_points,
        image_id=image_id,
        closed=closed,
        default={"points": default_points, "closed": closed},
        key=key,
    )


def pct_input(label: str, value: float, help_text: str | None = None) -> float:
    display_label = label if "％" in label or "%" in label else f"{label}(%)"
    return st.number_input(display_label, min_value=0.0, max_value=100.0, value=value * 100, step=1.0, help=help_text) / 100


inject_brand_style()
render_brand_header()
st.caption("内部初步测算 MVP：公式透明、参数可改、支持 Excel 导出。图片面积和电费单识别结果仅用于辅助判断。")

location_df = load_location_solar_data()

with st.sidebar:
    st.header("项目基础信息")
    project_name = st.text_input("项目名称", "示例工商业屋顶光伏项目")
    provinces = list_provinces(location_df)
    default_province_index = provinces.index("陕西省") if "陕西省" in provinces else 0
    province = st.selectbox("项目地点-省份", provinces, index=default_province_index)
    cities = list_cities(location_df, province)
    city = st.selectbox("项目地点-城市", cities, index=0, key=f"city_{province}")
    counties = list_counties(location_df, province, city)
    county = st.selectbox("项目地点-区县", counties, index=0, key=f"county_{province}_{city}")
    project_location = f"{province}{city}{county}"
    solar_profile = get_solar_profile(location_df, province, city, county)
    project_type = st.selectbox("项目类型", ["工商业屋顶分布式光伏", "其他分布式光伏"], index=0)
    seasonal_variation = st.checkbox("月用电量波动明显/存在季节性停产", value=False)
    st.caption(f"当前城市区县数量：{len(counties)}")
    latitude_mode = st.radio("项目纬度来源", ["按区县自动匹配", "手动输入纬度"], horizontal=True)
    manual_latitude = None
    if latitude_mode == "手动输入纬度":
        manual_latitude = st.number_input("项目纬度(°)", min_value=0.0, max_value=55.0, value=float(solar_profile.latitude), step=0.1)
    roof_type = st.selectbox("屋面类型", ["彩钢瓦屋面", "混凝土平屋面", "其他屋面"], index=0)
    roof_slope_deg = st.number_input("屋面坡度(°)", min_value=0.0, max_value=60.0, value=5.0, step=1.0)
    project_priority = st.selectbox("倾角策略", ["均衡", "发电量优先", "装机容量优先", "抗风优先"], index=0)
    tilt_recommendation = recommend_tilt_angle(
        province=province,
        city=city,
        county=county,
        location_latitude=solar_profile.latitude,
        roof_type=roof_type,
        roof_slope_deg=roof_slope_deg,
        priority=project_priority,
        manual_latitude=manual_latitude,
    )
    st.caption(f"光照条件：{solar_profile.resource_level}｜理论倾角约 {tilt_recommendation.theoretical_tilt_deg:.0f}°｜等效小时 {solar_profile.equivalent_hours:.0f} h")

with st.sidebar:
    st.divider()
    st.subheader("并网方式")
    grid_mode = st.selectbox("并网模式", GRID_MODES, index=1)
    voltage_level = st.selectbox("接入电压等级", VOLTAGE_LEVELS, index=0)
    connection_point_type = st.selectbox("接入点类型", CONNECTION_POINT_TYPES, index=1)
    default_allow_export = grid_mode != "自发自用，不允许反送"
    allow_export = st.checkbox("允许余电上网", value=default_allow_export, disabled=grid_mode in ["全额上网", "自发自用，不允许反送"])
    if grid_mode == "全额上网":
        allow_export = True
    if grid_mode == "自发自用，不允许反送":
        allow_export = False
    export_limit_kw = 0.0 if not allow_export else st.number_input("最大允许反送功率(kW)", min_value=0.0, value=1000.0, step=50.0)
    grid_capacity_limit_kw = st.number_input("并网容量限制(kW)", min_value=0.0, value=1000.0, step=50.0)
    grid_connection_distance_m = st.number_input("并网点距离(m)", min_value=0.0, value=80.0, step=10.0)
    self_use_tariff_grid = st.number_input("自用电价(元/kWh)", min_value=0.0, value=REVENUE_DEFAULTS["self_use_tariff"], step=0.01)
    export_tariff_grid = st.number_input("上网电价(元/kWh)", min_value=0.0, value=0.0 if not allow_export else REVENUE_DEFAULTS["feed_in_tariff"], step=0.01)
    need_transformer = st.checkbox("需要箱变", value=voltage_level == "35kV 高压")
    need_distribution_room_retrofit = st.checkbox("需要配电房改造", value=False)
    need_protection_device = st.checkbox("需要继电保护/防孤岛/电能质量装置", value=("10kV" in voltage_level or "35kV" in voltage_level))
    storage_power_kw = storage_capacity_kwh = 0.0
    storage_charge_efficiency = storage_discharge_efficiency = 0.95
    storage_cost_per_kwh = 900.0
    peak_tariff = 1.05
    flat_tariff = 0.75
    valley_tariff = 0.35
    if grid_mode == "储能配套削峰填谷":
        storage_power_kw = st.number_input("储能功率(kW)", min_value=0.0, value=250.0, step=50.0)
        storage_capacity_kwh = st.number_input("储能容量(kWh)", min_value=0.0, value=500.0, step=50.0)
        storage_cost_per_kwh = st.number_input("储能单价(元/kWh)", min_value=0.0, value=900.0, step=50.0)
        peak_tariff = st.number_input("峰电价(元/kWh)", min_value=0.0, value=1.05, step=0.01)
        flat_tariff = st.number_input("平电价(元/kWh)", min_value=0.0, value=0.75, step=0.01)
        valley_tariff = st.number_input("谷电价(元/kWh)", min_value=0.0, value=0.35, step=0.01)
    connection_points = []
    if grid_mode == "多并网点接入":
        points_df = st.data_editor(
            pd.DataFrame(
                [
                    {"connection_point_name": "并网点1", "voltage_level": voltage_level, "capacity_limit_kw": 500.0, "distance_m": 80.0, "connection_cost": 80000.0, "related_roof_area": 2500.0, "allocated_capacity_kw": 500.0},
                    {"connection_point_name": "并网点2", "voltage_level": voltage_level, "capacity_limit_kw": 500.0, "distance_m": 120.0, "connection_cost": 100000.0, "related_roof_area": 2500.0, "allocated_capacity_kw": 500.0},
                ]
            ),
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            key="grid_connection_points_editor",
        )
        connection_points = points_df.to_dict(orient="records")
    grid_connection = normalize_grid_connection(
        GridConnection(
            grid_mode=grid_mode,
            voltage_level=voltage_level,
            connection_point_type=connection_point_type,
            allow_export=allow_export,
            export_limit_kw=export_limit_kw,
            export_tariff=export_tariff_grid,
            self_use_tariff=self_use_tariff_grid,
            grid_capacity_limit_kw=grid_capacity_limit_kw,
            grid_connection_distance_m=grid_connection_distance_m,
            need_transformer=need_transformer,
            need_distribution_room_retrofit=need_distribution_room_retrofit,
            need_protection_device=need_protection_device,
            connection_points=connection_points,
            storage_enabled=grid_mode == "储能配套削峰填谷",
            storage_power_kw=storage_power_kw,
            storage_capacity_kwh=storage_capacity_kwh,
            storage_charge_efficiency=storage_charge_efficiency,
            storage_discharge_efficiency=storage_discharge_efficiency,
            storage_cost_per_kwh=storage_cost_per_kwh,
            peak_tariff=peak_tariff,
            flat_tariff=flat_tariff,
            valley_tariff=valley_tariff,
        )
    )
    for warning in validate_grid_connection(grid_connection):
        st.warning(warning)

render_summary_strip(
    [
        ("项目地点", project_location),
        ("资源等级", solar_profile.resource_level),
        ("理论最佳倾角", f"{tilt_recommendation.theoretical_tilt_deg:.0f}°"),
        ("年等效利用小时", f"{solar_profile.equivalent_hours:,.0f} h"),
    ]
)
render_note("当前区县光照数据为省级代表值或内置估算值，不是实测区县级辐照数据。正式测算请使用气象数据、PVsyst、Meteonorm、Solargis 或设计院资源报告复核。")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["Step 1 容量测算", "Step 2 消纳测算", "Step 3 造价测算", "Step 4 收益测算", "Step 5 动态调整", "Step 6 导出报告"]
)

with tab1:
    render_section_heading(1, "容量测算", "从屋顶面积、组件规格和扣减系数推算可安装容量")
    render_note("图片识别面积仅用于初步测算，最终面积应以现场踏勘、设计图纸或测绘结果为准。")
    area_basis_label = st.radio(
        "面积口径",
        ["屋顶总面积", "可利用面积", "已确认可铺设面积"],
        horizontal=True,
        help="屋顶总面积应用屋顶利用率、综合扣减和排布损耗；可利用面积不再应用屋顶利用率；已确认可铺设面积默认只应用排布损耗。",
    )
    area_basis_map = {"屋顶总面积": "roof_total_area", "可利用面积": "usable_area", "已确认可铺设面积": "installable_area"}
    area_basis = area_basis_map[area_basis_label]
    render_note("请确认面积口径：如果输入的是已扣除通道、设备区、遮挡后的可铺设面积，请选择“已确认可铺设面积”，避免屋顶利用率和综合扣减重复扣减。")
    mode = st.radio("面积输入方式", ["手动输入面积", "地图截图自动识别", "图片矩形辅助估算"], horizontal=True)
    estimated_area = 5000.0
    area_input_label = f"{area_basis_label}(平方米)"
    area_result_label = area_input_label
    if mode == "地图截图自动识别":
        area_input_label = "框选面积(平方米)"
        area_result_label = "框选面积(平方米)"
        image_file = st.file_uploader("上传奥维互动地图截图", type=["png", "jpg", "jpeg"], key="map_auto")
        render_note("自动识别会用橙色框初步标出疑似可铺光伏区域。识别结果仅用于初算，必须支持人工校正并以现场踏勘和设计图纸为准。")
        render_note("比例尺像素长度必须根据当前截图重新测量。若地图缩放或截图尺寸变化，不能沿用之前的像素长度。")
        if image_file:
            original_map_image = load_rgb_image(image_file)
            map_image, display_scale_ratio = resized_for_selector(original_map_image)
            image_width, image_height = map_image.size
            detected_regions = detect_pv_candidate_regions(map_image)

            c_scale1, c_scale2, c_scale3 = st.columns(3)
            with c_scale1:
                scale_meters = st.number_input("比例尺实际长度(m)", min_value=0.01, value=10.0, step=1.0, key="map_scale_m")
            with c_scale2:
                default_scale_pixels = round(56.0 * display_scale_ratio, 2)
                scale_pixels = st.number_input("比例尺像素长度(px)", min_value=0.01, value=default_scale_pixels, step=1.0, key=f"map_scale_px_{image_width}")
            with c_scale3:
                selected_region_idx = st.selectbox(
                    "选择识别区域",
                    list(range(len(detected_regions))),
                    format_func=lambda idx: f"区域{idx + 1}｜置信度 {detected_regions[idx].confidence:.2f}",
                )
            if display_scale_ratio < 1:
                st.caption(f"为保证图上框选稳定，页面已把截图按 {display_scale_ratio:.2f} 倍压缩显示；比例尺像素长度请按当前显示图填写，默认已随压缩比例换算。")
            st.caption("后续预留：支持在截图上点击比例尺两端点，自动计算比例尺像素长度。")

            base_region = detected_regions[selected_region_idx]
            auto_points = [
                {"order": 1, "x": float(base_region.x), "y": float(base_region.y)},
                {"order": 2, "x": float(base_region.x + base_region.width), "y": float(base_region.y)},
                {"order": 3, "x": float(base_region.x + base_region.width), "y": float(base_region.y + base_region.height)},
                {"order": 4, "x": float(base_region.x), "y": float(base_region.y + base_region.height)},
            ]
            image_signature = f"{image_file.name}-{getattr(image_file, 'size', 0)}-{selected_region_idx}-{image_width}x{image_height}"
            if st.session_state.get("map_polygon_signature") != image_signature:
                st.session_state["map_polygon_signature"] = image_signature
                st.session_state["map_polygon_points"] = auto_points
                st.session_state["map_polygon_closed"] = True

            reset_col, help_col = st.columns([1, 3])
            with reset_col:
                if st.button("重置为自动边界", key=f"reset_polygon_{image_signature}"):
                    st.session_state["map_polygon_points"] = auto_points
                    st.session_state["map_polygon_closed"] = True
            with help_col:
                st.caption("人工修改区域：直接在截图中沿屋顶边缘点选，点击第一个点或按“闭合区域”完成不规则框选。")

            selected_polygon = polygon_selector(
                map_image,
                st.session_state.get("map_polygon_points", auto_points),
                image_id=image_signature,
                closed=st.session_state.get("map_polygon_closed", True),
                key=f"polygon_selector_{image_signature}",
            )
            if isinstance(selected_polygon, dict) and "points" in selected_polygon:
                st.session_state["map_polygon_points"] = selected_polygon.get("points", [])
                st.session_state["map_polygon_closed"] = bool(selected_polygon.get("closed", False))

            polygon_points = [
                (float(point["x"]), float(point["y"]))
                for point in st.session_state.get("map_polygon_points", [])
                if point.get("x") is not None and point.get("y") is not None
            ]
            area_estimate = estimate_polygon_area(polygon_points, scale_meters, scale_pixels, (image_width, image_height))
            polygon_is_valid = len(polygon_points) >= 3 and st.session_state.get("map_polygon_closed", False)
            estimated_area = area_estimate.estimated_area_m2 if polygon_is_valid else 0.0
            k1, k2, k3 = st.columns(3)
            k1.metric("估算可铺设面积", f"{estimated_area:,.2f} 平方米")
            k2.metric("比例尺换算", f"{area_estimate.meters_per_pixel:.4f} 米/像素")
            k3.metric("已选点/像素面积", f"{len(polygon_points)} 点｜{area_estimate.polygon_area_px:,.0f} px")
            if not polygon_is_valid:
                st.warning("请至少选择 3 个点并闭合区域后，再使用该面积进入容量测算。")
            else:
                st.image(draw_polygon_overlay(map_image, polygon_points), caption="橙色不规则框为最终闭合区域", width="stretch")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "自动候选区域": f"区域{idx + 1}",
                            "X(px)": region.x,
                            "Y(px)": region.y,
                            "宽(px)": region.width,
                            "高(px)": region.height,
                            "像素面积": region.area_px,
                            "置信度": region.confidence,
                        }
                        for idx, region in enumerate(detected_regions)
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
    elif mode == "图片矩形辅助估算":
        area_input_label = "图片估算面积(平方米)"
        area_result_label = "图片估算面积(平方米)"
        image_file = st.file_uploader("上传屋顶/地图图片", type=["png", "jpg", "jpeg"])
        col_a, col_b = st.columns(2)
        with col_a:
            reference_pixels = st.number_input("比例尺像素长度(px)", min_value=0.01, value=100.0, step=10.0)
            reference_meters = st.number_input("比例尺实际长度(m)", min_value=0.0, value=10.0, step=1.0)
        with col_b:
            selected_width_px = st.number_input("矩形区域宽度(px)", min_value=0.0, value=1000.0, step=10.0)
            selected_height_px = st.number_input("矩形区域高度(px)", min_value=0.0, value=600.0, step=10.0)
        if image_file:
            st.image(image_file, caption="上传图片预览", width="stretch")
            width, height = open_image_size(image_file)
            image_file.seek(0)
            area_estimate = estimate_rect_area(
                width, height, selected_width_px, selected_height_px, reference_pixels, reference_meters
            )
            estimated_area = area_estimate.estimated_area_m2
            st.success(f"图片辅助估算面积：{estimated_area:,.2f} 平方米")
    usable_area_m2 = st.number_input(area_input_label, min_value=0.0, value=float(estimated_area), step=100.0)

    c1, c2, c3 = st.columns(3)
    with c1:
        module_area_m2 = st.number_input("单块组件面积(平方米)", min_value=0.01, value=CAPACITY_DEFAULTS["module_area_m2"], step=0.01)
        module_power_wp = st.number_input(
            "单块组件功率(Wp)",
            min_value=0.0,
            value=CAPACITY_DEFAULTS["module_power_kwp"] * 1000,
            step=5.0,
            help="页面按 Wp 输入，后台自动换算为 kWp 参与容量测算。",
        )
        module_power_kwp = module_power_wp / 1000
    with c2:
        default_roof_utilization = CAPACITY_DEFAULTS["roof_utilization_ratio"] if area_basis == "roof_total_area" else 1.0
        default_deduction = CAPACITY_DEFAULTS["deduction_ratio"] if area_basis in ["roof_total_area", "usable_area"] else 0.0
        roof_utilization_ratio = pct_input("屋顶利用率", default_roof_utilization)
        deduction_ratio = pct_input("检修通道/安全间距/设备区扣减比例", default_deduction)
    with c3:
        layout_loss_ratio = pct_input("组件排布损耗系数", CAPACITY_DEFAULTS["layout_loss_ratio"])
        dc_ac_ratio = st.number_input("容配比", min_value=0.1, value=CAPACITY_DEFAULTS["dc_ac_ratio"], step=0.01)
    d1, d2 = st.columns(2)
    with d1:
        apply_roof_utilization = st.checkbox("应用屋顶利用率", value=area_basis == "roof_total_area")
    with d2:
        apply_deduction = st.checkbox("应用综合扣减比例", value=area_basis in ["roof_total_area", "usable_area"])

    capacity = calculate_capacity(
        usable_area_m2,
        module_area_m2,
        module_power_kwp,
        roof_utilization_ratio,
        deduction_ratio,
        layout_loss_ratio,
        dc_ac_ratio,
        recommended_tilt_deg=tilt_recommendation.recommended_tilt_deg,
        tilt_layout_adjustment_ratio=tilt_recommendation.layout_adjustment_ratio,
        area_basis=area_basis_label,
        apply_roof_utilization=apply_roof_utilization,
        apply_deduction=apply_deduction,
        roof_type=roof_type,
        grid_connection=grid_connection,
    )
    grid_capacity_check = {
        "roof_installable_capacity_kwp": capacity.roof_installable_capacity_kwp,
        "grid_capacity_limit_kw": capacity.grid_capacity_limit_kw,
        "grid_limited_capacity_kwp": capacity.dc_capacity_kwp,
        "capacity_limited_by_grid": capacity.capacity_limited_by_grid,
        "capacity_limit_note": capacity.capacity_limit_note,
    }
    if capacity.capacity_limited_by_grid:
        st.warning(capacity.capacity_limit_note)
    grid_capacity_info = {
        "屋顶可安装容量(kWp)": grid_capacity_check["roof_installable_capacity_kwp"],
        "并网容量限制(kW)": grid_capacity_check["grid_capacity_limit_kw"],
        "并网校核后容量(kWp)": grid_capacity_check["grid_limited_capacity_kwp"],
        "容量校核说明": grid_capacity_check["capacity_limit_note"],
    }
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("直流装机容量", f"{capacity.dc_capacity_kwp:,.2f} kWp", f"{capacity.dc_capacity_kwp / 1000:.3f} MWp")
    m2.metric("交流侧容量", f"{capacity.ac_capacity_kw:,.2f} kW")
    m3.metric("可安装组件数", f"{capacity.module_count:,} 块")
    m4.metric("装机密度", f"{capacity.density_kwp_per_m2:.3f} kWp/平方米")
    st.info(capacity.density_risk_note)
    st.dataframe(
        labeled_table(
            capacity.to_dict(),
            {
                "input_area_m2": "输入面积(平方米)",
                "usable_area_m2": area_result_label,
                "area_basis": "面积口径",
                "roof_utilization_ratio": "屋顶利用率",
                "deduction_ratio": "综合扣减比例",
                "layout_loss_ratio": "排布损耗比例",
                "applied_roof_utilization_ratio": "实际应用屋顶利用率",
                "applied_deduction_ratio": "实际应用综合扣减比例",
                "area_reduction_factor": "面积折减总系数",
                "effective_install_area_m2": "有效安装面积(平方米)",
                "module_count": "可安装组件数(块)",
                "dc_capacity_kwp": "直流装机容量(kWp)",
                "ac_capacity_kw": "交流侧容量(kW)",
                "dc_ac_ratio": "容配比",
                "area_utilization_ratio": "面积利用率",
                "density_kwp_per_m2": "单位面积装机密度(kWp/平方米)",
                "recommended_tilt_deg": "屋面实际推荐倾角(°)",
                "tilt_layout_adjustment_ratio": "倾角排布修正系数",
                "adjusted_layout_loss_ratio": "修正后组件排布损耗系数",
                "density_risk_note": "装机密度风险提示",
            },
        ),
        width="stretch",
        hide_index=True,
    )

    render_section_heading(1, "区县最佳倾角推荐", "数据库优先，缺省时按纬度分档估算，并结合屋面类型和项目策略修正")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("资源等级", solar_profile.resource_level)
    s2.metric("理论最佳倾角", f"{tilt_recommendation.theoretical_tilt_deg:.0f}°")
    s3.metric("屋面实际推荐倾角", f"{tilt_recommendation.recommended_tilt_deg:.1f}°")
    s4.metric("年等效利用小时数", f"{solar_profile.equivalent_hours:,.0f} h")
    s5.metric("每MWp年发电量", f"{solar_profile.annual_specific_yield_kwh_per_kwp * 1000 / 10000:.2f} 万kWh")
    render_note("区县最佳倾角为初步测算推荐值，最终应结合屋面结构、当地风荷载、阵列间距、遮挡分析和设计图纸确定。")
    render_note(f"{project_location}：光照数据说明：{solar_profile.data_source_note}。倾角数据库可通过 data/county_tilt.csv 覆盖，模板见 data/county_tilt_template.csv。")
    st.dataframe(
        pd.DataFrame(
            [
                {"修正因素": "倾角数据来源", "说明": tilt_recommendation.data_source},
                {"修正因素": "项目纬度", "说明": f"{tilt_recommendation.latitude:.2f}°"},
                {"修正因素": "理论最佳倾角", "说明": f"按纬度分档规则估算为 {tilt_recommendation.theoretical_tilt_deg:.0f}°"},
                {"修正因素": "数据库默认屋面倾角", "说明": f"{tilt_recommendation.rooftop_default_tilt_deg:.1f}°"},
                {"修正因素": "屋面类型", "说明": roof_type},
                {"修正因素": "屋面坡度", "说明": f"{roof_slope_deg:.1f}°；彩钢瓦顺坡安装时倾角取屋面坡度"},
                {"修正因素": "项目策略", "说明": project_priority},
                {"修正因素": "倾角排布修正", "说明": f"{tilt_recommendation.layout_adjustment_ratio * 100:.1f}% 已计入容量测算"},
                {"修正因素": "推荐结论", "说明": "；".join(tilt_recommendation.notes)},
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    module_power_options = sorted(set([550.0, 585.0, 610.0, 620.0, 650.0, 700.0, module_power_wp]))
    st.dataframe(module_generation_table(solar_profile, module_power_options), width="stretch")

with tab2:
    render_section_heading(2, "消纳测算", "支持逐时负荷曲线、月度分时电费单和快速估算三种消纳判断")
    first_year_generation_for_consumption = capacity.dc_capacity_kwp * solar_profile.equivalent_hours * (
        1 - REVENUE_DEFAULTS["first_year_degradation_ratio"]
    )
    render_note(
        "精确模式适合已有15分钟负荷曲线的项目；月度分时模式适合有12个月尖峰平谷电费单的项目；快速估算用于前期粗筛。"
    )
    render_note("节假日和停产安排会显著影响自发自用比例。若企业春节、周末或寒暑假停产较多，仅使用全年电量会高估消纳能力。正式投资测算建议提供15分钟负荷曲线。")
    holiday_df = load_holiday_config(HOLIDAY_CONFIG_PATH)
    with st.expander("节假日与停产日历设置", expanded=False):
        h1, h2, h3 = st.columns(3)
        with h1:
            analysis_year = st.number_input("测算年份", min_value=2020, max_value=2040, value=2026, step=1)
            weekend_mode = st.selectbox("是否周末生产", ["周末正常生产", "周末低负荷生产", "周末停产"], index=2)
        weekend_default_map = {
            "周末正常生产": WEEKEND_LOAD_FACTOR_NORMAL,
            "周末低负荷生产": WEEKEND_LOAD_FACTOR_LOW,
            "周末停产": WEEKEND_LOAD_FACTOR_STOP,
        }
        with h2:
            weekend_load_factor = pct_input("周末负荷系数", weekend_default_map[weekend_mode])
            legal_holiday_load_factor = pct_input("法定节假日负荷系数", LEGAL_HOLIDAY_LOAD_FACTOR)
        with h3:
            force_holiday_adjustment = st.checkbox("强制应用节假日修正到逐时曲线", value=False)
            spring_enabled = st.checkbox("春节是否停产", value=True)

        s1, s2, s3 = st.columns(3)
        with s1:
            spring_start = st.date_input("春节停产开始日期", value=pd.Timestamp(f"{int(analysis_year)}-02-16").date())
        with s2:
            spring_end = st.date_input("春节停产结束日期", value=pd.Timestamp(f"{int(analysis_year)}-02-22").date())
        with s3:
            spring_load_factor = pct_input("春节停产负荷系数", SPRING_FESTIVAL_LOAD_FACTOR)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            maintenance_enabled = st.checkbox("是否存在年度检修停产", value=False)
        with m2:
            maintenance_start = st.date_input("检修停产开始日期", value=pd.Timestamp(f"{int(analysis_year)}-08-01").date())
        with m3:
            maintenance_end = st.date_input("检修停产结束日期", value=pd.Timestamp(f"{int(analysis_year)}-08-03").date())
        with m4:
            maintenance_load_factor = pct_input("检修停产负荷系数", MAINTENANCE_LOAD_FACTOR)

        st.caption("内置法定节假日/调休补班日，可在下表修改负荷系数；第一版不联网自动更新国家放假安排。")
        edited_holiday_df = st.data_editor(
            holiday_df,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            key="holiday_config_editor",
        )
        st.caption("自定义停产/低负荷日期：可添加春节以外的寒暑假、园区停产、企业临时检修等多个日期区间。")
        custom_template = pd.DataFrame(
            [
                {
                    "名称": "自定义停产",
                    "开始日期": pd.Timestamp(f"{int(analysis_year)}-07-01").date(),
                    "结束日期": pd.Timestamp(f"{int(analysis_year)}-07-01").date(),
                    "负荷系数": CUSTOM_STOP_LOAD_FACTOR,
                    "启用": False,
                }
            ]
        )
        custom_df = st.data_editor(
            custom_template,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            key="custom_shutdown_editor",
            column_config={
                "负荷系数": st.column_config.NumberColumn("负荷系数", min_value=0.0, max_value=1.0, step=0.05),
                "启用": st.column_config.CheckboxColumn("启用"),
            },
        )
        custom_periods = [
            {
                "name": row.get("名称", "自定义停产"),
                "start_date": row.get("开始日期"),
                "end_date": row.get("结束日期"),
                "load_factor": row.get("负荷系数", CUSTOM_STOP_LOAD_FACTOR),
                "enabled": bool(row.get("启用", False)),
                "type": "custom_stop",
            }
            for _, row in custom_df.iterrows()
        ]
        holiday_calendar_config = build_holiday_calendar_config(
            int(analysis_year),
            edited_holiday_df,
            weekend_mode,
            weekend_load_factor,
            legal_holiday_load_factor,
            spring_enabled,
            spring_start,
            spring_end,
            spring_load_factor,
            maintenance_enabled,
            maintenance_start,
            maintenance_end,
            maintenance_load_factor,
            custom_periods,
            force_holiday_adjustment,
        )
        holiday_calendar_table = build_calendar_table(int(analysis_year), holiday_calendar_config)
        st.dataframe(holiday_calendar_table.head(40), width="stretch", hide_index=True)

    consumption_mode = st.radio(
        "消纳计算模式",
        ["精确模式", "月度分时模式", "快速估算模式"],
        horizontal=True,
        index=2,
    )
    default_annual_consumption = 4_000_000.0
    consumption_detail_table: pd.DataFrame | None = None
    selected_production_mode = "按负荷曲线/分时电量测算"

    if consumption_mode == "精确模式":
        c1, c2 = st.columns(2)
        with c1:
            load_curve_file = st.file_uploader("上传15分钟负荷曲线 Excel / CSV", type=["xlsx", "xls", "csv"], key="load_curve")
        with c2:
            pv_curve_file = st.file_uploader("上传光伏逐时出力曲线（可选）", type=["xlsx", "xls", "csv"], key="pv_curve")
        st.caption("负荷曲线字段至少包含：时间、负荷kW或用电量kWh。默认优先使用实际曲线；如需对曲线强制乘以日历负荷系数，请在上方勾选“强制应用节假日修正到逐时曲线”。")
        if load_curve_file:
            try:
                load_curve = normalize_power_or_energy_curve(read_curve_file(load_curve_file), value_kind="load")
                pv_curve = normalize_power_or_energy_curve(read_curve_file(pv_curve_file), value_kind="pv") if pv_curve_file else None
                consumption, consumption_detail_table = calculate_precise_consumption(
                    load_curve,
                    first_year_generation_for_consumption,
                    pv_curve,
                    capacity.dc_capacity_kwp,
                    0.0,
                    0.0,
                    holiday_calendar_config,
                    force_holiday_adjustment,
                )
            except Exception as exc:
                st.warning(f"负荷曲线解析失败，已临时切换为快速估算。错误：{exc}")
                consumption = calculate_quick_consumption(
                    default_annual_consumption,
                    CONSUMPTION_DEFAULTS["daytime_usage_ratio"],
                    first_year_generation_for_consumption,
                    "单班制",
                    True,
                    0.0,
                    capacity.dc_capacity_kwp,
                    0.0,
                    holiday_calendar_config,
                )
        else:
            st.info("请上传15分钟负荷曲线后启用精确消纳测算；当前结果先按快速估算兜底显示。")
            consumption = calculate_quick_consumption(
                default_annual_consumption,
                CONSUMPTION_DEFAULTS["daytime_usage_ratio"],
                first_year_generation_for_consumption,
                "单班制",
                True,
                0.0,
                capacity.dc_capacity_kwp,
                0.0,
                holiday_calendar_config,
            )

    elif consumption_mode == "月度分时模式":
        c1, c2 = st.columns(2)
        with c1:
            monthly_bill_file = st.file_uploader("上传12个月电费单 / 分时电量表", type=["pdf", "xlsx", "xls", "csv"], key="monthly_tou")
        with c2:
            flat_daytime_ratio = pct_input("平段白天可消纳比例", 0.60)
        st.caption("建议表格字段包含：月份、总电量、尖电量、峰电量、平电量、谷电量。节假日/停产影响由上方日历模块统一修正。不同省份分时电价时段不同，若用于正式测算，请按当地最新分时电价政策配置尖峰平谷时段。")
        tou_config = load_tou_period_config()
        tou_weights = tou_weights_for_province(province, tou_config)
        monthly_source = pd.DataFrame(
            {
                "月份": list(range(1, 13)),
                "总电量(kWh)": [default_annual_consumption / 12] * 12,
                "尖电量(kWh)": [default_annual_consumption / 12 * 0.10] * 12,
                "峰电量(kWh)": [default_annual_consumption / 12 * 0.35] * 12,
                "平电量(kWh)": [default_annual_consumption / 12 * 0.35] * 12,
                "谷电量(kWh)": [default_annual_consumption / 12 * 0.20] * 12,
                "节假日/停产天数": [0.0] * 12,
            }
        )
        if monthly_bill_file:
            try:
                if monthly_bill_file.name.lower().endswith(".pdf"):
                    parsed = parse_bill_file(monthly_bill_file)
                    for warning in parsed.warnings:
                        st.warning(warning)
                    if not parsed.parsed_table.empty and {"字段", "值"}.isdisjoint(parsed.parsed_table.columns):
                        monthly_source = normalize_monthly_tou_table(parsed.parsed_table)
                    else:
                        st.info("PDF 暂未解析出12个月分时表，下面可先手动录入尖峰平谷电量。")
                else:
                    monthly_source = normalize_monthly_tou_table(read_curve_file(monthly_bill_file))
            except Exception as exc:
                st.warning(f"电费单解析失败，请在下表手动录入12个月分时电量。错误：{exc}")
        edited_monthly = st.data_editor(
            monthly_source,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="monthly_tou_editor",
        )
        consumption, consumption_detail_table = calculate_monthly_tou_consumption(
            normalize_monthly_tou_table(edited_monthly),
            first_year_generation_for_consumption,
            capacity.dc_capacity_kwp,
            flat_daytime_ratio,
            0.0,
            0.0,
            holiday_calendar_config,
            tou_weights,
        )

    else:
        bill_file = st.file_uploader("上传电费单 PDF / Excel（可选）", type=["pdf", "xlsx", "xls"], key="bill")
        if bill_file:
            try:
                parsed = parse_bill_file(bill_file)
                default_annual_consumption = parsed.annual_consumption_kwh or default_annual_consumption
                if parsed.parsed_status == "need_manual_review":
                    st.warning("电费单未能可靠识别总电量，请在下方手动修正年用电量。")
                for warning in parsed.warnings:
                    st.warning(warning)
                if not parsed.parsed_table.empty:
                    st.dataframe(parsed.parsed_table.head(20), width="stretch")
            except Exception as exc:
                st.warning(f"电费单解析失败，请手动填写年用电量。错误：{exc}")

        c1, c2, c3 = st.columns(3)
        with c1:
            annual_consumption_kwh = st.number_input("年用电量(kWh)", min_value=0.0, value=float(default_annual_consumption), step=10000.0)
        with c2:
            daytime_usage_ratio = pct_input("白天用电比例", CONSUMPTION_DEFAULTS["daytime_usage_ratio"])
        with c3:
            production_mode = st.selectbox("生产制度", ["三班连续生产", "双班制", "单班制", "周末停产", "季节性停产"], index=2)
            selected_production_mode = production_mode
        weekend_production = weekend_mode != "周末停产"
        shutdown_days = 0.0
        consumption = calculate_quick_consumption(
            annual_consumption_kwh,
            daytime_usage_ratio,
            first_year_generation_for_consumption,
            production_mode,
            weekend_production,
            shutdown_days,
            capacity.dc_capacity_kwp,
            0.0,
            holiday_calendar_config,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("光伏年发电量", energy(consumption.pv_generation_kwh))
    m2.metric("自发自用比例", ratio(consumption.self_use_ratio))
    m3.metric("余电上网比例", ratio(consumption.feed_in_ratio))
    m4.metric("月均用电量", energy(consumption.monthly_average_kwh))
    st.warning(consumption.risk_note)
    grid_adjusted_consumption = adjust_consumption_for_grid(consumption.to_dict(), grid_connection)
    consumption.self_use_kwh = grid_adjusted_consumption["self_use_kwh"]
    consumption.feed_in_kwh = grid_adjusted_consumption["feed_in_kwh"]
    consumption.self_use_ratio = grid_adjusted_consumption["self_use_ratio"]
    consumption.feed_in_ratio = grid_adjusted_consumption["feed_in_ratio"]
    st.markdown("#### 并网方式修正后的消纳结果")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("自用电量", energy(grid_adjusted_consumption["self_use_kwh"]))
    g2.metric("余电上网电量", energy(grid_adjusted_consumption["feed_in_kwh"]))
    g3.metric("弃光电量", energy(grid_adjusted_consumption["curtailment_kwh"]))
    g4.metric("弃光率", ratio(grid_adjusted_consumption["curtailment_ratio"]))
    st.dataframe(
        labeled_table(
            consumption.to_dict(),
            {
                "annual_consumption_kwh": "年用电量(kWh)",
                "monthly_average_kwh": "月均用电量(kWh)",
                "daytime_consumption_kwh": "白天用电量(kWh)",
                "pv_generation_kwh": "光伏年发电量(kWh)",
                "self_use_kwh": "自用电量(kWh)",
                "feed_in_kwh": "余电上网电量(kWh)",
                "self_use_ratio": "自发自用比例",
                "feed_in_ratio": "余电上网比例",
                "annual_holiday_days": "年度节假日天数",
                "weekend_shutdown_days": "周末停产天数",
                "spring_shutdown_days": "春节停产天数",
                "maintenance_shutdown_days": "检修停产天数",
                "custom_shutdown_days": "自定义停产天数",
                "low_load_days": "年度停产/低负荷天数",
                "pre_adjust_self_use_ratio": "修正前自发自用比例",
                "post_adjust_self_use_ratio": "修正后自发自用比例",
                "pre_adjust_feed_in_ratio": "修正前余电上网比例",
                "post_adjust_feed_in_ratio": "修正后余电上网比例",
                "holiday_extra_feed_in_kwh": "节假日导致的余电增加量(kWh)",
                "holiday_impact_note": "节假日影响说明",
                "data_quality_note": "数据质量提示",
                "risk_note": "消纳风险提示",
                "mode": "消纳计算模式",
            },
        ),
        width="stretch",
        hide_index=True,
    )
    if consumption_detail_table is not None and not consumption_detail_table.empty:
        st.caption("消纳明细预览")
        st.dataframe(consumption_detail_table.head(200), width="stretch", hide_index=True)
    st.caption("节假日与停产日历预览")
    st.dataframe(holiday_calendar_table.head(80), width="stretch", hide_index=True)

with tab3:
    render_section_heading(3, "造价测算", "按分项元/Wp、容量规模和一次性费用计算总投资")
    st.caption("单位造价为元/Wp；系统会按容量规模自动调整：<500kWp 上浮8%，>2MWp 下降5%。")
    cost_labels = {
        "module": "组件",
        "inverter": "逆变器",
        "mounting": "支架",
        "cable_tray": "电缆桥架",
        "distribution": "配电设备",
        "grid_connection": "并网接入",
        "civil_reinforcement": "土建及加固",
        "installation": "施工安装",
        "design_supervision_testing": "设计/监理/检测/验收",
        "project_management": "项目管理及其他",
    }
    unit_costs = {}
    cols = st.columns(2)
    for idx, (key, label) in enumerate(cost_labels.items()):
        with cols[idx % 2]:
            unit_costs[key] = st.number_input(f"{label}(元/Wp)", min_value=0.0, value=COST_DEFAULTS[key], step=0.01)
    c1, c2 = st.columns(2)
    with c1:
        contingency_ratio = pct_input("不可预见费率", COST_DEFAULTS["contingency_ratio"])
    with c2:
        other_one_time_cost_yuan = st.number_input("其他一次性费用(元)", min_value=0.0, value=0.0, step=10000.0)
    grid_extra_cost_items = grid_cost_items_yuan(capacity.dc_capacity_kwp, grid_connection)
    cost = calculate_cost(
        capacity.dc_capacity_kwp,
        unit_costs,
        contingency_ratio,
        other_one_time_cost_yuan,
        grid_connection=grid_connection,
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("总投资", money(cost.total_investment_yuan))
    m2.metric("单瓦造价", f"{cost.adjusted_unit_cost_yuan_per_wp:.3f} 元/Wp")
    m3.metric("单位千瓦投资", f"{cost.investment_per_kw_yuan:,.2f} 元/kWp")
    st.info(cost.risk_note)
    if grid_extra_cost_items:
        st.markdown("#### 并网方式新增费用")
        st.dataframe(pd.DataFrame([{"费用项": k, "金额(元)": v, "金额(万元)": v / 10000} for k, v in grid_extra_cost_items.items()]), width="stretch", hide_index=True)
    st.dataframe(
        labeled_table(
            cost.to_dict(),
            {
                "capacity_kwp": "装机容量(kWp)",
                "base_unit_cost_yuan_per_wp": "基础单瓦造价(元/Wp)",
                "adjusted_unit_cost_yuan_per_wp": "调整后单瓦造价(元/Wp)",
                "base_investment_yuan": "基础投资(元)",
                "contingency_yuan": "不可预见费(元)",
                "other_one_time_cost_yuan": "其他一次性费用(元)",
                "total_investment_yuan": "总投资(元)",
                "investment_per_kw_yuan": "单位千瓦投资(元/kWp)",
                "risk_note": "造价风险提示",
            },
        ),
        width="stretch",
        hide_index=True,
    )
    st.dataframe(pd.DataFrame([{"分项": k, "投资(元)": v, "投资(万元)": v / 10000} for k, v in cost.cost_items_yuan.items()]), width="stretch")

with tab4:
    render_section_heading(4, "收益测算", "生成运营期现金流，计算回收期、IRR、NPV 和 LCOE")
    revenue_method_note = "当前版本为简化全投资现金流测算口径，主要用于项目初筛。当前模型尚未完整考虑融资贷款、折旧抵税、增值税及附加、残值、逆变器更换、屋顶租金递增和合同能源管理分成。正式投资决策请采用完整财务模型复核。"
    render_note(revenue_method_note)
    c1, c2, c3 = st.columns(3)
    with c1:
        equivalent_hours = st.number_input(
            "首年等效利用小时数(h)",
            min_value=0.0,
            value=float(solar_profile.equivalent_hours),
            step=50.0,
            help="默认来自所选地区的内置光照估算值，可按项目实际资源报告修正。",
        )
        operating_years = st.number_input("运营年限(年)", min_value=1, max_value=40, value=REVENUE_DEFAULTS["operating_years"], step=1)
        discount_rate = pct_input("折现率", REVENUE_DEFAULTS["discount_rate"])
    with c2:
        first_year_degradation_ratio = pct_input("首年衰减率", REVENUE_DEFAULTS["first_year_degradation_ratio"])
        annual_degradation_ratio = pct_input("后续年衰减率", REVENUE_DEFAULTS["annual_degradation_ratio"])
        income_tax_ratio = pct_input("所得税率", REVENUE_DEFAULTS["income_tax_ratio"])
    with c3:
        self_use_tariff = st.number_input("自用电价(元/kWh)", min_value=0.0, value=float(grid_connection.self_use_tariff), step=0.01)
        feed_in_tariff = st.number_input("上网电价(元/kWh)", min_value=0.0, value=float(grid_connection.export_tariff), step=0.01)
        contract_discount_ratio = pct_input("合同折扣比例", REVENUE_DEFAULTS["contract_discount_ratio"])

    c4, c5, c6 = st.columns(3)
    with c4:
        om_cost_yuan_per_wp_year = st.number_input("运维费(元/Wp/年)", min_value=0.0, value=REVENUE_DEFAULTS["om_cost_yuan_per_wp_year"], step=0.005)
        cleaning_cost_yuan_per_wp_year = st.number_input("清洗费(元/Wp/年)", min_value=0.0, value=REVENUE_DEFAULTS["cleaning_cost_yuan_per_wp_year"], step=0.005)
    with c5:
        insurance_ratio = pct_input("保险费率(占总投资/年)", REVENUE_DEFAULTS["insurance_ratio"])
        roof_rent_yuan_per_year = st.number_input("屋顶租金(元/年)", min_value=0.0, value=REVENUE_DEFAULTS["roof_rent_yuan_per_year"], step=10000.0)
    with c6:
        other_cost_yuan_per_year = st.number_input("其他运营费用(元/年)", min_value=0.0, value=REVENUE_DEFAULTS["other_cost_yuan_per_year"], step=10000.0)

    revenue_inputs = {
        "capacity_kwp": capacity.dc_capacity_kwp,
        "total_investment_yuan": cost.total_investment_yuan,
        "equivalent_hours": equivalent_hours,
        "first_year_degradation_ratio": first_year_degradation_ratio,
        "annual_degradation_ratio": annual_degradation_ratio,
        "operating_years": int(operating_years),
        "self_use_ratio": consumption.self_use_ratio,
        "feed_in_ratio": consumption.feed_in_ratio,
        "self_use_tariff": self_use_tariff,
        "feed_in_tariff": feed_in_tariff,
        "contract_discount_ratio": contract_discount_ratio,
        "om_cost_yuan_per_wp_year": om_cost_yuan_per_wp_year,
        "insurance_ratio": insurance_ratio,
        "cleaning_cost_yuan_per_wp_year": cleaning_cost_yuan_per_wp_year,
        "roof_rent_yuan_per_year": roof_rent_yuan_per_year,
        "other_cost_yuan_per_year": other_cost_yuan_per_year,
        "income_tax_ratio": income_tax_ratio,
        "discount_rate": discount_rate,
        "grid_connection": grid_connection,
        "curtailment_ratio": grid_adjusted_consumption.get("curtailment_ratio", 0.0),
        "storage_arbitrage_yuan": grid_adjusted_consumption.get("storage_arbitrage_yuan", 0.0),
        "recommended_tilt_deg": tilt_recommendation.recommended_tilt_deg,
    }
    revenue_calc_inputs = {key: value for key, value in revenue_inputs.items() if key != "recommended_tilt_deg"}
    revenue = calculate_revenue(**revenue_calc_inputs)
    if revenue.tax_simplification_note:
        st.warning(revenue.tax_simplification_note)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("首年发电量", energy(revenue.first_year_generation_kwh))
    m2.metric("静态回收期", years(revenue.simple_payback_years))
    m3.metric("项目 IRR", ratio(revenue.project_irr))
    m4.metric("NPV", money(revenue.project_npv_yuan))
    m5, m6, m7, m8 = st.columns(4)
    m5.metric("LCOE", f"{revenue.lcoe_yuan_per_kwh:.4f} 元/kWh")
    m6.metric("年均收入", money(revenue.average_revenue_yuan))
    m7.metric("年均净现金流", money(revenue.average_net_cashflow_yuan))
    m8.metric("动态回收期", years(revenue.discounted_payback_years))
    st.line_chart(revenue.cashflow_table.set_index("年份")[["累计现金流(元)", "净现金流(元)"]])
    st.line_chart(revenue.cashflow_table.set_index("年份")[["发电量(kWh)"]])
    st.dataframe(revenue.cashflow_table, width="stretch")

with tab5:
    render_section_heading(5, "动态调整与敏感性分析", "自动识别关键风险，并对投资、电价、小时数等因素做扰动测算")
    grid_risks = grid_risk_suggestions(grid_connection, grid_adjusted_consumption, capacity.dc_capacity_kwp)
    suggestions = build_risk_suggestions(
        consumption.self_use_ratio,
        consumption.feed_in_ratio,
        revenue.simple_payback_years,
        revenue.project_irr,
        revenue.unit_investment_yuan_per_wp,
        capacity.density_kwp_per_m2,
        seasonal_variation,
    )
    suggestions.extend(grid_risks)
    for item in suggestions:
        st.warning(item)
    st.markdown("#### 并网方式容量方案推荐")
    scenario_table = recommend_capacity_scenarios(
        grid_capacity_check["roof_installable_capacity_kwp"],
        equivalent_hours,
        consumption.annual_consumption_kwh,
        cost.investment_per_kw_yuan,
        grid_connection,
        discount_rate,
        int(operating_years),
        discount_rate,
    )
    st.dataframe(
        scenario_table.assign(
            方案容量比例=scenario_table["方案容量比例"].map(lambda x: f"{x * 100:.0f}%"),
            自发自用率=scenario_table["自发自用率"].map(lambda x: f"{x * 100:.2f}%"),
            余电上网率=scenario_table["余电上网率"].map(lambda x: f"{x * 100:.2f}%"),
            弃光率=scenario_table["弃光率"].map(lambda x: f"{x * 100:.2f}%"),
            IRR=scenario_table["IRR"].map(lambda x: "-" if pd.isna(x) else f"{x * 100:.2f}%"),
        ),
        width="stretch",
        hide_index=True,
    )
    sensitivity = sensitivity_analysis(revenue_calc_inputs, SENSITIVITY_STEPS)
    st.dataframe(
        sensitivity.assign(
            变化幅度=sensitivity["变化幅度"].map(lambda x: f"{x * 100:.0f}%"),
            IRR=sensitivity["IRR"].map(lambda x: "-" if pd.isna(x) else f"{x * 100:.2f}%"),
        ),
        width="stretch",
    )
    chart_df = sensitivity.copy()
    chart_df["变化幅度"] = chart_df["变化幅度"] * 100
    st.line_chart(chart_df, x="变化幅度", y="NPV(元)", color="变量")

with tab6:
    render_section_heading(6, "导出 Excel 测算报告", "一键生成包含参数、结果、现金流、敏感性和建议的工作簿")
    project_info = {
        "项目名称": project_name,
        "项目地点": project_location,
        "项目类型": project_type,
        "项目纬度": tilt_recommendation.latitude,
        "理论最佳倾角(°)": tilt_recommendation.theoretical_tilt_deg,
        "屋面实际推荐倾角(°)": tilt_recommendation.recommended_tilt_deg,
        "倾角排布修正系数": tilt_recommendation.layout_adjustment_ratio,
        "生产制度": selected_production_mode,
        "季节性波动": "是" if seasonal_variation else "否",
        "光照数据等级": solar_profile.solar_data_level,
        "光照数据口径说明": "当前区县光照数据为省级代表值或内置估算值，不是实测区县级辐照数据。正式测算请使用气象数据、PVsyst、Meteonorm、Solargis 或设计院资源报告复核。",
    }
    project_info.update(
        {
            "并网模式": grid_connection.grid_mode,
            "接入电压等级": grid_connection.voltage_level,
            "接入点类型": grid_connection.connection_point_type,
            "是否允许余电上网": "是" if grid_connection.allow_export else "否",
            "最大允许反送功率(kW)": grid_connection.export_limit_kw,
            "并网容量限制(kW)": grid_capacity_check["grid_capacity_limit_kw"],
        }
    )
    revenue_summary = {
        "首年发电量(kWh)": revenue.first_year_generation_kwh,
        "年均发电量(kWh)": revenue.average_generation_kwh,
        "全生命周期发电量(kWh)": revenue.lifetime_generation_kwh,
        "年均收入(元)": revenue.average_revenue_yuan,
        "年均运营成本(元)": revenue.average_operating_cost_yuan,
        "年均净现金流(元)": revenue.average_net_cashflow_yuan,
        "总投资(元)": revenue.total_investment_yuan,
        "单瓦投资(元/Wp)": revenue.unit_investment_yuan_per_wp,
        "静态回收期(年)": revenue.simple_payback_years,
        "动态回收期(年)": revenue.discounted_payback_years,
        "项目IRR": revenue.project_irr,
        "NPV(元)": revenue.project_npv_yuan,
        "LCOE(元/kWh)": revenue.lcoe_yuan_per_kwh,
        "财务模型范围": revenue.finance_model_scope,
        "收益测算口径说明": revenue_method_note,
        "所得税简化提示": revenue.tax_simplification_note,
    }
    grid_analysis = grid_analysis_summary(
        grid_connection,
        grid_capacity_check,
        grid_adjusted_consumption,
        sum(grid_extra_cost_items.values()),
        grid_risks,
    )
    excel_bytes = build_excel_report(
        project_info,
        capacity.to_dict(),
        consumption.to_dict(),
        cost.to_dict(),
        revenue_summary,
        revenue.cashflow_table,
        sensitivity,
        suggestions,
        holiday_calendar_table,
        unit_costs,
        grid_analysis,
        scenario_table,
    )
    st.download_button(
        "下载 Excel 测算报告",
        data=excel_bytes,
        file_name=f"{project_name}_光伏项目测算.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.success("Excel 包含：项目基础参数、容量测算、消纳测算、造价测算、收益测算、25年现金流、敏感性分析、节假日与停产修正、风险提示与优化建议。")
