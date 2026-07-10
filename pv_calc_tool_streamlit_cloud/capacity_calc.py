from __future__ import annotations

from dataclasses import dataclass, asdict
from math import floor


@dataclass
class CapacityResult:
    input_area_m2: float
    usable_area_m2: float
    area_basis: str
    roof_utilization_ratio: float
    deduction_ratio: float
    layout_loss_ratio: float
    applied_roof_utilization_ratio: float
    applied_deduction_ratio: float
    area_reduction_factor: float
    effective_install_area_m2: float
    module_count: int
    dc_capacity_kwp: float
    ac_capacity_kw: float
    dc_ac_ratio: float
    area_utilization_ratio: float
    density_kwp_per_m2: float
    recommended_tilt_deg: float
    tilt_layout_adjustment_ratio: float
    adjusted_layout_loss_ratio: float
    density_risk_note: str
    grid_capacity_limit_kw: float = 0.0
    grid_limited_capacity_kwp: float = 0.0
    capacity_limited_by_grid: bool = False
    capacity_limit_note: str = ""
    roof_installable_capacity_kwp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def calculate_capacity(
    usable_area_m2: float,
    module_area_m2: float,
    module_power_kwp: float,
    roof_utilization_ratio: float,
    deduction_ratio: float,
    layout_loss_ratio: float,
    dc_ac_ratio: float,
    recommended_tilt_deg: float = 0.0,
    tilt_layout_adjustment_ratio: float = 0.0,
    area_basis: str = "roof_total_area",
    apply_roof_utilization: bool | None = None,
    apply_deduction: bool | None = None,
    roof_type: str = "",
    grid_connection: dict | object | None = None,
) -> CapacityResult:
    """容量测算：按面积口径决定是否应用屋顶利用率和综合扣减。"""
    usable_area_m2 = max(float(usable_area_m2), 0.0)
    module_area_m2 = max(float(module_area_m2), 0.0001)
    module_power_kwp = max(float(module_power_kwp), 0.0)
    dc_ac_ratio = max(float(dc_ac_ratio), 0.0001)

    roof_utilization_ratio = _ratio(roof_utilization_ratio)
    deduction_ratio = _ratio(deduction_ratio)
    layout_loss_ratio = _ratio(layout_loss_ratio)
    tilt_layout_adjustment_ratio = _ratio(tilt_layout_adjustment_ratio)
    adjusted_layout_loss_ratio = _ratio(layout_loss_ratio + tilt_layout_adjustment_ratio)
    basis_map = {
        "屋顶总面积": "roof_total_area",
        "可利用面积": "usable_area",
        "已确认可铺设面积": "installable_area",
        "confirmed_installable_area": "installable_area",
    }
    normalized_basis = basis_map.get(str(area_basis), str(area_basis))
    if normalized_basis not in {"roof_total_area", "usable_area", "installable_area"}:
        normalized_basis = "roof_total_area"

    if apply_roof_utilization is None:
        apply_roof_utilization = normalized_basis == "roof_total_area"
    if apply_deduction is None:
        apply_deduction = normalized_basis in {"roof_total_area", "usable_area"}
    applied_roof_utilization_ratio = roof_utilization_ratio if apply_roof_utilization else 1.0
    applied_deduction_ratio = deduction_ratio if apply_deduction else 0.0

    area_reduction_factor = applied_roof_utilization_ratio * (1 - applied_deduction_ratio) * (1 - adjusted_layout_loss_ratio)
    effective_area = usable_area_m2 * area_reduction_factor
    # 可安装组件数 = floor(有效安装面积 / 单块组件面积)
    module_count = max(floor(effective_area / module_area_m2), 0)
    # 直流侧容量(kWp) = 组件数 * 单块组件功率(kWp)
    dc_capacity = module_count * module_power_kwp
    # 交流侧容量(kW) = 直流侧容量 / 容配比
    ac_capacity = dc_capacity / dc_ac_ratio
    roof_installable_capacity_kwp = dc_capacity
    grid_capacity_limit_kw = 0.0
    grid_limited_capacity_kwp = dc_capacity
    capacity_limited_by_grid = False
    capacity_limit_note = "未设置并网容量限制。"
    if grid_connection is not None:
        from .grid_connection_config import apply_capacity_limit

        grid_check = apply_capacity_limit(dc_capacity, grid_connection)
        grid_capacity_limit_kw = grid_check["grid_capacity_limit_kw"]
        grid_limited_capacity_kwp = grid_check["grid_limited_capacity_kwp"]
        capacity_limited_by_grid = bool(grid_check["capacity_limited_by_grid"])
        capacity_limit_note = grid_check["capacity_limit_note"]
        if capacity_limited_by_grid:
            dc_capacity = grid_limited_capacity_kwp
            module_count = max(floor(dc_capacity / module_power_kwp), 0) if module_power_kwp else 0
            ac_capacity = dc_capacity / dc_ac_ratio

    density = dc_capacity / usable_area_m2 if usable_area_m2 else 0.0
    area_utilization = effective_area / usable_area_m2 if usable_area_m2 else 0.0
    density_risk_note = "装机密度处于常规初算范围。"
    if "混凝土" in roof_type or "平屋面" in roof_type:
        if density < 0.12:
            density_risk_note = "装机密度偏低，可能存在重复扣减或排布效率偏低。"
        elif density > 0.24:
            density_risk_note = "装机密度偏高，请复核面积、组件面积和排布方式。"
    elif "彩钢瓦" in roof_type:
        if density < 0.16:
            density_risk_note = "装机密度偏低，请复核可铺设面积。"
        elif density > 0.26:
            density_risk_note = "装机密度偏高，请复核面积和组件参数。"

    return CapacityResult(
        input_area_m2=usable_area_m2,
        usable_area_m2=usable_area_m2,
        area_basis=normalized_basis,
        roof_utilization_ratio=roof_utilization_ratio,
        deduction_ratio=deduction_ratio,
        layout_loss_ratio=layout_loss_ratio,
        applied_roof_utilization_ratio=applied_roof_utilization_ratio,
        applied_deduction_ratio=applied_deduction_ratio,
        area_reduction_factor=area_reduction_factor,
        effective_install_area_m2=effective_area,
        module_count=module_count,
        dc_capacity_kwp=dc_capacity,
        ac_capacity_kw=ac_capacity,
        dc_ac_ratio=dc_ac_ratio,
        area_utilization_ratio=area_utilization,
        density_kwp_per_m2=density,
        recommended_tilt_deg=max(float(recommended_tilt_deg), 0.0),
        tilt_layout_adjustment_ratio=tilt_layout_adjustment_ratio,
        adjusted_layout_loss_ratio=adjusted_layout_loss_ratio,
        density_risk_note=density_risk_note,
        grid_capacity_limit_kw=grid_capacity_limit_kw,
        grid_limited_capacity_kwp=grid_limited_capacity_kwp,
        capacity_limited_by_grid=capacity_limited_by_grid,
        capacity_limit_note=capacity_limit_note,
        roof_installable_capacity_kwp=roof_installable_capacity_kwp,
    )
