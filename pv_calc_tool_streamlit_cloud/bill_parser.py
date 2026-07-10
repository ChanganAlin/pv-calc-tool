from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from io import BytesIO
from typing import Optional

import pandas as pd
from pypdf import PdfReader


@dataclass
class BillParseResult:
    annual_consumption_kwh: float
    monthly_average_kwh: float
    parsed_table: pd.DataFrame
    extracted_fields: dict
    warnings: list[str]
    parsed_status: str = "ok"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["parsed_table"] = self.parsed_table.to_dict(orient="records")
        return data


FIELD_ALIASES = {
    "month": ["月份", "月", "账期", "日期"],
    "total_kwh": ["总电量", "总用电量", "合计电量", "电量合计", "本月用电量", "月用电量"],
    "peak_kwh": ["尖电量", "尖"],
    "high_kwh": ["峰电量", "峰"],
    "flat_kwh": ["平电量", "平"],
    "valley_kwh": ["谷电量", "谷"],
    "basic_fee": ["基本电费"],
    "total_fee": ["总电费", "金额", "电费合计", "合计金额", "应缴金额"],
}


def _find_column(columns: list[str], aliases: list[str]) -> Optional[str]:
    normalized = {str(col).strip(): col for col in columns}
    for name in normalized:
        for alias in aliases:
            if alias.lower() in name.lower():
                return normalized[name]
    return None


def parse_excel_bill(uploaded_file) -> BillParseResult:
    """电费单解析：优先从 Excel 表头中识别总电量等字段，识别后仍允许人工修正。"""
    data = uploaded_file.read()
    xls = pd.ExcelFile(BytesIO(data))
    df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
    df = df.dropna(how="all")
    cols = list(df.columns)
    total_col = _find_column(cols, FIELD_ALIASES["total_kwh"])
    tou_cols = {
        "peak_kwh": _find_column(cols, FIELD_ALIASES["peak_kwh"]),
        "high_kwh": _find_column(cols, FIELD_ALIASES["high_kwh"]),
        "flat_kwh": _find_column(cols, FIELD_ALIASES["flat_kwh"]),
        "valley_kwh": _find_column(cols, FIELD_ALIASES["valley_kwh"]),
    }
    warnings: list[str] = []

    extracted: dict = {}
    parsed_status = "ok"
    if all(tou_cols.values()):
        annual = float(sum(pd.to_numeric(df[col], errors="coerce").fillna(0).sum() for col in tou_cols.values()))
        extracted["total_kwh_source"] = "tou_sum"
    elif total_col is not None:
        fee_col = _find_column(cols, FIELD_ALIASES["total_fee"])
        if fee_col is not None and str(total_col) == str(fee_col):
            annual = 0.0
            parsed_status = "need_manual_review"
            warnings.append("未能可靠识别总电量，请手动确认。")
        else:
            annual = float(pd.to_numeric(df[total_col], errors="coerce").fillna(0).sum())
            extracted["total_kwh_column"] = str(total_col)
    else:
        annual = 0.0
        parsed_status = "need_manual_review"
        warnings.append("未能可靠识别总电量，请手动确认。")
    monthly_avg = annual / 12 if annual else 0.0

    for key, aliases in FIELD_ALIASES.items():
        col = _find_column(cols, aliases)
        if col is not None:
            extracted[key] = str(col)

    return BillParseResult(
        annual_consumption_kwh=annual,
        monthly_average_kwh=monthly_avg,
        parsed_table=df,
        extracted_fields=extracted,
        warnings=warnings,
        parsed_status=parsed_status,
    )


def parse_text_bill(text: str) -> dict:
    """OCR 文本解析预留：从文本中用关键词和数字做弱提取，结果仅作人工修正草稿。"""
    fields = {}
    patterns = {
        "total_kwh": r"(?:总电量|总用电量|用电量)[^\d]*(\d+(?:\.\d+)?)",
        "basic_fee": r"(?:基本电费)[^\d]*(\d+(?:\.\d+)?)",
        "total_fee": r"(?:总电费|应缴金额|合计金额)[^\d]*(\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[key] = float(match.group(1))
    return fields


def extract_pdf_text(uploaded_file) -> str:
    """PDF 电费单解析：优先从可复制文本 PDF 中抽取文字。"""
    data = uploaded_file.read()
    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _extract_numbers_near_keywords(text: str, keywords: list[str]) -> list[float]:
    values: list[float] = []
    for keyword in keywords:
        pattern = rf"{keyword}[^\d]{{0,20}}(\d+(?:,\d{{3}})*(?:\.\d+)?)"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            number = match.group(1).replace(",", "")
            try:
                values.append(float(number))
            except ValueError:
                continue
    return values


def parse_pdf_bill(uploaded_file) -> BillParseResult:
    """PDF 电费单解析：抽取文字后识别电量字段，扫描件识别失败时提示人工修正。"""
    warnings: list[str] = []
    text = extract_pdf_text(uploaded_file)
    normalized = re.sub(r"\s+", " ", text)
    if len(normalized.strip()) < 20:
        warnings.append("PDF 未抽取到有效文字，可能是扫描件。请先手动填写年用电量，后续可接入 OCR。")
        return BillParseResult(
            annual_consumption_kwh=0.0,
            monthly_average_kwh=0.0,
            parsed_table=pd.DataFrame([{"识别文本": ""}]),
            extracted_fields={},
            warnings=warnings,
            parsed_status="need_manual_review",
        )

    total_candidates = _extract_numbers_near_keywords(
        normalized,
        ["总电量", "总用电量", "合计电量", "本期电量", "用电量", "电量合计"],
    )
    tou_values = _extract_numbers_near_keywords(normalized, ["尖电量", "峰电量", "平电量", "谷电量"])
    fields = parse_text_bill(normalized)

    annual = 0.0
    extracted_fields = {"text_length": len(normalized)}
    if total_candidates:
        annual = max(total_candidates)
        extracted_fields["total_kwh_candidates"] = total_candidates
        warnings.append("PDF 已识别到电量候选值，请核对是否为单月电量；如只上传单月电费单，请在页面手动换算年用电量。")
    elif tou_values:
        annual = sum(tou_values)
        extracted_fields["tou_kwh_sum"] = annual
        warnings.append("PDF 未识别总电量，已尝试按尖峰平谷电量求和，请人工复核。")
    elif "total_kwh" in fields:
        annual = fields["total_kwh"]
        extracted_fields.update(fields)
        warnings.append("PDF 已按文本关键词识别总电量，请人工复核。")
    else:
        warnings.append("未能可靠识别总电量，请手动确认。")

    parsed_table = pd.DataFrame(
        [
            {"字段": "识别电量(kWh)", "值": annual},
            {"字段": "文本预览", "值": normalized[:500]},
        ]
    )
    return BillParseResult(
        annual_consumption_kwh=annual,
        monthly_average_kwh=annual / 12 if annual else 0.0,
        parsed_table=parsed_table,
        extracted_fields=extracted_fields,
        warnings=warnings,
        parsed_status="ok" if annual > 0 else "need_manual_review",
    )


def parse_bill_file(uploaded_file) -> BillParseResult:
    """电费单统一入口：支持 Excel 和 PDF。"""
    name = (uploaded_file.name or "").lower()
    if name.endswith((".xlsx", ".xls")):
        return parse_excel_bill(uploaded_file)
    if name.endswith(".pdf"):
        return parse_pdf_bill(uploaded_file)
    return BillParseResult(
        annual_consumption_kwh=0.0,
        monthly_average_kwh=0.0,
        parsed_table=pd.DataFrame(),
        extracted_fields={},
        warnings=["暂不支持该文件格式，请上传 PDF、Excel，或手动填写年用电量。"],
        parsed_status="need_manual_review",
    )
