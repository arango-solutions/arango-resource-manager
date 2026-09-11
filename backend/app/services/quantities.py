"""Parsing and formatting of Kubernetes resource quantities.

The API returns quantities as strings ("250m", "2", "1Gi", "500M"). Everything
downstream works in cores (float) and bytes (int).

The rule that matters here: an absent quantity is None, never 0. A container
with no limit has not reserved zero - it has reserved nothing, which is a
different and more dangerous thing. Collapsing the two silently under-reports
totals and makes the "pods without limits" risk count impossible to compute.
"""

from __future__ import annotations

# Binary suffixes are the common case in manifests; decimal ones are legal too.
_BINARY: dict[str, int] = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
}
_DECIMAL: dict[str, int] = {
    "k": 10**3,
    "K": 10**3,
    "M": 10**6,
    "G": 10**9,
    "T": 10**12,
    "P": 10**15,
    "E": 10**18,
}

_GI = 1024**3


def parse_cpu(value: str | int | float | None) -> float | None:
    """Parse a CPU quantity into cores. "250m" -> 0.25, "2" -> 2.0.

    Returns None when the quantity is absent or unparseable, never 0.0.
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)

    text = value.strip()
    if not text:
        return None

    try:
        # "n" (nano) and "u" (micro) appear in metrics responses, not in specs.
        if text.endswith("n"):
            return float(text[:-1]) / 1_000_000_000
        if text.endswith("u"):
            return float(text[:-1]) / 1_000_000
        if text.endswith("m"):
            return float(text[:-1]) / 1000
        return float(text)
    except ValueError:
        return None


def parse_memory(value: str | int | float | None) -> int | None:
    """Parse a memory quantity into bytes. "512Mi" -> 536870912, "1G" -> 10**9.

    Returns None when the quantity is absent or unparseable, never 0.
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return int(value)

    text = value.strip()
    if not text:
        return None

    for suffix, factor in _BINARY.items():
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return None

    # Single-letter decimal suffixes. Checked after the two-letter binary ones
    # so that "Mi" is never mistaken for "M".
    for suffix, factor in _DECIMAL.items():
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return None

    try:
        return int(float(text))
    except ValueError:
        return None


def add_optional(left: float | None, right: float | None) -> float | None:
    """Sum two quantities where None means "unset".

    None + None stays None (nothing was set), but None + a value is that value
    (something was set). This is what lets a workload with one unlimited
    container still report the limits its other containers declared, while a
    workload with no limits at all reports None rather than a misleading 0.
    """
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def format_cpu(cores: float | None) -> str:
    """Render cores for display: 0.003 -> "3m", 2.0 -> "2", 46.25 -> "46.25"."""
    if cores is None:
        return "—"
    if cores == 0:
        return "0"
    if cores < 1:
        return f"{round(cores * 1000)}m"
    return f"{cores:.2f}".rstrip("0").rstrip(".")


def format_memory(num_bytes: int | float | None) -> str:
    """Render bytes in the largest binary unit that keeps it readable."""
    if num_bytes is None:
        return "—"
    value = float(num_bytes)
    for suffix in ("Ei", "Pi", "Ti", "Gi", "Mi", "Ki"):
        factor = _BINARY[suffix]
        if value >= factor:
            return f"{value / factor:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{int(value)}B"


def bytes_to_gi(num_bytes: int | float | None) -> float | None:
    if num_bytes is None:
        return None
    return float(num_bytes) / _GI


def gi_to_bytes(gi: float | None) -> int | None:
    if gi is None:
        return None
    return int(gi * _GI)
