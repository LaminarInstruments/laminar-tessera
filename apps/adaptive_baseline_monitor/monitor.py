"""
Adaptive Baseline Monitor — demonstrates the thing a STATIC threshold
(signals.anomalies()/entropy()) structurally cannot do: tell a legitimate,
gradual drift apart from noise, and catch instability that never produces
an individually-abnormal reading.

Problem: a service's "normal" latency legitimately changes over time (load
grows, a dependency gets slower) without any single reading ever being
abnormal relative to the moment it occurred. A static population mean/std
over the whole history either gets swallowed by the trend (flags nothing,
confirmed below) or, once trained, stays wrong about what "normal" is right
now. Separately: a service flapping between two individually-ordinary
values (20ms / 24ms) never produces an outlier either — the INSTABILITY is
the signal, not any one reading.

Tessera components used:
    baseline (tessera.baseline.AdaptiveBaseline) — the engine's adaptive
                                                     feedback (EMA) + entropy-
                                                     baseline capability,
                                                     never exposed by a door
                                                     before
    signals  (tessera.signals.Signals)            — the static comparison,
                                                     to prove the gap is real

Run:  python3 monitor.py demo
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.baseline import AdaptiveBaseline
from tessera.signals import Signals


def demo():
    import random
    random.seed(42)

    print("=== Scenario 1: gradual, legitimate drift (10ms -> 50ms over 40 readings) ===")
    ramp = [10 + 40 * (i / 39) + random.gauss(0, 1) for i in range(40)]

    sig = Signals()
    sig.measure("latency", ramp)
    flagged = sig.anomalies("latency", threshold=3)
    stats = sig.stats("latency")
    print(f"[static]   anomalies() over the whole ramp -> {flagged} "
          f"(mean={stats['mean']:.1f}, std={stats['std']:.1f})")
    assert flagged == [], "static detector should miss a smooth drift entirely"
    print(f"[static]   that static mean ({stats['mean']:.1f}) is now a BAD estimate "
          f"of current normal ({ramp[-1]:.1f}) — it averages the whole climb.")

    baseline = AdaptiveBaseline("latency-adaptive")
    baseline.set_rate(alpha=0.85, beta=0.15)
    for v in ramp:
        baseline.learn(v)
    print(f"[adaptive] AdaptiveBaseline tracks the climb -> {baseline.value():.1f} "
          f"(close to the actual current level, {ramp[-1]:.1f})")
    assert abs(baseline.value() - ramp[-1]) < abs(stats["mean"] - ramp[-1]), \
        "adaptive baseline should land closer to current reality than the static mean does"

    print()
    print("=== Scenario 2: flapping between two individually-normal values (20ms / 24ms) ===")
    flap = [20, 24, 20, 24, 20, 24, 20, 24, 20, 24]

    sig2 = Signals()
    sig2.measure("flap", flap)
    flagged2 = sig2.anomalies("flap", threshold=3)
    print(f"[static]   anomalies() over the flapping series -> {flagged2} "
          f"(every reading looks individually normal)")
    assert flagged2 == [], "static detector should miss flapping entirely — no single point is extreme"

    b2 = AdaptiveBaseline("flap-adaptive")
    b2.set_rate(alpha=0.5, beta=0.5)
    for v in flap:
        b2.learn(v)
    is_oscillating = b2.oscillating(threshold=0.5)
    print(f"[adaptive] oscillating(threshold=0.5) -> {is_oscillating}")
    assert is_oscillating, "adaptive detector should catch the instability pattern itself"

    print()
    print("OK — both gaps are real, both get closed by the adaptive door, neither")
    print("by the static one. This is the first public door onto that capability.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        print(__doc__)
