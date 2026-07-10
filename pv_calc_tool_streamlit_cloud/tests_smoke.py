from config.default_params import CAPACITY_DEFAULTS, CONSUMPTION_DEFAULTS, COST_DEFAULTS, REVENUE_DEFAULTS, SENSITIVITY_STEPS
from modules.capacity_calc import calculate_capacity
from modules.consumption_calc import calculate_consumption
from modules.cost_calc import calculate_cost
from modules.revenue_calc import calculate_revenue
from modules.sensitivity_calc import sensitivity_analysis


def main():
    capacity = calculate_capacity(
        usable_area_m2=5000,
        module_area_m2=CAPACITY_DEFAULTS["module_area_m2"],
        module_power_kwp=CAPACITY_DEFAULTS["module_power_kwp"],
        roof_utilization_ratio=CAPACITY_DEFAULTS["roof_utilization_ratio"],
        deduction_ratio=CAPACITY_DEFAULTS["deduction_ratio"],
        layout_loss_ratio=CAPACITY_DEFAULTS["layout_loss_ratio"],
        dc_ac_ratio=CAPACITY_DEFAULTS["dc_ac_ratio"],
    )
    assert capacity.dc_capacity_kwp > 0
    pv_generation = capacity.dc_capacity_kwp * REVENUE_DEFAULTS["equivalent_hours"] * (1 - REVENUE_DEFAULTS["first_year_degradation_ratio"])
    consumption = calculate_consumption(4_000_000, 0.65, pv_generation, CONSUMPTION_DEFAULTS["production_caps"]["连续生产"])
    cost_keys = [k for k in COST_DEFAULTS if k != "contingency_ratio"]
    cost = calculate_cost(capacity.dc_capacity_kwp, {k: COST_DEFAULTS[k] for k in cost_keys}, COST_DEFAULTS["contingency_ratio"])
    revenue_inputs = {
        "capacity_kwp": capacity.dc_capacity_kwp,
        "total_investment_yuan": cost.total_investment_yuan,
        "equivalent_hours": REVENUE_DEFAULTS["equivalent_hours"],
        "first_year_degradation_ratio": REVENUE_DEFAULTS["first_year_degradation_ratio"],
        "annual_degradation_ratio": REVENUE_DEFAULTS["annual_degradation_ratio"],
        "operating_years": REVENUE_DEFAULTS["operating_years"],
        "self_use_ratio": consumption.self_use_ratio,
        "feed_in_ratio": consumption.feed_in_ratio,
        "self_use_tariff": REVENUE_DEFAULTS["self_use_tariff"],
        "feed_in_tariff": REVENUE_DEFAULTS["feed_in_tariff"],
        "contract_discount_ratio": REVENUE_DEFAULTS["contract_discount_ratio"],
        "om_cost_yuan_per_wp_year": REVENUE_DEFAULTS["om_cost_yuan_per_wp_year"],
        "insurance_ratio": REVENUE_DEFAULTS["insurance_ratio"],
        "cleaning_cost_yuan_per_wp_year": REVENUE_DEFAULTS["cleaning_cost_yuan_per_wp_year"],
        "roof_rent_yuan_per_year": REVENUE_DEFAULTS["roof_rent_yuan_per_year"],
        "other_cost_yuan_per_year": REVENUE_DEFAULTS["other_cost_yuan_per_year"],
        "income_tax_ratio": REVENUE_DEFAULTS["income_tax_ratio"],
        "discount_rate": REVENUE_DEFAULTS["discount_rate"],
    }
    revenue = calculate_revenue(**revenue_inputs)
    sensitivity = sensitivity_analysis(revenue_inputs, SENSITIVITY_STEPS)
    assert len(revenue.cashflow_table) == REVENUE_DEFAULTS["operating_years"]
    assert len(sensitivity) == 25
    print("smoke ok", round(capacity.dc_capacity_kwp, 2), round(cost.total_investment_yuan, 2), round(revenue.project_npv_yuan, 2))


if __name__ == "__main__":
    main()

