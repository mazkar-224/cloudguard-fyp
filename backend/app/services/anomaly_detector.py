"""
Anomaly detection for CloudGuard — pure, I/O-free, fully testable.

Core idea
---------
We look at how much a service normally costs (the mean), measure how
spread out those costs are (the standard deviation, σ), then ask: how
many standard deviations above normal is today's spend?  That number
is the z-score.

    z = (today − mean) / σ

The 2-sigma rule: if cloud spend followed a perfect bell curve, roughly
95% of normal days fall within 2σ of the mean, so a day beyond 2σ is in
the unusual ~5%.  We use z ≥ 2.0 as the default threshold.

Real cloud spend is NOT a perfect bell curve, so treat 2σ as a sensible,
tunable heuristic — not a law of nature.

Two guards against false alarms
--------------------------------
- Dollar floor: ignore spikes under $1.  A jump from $0.01 → $0.05 is
  technically 5×, but not worth an alert.
- Minimum history: require at least 7 prior days before judging anything.
  Without enough history the mean and σ are unreliable (cold-start problem).

No database, no network, no side effects — just numbers in, decision out.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class AnomalyResult:
    """
    The verdict returned by detect_anomalies().

    Attributes
    ----------
    is_anomaly:     True if all three conditions are met (z-score, dollar floor,
                    sufficient history).
    z_score:        How many standard deviations today's spend sits above the
                    baseline mean.  Negative means below average.
    today_amount:   The candidate day's spend in USD.
    baseline_mean:  Average daily spend over the trailing window (USD).
    baseline_std:   Population standard deviation of the trailing window (USD).
    severity:       'low' (z ∈ [2,3)), 'medium' (z ∈ [3,4)), 'high' (z ≥ 4),
                    or None when is_anomaly is False.
    reason:         Short human-readable explanation of the decision.
    """

    is_anomaly: bool
    z_score: float
    today_amount: float
    baseline_mean: float
    baseline_std: float
    severity: Optional[str]
    reason: str


def detect_anomalies(
    daily_totals: list[dict],
    threshold: float = 2.0,
    dollar_floor: float = 1.0,
) -> AnomalyResult:
    """
    Decide whether the most recent day in *daily_totals* is anomalous.

    Parameters
    ----------
    daily_totals : list of dicts
        Each dict must have ``date`` (str, YYYY-MM-DD) and ``amount_usd``
        (float/Decimal).  Must be sorted oldest → newest.  The last entry
        is the candidate day being evaluated; all prior entries form the
        baseline window.
    threshold : float
        Minimum z-score to flag an anomaly.  Default 2.0 (the 2-sigma rule).
    dollar_floor : float
        Minimum absolute spend (USD) to consider worth alerting on.
        Prevents noise from micro-cent fluctuations.

    Returns
    -------
    AnomalyResult
        See the dataclass docstring for field descriptions.
    """
    if not daily_totals:
        return AnomalyResult(
            is_anomaly=False,
            z_score=0.0,
            today_amount=0.0,
            baseline_mean=0.0,
            baseline_std=0.0,
            severity=None,
            reason="no data provided",
        )

    candidate = daily_totals[-1]
    today_amount = float(candidate["amount_usd"])

    # Build baseline: up to 14 days immediately before the candidate.
    prior_days = daily_totals[:-1]
    window = prior_days[-14:]

    if len(window) < 7:
        return AnomalyResult(
            is_anomaly=False,
            z_score=0.0,
            today_amount=today_amount,
            baseline_mean=0.0,
            baseline_std=0.0,
            severity=None,
            reason="insufficient history — need at least 7 prior days",
        )

    amounts = [float(d["amount_usd"]) for d in window]
    mean = sum(amounts) / len(amounts)

    # Population standard deviation (we are describing the window, not sampling).
    variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
    std = math.sqrt(variance)

    if std == 0.0:
        return AnomalyResult(
            is_anomaly=False,
            z_score=0.0,
            today_amount=today_amount,
            baseline_mean=round(mean, 4),
            baseline_std=0.0,
            severity=None,
            reason="zero variance in baseline — z-score undefined",
        )

    z_score = (today_amount - mean) / std

    if z_score < threshold:
        return AnomalyResult(
            is_anomaly=False,
            z_score=round(z_score, 4),
            today_amount=today_amount,
            baseline_mean=round(mean, 4),
            baseline_std=round(std, 4),
            severity=None,
            reason=f"z-score {z_score:.2f} is below threshold {threshold}",
        )

    if today_amount < dollar_floor:
        return AnomalyResult(
            is_anomaly=False,
            z_score=round(z_score, 4),
            today_amount=today_amount,
            baseline_mean=round(mean, 4),
            baseline_std=round(std, 4),
            severity=None,
            reason=f"spike is under the ${dollar_floor:.2f} dollar floor",
        )

    # All three conditions met — determine severity from z-score bands.
    if z_score >= 4.0:
        severity = "high"
    elif z_score >= 3.0:
        severity = "medium"
    else:
        severity = "low"

    return AnomalyResult(
        is_anomaly=True,
        z_score=round(z_score, 4),
        today_amount=today_amount,
        baseline_mean=round(mean, 4),
        baseline_std=round(std, 4),
        severity=severity,
        reason=(
            f"${today_amount:.2f} is {z_score:.1f}σ above the "
            f"{len(window)}-day mean of ${mean:.2f}"
        ),
    )
