from modules.cost_calc import calculate_cost
from modules.capacity_calc import calculate_capacity
from modules.revenue_calc import calculate_revenue
from modules.grid_connection_config import (
    GridConnection,
    adjust_consumption_for_grid,
    apply_capacity_limit,
    calculate_grid_energy,
    grid_cost_items_yuan,
    normalize_grid_connection,
    recommend_capacity_scenarios,
    validate_grid_connection,
)


def test_full_export_mode():
    grid = GridConnection(grid_mode="全额上网", export_tariff=0.39, self_use_tariff=0.8)
    result = calculate_grid_energy(10000, 8000, grid)
    assert result.self_use_kwh == 0
    assert result.export_kwh == 10000
    assert result.curtailment_kwh == 0
    assert result.annual_revenue_yuan == 3900


def test_self_use_with_export_mode():
    grid = GridConnection(grid_mode="自发自用，余电上网", export_tariff=0.35, self_use_tariff=0.8)
    result = calculate_grid_energy(10000, 7000, grid)
    assert result.self_use_kwh == 7000
    assert result.export_kwh == 3000
    assert result.curtailment_kwh == 0
    assert result.annual_revenue_yuan == 7000 * 0.8 + 3000 * 0.35


def test_no_reverse_power_mode():
    grid = normalize_grid_connection(GridConnection(grid_mode="自发自用，不允许反送", allow_export=True, export_limit_kw=50))
    result = calculate_grid_energy(10000, 7000, grid)
    assert grid.allow_export is False
    assert grid.export_limit_kw == 0
    assert result.export_kwh == 0
    assert result.curtailment_kwh == 3000


def test_voltage_cost_rules():
    low = grid_cost_items_yuan(1000, GridConnection(voltage_level="低压 380V"))
    high = grid_cost_items_yuan(1000, GridConnection(voltage_level="10kV 高压"))
    assert sum(high.values()) > sum(low.values())
    assert "高压柜费用" in high
    assert validate_grid_connection(GridConnection(voltage_level="10kV 高压"))


def test_export_limit_interval():
    grid = GridConnection(grid_mode="自发自用，余电上网", export_limit_kw=100, export_tariff=0.35)
    result = calculate_grid_energy(500, 100, grid, interval_hours=0.25)
    assert result.export_kwh == 25
    assert result.curtailment_kwh == 375


def test_multi_connection_capacity_limit():
    grid = GridConnection(
        grid_mode="多并网点接入",
        connection_points=[
            {"connection_point_name": "A", "capacity_limit_kw": 300},
            {"connection_point_name": "B", "capacity_limit_kw": 500},
        ],
    )
    check = apply_capacity_limit(1000, grid)
    assert check["grid_limited_capacity_kwp"] == 800
    assert check["capacity_limited_by_grid"] is True


def test_storage_cost_and_scenario():
    grid = GridConnection(grid_mode="储能配套削峰填谷", storage_capacity_kwh=500, storage_cost_per_kwh=900)
    costs = grid_cost_items_yuan(1000, grid)
    assert costs["储能系统费用"] == 450000
    scenarios = recommend_capacity_scenarios(1000, 1000, 800000, 3000, grid)
    assert len(scenarios) == 6
    assert scenarios["是否推荐"].sum() == 1


def test_adjust_consumption_for_grid_no_export():
    consumption = {
        "pv_generation_kwh": 10000,
        "annual_consumption_kwh": 12000,
        "self_use_kwh": 7000,
        "feed_in_kwh": 3000,
        "self_use_ratio": 0.7,
        "feed_in_ratio": 0.3,
    }
    adjusted = adjust_consumption_for_grid(consumption, GridConnection(grid_mode="自发自用，不允许反送"))
    assert adjusted["feed_in_kwh"] == 0
    assert adjusted["curtailment_kwh"] == 3000


def test_cost_accepts_grid_extra_items():
    cost = calculate_cost(
        100,
        {"module": 1.0, "inverter": 0.1},
        0.0,
        extra_cost_items_yuan={"并网柜费用": 10000},
    )
    assert cost.total_investment_yuan > 100000
    assert cost.cost_items_yuan["并网柜费用"] == 10000


def test_capacity_reads_grid_connection_limit():
    grid = GridConnection(grid_capacity_limit_kw=300)
    capacity = calculate_capacity(
        usable_area_m2=5000,
        module_area_m2=2.5,
        module_power_kwp=0.6,
        roof_utilization_ratio=1.0,
        deduction_ratio=0.0,
        layout_loss_ratio=0.0,
        dc_ac_ratio=1.2,
        area_basis="installable_area",
        grid_connection=grid,
    )
    assert capacity.roof_installable_capacity_kwp > 300
    assert capacity.dc_capacity_kwp == 300
    assert capacity.ac_capacity_kw == 250
    assert capacity.capacity_limited_by_grid is True


def test_cost_reads_grid_connection():
    base = calculate_cost(500, {"module": 1.0}, 0.0)
    grid_cost = calculate_cost(500, {"module": 1.0}, 0.0, grid_connection=GridConnection(voltage_level="10kV 高压"))
    assert grid_cost.total_investment_yuan > base.total_investment_yuan
    assert "高压柜费用" in grid_cost.cost_items_yuan


def test_revenue_reads_grid_connection_full_export_and_no_export():
    common = dict(
        capacity_kwp=100,
        total_investment_yuan=200000,
        equivalent_hours=1000,
        first_year_degradation_ratio=0,
        annual_degradation_ratio=0,
        operating_years=2,
        self_use_ratio=0.8,
        feed_in_ratio=0.2,
        self_use_tariff=1.0,
        feed_in_tariff=0.1,
        contract_discount_ratio=1.0,
        om_cost_yuan_per_wp_year=0,
        insurance_ratio=0,
        cleaning_cost_yuan_per_wp_year=0,
        roof_rent_yuan_per_year=0,
        other_cost_yuan_per_year=0,
        income_tax_ratio=0,
        discount_rate=0.06,
    )
    full_export = calculate_revenue(**common, grid_connection=GridConnection(grid_mode="全额上网", export_tariff=0.4))
    no_export = calculate_revenue(**common, grid_connection=GridConnection(grid_mode="自发自用，不允许反送", self_use_tariff=1.0))
    assert full_export.cashflow_table["自用电量(kWh)"].iloc[0] == 0
    assert full_export.cashflow_table["上网电量(kWh)"].iloc[0] == 100000
    assert no_export.cashflow_table["上网电量(kWh)"].iloc[0] == 0
    assert no_export.cashflow_table["弃光电量(kWh)"].iloc[0] > 0


if __name__ == "__main__":
    test_full_export_mode()
    test_self_use_with_export_mode()
    test_no_reverse_power_mode()
    test_voltage_cost_rules()
    test_export_limit_interval()
    test_multi_connection_capacity_limit()
    test_storage_cost_and_scenario()
    test_adjust_consumption_for_grid_no_export()
    test_cost_accepts_grid_extra_items()
    test_capacity_reads_grid_connection_limit()
    test_cost_reads_grid_connection()
    test_revenue_reads_grid_connection_full_export_and_no_export()
    print("grid connection tests ok")
