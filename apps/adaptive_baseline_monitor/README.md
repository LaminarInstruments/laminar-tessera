# Adaptive Baseline Monitor

## Problem

A static anomaly detector (mean/std over a series' whole history) structurally
cannot do two things: tell a legitimate gradual drift apart from noise, and
catch instability where no single reading is ever individually abnormal.

## Tessera components

| Door | Role |
|---|---|
| `tessera.baseline.AdaptiveBaseline` | first public door onto the engine's adaptive feedback (EMA) and entropy-baseline capability — never exposed before this |
| `tessera.signals.Signals` | the static comparison, to prove the gap is real rather than assumed |

## Sample input / output

```python
from tessera.baseline import AdaptiveBaseline
from tessera.signals import Signals

ramp = [10 + 40*(i/39) for i in range(40)]   # a legitimate climb from 10 to 50

sig = Signals(); sig.measure("latency", ramp)
sig.anomalies("latency", threshold=3)   # [] — misses it entirely
sig.stats("latency")["mean"]            # ~30 — a stale estimate of "now"

b = AdaptiveBaseline("latency")
b.set_rate(alpha=0.85, beta=0.15)
for v in ramp: b.learn(v)
b.value()   # ~44 — tracks the actual current level
```

Run it: `python3 monitor.py demo`
Run the tests: `python3 test_baseline_demo.py`

## What's actually demonstrated, verified not assumed

Both scenarios were run for real before writing any claim about them:
- **Drift**: a smooth 10→50 climb never crosses `anomalies()`'s 3σ threshold
  at any point — the static mean (29.9) ends up averaging the whole climb,
  a bad estimate of what's actually normal *now* (49.0). `AdaptiveBaseline`
  tracks to 43.9 — far closer to current reality.
- **Flapping**: alternating 20/24ms readings never register as outliers
  either (each one is individually unremarkable) — `oscillating()` correctly
  flags the instability pattern itself, which `anomalies()` has no concept of.

## Deployment limitations

- **One instance tracks ONE scalar baseline.** The engine's feedback state
  (alpha/beta/ema) is a single triple, not a dict keyed by series name —
  confirmed by direct probing of the raw engine, not assumed from docs.
  Track multiple things independently by opening multiple named
  `AdaptiveBaseline`s, the same pattern every other door uses.
- **`learning rate` is a real tuning knob, not a free parameter.** Too high
  a `beta` makes the baseline chase noise as if it were real drift; too low
  makes it lag behind a genuine regime change. `oscillating()` is one signal
  that the rate may be miscalibrated for a given series — not a substitute
  for choosing a sensible rate for your actual signal's volatility.
- **`entropy_drift()`/`track_entropy()` inherit the same histogram-spread
  caveat as `signals.entropy()`** (see `COOKBOOK.md` Recipe 5) — "more
  disordered" means spread further across the batch's own value range, not
  a severity score comparable across different kinds of data.
