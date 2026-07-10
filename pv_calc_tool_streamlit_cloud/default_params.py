"""Default assumptions for the PV project calculator MVP.

Units:
- Capacity: kWp unless otherwise noted.
- Area: square meters.
- Money: CNY yuan.
- Unit cost: CNY/Wp.
- Ratios: decimals in code, percentages in UI.
"""

CAPACITY_DEFAULTS = {
    "module_area_m2": 2.77,
    "module_power_kwp": 0.62,
    "roof_utilization_ratio": 0.80,
    "deduction_ratio": 0.15,
    "layout_loss_ratio": 0.05,
    "dc_ac_ratio": 1.15,
}

CONSUMPTION_DEFAULTS = {
    "daytime_usage_ratio": 0.65,
    "production_caps": {
        "连续生产": 0.95,
        "三班制": 0.95,
        "双班制": 0.85,
        "单班制": 0.75,
        "周末停产": 0.65,
        "季节性停产": 0.55,
    },
}

COST_DEFAULTS = {
    "module": 0.75,
    "inverter": 0.12,
    "mounting": 0.18,
    "cable_tray": 0.15,
    "distribution": 0.18,
    "grid_connection": 0.10,
    "civil_reinforcement": 0.12,
    "installation": 0.25,
    "design_supervision_testing": 0.08,
    "project_management": 0.08,
    "contingency_ratio": 0.03,
}

REVENUE_DEFAULTS = {
    "operating_years": 25,
    "equivalent_hours": 1000.0,
    "first_year_degradation_ratio": 0.02,
    "annual_degradation_ratio": 0.0045,
    "self_use_tariff": 0.75,
    "feed_in_tariff": 0.38,
    "contract_discount_ratio": 0.90,
    "om_cost_yuan_per_wp_year": 0.04,
    "insurance_ratio": 0.002,
    "cleaning_cost_yuan_per_wp_year": 0.01,
    "roof_rent_yuan_per_year": 0.0,
    "other_cost_yuan_per_year": 0.0,
    "income_tax_ratio": 0.0,
    "discount_rate": 0.06,
    "residual_ratio": 0.05,
}

SENSITIVITY_STEPS = [-0.10, -0.05, 0.0, 0.05, 0.10]

WEEKEND_LOAD_FACTOR_NORMAL = 1.0
WEEKEND_LOAD_FACTOR_LOW = 0.5
WEEKEND_LOAD_FACTOR_STOP = 0.1
LEGAL_HOLIDAY_LOAD_FACTOR = 0.1
SPRING_FESTIVAL_LOAD_FACTOR = 0.05
MAINTENANCE_LOAD_FACTOR = 0.1
CUSTOM_STOP_LOAD_FACTOR = 0.1
