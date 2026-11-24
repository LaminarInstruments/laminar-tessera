# Crash-Recoverable Order Processor

## Problem

A checkout pipeline (reserve stock, charge a card, ship) needs to survive a
real crash mid-process without double-charging the customer or losing track
of what already happened.

## Tessera components

| Door | Role |
|---|---|
| `tessera.workflow.Workflow` | `reserve -> charge -> ship`, resumable after a crash |
| `tessera.replay.EventLog` | durable trail of what happened, for audit |

## Sample input / output

```bash
python3 order_processor.py run /tmp/demo A1 3
# completed steps: ['reserve', 'charge', 'ship']
# ctx: {'qty': 3, 'order_id': 'A1', 'reserve': {'held': 3}, 'charge': {'paid': True}, 'ship': {'tracking': 'XZ-A1'}}
```

## Failure-recovery demonstration — a real `SIGKILL`, not a simulation

`crash_test.py` launches the checkout as a genuine child process, waits until
`charge()`'s external effect (a line appended to `charges.log`, standing in
for an actual payment call) has happened, then sends `SIGKILL` — no
exception handler, no graceful shutdown, exactly like a real crash. Then it
relaunches the same command as the resume.

**Result, reproduced on purpose:** without an idempotency key, `charge()` was
not checkpointed before the kill, so resume re-ran it — a real second
ledger line for the same order. **This is the exact double-charge risk named
in the Cookbook, triggered with an actual process kill, not described in the
abstract.** With the `--idempotent` guard (skip charging if `tessera.idempotent
.IdempotentLedger.seen(order_id)` is already True), the same kill + resume
produces exactly one charge. Meanwhile `reserve` — which *was* checkpointed
before the kill — correctly does not re-run either way.

The guard itself is `tessera.idempotent.IdempotentLedger` — this app
originally hand-rolled it (a linear scan over `charges.log` for a matching
`order_id`), and that hand-rolled version is what motivated promoting it to
its own door. `charges.log` (the plain append-only file `charge()` writes to
on every REAL charge) is unchanged — it's standing in for the external
payment provider's own ledger, not Tessera's; `IdempotentLedger` is only
the guard deciding whether to call that external effect again.

Run it: `python3 crash_test.py`
Run the (non-crash) correctness suite: `python3 test_order_processor.py`

## The most important thing this app surfaced

**Building this app is what surfaced the biggest gap found in this whole
documentation effort: `Workflow(name, persistence=dir)` — the plain
constructor — does NOT resume prior progress. It silently starts a blank
workflow, and the next `.save()`/checkpoint overwrites the old progress file
with the fresh run's (incomplete) state.** Verified directly:

```python
wf = Workflow("job", persistence="d"); wf.add("a", fn); wf.run({})
# completed: ['a']

wf2 = Workflow("job", persistence="d")   # fresh constructor, NOT .load()
wf2.add("a", fn); wf2.run({})             # re-runs "a" — no error, no warning
# completed: ['a']  <- looks identical, but "a" ran TWICE, and the checkpoint
#                      file was overwritten with this second run's record
```

The same trap exists for **every** door that persists, including `replay` —
a fresh `EventLog(persistence=dir, name=...)` followed by `.append()`
**silently destroys previously saved events**, not just skips resuming them.
Verified: two sessions, each appending one event with a fresh (non-`.load()`)
constructor, end with the log containing only the *second* session's event —
the first is gone.

**The only safe pattern, used in `order_processor.py`
(`_load_or_create_workflow`/`_load_or_create_eventlog`):** check whether the
persisted file already exists; if it does, call `.load()`; only construct
fresh if it doesn't. There is no SDK-level guard against getting this wrong —
it is entirely the caller's responsibility, and getting it wrong produces no
exception at all.

## Deployment limitations

- Single-writer, single-machine. No distributed workers, no multi-process
  coordination — two processes resuming the same `order_id` concurrently
  will race.
- `IdempotentLedger` closes the "fine for a demo" gap an earlier,
  hand-rolled linear-scan version of this check had — but a real system
  may still prefer to push the idempotency key to the actual payment
  provider's API instead of (or in addition to) tracking it locally.
- `ship()`'s result isn't similarly guarded — this demo only idempotency-
  protects the step that actually costs money. Guard any other
  side-effecting step the same way if it matters for your use case.
