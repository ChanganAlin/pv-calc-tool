from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TiltRecommendation:
    theoretical_tilt_deg: float
    practical_tilt_deg: float
    roof_type: str
    wind_load_level: str
    notes: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["notes"] = "；".join(self.notes)
        return data


def theoretical_tilt_from_latitude(latitude: float) -> float:
    """理论最佳倾角：按项目所在地纬度分档估算。"""
    latitude = float(latitude)
    if latitude < 22:
        return 10.0
    if latitude < 25:
        return 15.0
    if latitude < 30:
        return 20.0
    if latitude < 35:
        return 25.0
    if latitude < 40:
        return 30.0
    if latitude < 45:
        return 35.0
    return 40.0


def practical_roof_tilt(
    latitude: float,
    roof_type: str,
    roof_slope_deg: float,
    project_priority: str,
    flat_roof_tilt_cap_deg: float,
    density_kwp_per_m2: float,
    wind_load_level: str,
    typhoon_region: bool,
    maintenance_deduction_ratio: float,
) -> TiltRecommendation:
    """屋面实际推荐倾角：在理论倾角基础上结合屋面类型、排布密度、风荷载和检修通道修正。"""
    theoretical = theoretical_tilt_from_latitude(latitude)
    practical = theoretical
    min_allowed = 3.0
    max_allowed = theoretical
    notes: list[str] = [f"理论最佳倾角按纬度估算为 {theoretical:.0f}°"]

    if roof_type == "彩钢瓦顺坡":
        practical = max(float(roof_slope_deg), 0.0)
        min_allowed = practical
        max_allowed = practical
        notes.append(f"彩钢瓦顺坡安装按屋面坡度取值，当前屋面坡度 {practical:.1f}°")
    elif roof_type == "混凝土平屋面":
        cap = 20.0 if float(flat_roof_tilt_cap_deg) >= 20 else 15.0
        practical = min(theoretical, cap)
        max_allowed = practical
        notes.append(f"混凝土平屋面按 min(理论推荐倾角, {cap:.0f}°) 取值")
    elif roof_type == "BIPV/一体化屋面":
        practical = min(max(theoretical, 3.0), 12.0)
        notes.append("BIPV 一体化屋面通常以建筑坡度和防水构造为主，倾角建议 3°-12°")
    else:
        practical = min(max(theoretical, 8.0), 22.0)
        notes.append("未知屋面类型，按常规工商业屋顶保守取值")

    if project_priority == "面积紧张":
        practical = min(max(practical, 5.0), 10.0)
        max_allowed = min(max_allowed, 10.0)
        min_allowed = max(min_allowed, 5.0)
        notes.append("面积紧张项目优先保证排布容量，倾角建议控制在 5°-10°")
    elif project_priority == "发电量优先":
        if roof_type != "彩钢瓦顺坡":
            practical = min(max_allowed, max(practical, theoretical - 2))
        notes.append("发电量优先项目倾角尽量接近理论最佳倾角，但不突破屋面结构或上限约束")

    if roof_type != "彩钢瓦顺坡" and density_kwp_per_m2 >= 0.18:
        practical -= 4
        notes.append("装机密度较高，为减少前后排遮挡和保留排布容量，实际倾角下调约 4°")
    elif roof_type != "彩钢瓦顺坡" and density_kwp_per_m2 >= 0.16:
        practical -= 2
        notes.append("装机密度偏高，实际倾角下调约 2°以兼顾排布密度")

    if roof_type == "彩钢瓦顺坡" and wind_load_level in {"较高", "高"}:
        notes.append("彩钢瓦顺坡倾角受屋面坡度约束，抗风要求主要通过夹具、支座和连接方式加强")
    elif wind_load_level == "高":
        practical -= 4
        notes.append("风荷载等级高，降低倾角以减小迎风面积和支架受力")
    elif wind_load_level == "较高":
        practical -= 2
        notes.append("风荷载等级较高，实际倾角适度下调")

    if roof_type == "彩钢瓦顺坡" and typhoon_region:
        notes.append("南方台风地区的彩钢瓦顺坡项目，应重点复核夹具抗拔、屋面连接和边缘区加固")
    elif typhoon_region:
        practical -= 3
        notes.append("南方台风地区建议适当降低倾角，降低迎风风险")

    if maintenance_deduction_ratio >= 0.20:
        practical += 1
        notes.append("检修通道和安全间距较充足，可适度提高倾角")
    elif maintenance_deduction_ratio <= 0.10:
        practical -= 1
        notes.append("检修通道扣减较低，倾角略下调以降低遮挡和运维冲突")

    practical = round(min(max(practical, min_allowed), max_allowed), 1)
    return TiltRecommendation(
        theoretical_tilt_deg=round(theoretical, 1),
        practical_tilt_deg=practical,
        roof_type=roof_type,
        wind_load_level=wind_load_level,
        notes=notes,
    )
