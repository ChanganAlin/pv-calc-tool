from __future__ import annotations

import math


def npv(rate: float, cashflows: list[float]) -> float:
    """NPV：按折现率把第0年至第n年现金流折现求和。"""
    return sum(cf / ((1 + rate) ** idx) for idx, cf in enumerate(cashflows))


def irr(cashflows: list[float], low: float = -0.95, high: float = 1.0, tol: float = 1e-7) -> float | None:
    """IRR：用二分法寻找使 NPV=0 的折现率。"""
    if not cashflows or all(cf >= 0 for cf in cashflows) or all(cf <= 0 for cf in cashflows):
        return None
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    expand_count = 0
    while f_low * f_high > 0 and expand_count < 20:
        high *= 2
        f_high = npv(high, cashflows)
        expand_count += 1
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2


def simple_payback(cashflows: list[float]) -> float | None:
    """静态回收期：累计现金流由负转正时，按年内插值计算。"""
    cumulative = cashflows[0] if cashflows else 0.0
    if cumulative >= 0:
        return 0.0
    for year in range(1, len(cashflows)):
        previous = cumulative
        cumulative += cashflows[year]
        if cumulative >= 0:
            annual_cf = cashflows[year]
            fraction = abs(previous) / annual_cf if annual_cf else 0.0
            return year - 1 + fraction
    return None


def discounted_payback(cashflows: list[float], discount_rate: float) -> float | None:
    """动态回收期：先折现每年现金流，再按累计折现现金流转正点插值。"""
    discounted = [cf / ((1 + discount_rate) ** idx) for idx, cf in enumerate(cashflows)]
    return simple_payback(discounted)

