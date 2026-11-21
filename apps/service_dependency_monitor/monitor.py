"""
Service Dependency / Anomaly Monitor — tracks which services depend on which,
watches their latency, flags a service that's behaving abnormally for ITS
OWN history, and reports the blast radius (what's downstream of it).

Tessera components used:
    graph   (tessera.graph.Graph)     — service dependency edges, blast radius
    signals (tessera.signals.Signals) — per-service latency stream + anomaly
                                         detection against that service's own
                                         history (NOT entropy — see note below)

Run the demo:        python3 monitor.py demo
Run the test suite:  python3 test_monitor.py

Note on what this does NOT claim: `anomalies()`/`stats().std` are generic
statistical detectors against a service's own recorded history. A service
with no prior history, or very few samples, will not reliably flag anything.
This is operational triage, not a root-cause diagnosis.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.graph import Graph
from tessera.signals import Signals

ANOMALY_STD_THRESHOLD = 2.5


def _load_or_create_graph(name, persist_dir):
    """See crash_recoverable_order_processor/README.md: constructing a door
    fresh instead of loading it silently discards any previously saved state
    the next time you save. This is the safe pattern for every door."""
    path = Path(persist_dir) / f"{name}.graph.json"
    if path.exists():
        return Graph.load(name, persistence=persist_dir)
    return Graph(persistence=persist_dir, name=name)


def _load_or_create_signals(name, persist_dir):
    path = Path(persist_dir) / f"{name}.signals.json"
    if path.exists():
        return Signals.load(name, persistence=persist_dir)
    return Signals(persistence=persist_dir, name=name)


class ServiceMonitor:
    def __init__(self, name, persistence):
        self.name = name
        self.persistence = persistence
        self.graph = _load_or_create_graph(name, persistence)
        self.signals = _load_or_create_signals(name, persistence)

    def depends_on(self, service, dependency):
        self.graph.connect(service, dependency)
        return self

    def record_latency(self, service, samples_ms):
        self.signals.measure(f"latency:{service}", samples_ms)
        return self

    def check(self, service, latest_samples_ms):
        """Check the latest readings against this service's EXISTING
        baseline, then record them.

        Deliberately NOT "measure() then anomalies() over the whole series":
        verified that ordering lets the new outliers inflate the very std
        they're being judged against — two badly-degraded readings (300ms,
        310ms against a ~15ms/1std baseline) pushed the combined std from
        ~1ms to ~112ms, which then swallowed both outliers as "within
        threshold." Freezing the baseline BEFORE appending avoids that
        self-contamination."""
        series = f"latency:{service}"
        try:
            baseline = self.signals.stats(series)
        except ValueError:
            # no prior measurements for this service at all — nothing to
            # compare against yet, so we can't evaluate (not "assume normal").
            baseline = {"n": 0, "mean": 0.0, "std": 0.0}
        flagged = []
        if baseline.get("n", 0) >= 2 and baseline["std"] > 0:
            for i, v in enumerate(latest_samples_ms):
                z = abs(v - baseline["mean"]) / baseline["std"]
                if z > ANOMALY_STD_THRESHOLD:
                    flagged.append(i)
        self.signals.measure(series, latest_samples_ms)
        stats_after = self.signals.stats(series)
        return {"service": service, "baseline": baseline, "stats": stats_after,
                "anomalous": len(flagged) > 0, "anomaly_indices_in_new_batch": flagged}

    def blast_radius(self, service):
        """What's reachable downstream of `service` in the dependency graph,
        and how many hops away. Undirected graph, so this is "connected to",
        not strictly "downstream of" — see README limitations."""
        return self.graph.reach(service)

    def save(self):
        self.graph.save()
        self.signals.save()
        return self


def demo():
    import shutil
    tmp = "/tmp/tessera_service_monitor_demo"
    shutil.rmtree(tmp, ignore_errors=True)   # demo() must be repeatable, not accumulate across runs

    print("=== Build the dependency graph ===")
    mon = ServiceMonitor("prod-cluster", persistence=tmp)
    mon.depends_on("api", "cache").depends_on("api", "db").depends_on("worker", "queue").depends_on("queue", "db")
    print("api blast radius:", mon.blast_radius("api"))

    print("\n=== Feed normal latency history for every service ===")
    normal = {
        "api": [40, 42, 39, 41, 40, 43],
        "cache": [2, 3, 2, 2, 3, 2],
        "db": [15, 16, 14, 15, 17, 15],
        "worker": [20, 21, 19, 20, 22, 20],
        "queue": [5, 6, 5, 4, 5, 6],
    }
    for svc, samples in normal.items():
        mon.record_latency(svc, samples)

    print("\n=== A new reading comes in for 'db' — and it's badly degraded ===")
    result = mon.check("db", [15, 16, 300, 310, 14])   # two badly degraded readings
    print("db baseline (before):", {k: round(v, 1) for k, v in result["baseline"].items()},
          "-> anomalous =", result["anomalous"], "at new-batch indices", result["anomaly_indices_in_new_batch"])
    assert result["anomalous"], "300ms/310ms readings against a ~15ms, ~1ms-std baseline must flag"

    print("\n=== Who is downstream of 'db'? (blast radius) ===")
    affected = mon.blast_radius("db")
    print("reach from db:", affected)
    assert "api" in affected and "worker" in affected and "queue" in affected

    db_count_before_save = mon.signals.stats("latency:db")["n"]
    mon.save()
    print("\n=== Reload in a fresh process-equivalent object (correct load-or-create path) ===")
    mon2 = ServiceMonitor("prod-cluster", persistence=tmp)   # same name+dir -> loads, doesn't reset
    assert mon2.blast_radius("db") == affected
    assert mon2.signals.stats("latency:db")["n"] == db_count_before_save, "history should survive the reload exactly"
    print(f"OK — graph and latency history (n={db_count_before_save} for db) both survived the reload intact.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        print(__doc__)
