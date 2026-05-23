"""
Unit tests for the anomaly detection algorithm.

Each test feeds in a fully-controlled series of daily totals so the
expected outcome is deterministic and the math is easy to verify by hand.
No database, no network, no fixtures needed.
"""

from datetime import date, timedelta

from app.services.anomaly_detector import detect_anomalies


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_series(amounts: list[float], base_date: date | None = None) -> list[dict]:
    """Build a daily_totals list from a plain list of amounts."""
    if base_date is None:
        base_date = date(2026, 5, 1)
    return [
        {"date": str(base_date + timedelta(days=i)), "amount_usd": amt}
        for i, amt in enumerate(amounts)
    ]


# ── Test 1: real spike — should fire ─────────────────────────────────────────

def test_spike_detected():
    """
    14 baseline days alternating $0.90/$1.10 (mean=1.0, std=0.1),
    followed by $20 today.  z = (20 - 1) / 0.1 = 190 → high severity.
    """
    # 14 baseline days: alternating $0.90 / $1.10  →  mean=1.0, std=0.1
    baseline = [0.90, 1.10] * 7
    series = _make_series(baseline + [20.0])  # 15 entries, last is candidate

    result = detect_anomalies(series, threshold=2.0, dollar_floor=1.0)

    assert result.is_anomaly is True
    assert result.z_score > 2.0
    assert result.severity == "high"
    assert result.today_amount == 20.0
    assert "σ above" in result.reason


# ── Test 2: normal day — should not fire ──────────────────────────────────────

def test_normal_day_not_flagged():
    """
    14 days of ~$5/day with small variance, today $5.20.
    mean=5.0, std≈0.236  →  z≈0.85 — well below the 2.0 threshold.
    """
    # mean=5.0, std≈0.236  →  z for $5.20 ≈ 0.85 — well below threshold
    baseline = [4.5, 5.0, 5.5, 5.0, 4.8, 5.2, 5.0, 4.9, 5.1, 5.0, 4.7, 5.3, 5.0, 5.0]
    series = _make_series(baseline + [5.20])

    result = detect_anomalies(series, threshold=2.0, dollar_floor=1.0)

    assert result.is_anomaly is False
    assert result.z_score < 2.0
    assert result.severity is None
    assert "below threshold" in result.reason


# ── Test 3: zero variance — std is 0, z-score undefined ──────────────────────

def test_zero_variance_not_flagged():
    """
    14 days of exactly $5.00 — std is 0.
    We cannot divide by zero, so we must return not-anomaly gracefully.
    """
    series = _make_series([5.0] * 14 + [10.0])

    result = detect_anomalies(series)

    assert result.is_anomaly is False
    assert result.z_score == 0.0
    assert result.baseline_std == 0.0
    assert "zero variance" in result.reason


# ── Test 4: too-short series — insufficient history ───────────────────────────

def test_insufficient_history():
    """
    Only 5 days of data (4 prior + 1 candidate).
    The algorithm requires at least 7 prior days — must return not-anomaly.
    """
    series = _make_series([1.0, 2.0, 1.5, 1.0, 50.0])  # massive spike but not enough history

    result = detect_anomalies(series)

    assert result.is_anomaly is False
    assert result.severity is None
    assert "insufficient history" in result.reason


# ── Extra edge cases ──────────────────────────────────────────────────────────

def test_empty_list_no_crash():
    """Empty input must return a clean not-anomaly, not raise IndexError."""
    result = detect_anomalies([])

    assert result.is_anomaly is False
    assert result.reason == "no data provided"


def test_dollar_floor_suppresses_micro_spike():
    """
    A statistically extreme spike that is still under $1 should be suppressed.
    Baseline: 14 days alternating $0.01/$0.02 (mean=0.015, std=0.005),
    today $0.50 — z≈97, way above threshold, but $0.50 < $1.00 floor.
    """
    baseline = [0.01, 0.02] * 7  # mean=0.015, std=0.005
    series = _make_series(baseline + [0.50])

    result = detect_anomalies(series, threshold=2.0, dollar_floor=1.0)

    assert result.is_anomaly is False
    assert "dollar floor" in result.reason


def test_severity_bands():
    """Verify the three severity bands: low (z≥2), medium (z≥3), high (z≥4)."""
    # Build a series where we can control the exact z-score by choosing today's amount.
    # 14 days alternating $0.90/$1.10 → mean=1.0, std=0.1
    baseline = [0.90, 1.10] * 7

    # z=2.5 → low
    r_low = detect_anomalies(_make_series(baseline + [1.25]))
    assert r_low.severity == "low"

    # z=3.5 → medium
    r_med = detect_anomalies(_make_series(baseline + [1.35]))
    assert r_med.severity == "medium"

    # z=4.5 → high
    r_high = detect_anomalies(_make_series(baseline + [1.45]))
    assert r_high.severity == "high"
