from __future__ import annotations

import pandas as pd


def money(yuan: float) -> str:
    return f"{yuan:,.2f} 元 / {yuan / 10000:,.2f} 万元"


def energy(kwh: float) -> str:
    return f"{kwh:,.0f} kWh / {kwh / 10000:,.2f} 万kWh"


def ratio(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def years(value: float | None) -> str:
    return "未回收" if value is None else f"{value:.2f} 年"


def labeled_table(data: dict, labels: dict[str, str]) -> pd.DataFrame:
    rows = []
    for key, label in labels.items():
        value = data.get(key)
        if isinstance(value, float):
            if "比例" in label or "率" in label or "系数" in label:
                display_value = f"{value * 100:.2f}%"
            else:
                display_value = f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"
        else:
            display_value = value
        rows.append({"指标": label, "数值": display_value})
    return pd.DataFrame(rows)
