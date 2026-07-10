from __future__ import annotations

from dataclasses import dataclass, asdict
from io import BytesIO
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw


@dataclass
class ImageAreaEstimate:
    image_width_px: int
    image_height_px: int
    selected_width_px: float
    selected_height_px: float
    meters_per_pixel: float
    estimated_area_m2: float
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DetectedRegion:
    x: int
    y: int
    width: int
    height: int
    area_px: int
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MapAreaResult:
    image_width_px: int
    image_height_px: int
    scale_meters: float
    scale_pixels: float
    meters_per_pixel: float
    region: DetectedRegion
    estimated_area_m2: float

    def to_dict(self) -> dict:
        data = asdict(self)
        data["region"] = self.region.to_dict()
        return data


@dataclass
class PolygonAreaResult:
    image_width_px: int
    image_height_px: int
    scale_meters: float
    scale_pixels: float
    meters_per_pixel: float
    polygon_area_px: float
    estimated_area_m2: float
    points: list[tuple[float, float]]

    def to_dict(self) -> dict:
        return asdict(self)


def open_image_size(file_obj) -> tuple[int, int]:
    """图片辅助：读取图片像素尺寸，供矩形区域估算面积。"""
    image = Image.open(file_obj)
    return image.size


def load_rgb_image(file_obj) -> Image.Image:
    """图片读取：把上传文件统一转换为 RGB 图片。"""
    file_obj.seek(0)
    return Image.open(file_obj).convert("RGB")


def estimate_rect_area(
    image_width_px: int,
    image_height_px: int,
    selected_width_px: float,
    selected_height_px: float,
    reference_pixels: float,
    reference_meters: float,
) -> ImageAreaEstimate:
    """面积估算：按参考比例尺把矩形像素面积换算为平方米。"""
    reference_pixels = max(float(reference_pixels), 0.0001)
    reference_meters = max(float(reference_meters), 0.0)
    selected_width_px = max(float(selected_width_px), 0.0)
    selected_height_px = max(float(selected_height_px), 0.0)
    meters_per_pixel = reference_meters / reference_pixels
    area = selected_width_px * selected_height_px * meters_per_pixel * meters_per_pixel
    return ImageAreaEstimate(
        image_width_px=int(image_width_px),
        image_height_px=int(image_height_px),
        selected_width_px=selected_width_px,
        selected_height_px=selected_height_px,
        meters_per_pixel=meters_per_pixel,
        estimated_area_m2=area,
        note="图片估算面积仅用于初步测算，最终面积应以现场踏勘、设计图纸或测绘结果为准。",
    )


def detect_scale_bar_pixels(image: Image.Image) -> float:
    """比例尺识别：优先在图片底部寻找较长水平线，失败时返回 100px 作为人工修正默认值。"""
    arr = np.array(image)
    height, width = arr.shape[:2]
    bottom = arr[int(height * 0.60) :, :, :]
    gray = cv2.cvtColor(bottom, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    horizontal = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[int] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= max(35, width * 0.04) and h <= 8:
            candidates.append(w)
    if not candidates:
        return 100.0
    return float(max(candidates))


def detect_pv_candidate_regions(image: Image.Image, max_regions: int = 6) -> list[DetectedRegion]:
    """地图区域识别：基于颜色、亮度和轮廓面积初步找出疑似可铺设光伏的屋面/空地矩形区域。"""
    arr = np.array(image)
    height, width = arr.shape[:2]
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    hue, saturation, value = cv2.split(hsv)

    # 候选区域：排除明显植被/水体，保留低饱和度或较亮的屋面、硬化地面。
    not_green = ~((hue >= 35) & (hue <= 95) & (saturation > 45))
    not_blue = ~((hue >= 90) & (hue <= 135) & (saturation > 45))
    near_white_ui = (saturation < 18) & (value > 238)
    roof_like = (((saturation < 70) & (value > 70)) | ((value > 135) & (saturation < 120))) & (~near_white_ui)
    mask = (roof_like & not_green & not_blue).astype(np.uint8) * 255

    mask[: int(height * 0.06), :] = 0
    mask[int(height * 0.92) :, :] = 0
    mask[:, : int(width * 0.02)] = 0
    mask[:, int(width * 0.98) :] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_area = width * height
    regions: list[DetectedRegion] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.002:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 30 or h < 30:
            continue
        rect_area = w * h
        if rect_area > image_area * 0.72:
            continue
        fill_ratio = min(area / rect_area, 1.0)
        aspect = max(w / h, h / w)
        if aspect > 8:
            continue
        confidence = round(min(0.95, 0.35 + fill_ratio * 0.45 + min(rect_area / image_area, 0.15)), 2)
        regions.append(DetectedRegion(x=x, y=y, width=w, height=h, area_px=rect_area, confidence=confidence))

    regions.sort(key=lambda item: (item.area_px, item.confidence), reverse=True)
    if regions:
        return regions[:max_regions]

    fallback_w = int(width * 0.45)
    fallback_h = int(height * 0.35)
    return [
        DetectedRegion(
            x=int((width - fallback_w) / 2),
            y=int((height - fallback_h) / 2),
            width=fallback_w,
            height=fallback_h,
            area_px=fallback_w * fallback_h,
            confidence=0.20,
        )
    ]


def estimate_map_region_area(region: DetectedRegion, scale_meters: float, scale_pixels: float, image_size: tuple[int, int]) -> MapAreaResult:
    """地图面积估算：按比例尺线段像素长度换算选中区域面积。"""
    scale_pixels = max(float(scale_pixels), 0.0001)
    scale_meters = max(float(scale_meters), 0.0)
    meters_per_pixel = scale_meters / scale_pixels
    area = region.width * region.height * meters_per_pixel * meters_per_pixel
    return MapAreaResult(
        image_width_px=image_size[0],
        image_height_px=image_size[1],
        scale_meters=scale_meters,
        scale_pixels=scale_pixels,
        meters_per_pixel=meters_per_pixel,
        region=region,
        estimated_area_m2=area,
    )


def polygon_area_px(points: list[tuple[float, float]]) -> float:
    """多边形面积：使用鞋带公式计算任意框选区域的像素面积。"""
    if len(points) < 3:
        return 0.0
    area = 0.0
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def estimate_polygon_area(points: list[tuple[float, float]], scale_meters: float, scale_pixels: float, image_size: tuple[int, int]) -> PolygonAreaResult:
    """地图多边形面积估算：按比例尺把任意多边形像素面积换算为平方米。"""
    scale_pixels = max(float(scale_pixels), 0.0001)
    scale_meters = max(float(scale_meters), 0.0)
    meters_per_pixel = scale_meters / scale_pixels
    area_px = polygon_area_px(points)
    return PolygonAreaResult(
        image_width_px=image_size[0],
        image_height_px=image_size[1],
        scale_meters=scale_meters,
        scale_pixels=scale_pixels,
        meters_per_pixel=meters_per_pixel,
        polygon_area_px=area_px,
        estimated_area_m2=area_px * meters_per_pixel * meters_per_pixel,
        points=points,
    )


def estimate_area_from_pixel_area(pixel_area: float, scale_meters: float, scale_pixels: float) -> float:
    """按比例尺把目标区域像素面积换算为平方米。"""
    scale_pixels = max(float(scale_pixels), 0.0001)
    meters_per_pixel = max(float(scale_meters), 0.0) / scale_pixels
    return max(float(pixel_area), 0.0) * meters_per_pixel * meters_per_pixel


def draw_regions_overlay(image: Image.Image, regions: list[DetectedRegion], active_index: int = 0) -> Image.Image:
    """橙色框选：把自动识别或人工修改后的区域叠加到原图。"""
    output = image.copy()
    draw = ImageDraw.Draw(output, "RGBA")
    for idx, region in enumerate(regions):
        color = (240, 90, 26, 235) if idx == active_index else (240, 90, 26, 140)
        fill = (240, 90, 26, 42) if idx == active_index else (240, 90, 26, 20)
        x1, y1 = region.x, region.y
        x2, y2 = region.x + region.width, region.y + region.height
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4, fill=fill)
        draw.text((x1 + 6, max(y1 + 6, 0)), f"区域{idx + 1}", fill=color)
    return output


def draw_polygon_overlay(image: Image.Image, points: list[tuple[float, float]]) -> Image.Image:
    """橙色不规则框选：把人工编辑的多边形区域叠加到原图。"""
    output = image.copy()
    draw = ImageDraw.Draw(output, "RGBA")
    if len(points) >= 3:
        polygon = [(float(x), float(y)) for x, y in points]
        draw.polygon(polygon, outline=(240, 90, 26, 240), fill=(240, 90, 26, 46))
        draw.line(polygon + [polygon[0]], fill=(240, 90, 26, 255), width=4)
    for idx, (x, y) in enumerate(points, start=1):
        radius = 5
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(240, 90, 26, 255))
        draw.text((x + 7, y + 3), str(idx), fill=(240, 90, 26, 255))
    return output
