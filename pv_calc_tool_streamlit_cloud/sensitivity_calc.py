from __future__ import annotations

import pandas as pd

from .revenue_calc import calculate_revenue


def build_risk_suggestions(
    self_use_ratio: float,
    feed_in_ratio: float,
    simple_payback_years: float | None,
    project_irr: float | None,
    unit_investment_yuan_per_wp: float,
    density_kwp_per_m2: float,
    seasonal_variation: bool = False,
) -> list[str]:
    """动态调整：依据消纳、回收期、IRR、单位投资等指标输出优化建议。"""
    suggestions = []
    if self_use_ratio < 0.70:
        suggestions.append("当前装机容量可能偏大，建议降低装机容量或配置储能，提高消纳比例。")
    if simple_payback_years is not None and simple_payback_years > 8:
        suggestions.append("项目回收期偏长，请检查造价、电价、消纳比例和发电小时数。")
    if project_irr is not None and project_irr < 0.06:
        suggestions.append("项目收益率偏低，建议优化投资成本、提高自用比例或调整商务模式。")
    if unit_investment_yuan_per_wp > 3.5:
        suggestions.append("单位投资偏高，建议复核组件、支架、并网接入、屋面加固等费用。")
    if density_kwp_per_m2 < 0.16:
        suggestions.append("屋面利用效率偏低，建议优化组件排布。")
    if feed_in_ratio > 0.30:
        suggestions.append("余电比例偏高，项目收益对上网电价较敏感。")
    if seasonal_variation:
        suggestions.append("月用电量波动明显，存在季节性消纳风险，建议补充月度或逐时负荷数据。")
    return suggestions or ["核心指标未触发高风险阈值，建议继续结合现场踏勘和电费单复核。"]


def sensitivity_analysis(base_inputs: dict, steps: list[float]) -> pd.DataFrame:
    """敏感性分析：分别扰动总投资、小时数、自用比例、自用电价、上网电价并重算核心财务指标。"""
    rows = []
    variables = {
        "总投资": "total_investment_yuan",
        "发电小时数": "equivalent_hours",
        "自发自用比例": "self_use_ratio",
        "自用电价": "self_use_tariff",
        "上网电价": "feed_in_tariff",
    }
    for label, key in variables.items():
        for step in steps:
            params = dict(base_inputs)
            params[key] = max(params[key] * (1 + step), 0.0)
            if key == "self_use_ratio":
                params["self_use_ratio"] = min(params["self_use_ratio"], 1.0)
                params["feed_in_ratio"] = max(1 - params["self_use_ratio"], 0.0)
            result = calculate_revenue(**params)
            rows.append(
                {
                    "变量": label,
                    "变化幅度": step,
                    "静态回收期(年)": result.simple_payback_years,
                    "IRR": result.project_irr,
                    "NPV(元)": result.project_npv_yuan,
                    "LCOE(元/kWh)": result.lcoe_yuan_per_kwh,
                }
            )
    return pd.DataFrame(rows)

