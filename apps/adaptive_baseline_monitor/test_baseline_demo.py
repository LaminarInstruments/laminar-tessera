"""
Correctness + persistence tests for the adaptive baseline monitor.

Run:  python3 test_baseline_demo.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.baseline import AdaptiveBaseline


def test_demo_runs_and_asserts_pass():
    import monitor
    monitor.demo()
    print("[PASS] demo() proves both gaps are real and both close")


def test_scoped_per_name_not_shared_globally():
    """The engine's feedback state is a single scalar, not keyed by series —
    confirmed by direct probing before this door was built. Two different
    AdaptiveBaseline names must NOT share a learned value."""
    d = "/tmp/baseline_scope_test"
    shutil.rmtree(d, ignore_errors=True)
    a = AdaptiveBaseline.open("series-a", persistence=d)
    b = AdaptiveBaseline.open("series-b", persistence=d)
    a.set_rate(alpha=0.5, beta=0.5)
    a.learn(100)
    b.set_rate(alpha=0.5, beta=0.5)
    b.learn(0)
    assert a.value() != b.value(), "two independently-named baselines must not share state"
    assert a.value() == 50.25   # 0.5*0.5 + 0.5*100
    assert b.value() == 0.25    # 0.5*0.5 + 0.5*0
    shutil.rmtree(d, ignore_errors=True)
    print("[PASS] two independently-named baselines stay independent")


def test_survives_restart_via_open():
    d = "/tmp/baseline_restart_test"
    shutil.rmtree(d, ignore_errors=True)
    a = AdaptiveBaseline.open("svc", persistence=d)
    a.set_rate(alpha=0.9, beta=0.1)
    for v in [10, 11, 9, 10, 12]:
        a.learn(v)
    a.save()
    before = a.value()

    # genuinely separate object, same load-or-create pattern every other
    # door uses — must resume, not silently reset to the 0.5 default
    resumed = AdaptiveBaseline.open("svc", persistence=d)
    assert resumed.value() == before, "AdaptiveBaseline.open() must resume, not reset"
    resumed.learn(13)
    resumed.save()
    assert resumed.value() != before   # it kept learning from where it left off
    shutil.rmtree(d, ignore_errors=True)
    print("[PASS] AdaptiveBaseline.open() correctly resumes across a restart")


def test_entropy_drift_sign_matches_documented_meaning():
    b = AdaptiveBaseline("ent-test")
    flat = [10, 10, 10, 11]
    spread = [5, 20, 40, 60, 80, 100, 120, 140]
    assert b.track_entropy(flat) is True        # first call always "drops" — no prior baseline
    assert b.baseline_entropy() is not None
    drift_up = b.entropy_drift(spread)
    assert drift_up > 0, "a more evenly-spread series must read as positive drift vs a flat baseline"
    assert b.track_entropy(spread) is False, "entropy went UP relative to the flat baseline, so this must NOT count as a drop"
    print("[PASS] entropy_drift()/track_entropy() signs match their documented meaning")


if __name__ == "__main__":
    test_scoped_per_name_not_shared_globally()
    test_survives_restart_via_open()
    test_entropy_drift_sign_matches_documented_meaning()
    test_demo_runs_and_asserts_pass()
    print("\nALL TESTS PASSED")
