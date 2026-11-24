# Incident Response Coordinator

The "everything together" flagship: all seven Tessera doors, coordinating
on ONE shared Space, each door's output feeding the next door's decision —
not seven doors touched in isolation side by side.

## Problem statement

A small service fleet (`api`, `auth`, `cache`, `db`, `payments`) is
monitored round over round. Two kinds of real incident are scripted into
the simulated metrics:

- a **transient spike** — `db` has one bad round, then recovers on its own
- a **chronic drift** — `payments` creeps upward every round (a slow leak)

Catching these is two genuinely different jobs: a one-round spike is
exactly what `signals`' static population check is good at, and exactly
what it can no longer see once the elevated level has been sustained long
enough to become "normal" to it — which is exactly what `baseline`'s
adaptive, drift-following tracker is for instead (see
`apps/adaptive_baseline_monitor` for the first demonstration of that
division of labor; this app is a second, independent one, now wired into
a full response pipeline).

## Components used, and how they actually depend on each other

| Door | Role | Feeds into |
|---|---|---|
| `graph` | service dependency topology | `blast_radius()` sets incident **priority** |
| `signals` | per-service latency measurement | flags a **transient** spike |
| `baseline` | the SAME latency, tracked **separately, per service** via `BaselineSet` | flags a **chronic** drift `signals` cannot |
| `agents` | `fork()`s a mitigation decision in isolation | only `commit()`'d if the workflow below actually recovers the service |
| `workflow` (standalone, per incident) | `page_oncall → apply_mitigation → verify_recovery → close_incident`, crash-safe | reads the on-call roster (`store`) and the decided action (`agents`) |
| `store` | on-call roster, hard latency caps, open-incident tracker | durable config + coordination state read by every other step |
| `replay` | every decision/step logged | `reconstruct()` rebuilds the full incident timeline from events alone |

## Run it

```bash
python3 coordinator.py run /tmp/ops-demo 16
python3 test_coordinator.py
python3 crash_test.py
```

## Sample output (seed=7, 16 rounds — this is real output, not illustrative)

```
4 incident(s) handled:
  db        transient P1 -> restart    recovered=True
  api       transient P1 -> restart    recovered=True
  payments  chronic   P1 -> scale_up   recovered=True
  cache     transient P1 -> restart    recovered=True
```

Only `db` (round 6) and `payments` are *scripted* incidents. `api` and
`cache` are genuine, unscripted statistical false positives from ordinary
jitter at a 2.5-sigma threshold over a small sample — left in deliberately
rather than tuned away, because a realistic anomaly detector has a real
false-positive rate, and the coordinator handles those identically to the
scripted ones. That's part of the point: the pipeline doesn't need to know
*why* something was flagged to respond to it correctly.

## Two things found while building this one

(A third, the hand-rolled `{service: AdaptiveBaseline.open(...)}` dict this
app originally needed just to track five services' latency independently,
is what motivated adding `tessera.baseline.BaselineSet` — this app now uses
that instead; see `_open_baselines()`.)

1. **`signals.anomalies()` is a population check over the WHOLE series, not
   a sliding window.** A first draft checked "is anything in the flagged
   list" each round — which fires every round forever after one real spike,
   not once. The fix: track the flagged-list LENGTH and only fire when it
   *increases* — "a NEW index just got flagged," not "an old one is still
   there." (Still subject to `anomalies()`'s documented one-reading
   latency: it fires the round *after* the actual spike, not the same
   round.)
2. **`agents.commit()`'s staleness check used to need `force=True` inside a
   `Space`.** Every door in a Space shares one engine, so the ORIGINAL
   generation counter (the engine's whole op count) advanced from the
   workflow's own `signals.measure()`/`replay.append()` calls between
   `fork()` and `commit()` — not from some other, unrelated writer — making
   a perfectly fresh commit look stale. That finding is what motivated
   fixing `commit()` itself: it now tracks a per-field generation (bumped
   only by writes to `agents`' own unit), so this app no longer needs
   `force=True` at all. Real staleness (an actual conflicting write to
   `agents` itself) is still caught exactly as before.

## Failure-recovery proof

`crash_test.py` sends a real `SIGKILL` mid-`apply_mitigation` (after the
real external effect — a mitigation-log write — but before the step
checkpoints), using the exact same `os.kill`/marker-file pattern as
`crash_recoverable_order_processor`. Verified: the step before the kill
(`page_oncall`) stays checkpointed, `apply_mitigation` does not, the
open-incident record (saved before the workflow started) survives, and
resuming completes all four steps without re-applying the real effect a
second time (an idempotency check on the mitigation log, not a
double-apply gotcha — that demonstration already belongs to
`crash_recoverable_order_processor`).

## Deployment limitations

- Single-process, single-writer — same caveat as every other Tessera app;
  no multi-writer coordination is provided.
- The anomaly thresholds, drift rate, and hard caps are tuned for a
  readable 16-round demo, not calibrated against real production latency
  distributions.
- `apply_mitigation`'s "restart" / "scale_up" actions are logged, not
  executed against anything real — same simulated-external-effect pattern
  as `crash_recoverable_order_processor`'s `charge()`.
