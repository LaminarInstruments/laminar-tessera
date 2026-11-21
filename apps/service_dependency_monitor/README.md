# Service Dependency / Anomaly Monitor

## Problem

An operations team needs to know two things when a service misbehaves:
"is this latency reading actually abnormal for this service," and "what else
breaks if this service is the problem."

## Tessera components

| Door | Role |
|---|---|
| `tessera.graph.Graph` | service dependency edges, blast-radius lookup (`reach()`) |
| `tessera.signals.Signals` | per-service latency stream, baseline stats, anomaly detection |

## Sample input / output

```python
mon = ServiceMonitor("prod-cluster", persistence="/tmp/demo")
mon.depends_on("api", "db")
mon.record_latency("db", [15, 16, 14, 15, 17, 15])   # normal history

result = mon.check("db", [15, 16, 300, 310, 14])
# result["anomalous"] -> True
# result["anomaly_indices_in_new_batch"] -> [2, 3]   (the 300, 310 readings)

mon.blast_radius("db")
# {'db': 0, 'api': 1, ...}  — everything reachable from db, and how many hops away
```

Run it: `python3 monitor.py demo`
Run the tests: `python3 test_monitor.py`

## Two real bugs found while building this, both fixed in the code

**1. Checking anomalies against a self-contaminated baseline silently hides
large outliers.** The first version of `check()` called `measure()` (append
the new readings) and *then* `anomalies()` over the whole series. Verified
failure: two 300ms/310ms readings against a ~15ms baseline (std ≈ 0.9) did
**not** get flagged, because appending them first pushed the series' own std
to ≈112 — the outliers inflated the very yardstick being used to judge them,
and ended up well inside 2.5 std of the new, outlier-skewed mean. Fixed by
freezing `stats()` as the baseline *before* appending, and comparing the new
batch against that frozen baseline by hand. `test_baseline_is_not_contaminated_...`
is a regression test for exactly this.

**2. The universal load-vs-construct trap** (see
`crash_recoverable_order_processor/README.md` for the full writeup) applies
here too — `Graph(name, persistence=dir)` and `Signals(name, persistence=dir)`
constructed fresh (instead of `.load()`) silently discard prior saved state
on the next `.save()`. `ServiceMonitor` always goes through
`_load_or_create_graph`/`_load_or_create_signals`, which check whether the
file already exists before deciding whether to construct or load.
`test_fresh_reconstruction_across_separate_processes_preserves_history` proves
this with two genuinely separate OS processes, not an in-process simulation.

## Deployment limitations

- `anomalies()`/`stats()` are generic statistics against a service's own
  recorded history — not a root-cause diagnosis, and not reliable with very
  few samples (a brand-new service with 0–1 prior readings has no usable
  baseline; `check()` correctly skips flagging in that case rather than
  guessing).
- `graph.connect()` is **undirected**. `depends_on("api", "db")` and
  `depends_on("db", "api")` are the same edge — this models "related to," not
  strict upstream/downstream causality. `blast_radius()`/`reach()` returns
  everything *connected*, which over-reports true downstream impact in a
  graph with cycles or shared dependencies (see the demo: `reach("db")`
  includes services that depend on `db` as well as services `db` happens to
  share a neighbor with).
- Single-writer, single-machine, same as every other app in this kit — two
  processes calling `.save()` on the same monitor concurrently will race.
