"""
Test suite + recovery demonstration for the service dependency monitor.

Run:  python3 test_monitor.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(code):
    return subprocess.run([sys.executable, "-c", code], cwd=HERE,
                           capture_output=True, text=True)


def test_demo_runs_end_to_end():
    r = run("import monitor; monitor.demo()")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK — graph and latency history" in r.stdout
    print("[PASS] demo() builds the graph, detects the degraded db, computes blast radius, and survives a reload")


def test_baseline_is_not_contaminated_by_the_outliers_being_checked():
    """Regression test for the exact bug found while building this app:
    checking anomalies against stats computed AFTER appending the new
    (possibly anomalous) samples lets large outliers inflate their own
    threshold and go undetected."""
    tmp = "/tmp/monitor_test_contamination"
    shutil.rmtree(tmp, ignore_errors=True)
    r = run(f"""
from monitor import ServiceMonitor
mon = ServiceMonitor("x", persistence="{tmp}")
mon.record_latency("svc", [15, 16, 14, 15, 17, 15])
result = mon.check("svc", [300, 310])
assert result["anomalous"], "two 300ms readings against a 15ms/~1std baseline must be flagged"
print("flagged indices:", result["anomaly_indices_in_new_batch"])
""")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "flagged indices: [0, 1]" in r.stdout, r.stdout
    shutil.rmtree(tmp, ignore_errors=True)
    print("[PASS] both injected outliers are correctly flagged against the pre-existing baseline")


def test_fresh_reconstruction_across_separate_processes_preserves_history():
    """Real multi-process proof of the load-vs-construct fix: two genuinely
    separate OS processes, each adding data, using ServiceMonitor's
    load-or-create helpers. Unlike the naive pattern (see
    crash_recoverable_order_processor/README.md), nothing gets silently
    destroyed."""
    tmp = "/tmp/monitor_test_multiproc"
    shutil.rmtree(tmp, ignore_errors=True)

    r1 = run(f"""
from monitor import ServiceMonitor
mon = ServiceMonitor("svc-graph", persistence="{tmp}")
mon.depends_on("web", "db")
mon.record_latency("web", [10, 11, 10])
mon.save()
""")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = run(f"""
from monitor import ServiceMonitor
mon = ServiceMonitor("svc-graph", persistence="{tmp}")   # separate process, same name+dir
mon.depends_on("db", "disk")
mon.record_latency("web", [12, 11])
mon.save()
print(mon.signals.stats("latency:web")["n"], mon.graph.degree("db"))
""")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    n, degree = r2.stdout.strip().split()
    assert n == "5", f"expected all 5 latency samples across both processes, got {n}"
    assert degree == "2", f"expected db connected to both web and disk, got degree {degree}"
    print("[PASS] two separate processes, same ServiceMonitor — no data silently lost between them")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_demo_runs_end_to_end()
    test_baseline_is_not_contaminated_by_the_outliers_being_checked()
    test_fresh_reconstruction_across_separate_processes_preserves_history()
    print("\nALL TESTS PASSED")
