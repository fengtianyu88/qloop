"""Word / Excel document parsing helpers.

These helpers turn an uploaded ``.docx`` or ``.xlsx`` file into plain text
that can be embedded into an LLM review prompt. Only the modern
Office Open XML formats (``.docx`` / ``.xlsx``) are supported; the legacy
binary formats (``.doc`` / ``.xls``) return a descriptive message instead of
raising, so the review engine can still produce a (failed) result.
"""

from __future__ import annotations

import io
import os
from typing import List

from docx import Document
from openpyxl import load_workbook


# ---------------------------------------------------------------------------
# Word (.docx)
# ---------------------------------------------------------------------------
def parse_docx(file_data: bytes) -> str:
    """Extract text from a ``.docx`` file.

    Both paragraph text and table cell text are included, in document
    order. Empty paragraphs are skipped.

    Args:
        file_data: The raw bytes of the ``.docx`` file.

    Returns:
        The extracted plain text. If parsing fails, an error message is
        returned.
    """
    try:
        document = Document(io.BytesIO(file_data))
    except Exception as exc:  # noqa: BLE001
        return f"[解析 Word 文档失败: {exc}]"

    chunks: List[str] = []

    # Iterate over the document body in order, interleaving paragraphs and
    # tables as they appear.
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            chunks.append(text)

    for table in document.tables:
        chunks.append("--- 表格 ---")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                chunks.append(" | ".join(cells))
        chunks.append("--- 表格结束 ---")

    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Excel (.xlsx)
# ---------------------------------------------------------------------------
def parse_xlsx(file_data: bytes) -> str:
    """Extract text from an ``.xlsx`` file.

    Every worksheet is traversed row by row; non-empty rows are joined with
    ``|`` separators and prefixed with a sheet header.

    Args:
        file_data: The raw bytes of the ``.xlsx`` file.

    Returns:
        The extracted plain text. If parsing fails, an error message is
        returned.
    """
    try:
        workbook = load_workbook(io.BytesIO(file_data), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        return f"[解析 Excel 文档失败: {exc}]"

    chunks: List[str] = []
    for sheet in workbook.worksheets:
        chunks.append(f"=== Sheet: {sheet.title} ===")
        row_count = 0
        for row in sheet.iter_rows(values_only=True):
            # Skip completely empty rows.
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            chunks.append(" | ".join(cells))
            row_count += 1
        if row_count == 0:
            chunks.append("(空工作表)")
        chunks.append(f"=== Sheet 结束: {sheet.title} ===")

    try:
        workbook.close()
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def parse_document(file_data: bytes, filename: str) -> str:
    """Parse a document based on its file extension.

    Supported extensions:
        * ``.docx`` -> :func:`parse_docx`
        * ``.xlsx`` -> :func:`parse_xlsx`

    Legacy binary formats (``.doc`` / ``.xls``) and any other extension
    return a descriptive message instead of raising, so callers can still
    record a review result.

    Args:
        file_data: The raw bytes of the document.
        filename: The original file name (used to determine the parser).

    Returns:
        The extracted plain text, or a message explaining why parsing was
        skipped.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".docx":
        return parse_docx(file_data)
    if ext == ".xlsx":
        return parse_xlsx(file_data)
    if ext == ".doc":
        return (
            "[不支持旧版 .doc 格式，请将文档另存为 .docx 后重新上传以进行评审。]"
        )
    if ext == ".xls":
        return (
            "[不支持旧版 .xls 格式，请将文档另存为 .xlsx 后重新上传以进行评审。]"
        )

    # Last resort: try to decode as plain text.
    try:
        return file_data.decode("utf-8")
    except UnicodeDecodeError:
        return f"[无法解析的文档类型: {ext or '(无扩展名)'}]"
