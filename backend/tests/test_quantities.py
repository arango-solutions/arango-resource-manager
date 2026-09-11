"""Quantity parsing. The None-is-not-zero rule is the one that matters."""

import pytest

from app.services.quantities import (
    add_optional,
    bytes_to_gi,
    format_cpu,
    format_memory,
    parse_cpu,
    parse_memory,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2", 2.0),
        ("250m", 0.25),
        ("1500m", 1.5),
        ("0", 0.0),
        ("3m", 0.003),
        ("143m", 0.143),
        # metrics-server reports nano- and microcores.
        ("1500000n", 0.0015),
        ("2500u", 0.0025),
        (2, 2.0),
        (0.5, 0.5),
    ],
)
def test_parse_cpu(raw: object, expected: float) -> None:
    result = parse_cpu(raw)  # type: ignore[arg-type]
    assert result is not None
    assert result == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "   ", "not-a-number"])
def test_parse_cpu_returns_none_not_zero(raw: str | None) -> None:
    # A container with no CPU request has reserved nothing, not zero.
    assert parse_cpu(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("512Mi", 512 * 1024**2),
        ("1Gi", 1024**3),
        ("8Gi", 8 * 1024**3),
        ("320Gi", 320 * 1024**3),
        ("64Ki", 64 * 1024),
        ("1M", 10**6),
        ("1G", 10**9),
        ("500k", 500_000),
        ("1048576", 1048576),
    ],
)
def test_parse_memory(raw: str, expected: int) -> None:
    assert parse_memory(raw) == expected


def test_binary_suffix_is_not_confused_with_decimal() -> None:
    # "Mi" must not be read as "M": a 1000x error hiding behind one character.
    assert parse_memory("100Mi") == 100 * 1024**2
    assert parse_memory("100M") == 100 * 10**6
    assert parse_memory("100Mi") != parse_memory("100M")


@pytest.mark.parametrize("raw", [None, "", "   ", "garbage"])
def test_parse_memory_returns_none_not_zero(raw: str | None) -> None:
    assert parse_memory(raw) is None


def test_add_optional_distinguishes_unset_from_zero() -> None:
    # Nothing set anywhere stays unset...
    assert add_optional(None, None) is None
    # ...but one container declaring a limit makes the total meaningful.
    assert add_optional(None, 2.0) == 2.0
    assert add_optional(2.0, None) == 2.0
    assert add_optional(1.5, 2.5) == 4.0
    # An explicit zero is a real value and must survive.
    assert add_optional(0.0, None) == 0.0


def test_format_cpu() -> None:
    assert format_cpu(None) == "—"
    assert format_cpu(0) == "0"
    assert format_cpu(0.003) == "3m"
    assert format_cpu(0.25) == "250m"
    assert format_cpu(2.0) == "2"
    assert format_cpu(46.25) == "46.25"


def test_format_memory() -> None:
    assert format_memory(None) == "—"
    assert format_memory(512 * 1024**2) == "512Mi"
    assert format_memory(1024**3) == "1Gi"
    assert format_memory(int(1.5 * 1024**3)) == "1.5Gi"


def test_bytes_to_gi() -> None:
    assert bytes_to_gi(None) is None
    assert bytes_to_gi(1024**3) == pytest.approx(1.0)


def test_roundtrip_against_real_fixture_values(pods: list[dict]) -> None:
    """Every quantity recorded from the live namespace must parse."""
    seen_cpu = seen_mem = 0
    for pod in pods:
        for container in pod["spec"]["containers"]:
            resources = container.get("resources") or {}
            for block in (resources.get("requests"), resources.get("limits")):
                if not block:
                    continue
                if "cpu" in block:
                    assert parse_cpu(block["cpu"]) is not None, block["cpu"]
                    seen_cpu += 1
                if "memory" in block:
                    assert parse_memory(block["memory"]) is not None, block["memory"]
                    seen_mem += 1
    assert seen_cpu > 0 and seen_mem > 0
