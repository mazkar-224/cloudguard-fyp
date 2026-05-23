# Anomaly Detection in CloudGuard

This document explains, in plain English, how CloudGuard decides that a day's
AWS spend is "unusual." The logic lives in
`backend/app/services/anomaly_detector.py` — a pure, I/O-free function that
takes a list of daily amounts and returns a verdict.

## The idea in one sentence

> Compare today's spend to how much you *normally* spend, measured in units of
> "how spread out" your spending usually is. If today is far outside the normal
> range, flag it.

That "how many units away from normal" number is the **z-score**, and it's the
heart of the whole system.

---

## The building blocks

### 1. Mean (the baseline)

The **mean** is just the average of the recent days. If over the last two weeks
you spent `$10, $12, $9, $11, ...`, the mean might be about `$10.50`. This is
the "normal" we measure against.

```
mean = (sum of all daily amounts) / (number of days)
```

### 2. Standard deviation (how bumpy is normal?)

Two accounts can both average `$10/day` but behave very differently:

- Account A: `$10, $10, $10, $10` — dead steady.
- Account B: `$2, $18, $5, $15` — same average, wildly bumpy.

**Standard deviation (σ)** measures that bumpiness — the typical distance of a
day from the mean. Account A has a tiny σ; Account B has a large σ. A `$25` day
is shocking for A but unremarkable for B. Standard deviation is what lets us
judge "unusual" *relative to each account's own normal volatility*.

```
variance = average of (each day − mean)²
std (σ)  = square root of variance
```

> CloudGuard uses the **population** standard deviation (divide by N), because
> we are describing the window of days we actually have, not sampling from a
> larger unknown set.

### 3. Z-score (the verdict number)

The **z-score** answers: *how many standard deviations above the mean is today?*

```
z = (today's amount − mean) / σ
```

- `z = 0` → exactly average.
- `z = 1` → one σ above normal (mildly high).
- `z = 3` → three σ above normal (very unusual).

Because it's expressed in units of σ, the same `z = 3` means "equally surprising"
for both the steady account and the bumpy one. That's the elegance of it.

---

## The 2-sigma rule (why 2?)

CloudGuard flags a day when **z ≥ 2.0**. Why 2?

If spending followed a perfect bell curve (normal distribution), then about
**95% of normal days fall within 2σ of the mean** — so a day beyond 2σ sits in
the unusual ~5% tail. That makes 2σ a sensible, widely-used cutoff for "this is
worth a look."

Two honest caveats:

- Real cloud spend is **not** a perfect bell curve, so treat 2σ as a practical,
  tunable heuristic — not a law of nature.
- The threshold is a parameter (`threshold=2.0`), so it can be tightened or
  loosened without touching the logic.

---

## Two guards against false alarms

A raw z-score alone produces noisy, useless alerts. CloudGuard adds two guards:

### Dollar floor (`dollar_floor = $1.00`)

A jump from `$0.01` to `$0.05` is a 5× increase and a huge z-score — but it's
five cents. Nobody cares. The dollar floor ignores any spike whose amount is
below `$1`, killing this class of statistically-real-but-meaningless noise.

### Minimum history (≥ 7 prior days)

With only two or three days of data, the mean and σ are unreliable — the
"cold-start" problem. CloudGuard refuses to judge a day unless it has at least
**7 prior days** in the baseline window. Before that, it reports "insufficient
history" instead of guessing.

There's also a third implicit guard: if the baseline has **zero variance**
(every prior day identical, σ = 0), the z-score is mathematically undefined
(division by zero), so CloudGuard reports "zero variance" rather than crashing.

### The window

The baseline is the **most recent 14 days before the candidate day**
(`window = prior_days[-14:]`). Recent enough to reflect current behavior, long
enough to be statistically stable.

---

## Severity bands

When a day is flagged, its z-score also sets a severity, so the worst spikes
stand out:

| Severity | Z-score range | Meaning |
|----------|---------------|---------|
| **low**    | 2.0 ≤ z < 3.0 | Unusual, worth a glance |
| **medium** | 3.0 ≤ z < 4.0 | Clearly abnormal |
| **high**   | z ≥ 4.0       | Major spike, act now |

---

## Worked example

Baseline of 14 days averaging **$80/day** with σ ≈ **$2**. Today: **$900**.

```
z = (900 − 80) / 2 = 410
```

`z = 410` is astronomically above the threshold, the amount clears the $1 floor,
and there are 14 ≥ 7 days of history — so CloudGuard raises a **high**-severity
alert. (This is exactly what `scripts/inject_spike.py` sets up for the live demo.)

---

## Limitations (a frank list)

No detector is perfect. Being honest about the weaknesses is part of the design:

1. **Assumes roughly normal, stationary data.** The 2σ rule's "95%" intuition
   only holds for bell-curve-shaped data. Cloud spend is often skewed (a long
   tail of expensive days), which can make the threshold fire too often or too
   rarely.
2. **No concept of trend.** If your spend is steadily *growing* (a scaling
   startup), each new high day looks anomalous even though it's expected. The
   model has no notion of "normal upward drift."
3. **No concept of seasonality.** Many workloads spike every Monday, or at
   month-end batch jobs. A flat 14-day mean treats those predictable peaks as
   anomalies.
4. **Cold-start.** Needs ≥ 7 days of history before it says anything, so brand
   new accounts/services get no protection initially.
5. **Sensitive to window size.** 14 days is a judgement call. Too short → jumpy
   baseline; too long → slow to adapt to legitimate changes.
6. **Single-point detection.** It only evaluates the most recent day in the
   window; a missed sync means intermediate anomalous days are never flagged.

---

## Possible improvements

Natural next steps (and good Phase 5+ extensions):

- **EWMA (exponentially weighted moving average).** Weight recent days more
  heavily so the baseline adapts faster and handles gentle trends.
- **Seasonal baselines.** Compare each day against the same weekday/period
  history (e.g. "this Monday vs. previous Mondays") to stop punishing
  predictable peaks.
- **Per-service learned thresholds.** Some services are naturally bursty; learn
  a separate sensitivity per service instead of one global 2σ rule.
- **Robust statistics.** Use median + MAD (median absolute deviation) instead of
  mean + σ, so a single huge outlier doesn't inflate the baseline and mask the
  next spike.
- **ML approaches.** An unsupervised model such as **Isolation Forest** can
  learn multi-dimensional "normal" (amount, service, day-of-week together) and
  flag outliers without an explicit z-score rule.

---

## Live demo

See `backend/scripts/inject_spike.py`. The 5-line defense demo:

```bash
# (backend running + venv active)
python scripts/inject_spike.py            # 1. inject a $900 spike on yesterday
curl -X POST localhost:8000/api/v1/admin/sync   # 2. "Sync now" → detection runs
open http://localhost:5173/alerts         # 3. high-severity alert + email appear
python scripts/inject_spike.py --undo     # 4. clean up afterwards
# 5. (talk track) "z = (900 − 80)/2 ≈ 410, far beyond the 2σ threshold → high severity"
```
