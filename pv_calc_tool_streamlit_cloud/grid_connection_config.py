from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .finance_calc import discounted_payback, irr, npv, simple_payback


GRID_MODES = [
    "全额上网",
    "自发自用，余电上网",
    "自发自用，不允许反送",
    "储能配套削峰填谷",
    "多并网点接入",
]

VOLTAGE_LEVELS = ["低压 380V", "10kV 高压", "35kV 高压", "用户自定义"]
CONNECTION_POINT_TYPES = ["低压配电柜", "变压器低压侧", "10kV 母线", "专用箱变", "新建开关站", "多个接入点"]


@dataclass
class GridConnection:
    grid_mode: str = "自发自用，余电上网"
    voltage_level: str = "低压 380V"
    connection_point_type: str = "变压器低压侧"
    allow_export: bool = True
    export_limit_kw: float = 0.0
    export_tariff: float = 0.38
    self_use_tariff: float = 0.75
    grid_capacity_limit_kw: float = 999999.0
    grid_connection_distance_m: float = 80.0
    need_transformer: bool = False
    need_distribution_room_retrofit: bool = False
    need_protection_device: bool = False
    connection_points: list[dict] = field(default_factory=list)
    storage_enabled: bool = False
    storage_power_kw: float = 0.0
    storage_capacity_kwh: float = 0.0
    storage_charge_efficiency: float = 0.95
    storage_discharge_efficiency: float = 0.95
    storage_cost_per_kwh: float = 900.0
    peak_tariff: float = 1.05
    flat_tariff: float = 0.75
    valley_tariff: float = 0.35

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GridEnergyResult:
    pv_generation_kwh: float
    self_use_kwh: float
    export_kwh: float
    curtailment_kwh: float
    purchase_kwh: float
    self_use_ratio: float
    export_ratio: float
    curtailment_ratio: float
    storage_arbitrage_yuan: float
    annual_revenue_yuan: float
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def default_grid_connection(capacity_kw: float = 0.0, mode: str = "自发自用，余电上网") -> GridConnection:
    allow_export = mode not in {"自发自用，不允许反送"}
    return GridConnection(
        grid_mode=mode,
        allow_export=allow_export,
        export_limit_kw=max(float(capacity_kw), 0.0) if allow_export else 0.0,
        grid_capacity_limit_kw=max(float(capacity_kw), 0.0) if capacity_kw else 999999.0,
        need_protection_device=False,
        storage_enabled=mode == "储能配套削峰填谷",
    )


def normalize_grid_connection(config: GridConnection | dict) -> GridConnection:
    if isinstance(config, GridConnection):
        grid = config
    else:
        data = {k: v for k, v in dict(config).items() if k in GridConnection.__dataclass_fields__}
        grid = GridConnection(**data)

    if grid.grid_mode == "全额上网":
        grid.allow_export = True
    elif grid.grid_mode == "自发自用，不允许反送":
        grid.allow_export = False
        grid.export_limit_kw = 0.0
        grid.export_tariff = 0.0
    elif grid.grid_mode == "储能配套削峰填谷":
        grid.storage_enabled = True
    elif grid.grid_mode == "多并网点接入":
        grid.connection_point_type = "多个接入点"

    if not grid.allow_export:
        grid.export_limit_kw = 0.0
        grid.export_tariff = 0.0
    if "10kV" in grid.voltage_level or "35kV" in grid.voltage_level:
        grid.need_protection_device = True
        if grid.voltage_level == "35kV 高压":
            grid.need_transformer = True
    return grid


def validate_grid_connection(config: GridConnection | dict) -> list[str]:
    grid = normalize_grid_connection(config)
    warnings: list[str] = []
    if grid.grid_mode == "全额上网" and grid.export_tariff <= 0:
        warnings.append("全额上网模式必须填写上网电价。")
    if grid.grid_mode == "自发自用，余电上网" and (grid.self_use_tariff <= 0 or grid.export_tariff <= 0):
        warnings.append("自发自用余电上网模式必须填写自用电价和上网电价。")
    if grid.grid_mode == "自发自用，不允许反送" and (grid.allow_export or grid.export_limit_kw != 0):
        warnings.append("不允许反送模式下 allow_export 必须为 false，export_limit_kw 必须为 0。")
    if "10kV" in grid.voltage_level or "35kV" in grid.voltage_level:
        warnings.append("高压并网通常需要继电保护、计量、调度通讯和较长验收周期。")
    if grid.grid_connection_distance_m > 300:
        warnings.append("并网点距离较远，电缆、桥架和施工成本可能明显上升。")
    if grid.grid_mode == "多并网点接入":
        if not grid.connection_points:
            warnings.append("多并网点模式建议录入各接入点容量限制、距离和接入费用。")
        for point in grid.connection_points:
            if float(point.get("allocated_capacity_kw", 0) or 0) > float(point.get("capacity_limit_kw", 0) or 0):
                warnings.append(f"{point.get('connection_point_name', '并网点')} 分配容量超过容量限制。")
    return warnings


def total_grid_capacity_limit_kw(grid: GridConnection | dict) -> float:
    grid = normalize_grid_connection(grid)
    if grid.grid_mode == "多并网点接入" and grid.connection_points:
        return sum(max(float(p.get("capacity_limit_kw", 0) or 0), 0.0) for p in grid.connection_points)
    return max(float(grid.grid_capacity_limit_kw), 0.0)


def apply_capacity_limit(dc_capacity_kwp: float, grid: GridConnection | dict) -> dict:
    grid = normalize_grid_connection(grid)
    roof_capacity = max(float(dc_capacity_kwp), 0.0)
    limit = total_grid_capacity_limit_kw(grid)
    final_capacity = min(roof_capacity, limit) if limit > 0 else roof_capacity
    return {
        "roof_installable_capacity_kwp": roof_capacity,
        "grid_capacity_limit_kw": limit,
        "grid_limited_capacity_kwp": final_capacity,
        "capacity_limited_by_grid": final_capacity < roof_capacity,
        "capacity_limit_note": (
            f"受并网容量限制，装机容量由 {roof_capacity:.2f} kWp 校核为 {final_capacity:.2f} kWp。"
            if final_capacity < roof_capacity
            else "并网容量限制未约束当前屋顶可安装容量。"
        ),
    }


def grid_cost_items_yuan(capacity_kwp: float, grid: GridConnection | dict) -> dict:
    grid = normalize_grid_connection(grid)
    capacity_wp = max(float(capacity_kwp), 0.0) * 1000
    distance = max(float(grid.grid_connection_distance_m), 0.0)
    if grid.voltage_level == "低压 380V":
        grid_unit = 0.12
    elif grid.voltage_level == "10kV 高压":
        grid_unit = 0.32
    elif grid.voltage_level == "35kV 高压":
        grid_unit = 0.62
    else:
        grid_unit = 0.20

    items = {
        "并网柜费用": capacity_wp * grid_unit * 0.18,
        "计量柜费用": capacity_wp * grid_unit * 0.10,
        "电缆接入费用": distance * (180 if grid.voltage_level == "低压 380V" else 420),
        "并网检测验收费用": max(8000.0, capacity_wp * 0.015),
        "电网接入手续费用": max(5000.0, capacity_wp * 0.008),
    }
    if "10kV" in grid.voltage_level or "35kV" in grid.voltage_level:
        items.update(
            {
                "高压柜费用": capacity_wp * (0.08 if "10kV" in grid.voltage_level else 0.16),
                "继电保护费用": capacity_wp * 0.035,
                "通讯装置费用": capacity_wp * 0.018,
            }
        )
    if grid.need_transformer:
        items["箱变费用"] = max(120000.0, capacity_wp * 0.12)
    if grid.need_distribution_room_retrofit:
        items["配电房改造费用"] = max(50000.0, capacity_wp * 0.04)
    if grid.need_protection_device:
        items["防孤岛装置费用"] = capacity_wp * 0.012
        items["电能质量治理费用"] = capacity_wp * 0.018
    if not grid.allow_export:
        items["防逆流装置费用"] = max(25000.0, capacity_wp * 0.035)
        items["EMS能量管理系统费用"] = max(30000.0, capacity_wp * 0.025)
    if grid.storage_enabled or grid.grid_mode == "储能配套削峰填谷":
        items["储能系统费用"] = max(float(grid.storage_capacity_kwh), 0.0) * max(float(grid.storage_cost_per_kwh), 0.0)
        items["EMS能量管理系统费用"] = items.get("EMS能量管理系统费用", 0.0) + max(50000.0, capacity_wp * 0.02)
        items["储能消防温控费用"] = max(float(grid.storage_capacity_kwh), 0.0) * 120.0
    if grid.grid_mode == "多并网点接入" and grid.connection_points:
        items["多并网点接入汇总费用"] = sum(max(float(p.get("connection_cost", 0) or 0), 0.0) for p in grid.connection_points)
    return {k: round(v, 2) for k, v in items.items() if v > 0}


def _ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def calculate_grid_energy(
    pv_generation_kwh: float,
    load_kwh: float,
    grid: GridConnection | dict,
    interval_hours: float | None = None,
) -> GridEnergyResult:
    grid = normalize_grid_connection(grid)
    pv = max(float(pv_generation_kwh), 0.0)
    load = max(float(load_kwh), 0.0)
    notes: list[str] = []

    if grid.grid_mode == "全额上网":
        self_use = 0.0
        export = pv
        curtailment = 0.0
        purchase = load
    else:
        self_use = min(load, pv)
        surplus = max(pv - load, 0.0)
        purchase = max(load - pv, 0.0)
        if grid.grid_mode == "自发自用，不允许反送":
            export = 0.0
            curtailment = surplus
        else:
            export = surplus if grid.allow_export else 0.0
            curtailment = 0.0 if grid.allow_export else surplus

    if grid.allow_export and grid.export_limit_kw > 0 and interval_hours:
        export_cap = grid.export_limit_kw * interval_hours
        if export > export_cap:
            curtailment += export - export_cap
            export = export_cap

    storage_arbitrage = 0.0
    if grid.grid_mode == "储能配套削峰填谷" and grid.storage_capacity_kwh > 0:
        daily_cycles = 250
        usable_storage = grid.storage_capacity_kwh * min(grid.storage_charge_efficiency, 1.0) * min(grid.storage_discharge_efficiency, 1.0)
        spread = max(grid.peak_tariff - grid.valley_tariff, 0.0)
        storage_arbitrage = usable_storage * daily_cycles * spread
        notes.append("储能收益按简化峰谷价差套利估算，正式测算需接入逐时电价和储能调度模型。")

    annual_revenue = self_use * grid.self_use_tariff + export * grid.export_tariff + storage_arbitrage
    result = GridEnergyResult(
        pv_generation_kwh=pv,
        self_use_kwh=self_use,
        export_kwh=export,
        curtailment_kwh=curtailment,
        purchase_kwh=purchase,
        self_use_ratio=_ratio(self_use / pv) if pv else 0.0,
        export_ratio=_ratio(export / pv) if pv else 0.0,
        curtailment_ratio=_ratio(curtailment / pv) if pv else 0.0,
        storage_arbitrage_yuan=storage_arbitrage,
        annual_revenue_yuan=annual_revenue,
        notes=notes,
    )
    return result


def adjust_consumption_for_grid(consumption: dict, grid: GridConnection | dict) -> dict:
    grid = normalize_grid_connection(grid)
    pv = max(float(consumption.get("pv_generation_kwh", 0) or 0), 0.0)
    annual_load = max(float(consumption.get("annual_consumption_kwh", 0) or 0), 0.0)
    base_self = max(float(consumption.get("self_use_kwh", 0) or 0), 0.0)
    base_export = max(float(consumption.get("feed_in_kwh", 0) or 0), 0.0)

    if grid.grid_mode == "全额上网":
        energy = calculate_grid_energy(pv, annual_load, grid)
    elif grid.grid_mode == "自发自用，不允许反送":
        energy = GridEnergyResult(
            pv_generation_kwh=pv,
            self_use_kwh=min(base_self, pv),
            export_kwh=0.0,
            curtailment_kwh=max(pv - min(base_self, pv), 0.0),
            purchase_kwh=max(annual_load - min(base_self, pv), 0.0),
            self_use_ratio=_ratio(min(base_self, pv) / pv) if pv else 0.0,
            export_ratio=0.0,
            curtailment_ratio=_ratio(max(pv - min(base_self, pv), 0.0) / pv) if pv else 0.0,
            storage_arbitrage_yuan=0.0,
            annual_revenue_yuan=min(base_self, pv) * grid.self_use_tariff,
            notes=[],
        )
    else:
        export = base_export if grid.allow_export else 0.0
        curtail = max(base_export - export, 0.0)
        storage_arbitrage = 0.0
        if grid.grid_mode == "储能配套削峰填谷" and grid.storage_capacity_kwh > 0:
            usable_storage = grid.storage_capacity_kwh * min(grid.storage_charge_efficiency, 1.0) * min(grid.storage_discharge_efficiency, 1.0)
            storage_arbitrage = usable_storage * 250 * max(grid.peak_tariff - grid.valley_tariff, 0.0)
        energy = GridEnergyResult(
            pv_generation_kwh=pv,
            self_use_kwh=min(base_self, pv),
            export_kwh=min(export, max(pv - min(base_self, pv), 0.0)),
            curtailment_kwh=curtail,
            purchase_kwh=max(annual_load - min(base_self, pv), 0.0),
            self_use_ratio=_ratio(min(base_self, pv) / pv) if pv else 0.0,
            export_ratio=_ratio(min(export, max(pv - min(base_self, pv), 0.0)) / pv) if pv else 0.0,
            curtailment_ratio=_ratio(curtail / pv) if pv else 0.0,
            storage_arbitrage_yuan=storage_arbitrage,
            annual_revenue_yuan=min(base_self, pv) * grid.self_use_tariff + min(export, max(pv - min(base_self, pv), 0.0)) * grid.export_tariff + storage_arbitrage,
            notes=[],
        )
    data = dict(consumption)
    data.update(
        {
            "grid_mode": grid.grid_mode,
            "allow_export": grid.allow_export,
            "self_use_kwh": energy.self_use_kwh,
            "feed_in_kwh": energy.export_kwh,
            "curtailment_kwh": energy.curtailment_kwh,
            "purchase_kwh": energy.purchase_kwh,
            "self_use_ratio": energy.self_use_ratio,
            "feed_in_ratio": energy.export_ratio,
            "curtailment_ratio": energy.curtailment_ratio,
            "grid_adjusted_annual_revenue_yuan": energy.annual_revenue_yuan,
            "storage_arbitrage_yuan": energy.storage_arbitrage_yuan,
        }
    )
    return data


def grid_risk_suggestions(grid: GridConnection | dict, energy: dict | GridEnergyResult, capacity_kwp: float) -> list[str]:
    grid = normalize_grid_connection(grid)
    data = energy.to_dict() if hasattr(energy, "to_dict") else dict(energy)
    risks: list[str] = []
    if grid.grid_mode == "全额上网":
        risks.append("全额上网项目需重点关注上网电价、消纳政策、接入批复和电网接入容量。")
    if grid.grid_mode == "自发自用，余电上网":
        risks.append("自发自用余电上网项目需关注企业负荷稳定性、节假日用电下降和余电电价变化。")
    if grid.grid_mode == "自发自用，不允许反送":
        risks.append("不允许反送项目需关注防逆流控制、弃光风险、容量是否偏大以及是否需要储能。")
    if grid.grid_mode == "储能配套削峰填谷":
        risks.append("储能配套项目需关注储能成本、循环寿命、安全消防、峰谷价差和容量配置合理性。")
    if "10kV" in grid.voltage_level or "35kV" in grid.voltage_level:
        risks.append("高压并网需关注高压接入手续、继电保护、计量、调度通讯、验收周期和接入成本。")
    if grid.grid_mode == "多并网点接入":
        risks.append("多并网点接入需关注容量分配、电缆路径、计量边界和运维管理复杂度。")
    if float(data.get("curtailment_ratio", 0) or 0) > 0.10:
        risks.append("弃光率超过10%，提示装机容量偏大或建议配置储能。")
    if float(data.get("feed_in_ratio", 0) or 0) > 0.30:
        risks.append("余电上网比例较高，项目收益对上网电价敏感。")
    if grid.grid_connection_distance_m > 300:
        risks.append("接入点距离较远，电缆和施工成本上升风险较高。")
    if total_grid_capacity_limit_kw(grid) < capacity_kwp:
        risks.append("并网容量限制低于屋顶可装容量，需按接入批复容量修正方案。")
    return risks


def recommend_capacity_scenarios(
    roof_capacity_kwp: float,
    equivalent_hours: float,
    annual_load_kwh: float,
    total_investment_per_kwp_yuan: float,
    grid: GridConnection | dict,
    discount_rate: float = 0.06,
    operating_years: int = 25,
    target_irr: float = 0.06,
) -> pd.DataFrame:
    grid = normalize_grid_connection(grid)
    rows: list[dict] = []
    max_capacity = min(max(float(roof_capacity_kwp), 0.0), total_grid_capacity_limit_kw(grid))
    for ratio in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        capacity = max_capacity * ratio
        pv = capacity * max(float(equivalent_hours), 0.0)
        load = max(float(annual_load_kwh), 0.0)
        energy = calculate_grid_energy(pv, load, grid)
        investment = capacity * max(float(total_investment_per_kwp_yuan), 0.0)
        annual_om = investment * 0.015
        annual_cf = energy.annual_revenue_yuan - annual_om
        cashflows = [-investment] + [annual_cf] * max(int(operating_years), 1)
        project_irr = irr(cashflows)
        project_npv = npv(discount_rate, cashflows)
        lcoe = (investment + annual_om * operating_years) / (pv * operating_years) if pv and operating_years else 0.0
        rows.append(
            {
                "方案容量比例": ratio,
                "装机容量(kWp)": capacity,
                "年发电量(kWh)": pv,
                "自用电量(kWh)": energy.self_use_kwh,
                "余电上网电量(kWh)": energy.export_kwh,
                "弃光电量(kWh)": energy.curtailment_kwh,
                "自发自用率": energy.self_use_ratio,
                "余电上网率": energy.export_ratio,
                "弃光率": energy.curtailment_ratio,
                "年收益(元)": energy.annual_revenue_yuan,
                "总投资(元)": investment,
                "IRR": project_irr,
                "NPV(元)": project_npv,
                "LCOE(元/kWh)": lcoe,
                "静态回收期(年)": simple_payback(cashflows),
                "动态回收期(年)": discounted_payback(cashflows, discount_rate),
            }
        )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    eligible = table[(table["NPV(元)"] > 0) & (table["IRR"].fillna(-1) >= target_irr)]
    if grid.grid_mode == "自发自用，不允许反送":
        eligible = eligible[eligible["弃光率"] <= 0.10]
    if eligible.empty:
        idx = table["NPV(元)"].idxmax()
    elif grid.grid_mode == "全额上网":
        idx = eligible["装机容量(kWp)"].idxmax()
    else:
        idx = eligible["NPV(元)"].idxmax()
    table["是否推荐"] = False
    table.loc[idx, "是否推荐"] = True
    return table


def grid_analysis_summary(grid: GridConnection | dict, capacity_check: dict, energy: dict | GridEnergyResult, grid_cost_yuan: float, risks: list[str]) -> dict:
    grid = normalize_grid_connection(grid)
    data = energy.to_dict() if hasattr(energy, "to_dict") else dict(energy)
    return {
        "并网方式选择": grid.grid_mode,
        "接入电压等级": grid.voltage_level,
        "接入点类型": grid.connection_point_type,
        "是否允许余电上网": "是" if grid.allow_export else "否",
        "最大允许反送功率(kW)": grid.export_limit_kw,
        "并网容量限制(kW)": capacity_check.get("grid_capacity_limit_kw", total_grid_capacity_limit_kw(grid)),
        "并网接入费用(元)": grid_cost_yuan,
        "自用电量(kWh)": data.get("self_use_kwh", 0.0),
        "余电上网电量(kWh)": data.get("feed_in_kwh", data.get("export_kwh", 0.0)),
        "弃光电量(kWh)": data.get("curtailment_kwh", 0.0),
        "自发自用率": data.get("self_use_ratio", 0.0),
        "余电上网率": data.get("feed_in_ratio", data.get("export_ratio", 0.0)),
        "弃光率": data.get("curtailment_ratio", 0.0),
        "并网方式对投资收益的影响": "收益、电量消纳和造价已按并网模式修正；储能和多并网点为简化估算口径。",
        "并网方式风险提示": "；".join(risks),
        "推荐并网方案结论": capacity_check.get("capacity_limit_note", ""),
    }
