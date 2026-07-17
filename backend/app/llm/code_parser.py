"""Code package parsing engine.

This module is responsible for unpacking a submitted code package (a ZIP
archive) and extracting a structured summary that can be fed to the LLM
review engine. It supports a variety of file types commonly found in BMS
SOX algorithm delivery packages:

* C source/header files (``.c`` / ``.h``)
* Python files (``.py``)
* MATLAB files (``.m``)
* MAT data files (``.mat``) - parsed via :mod:`scipy.io`
* Simulink models (``.slx``) - internally ZIP archives containing XML
* PyTorch model files (``.pth``) - parsed via :mod:`torch` (optional)

The main entry point is :func:`parse_code_package`, which returns a
:class:`CodeSummary`. :func:`build_llm_input` turns a summary into a plain
text representation suitable for LLM consumption (truncated to a maximum
character budget).
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# scipy is a hard dependency of the project (see requirements.txt).
import scipy.io


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class CodeSummary:
    """Structured summary of a parsed code package."""

    text_files: Dict[str, str] = field(default_factory=dict)
    functions: List[str] = field(default_factory=list)
    structs: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    mat_files_info: List[dict] = field(default_factory=list)
    simulink_info: List[dict] = field(default_factory=list)
    pth_info: List[dict] = field(default_factory=list)
    file_list: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# ZIP extraction
# ---------------------------------------------------------------------------
def extract_zip(file_data: bytes) -> Dict[str, bytes]:
    """Extract a ZIP archive into a mapping of ``path -> file content``.

    Args:
        file_data: The raw bytes of a ``.zip`` archive.

    Returns:
        A dictionary mapping each entry name to its decompressed bytes.

    Raises:
        zipfile.BadZipFile: If ``file_data`` is not a valid ZIP archive.
    """
    files: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
        for info in zf.infolist():
            # Skip directories.
            if info.is_dir():
                continue
            # Skip macOS metadata directories.
            if "__MACOSX" in info.filename or os.path.basename(info.filename).startswith("._"):
                continue
            try:
                files[info.filename] = zf.read(info)
            except (RuntimeError, zipfile.BadZipFile, OSError):
                # Skip entries that cannot be read.
                continue
    return files


# ---------------------------------------------------------------------------
# C file parsing
# ---------------------------------------------------------------------------
# Match C function definitions: a return type, optional pointer, a name,
# followed by a parameter list and an opening brace. This is intentionally
# permissive; it is used to surface structure to the LLM, not to fully
# parse C.
_C_FUNC_RE = re.compile(
    r"""
    ^                           # start of line
    (?:static\s+|inline\s+|extern\s+)*   # optional storage/qualifiers
    (?:[\w\*\s]+?)\s+           # return type (greedy-ish, non-greedy overall)
    ([A-Za-z_]\w*)              # function name (captured)
    \s*\([^;]*?\)               # parameter list
    \s*\{                       # opening brace
    """,
    re.MULTILINE | re.VERBOSE,
)

_C_STRUCT_RE = re.compile(
    r"""
    \b(?:struct|union|enum)\s+   # struct/union/enum keyword
    ([A-Za-z_]\w*)               # tag name (captured)
    \s*\{                        # opening brace
    """,
    re.VERBOSE,
)


def parse_c_file(content: str) -> Tuple[List[str], List[str]]:
    """Extract function names and struct/union/enum tag names from C source.

    Args:
        content: The C source code text.

    Returns:
        A tuple ``(functions, structs)`` of de-duplicated names.
    """
    # Strip line/block comments to reduce false positives.
    cleaned = re.sub(r"/\*.*?\*/", " ", content, flags=re.DOTALL)
    cleaned = re.sub(r"//[^\n]*", " ", cleaned)

    functions: List[str] = []
    seen_funcs = set()
    for match in _C_FUNC_RE.finditer(cleaned):
        name = match.group(1)
        # Filter out C keywords that may be captured as a "name".
        if name in {"if", "for", "while", "switch", "return", "sizeof", "do"}:
            continue
        if name not in seen_funcs:
            seen_funcs.add(name)
            functions.append(name)

    structs: List[str] = []
    seen_structs = set()
    for match in _C_STRUCT_RE.finditer(cleaned):
        name = match.group(1)
        if name not in seen_structs:
            seen_structs.add(name)
            structs.append(name)

    return functions, structs


# ---------------------------------------------------------------------------
# Python file parsing
# ---------------------------------------------------------------------------
_PY_FUNC_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*[\(:]", re.MULTILINE)


def parse_python_file(content: str) -> Tuple[List[str], List[str]]:
    """Extract ``def`` function names and ``class`` names from Python source.

    Args:
        content: The Python source code text.

    Returns:
        A tuple ``(functions, classes)`` of de-duplicated names.
    """
    functions: List[str] = []
    seen = set()
    for match in _PY_FUNC_RE.finditer(content):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            functions.append(name)

    classes: List[str] = []
    seen_cls = set()
    for match in _PY_CLASS_RE.finditer(content):
        name = match.group(1)
        if name not in seen_cls:
            seen_cls.add(name)
            classes.append(name)

    return functions, classes


# ---------------------------------------------------------------------------
# MATLAB file parsing
# ---------------------------------------------------------------------------
_MLAB_FUNC_RE = re.compile(
    r"^\s*function\s+(?:\[.*?\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z_]\w*)\s*(?:\(|$)",
    re.MULTILINE,
)


def parse_matlab_file(content: str) -> List[str]:
    """Extract ``function`` names from MATLAB source.

    Args:
        content: The MATLAB source code text.

    Returns:
        A de-duplicated list of function names.
    """
    functions: List[str] = []
    seen = set()
    for match in _MLAB_FUNC_RE.finditer(content):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            functions.append(name)
    return functions


# ---------------------------------------------------------------------------
# MAT file parsing
# ---------------------------------------------------------------------------
def parse_mat_file(file_data: bytes, filename: str) -> dict:
    """Extract variable information from a MATLAB ``.mat`` file.

    Args:
        file_data: The raw bytes of the ``.mat`` file.
        filename: The file name (used for reporting errors).

    Returns:
        A dict with keys ``filename``, ``variables`` (list of
        ``{name, shape, dtype}``) and optionally ``error``.
    """
    info: dict = {"filename": filename, "variables": []}
    try:
        mat = scipy.io.loadmat(io.BytesIO(file_data))
    except Exception as exc:  # noqa: BLE001 - surface any parsing failure
        info["error"] = f"Failed to parse .mat file: {exc}"
        return info

    for name, value in mat.items():
        # Skip MATLAB internal metadata fields.
        if name.startswith("__"):
            continue
        shape = list(getattr(value, "shape", []))
        dtype = str(getattr(value, "dtype", ""))
        info["variables"].append(
            {"name": name, "shape": shape, "dtype": dtype}
        )
    return info


# ---------------------------------------------------------------------------
# PyTorch .pth file parsing
# ---------------------------------------------------------------------------
def parse_pth_file(file_data: bytes, filename: str) -> dict:
    """Extract layer information from a PyTorch ``.pth`` checkpoint.

    Only the first 50 layers are reported to keep the summary compact. The
    ``torch`` package is optional; if it is not installed a descriptive
    error is returned instead of raising.

    Args:
        file_data: The raw bytes of the ``.pth`` file.
        filename: The file name (used for reporting).

    Returns:
        A dict with keys ``filename``, ``layers`` (list of
        ``{name, shape, num_params}``), ``total_params`` and optionally
        ``error``.
    """
    info: dict = {
        "filename": filename,
        "layers": [],
        "total_params": 0,
    }
    try:
        import torch  # type: ignore
    except ImportError:
        info["error"] = (
            "PyTorch is not installed; .pth files cannot be parsed."
        )
        return info

    try:
        # weights_only=False for compatibility with checkpoints that store
        # arbitrary Python objects. In production this should be reviewed
        # against the trust boundary of uploaded packages.
        state_dict = torch.load(
            io.BytesIO(file_data),
            map_location="cpu",
            weights_only=False,
        )
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"Failed to parse .pth file: {exc}"
        return info

    # Handle checkpoints stored as dicts with a 'state_dict' key.
    if isinstance(state_dict, dict) and "state_dict" in state_dict and isinstance(
        state_dict["state_dict"], dict
    ):
        state_dict = state_dict["state_dict"]

    if not isinstance(state_dict, dict):
        info["error"] = (
            "Unsupported .pth format: expected a state dict mapping."
        )
        return info

    total_params = 0
    for idx, (name, tensor) in enumerate(state_dict.items()):
        if idx >= 50:
            info["layers"].append(
                {"name": "...(truncated)", "shape": [], "num_params": 0}
            )
            break
        shape = list(getattr(tensor, "shape", []))
        try:
            num_params = int(tensor.numel())
        except Exception:  # noqa: BLE001
            num_params = 0
        total_params += num_params
        info["layers"].append(
            {"name": name, "shape": shape, "num_params": num_params}
        )

    info["total_params"] = total_params
    return info


# ---------------------------------------------------------------------------
# Simulink .slx file parsing
# ---------------------------------------------------------------------------
_SLX_BLOCK_RE = re.compile(
    r'<Block\s+[^>]*?Name="([^"]+)"[^>]*?BlockType="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_SLX_BLOCK_RE_ALT = re.compile(
    r'<Block\s+[^>]*?BlockType="([^"]+)"[^>]*?Name="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)


def parse_simulink_file(file_data: bytes, filename: str) -> dict:
    """Extract block information from a Simulink ``.slx`` model.

    An ``.slx`` file is a ZIP archive; the block hierarchy is stored in
    XML files (typically ``simulink/blockdiagram.xml``). This function
    extracts all ``<Block Name="..." BlockType="...">`` entries.

    Args:
        file_data: The raw bytes of the ``.slx`` file.
        filename: The file name (used for reporting).

    Returns:
        A dict with keys ``filename``, ``blocks`` (list of
        ``{name, block_type}``) and optionally ``error``.
    """
    info: dict = {"filename": filename, "blocks": []}
    try:
        extracted = extract_zip(file_data)
    except zipfile.BadZipFile as exc:
        info["error"] = f"Failed to open .slx (not a valid zip): {exc}"
        return info

    # Collect all XML content from the archive.
    xml_blobs: List[str] = []
    for path, data in extracted.items():
        if path.lower().endswith(".xml"):
            try:
                xml_blobs.append(data.decode("utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                continue

    if not xml_blobs:
        info["error"] = "No XML files found inside the .slx archive."
        return info

    combined_xml = "\n".join(xml_blobs)
    seen = set()
    for pattern in (_SLX_BLOCK_RE, _SLX_BLOCK_RE_ALT):
        for match in pattern.finditer(combined_xml):
            if pattern is _SLX_BLOCK_RE:
                name, block_type = match.group(1), match.group(2)
            else:
                block_type, name = match.group(1), match.group(2)
            key = (name, block_type)
            if key in seen:
                continue
            seen.add(key)
            info["blocks"].append(
                {"name": name, "block_type": block_type}
            )

    return info


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def _decode_text(data: bytes) -> Optional[str]:
    """Try to decode bytes as UTF-8 text; return None on failure."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk", errors="ignore")
        except Exception:  # noqa: BLE001
            return None


def parse_code_package(file_data: bytes) -> CodeSummary:
    """Parse an uploaded code package (ZIP) into a :class:`CodeSummary`.

    The function iterates every file inside the archive and dispatches to
    the appropriate parser based on the file extension. Any non-fatal
    parsing error for an individual file is recorded in the summary's
    ``error`` field without aborting the whole parse.

    Args:
        file_data: The raw bytes of the ``.zip`` code package.

    Returns:
        A :class:`CodeSummary`. If the archive itself cannot be opened,
        ``summary.error`` is set and the rest of the fields are empty.
    """
    summary = CodeSummary()

    try:
        files = extract_zip(file_data)
    except zipfile.BadZipFile as exc:
        summary.error = f"Invalid code package (not a zip archive): {exc}"
        return summary
    except Exception as exc:  # noqa: BLE001
        summary.error = f"Failed to extract code package: {exc}"
        return summary

    summary.file_list = sorted(files.keys())

    for path, data in files.items():
        ext = os.path.splitext(path)[1].lower()
        basename = os.path.basename(path)

        if ext in (".c", ".h"):
            text = _decode_text(data)
            if text is None:
                continue
            summary.text_files[path] = text
            funcs, structs = parse_c_file(text)
            summary.functions.extend(funcs)
            summary.structs.extend(structs)
        elif ext == ".py":
            text = _decode_text(data)
            if text is None:
                continue
            summary.text_files[path] = text
            funcs, classes = parse_python_file(text)
            summary.functions.extend(funcs)
            summary.classes.extend(classes)
        elif ext == ".m":
            text = _decode_text(data)
            if text is None:
                continue
            summary.text_files[path] = text
            summary.functions.extend(parse_matlab_file(text))
        elif ext == ".mat":
            summary.mat_files_info.append(
                parse_mat_file(data, basename or path)
            )
        elif ext == ".slx":
            summary.simulink_info.append(
                parse_simulink_file(data, basename or path)
            )
        elif ext == ".pth":
            summary.pth_info.append(
                parse_pth_file(data, basename or path)
            )
        elif ext in (".txt", ".md", ".rst", ".cfg", ".ini", ".yaml", ".yml", ".json"):
            text = _decode_text(data)
            if text is not None:
                summary.text_files[path] = text

    return summary


# ---------------------------------------------------------------------------
# LLM input builder
# ---------------------------------------------------------------------------
def _format_list(items: List[str], indent: str = "  ") -> str:
    if not items:
        return f"{indent}(none)"
    return "\n".join(f"{indent}- {item}" for item in items)


def _format_mat_info(infos: List[dict]) -> str:
    lines: List[str] = []
    for info in infos:
        lines.append(f"  File: {info.get('filename')}")
        if info.get("error"):
            lines.append(f"    Error: {info['error']}")
            continue
        for var in info.get("variables", []):
            lines.append(
                f"    - {var.get('name')}: shape={var.get('shape')}, "
                f"dtype={var.get('dtype')}"
            )
    return "\n".join(lines) if lines else "  (none)"


def _format_simulink_info(infos: List[dict]) -> str:
    lines: List[str] = []
    for info in infos:
        lines.append(f"  File: {info.get('filename')}")
        if info.get("error"):
            lines.append(f"    Error: {info['error']}")
            continue
        for block in info.get("blocks", []):
            lines.append(
                f"    - Block '{block.get('name')}' "
                f"(type: {block.get('block_type')})"
            )
    return "\n".join(lines) if lines else "  (none)"


def _format_pth_info(infos: List[dict]) -> str:
    lines: List[str] = []
    for info in infos:
        lines.append(f"  File: {info.get('filename')}")
        if info.get("error"):
            lines.append(f"    Error: {info['error']}")
            continue
        lines.append(f"    Total parameters: {info.get('total_params', 0)}")
        for layer in info.get("layers", []):
            lines.append(
                f"    - {layer.get('name')}: shape={layer.get('shape')}, "
                f"params={layer.get('num_params')}"
            )
    return "\n".join(lines) if lines else "  (none)"


def build_llm_input(
    summary: CodeSummary,
    change_notes: str,
    max_chars: int = 50000,
) -> str:
    """Assemble a plain-text representation of a :class:`CodeSummary`.

    The output contains:
        * The full file list.
        * Lists of functions, structs and classes discovered.
        * Summaries of ``.mat``, Simulink and ``.pth`` files.
        * The submitter's change notes.
        * The full text of every text source file, truncated so the whole
          result stays within ``max_chars``.

    Args:
        summary: The parsed code package summary.
        change_notes: Free-form change notes submitted with the package.
        max_chars: Maximum number of characters for the assembled text.

    Returns:
        The assembled LLM input string.
    """
    sections: List[str] = []

    sections.append("===== 文件列表 =====")
    sections.append(_format_list(summary.file_list) if summary.file_list else "  (空)")

    sections.append("\n===== 函数列表 =====")
    sections.append(_format_list(summary.functions))

    sections.append("\n===== 结构体/联合体/枚举列表 =====")
    sections.append(_format_list(summary.structs))

    sections.append("\n===== 类列表 (Python) =====")
    sections.append(_format_list(summary.classes))

    sections.append("\n===== MAT 文件信息 =====")
    sections.append(_format_mat_info(summary.mat_files_info))

    sections.append("\n===== Simulink 模型信息 =====")
    sections.append(_format_simulink_info(summary.simulink_info))

    sections.append("\n===== PyTorch 模型 (.pth) 信息 =====")
    sections.append(_format_pth_info(summary.pth_info))

    sections.append("\n===== 变更点说明 =====")
    sections.append(change_notes.strip() if change_notes and change_notes.strip() else "(未提供)")

    if summary.error:
        sections.append("\n===== 解析警告 =====")
        sections.append(summary.error)

    # Build the header and reserve room for it when budgeting the code text.
    header = "\n".join(sections)
    parts: List[str] = [header]

    if summary.text_files:
        parts.append("\n===== 代码文件全文 =====")
        budget = max_chars - len("\n".join(parts))
        for path, text in sorted(summary.text_files.items()):
            file_header = f"\n----- {path} -----\n"
            if budget <= len(file_header):
                parts.append("\n...(其余代码文件因长度限制被截断)...")
                break
            budget -= len(file_header)
            parts.append(file_header)
            available = max(0, budget)
            if len(text) > available:
                parts.append(text[:available])
                parts.append("\n...(该文件因长度限制被截断)...")
                budget = 0
                break
            parts.append(text)
            budget -= len(text)

    result = "\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars]
    return result
