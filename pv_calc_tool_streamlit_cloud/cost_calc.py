from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class CostResult:
    capacity_kwp: float
    adjusted_unit_cost_yuan_per_wp: float
    base_unit_cost_yuan_per_wp: float
    base_investment_yuan: float
    contingency_yuan: float
    other_one_time_cost_yuan: float
    total_investment_yuan: float
    investment_per_kw_yuan: float
    cost_items_yuan: dict
    risk_note: str

    def to_dict(self) -> dict:
        return asdict(self)


def capacity_scale_factor(capacity_kwp: float) -> float:
    """动态造价调整：小于500kWp上浮8%，大于2MWp下降5%。"""
    if capacity_kwp < 500:
        return 1.08
    if capacity_kwp > 2000:
        return 0.95
    return 1.0


def calculate_cost(
    capacity_kwp: float,
    unit_costs: dict,
    contingency_ratio: float,
    other_one_time_cost_yuan: float = 0.0,
    extra_cost_items_yuan: dict | None = None,
    grid_connection: dict | object | None = None,
) -> CostResult:
    """造价测算：分项单瓦造价求和后按装机容量换算总投资。"""
    capacity_kwp = max(float(capacity_kwp), 0.0)
    capacity_wp = capacity_kwp * 1000
    contingency_ratio = min(max(float(contingency_ratio), 0.0), 1.0)
    other_one_time_cost_yuan = max(float(other_one_time_cost_yuan), 0.0)

    cost_items = {k: max(float(v), 0.0) for k, v in unit_costs.items()}
    # 基础单位造价 = 各分项单瓦造价之和
    base_unit_cost = sum(cost_items.values())
    factor = capacity_scale_factor(capacity_kwp)
    adjusted_unit_cost = base_unit_cost * factor
    # 基础投资 = 装机容量(Wp) * 调整后单位造价(元/Wp)
    base_investment = capacity_wp * adjusted_unit_cost
    # 不可预见费 = 基础投资 * 不可预见费率
    contingency = base_investment * contingency_ratio
    extra_cost_items = {str(k): max(float(v), 0.0) for k, v in (extra_cost_items_yuan or {}).items()}
    if grid_connection is not None:
        from .grid_connection_config import grid_cost_items_yuan

        extra_cost_items.update(grid_cost_items_yuan(capacity_kwp, grid_connection))
    extra_cost_total = sum(extra_cost_items.values())
    # 总投资 = 基础投资 + 不可预见费 + 其他一次性费用 + 并网/储能增量费用
    total = base_investment + contingency + other_one_time_cost_yuan + extra_cost_total
    investment_per_kw = total / capacity_kwp if capacity_kwp else 0.0
    risk = "单位投资偏高，建议复核组件、支架、并网接入、屋面加固等费用。" if adjusted_unit_cost > 3.5 else "造价处于默认模型常规区间。"

    return CostResult(
        capacity_kwp=capacity_kwp,
        adjusted_unit_cost_yuan_per_wp=adjusted_unit_cost,
        base_unit_cost_yuan_per_wp=base_unit_cost,
        base_investment_yuan=base_investment,
        contingency_yuan=contingency,
        other_one_time_cost_yuan=other_one_time_cost_yuan,
        total_investment_yuan=total,
        investment_per_kw_yuan=investment_per_kw,
        cost_items_yuan={**{k: v * capacity_wp * factor for k, v in cost_items.items()}, **extra_cost_items},
        risk_note=risk,
    )
