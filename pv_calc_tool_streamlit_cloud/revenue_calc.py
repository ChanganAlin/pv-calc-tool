from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from .finance_calc import discounted_payback, irr, npv, simple_payback


@dataclass
class RevenueResult:
    first_year_generation_kwh: float
    average_generation_kwh: float
    lifetime_generation_kwh: float
    average_revenue_yuan: float
    average_operating_cost_yuan: float
    average_net_cashflow_yuan: float
    total_investment_yuan: float
    unit_investment_yuan_per_wp: float
    simple_payback_years: float | None
    discounted_payback_years: float | None
    project_irr: float | None
    project_npv_yuan: float
    lcoe_yuan_per_kwh: float
    cashflow_table: pd.DataFrame
    finance_model_scope: str = "simplified_unlevered_preliminary"
    finance_model_note: str = ""
    tax_simplification_note: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cashflow_table"] = self.cashflow_table.to_dict(orient="records")
        return data


def calculate_revenue(
    capacity_kwp: float,
    total_investment_yuan: float,
    equivalent_hours: float,
    first_year_degradation_ratio: float,
    annual_degradation_ratio: float,
    operating_years: int,
    self_use_ratio: float,
    feed_in_ratio: float,
    self_use_tariff: float,
    feed_in_tariff: float,
    contract_discount_ratio: float,
    om_cost_yuan_per_wp_year: float,
    insurance_ratio: float,
    cleaning_cost_yuan_per_wp_year: float,
    roof_rent_yuan_per_year: float,
    other_cost_yuan_per_year: float,
    income_tax_ratio: float,
    discount_rate: float,
    loan_ratio: float = 0.0,
    loan_interest_rate: float = 0.0,
    loan_years: int = 0,
    depreciation_years: int = 0,
    residual_rate: float = 0.0,
    vat_rate: float = 0.0,
    surcharge_rate: float = 0.0,
    inverter_replacement_year: int = 0,
    inverter_replacement_cost: float = 0.0,
    roof_rent_escalation_rate: float = 0.0,
    grid_connection: dict | object | None = None,
    curtailment_ratio: float = 0.0,
    storage_arbitrage_yuan: float = 0.0,
) -> RevenueResult:
    """simplified_project_cashflow：简化全投资现金流，不含融资、折旧抵税、增值税、残值和逆变器更换。"""
    capacity_kwp = max(float(capacity_kwp), 0.0)
    capacity_wp = capacity_kwp * 1000
    operating_years = max(int(operating_years), 1)
    self_use_ratio = min(max(float(self_use_ratio), 0.0), 1.0)
    feed_in_ratio = min(max(float(feed_in_ratio), 0.0), 1.0)
    if self_use_ratio + feed_in_ratio > 1:
        feed_in_ratio = 1 - self_use_ratio
    grid = None
    if grid_connection is not None:
        from .grid_connection_config import normalize_grid_connection

        grid = normalize_grid_connection(grid_connection)
        self_use_tariff = grid.self_use_tariff
        feed_in_tariff = grid.export_tariff
        if grid.grid_mode == "全额上网":
            self_use_ratio = 0.0
            feed_in_ratio = 1.0
            curtailment_ratio = 0.0
        elif grid.grid_mode == "自发自用，不允许反送" or not grid.allow_export:
            feed_in_ratio = 0.0
            curtailment_ratio = max(0.0, 1.0 - self_use_ratio)
        if grid.storage_enabled and grid.storage_capacity_kwh > 0:
            other_cost_yuan_per_year += grid.storage_capacity_kwh * 15.0

    rows = []
    cashflows = [-max(float(total_investment_yuan), 0.0)]
    discounted_generation_sum = 0.0
    discounted_cost_sum = max(float(total_investment_yuan), 0.0)

    # 首年发电量 = 装机容量(kWp) * 等效利用小时数 * (1 - 首年衰减率)
    first_year_generation = capacity_kwp * max(float(equivalent_hours), 0.0) * (1 - max(first_year_degradation_ratio, 0.0))

    for year in range(1, operating_years + 1):
        # 第n年发电量 = 首年发电量 * (1 - 后续年衰减率)^(n-1)
        generation = first_year_generation * ((1 - max(annual_degradation_ratio, 0.0)) ** (year - 1))
        self_use_kwh = generation * self_use_ratio
        feed_in_kwh = generation * feed_in_ratio
        curtailment_kwh = generation * min(max(float(curtailment_ratio), 0.0), 1.0)
        # 自用收益 = 自用电量 * 自用电价 * 合同折扣比例
        self_use_income = self_use_kwh * max(self_use_tariff, 0.0) * min(max(contract_discount_ratio, 0.0), 1.0)
        # 余电上网收益 = 上网电量 * 上网电价
        feed_in_income = feed_in_kwh * max(feed_in_tariff, 0.0)
        storage_income = max(float(storage_arbitrage_yuan), 0.0) if grid is not None and grid.grid_mode == "储能配套削峰填谷" else 0.0
        total_income = self_use_income + feed_in_income + storage_income
        # 年运营成本 = 运维费 + 保险费 + 屋顶租金 + 清洗费 + 其他费用
        om_cost = capacity_wp * max(om_cost_yuan_per_wp_year, 0.0)
        insurance = max(total_investment_yuan, 0.0) * max(insurance_ratio, 0.0)
        cleaning = capacity_wp * max(cleaning_cost_yuan_per_wp_year, 0.0)
        operating_cost = om_cost + insurance + cleaning + max(roof_rent_yuan_per_year, 0.0) + max(other_cost_yuan_per_year, 0.0)
        taxable_income = max(total_income - operating_cost, 0.0)
        # 所得税为简化估算，不含折旧抵税。
        tax = taxable_income * min(max(income_tax_ratio, 0.0), 1.0)
        # 年净现金流 = 年总收入 - 年运营成本 - 税费
        net_cashflow = total_income - operating_cost - tax
        cashflows.append(net_cashflow)
        useful_generation = max(generation - curtailment_kwh, 0.0)
        discounted_generation_sum += useful_generation / ((1 + discount_rate) ** year)
        discounted_cost_sum += operating_cost / ((1 + discount_rate) ** year)
        rows.append(
            {
                "年份": year,
                "发电量(kWh)": generation,
                "自用电量(kWh)": self_use_kwh,
                "上网电量(kWh)": feed_in_kwh,
                "弃光电量(kWh)": curtailment_kwh,
                "自用收益(元)": self_use_income,
                "上网收益(元)": feed_in_income,
                "储能套利收益(元)": storage_income,
                "并网模式": grid.grid_mode if grid is not None else "",
                "总收入(元)": total_income,
                "运营成本(元)": operating_cost,
                "税费(元)": tax,
                "净现金流(元)": net_cashflow,
                "累计现金流(元)": sum(cashflows),
                "折现净现金流(元)": net_cashflow / ((1 + discount_rate) ** year),
            }
        )

    cashflow_table = pd.DataFrame(rows)
    project_npv = npv(discount_rate, cashflows)
    project_irr = irr(cashflows)
    lcoe = discounted_cost_sum / discounted_generation_sum if discounted_generation_sum else 0.0
    unit_investment = total_investment_yuan / capacity_wp if capacity_wp else 0.0

    return RevenueResult(
        first_year_generation_kwh=first_year_generation,
        average_generation_kwh=float(cashflow_table["发电量(kWh)"].mean()) if not cashflow_table.empty else 0.0,
        lifetime_generation_kwh=float(cashflow_table["发电量(kWh)"].sum()) if not cashflow_table.empty else 0.0,
        average_revenue_yuan=float(cashflow_table["总收入(元)"].mean()) if not cashflow_table.empty else 0.0,
        average_operating_cost_yuan=float(cashflow_table["运营成本(元)"].mean()) if not cashflow_table.empty else 0.0,
        average_net_cashflow_yuan=float(cashflow_table["净现金流(元)"].mean()) if not cashflow_table.empty else 0.0,
        total_investment_yuan=total_investment_yuan,
        unit_investment_yuan_per_wp=unit_investment,
        simple_payback_years=simple_payback(cashflows),
        discounted_payback_years=discounted_payback(cashflows, discount_rate),
        project_irr=project_irr,
        project_npv_yuan=project_npv,
        lcoe_yuan_per_kwh=lcoe,
        cashflow_table=cashflow_table,
        finance_model_scope="simplified_unlevered_preliminary",
        finance_model_note=(
            "当前版本为简化全投资现金流测算口径，主要用于项目初筛。当前模型尚未完整考虑融资贷款、折旧抵税、"
            "增值税及附加、残值、逆变器更换、屋顶租金递增和合同能源管理分成。正式投资决策请采用完整财务模型复核。"
        ),
        tax_simplification_note=(
            "当前所得税为简化估算，未考虑折旧抵税，税后现金流仅供初步参考。"
            if income_tax_ratio > 0 and depreciation_years <= 0
            else ""
        ),
    )
