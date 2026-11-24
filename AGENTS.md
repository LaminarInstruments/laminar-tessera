# AGENTS.md — Tessera for AI coding agents

Tessera — created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com · patent(s) pending.
Hit a real bug (not a "capability not listed here")? File it:
https://github.com/LaminarInstruments/laminar-tessera/issues

You are integrating **Tessera**, a zero-dependency, offline, deterministic SDK.
Build against the **public API only**. Do not import or inspect `tessera._engine`
(a compiled binary) or invent methods. If a capability is not listed here, it
does not exist — ask or choose a different door.

## Install & verify
It's a proprietary package, but it IS on PyPI — the simplest path:
```bash
pip install laminar-tessera
python -m tessera.selftest        # must print "ALL SEVEN DOORS REAL"
```
Or install a specific wheel file directly. **Three wheels ship; never glob
them together (`*.whl`) — pick the one matching `python3 --version` and OS:**
```bash
python3 --version
pip install laminar_tessera-0.1.6-cp313-cp313-macosx_10_13_universal2.whl   # Python 3.13, any Mac
# or:
pip install laminar_tessera-0.1.6-cp311-cp311-macosx_26_0_arm64.whl        # Python 3.11, Apple Silicon only
# or:
pip install laminar_tessera-0.1.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl  # Python 3.12, Linux x86-64
```
Each wheel is built for exactly the CPython version/platform in its
filename — verified to fail outright on any other with "not a supported
wheel on this platform". If `pip install` fails, check `python3 --version`
and which wheel you targeted before assuming anything else is wrong. None of
the three wheels cover Windows, Intel Mac, or other Python versions — rebuild
from `src/` (README's REBUILD section) for those.

## Choosing a door
| Task | Import | Primary methods |
|---|---|---|
| agent memory + decisions | `from tessera.agents import Field, Program` | `observe(dict)`, `fork()`, `run(Program, **kw)`, `commit(branch)`, `save()`, `Field.open/load/create(name, persistence)`, `state()`, `history()` |
| durable key/value | `from tessera.store import Store` | `put(k, v)`, `get(k, default=None)`, `delete(k)`, `keys()`, `items()`, `transaction()`, `save()`, `Store.open/load/create(name, persistence)` |
| relationships | `from tessera.graph import Graph` | `connect(a, b)`, `disconnect(a, b)`, `neighbors(n)`, `degree(n)`, `path(a, b)`, `centrality()`, `rank()`, `reach(n)`, `clusters()`, `Graph.open/load/create(...)` |
| measurements | `from tessera.signals import Signals` | `measure(series, values)`, `stats(series)`, `correlate(a, b)`, `anomalies(series, threshold=3)`, `entropy(values)`, `gate(values, threshold)`, `Signals.open/load/create(...)` |
| durable multi-step jobs | `from tessera.workflow import Workflow` | `@wf.step`, `add(name, fn)`, `run(ctx=None)`, `completed()`, `reset()`, `Workflow.open/load/create(name, persistence)` |
| event log / audit | `from tessera.replay import EventLog` | `append(event)`, `events()`, `reconstruct(reducer, initial)`, `EventLog.open/load/create(name, persistence)` |
| adaptive/drifting thresholds | `from tessera.baseline import AdaptiveBaseline` | `set_rate(alpha,beta)`, `learn(value)`, `value()`, `convergence_rate()`, `oscillating()`, `track_entropy(values)`, `entropy_drift(values)`, `AdaptiveBaseline.open/load/create(name, persistence)` |
| all doors, one shared state | `from tessera.space import Space` | `.agents .store .graph .signals .workflow .replay .baseline`, `save()`, `Space.open/load/create(name, persistence)` |

## The single most important rule: use `.open()`, not the plain constructor, on any restart path

**Always generate `Door.open(name, persistence)` for any code path that might
run more than once against the same persisted name — never the plain
constructor.** Before this fix existed, every door silently destroyed
previously saved state if constructed fresh (not via `.load()`) when a save
already existed, with no exception raised. `.open()` is now the built-in,
correct fix: it loads if a save exists, and creates fresh otherwise.

```python
store = Store.open(name="inventory", persistence="local")
```

`.open()` exists identically on `Store`, `Graph`, `Signals`, `Field`,
`Workflow`, `EventLog`, and `Space`. There's also `.create(name, persistence)`,
which raises `FileExistsError` instead of silently resuming — use it when
resuming old state would itself be a bug (e.g. provisioning a brand-new
entity that must not collide with an existing one of the same name). The
plain constructor is unchanged (always starts fresh) for backward
compatibility — do not generate it for a restart-safe path.

For `workflow` specifically, `.open()` only solves half the problem: it
still does not restore the Python step functions (never serializable). You
must still re-add every step, by name, after `.open()`/`.load()` — see the
workflow contract below. If you forget, `run()` now raises
`MissingWorkflowStepsError` instead of silently skipping the work.

## Hard contracts (do not guess these)
- **Persistence:** `persistence="local"` → `~/.tessera`; `persistence="/dir"` → there;
  `persistence=None` (default) → in-memory, and `save()` raises `ValueError`;
  `persistence=""` raises `ValueError` (it used to silently resolve to the cwd).
  Two writers saving the same `(name, persistence)` concurrently can raise
  `tessera.ConcurrentWriteError` — there is no multi-writer coordination; treat
  any persisted name as single-writer. `save()` into a directory that doesn't
  exist raises plain `FileNotFoundError` (create the directory first) —
  distinct from `ConcurrentWriteError`, which means a writer collision, not a
  missing path. **`Door.load(name, persistence, path=...)` binds further
  saves to the actual `path` passed** — on every door (`Store`, `Graph`,
  `Signals`, `Workflow`, `AdaptiveBaseline`, `Space`, plus `Field` and
  `EventLog` already fixed before) — previously an explicit `path` was used
  only to read, then silently dropped, so a subsequent `save()` went to the
  default name-derived filename instead.
- **agents:** `Program(name)` has **no built-in names**. With no body it records the
  run and folds `**kwargs` into state (`run(Program("x"), q=100)` ⇒ `state()["q"]==100`).
  A `steps=[(opcode, kwargs), ...]` Program preflights every opcode name before
  running any of them (an unknown opcode now raises `ValueError` with nothing
  executed, not partway through); its per-operation results are logged into
  the run event's payload under `"results"` (check this if a step like
  `RESTORE_CHECKPOINT` can fail — its boolean return isn't raised as an error
  on its own). `fork()` is an isolated deep copy; it affects the original only
  after `commit(branch)`, which now **raises `ValueError`** if `branch` wasn't
  forked from this same field (a different Space/Field) or if this field
  changed since the fork (stale commit would otherwise silently discard
  whatever happened in between) — pass `force=True` for a deliberate
  whole-world replacement anyway. The staleness check only applies between a
  branch and the EXACT object it was directly `fork()`'d from — committing a
  fork-of-a-fork (`field.fork().fork()`) straight onto the original `field`
  skips the generation check (falling back to just the lineage check) rather
  than falsely rejecting it as stale; for full staleness protection at every
  hop, commit in chain order (leaf → intermediate → root) instead of
  skip-level. `observe()` validates every field BEFORE writing any of them (a
  conversion failure, e.g. an int too big for `float()`, used to leave
  earlier fields in this same call written with no log entry); it also
  rejects two keys that collide once stringified (`observe({3:..., "3":...})`,
  including a collision nested inside a value, not just at the top level),
  and raises `ValueError` for a numeric value with `abs(value) > 1e15` —
  `observe()` feeds the exact same shared measurement series
  `signals.stats()` reads, so this mirrors `Signals.measure()`'s own
  magnitude check (previously `observe()` bypassed it entirely, silently
  poisoning that series through a different door). `state()`/`history()`
  return deep copies — mutating what they return, or a dict you already
  passed to `observe()`, can no longer change stored state. An `fn=`-form
  `Program`'s **return value is discarded** — `fn` must call
  `field.observe(...)` itself to record anything; a non-`None` return
  triggers a `UserWarning`. **Upgrading from a pre-0.1.6 save**: `Field`
  migrates its old, un-namespaced descriptor data into the new namespaced
  unit automatically and transparently on first load — no action needed,
  but note it (previously this silently returned an empty `state()`).
- **store:** `transaction()` commits on clean exit, **rolls back and re-raises on any
  exception**. It never swallows exceptions — wrap in try/except if you expect one.
  Use `async with store.transaction():` (not `with`) for a block spanning
  `await` points — it serializes concurrent transactions on the same Store via
  a shared lock so two tasks' transactions can't interleave on the engine's
  shared state, and is reentrant for the SAME task (a nested `async with` from
  within another on the same task does not deadlock). **Mixing `with` and
  `async with` on the same Store now raises `RuntimeError`** instead of
  silently proceeding unguarded if the other flavor currently has a
  transaction open — the two are not mutually exclusive by default (the sync
  path never touches the async lock), so this makes misuse loud; use one
  flavor consistently for a Store also accessed from async code. `save()`
  **raises `RuntimeError`** while a transaction is still open on this Store
  (previously it wrote the in-progress, uncommitted values straight to disk).
  `put(key, value)` stringifies `key` internally — `put(1, ...)` and
  `put("1", ...)` **raise `ValueError`** on the second call instead of
  silently colliding; `delete()` enforces the same type match (`delete(1)`
  after `put("1", ...)` now raises instead of silently removing the wrong
  entry). `value` is deep-copied on `put()`/`get()`/`items()` — neither side
  can mutate the other's view. `value` is fully validated for persistence
  before being stored: `put()` raises `TypeError` for a dict key that isn't a
  valid JSON key type (e.g. a tuple) or for a value that isn't
  JSON-serializable at all (e.g. a raw `set`) — previously these were
  accepted silently and only failed later, with a raw internals error, at
  `save()` time. Tuples anywhere inside `value` are normalized to lists
  immediately at `put()` (not only after a reload — JSON has no tuple type).
  A dict `value` with two keys that collide once stringified (e.g.
  `{1: 'a', '1': 'b'}`) raises `ValueError` at `put()` instead of silently
  losing one on the next save. NaN/Inf anywhere inside `value` — including
  nested in a dict, which the shared dispatch sanitizer does not reach — is
  sanitized to `0.0` (previously a dict-nested NaN survived and could reach
  `save()` as a literal, nonstandard JSON token).
- **graph:** nodes **must be `str`** — `connect()` AND `disconnect()` raise `ValueError` for
  anything else (an int node round-trips fine in memory but loses its
  identity on save/reload, since JSON object keys are always strings; a tuple
  node gets silently converted to a list by the shared dispatch sanitizer and
  the edge is dropped with no signal at all). `path()`/`reach()` return `None`
  for an endpoint that was never `connect()`'d (previously an unregistered
  `path(x, x)` returned a trivial one-node "path" before any membership
  check). Equal-cost route selection is now a deterministic, documented
  tie-break (neighbors visited in `sorted(key=str)` order) — stable across
  processes and reloads, not dependent on Python's per-process hash seed.
- **signals:** `measure` **appends**; `series` **must be a `str`** (an int/str
  series pair that stringify the same silently merged on the next
  save/reload otherwise) and raises `ValueError` for any reading with
  `abs(value) > 1e15` (previously silently sanitized to `0.0` — a real,
  accepted finite number quietly zeroed with no error; this cap is scoped to
  `signals` specifically now, not every door's numbers — `store`/`agents`
  preserve any finite float exactly). `stats.std` is **population** std
  (`pstdev`). `anomalies`/`gate`'s `threshold` must be finite (and
  `anomalies`' nonnegative) — both **raise `ValueError`** otherwise (a NaN
  threshold previously got silently sanitized to `0.0`, which flagged nearly
  everything as anomalous with no indication the call was invalid).
  `stats()`/`anomalies()`/`correlate()` on a series with **no prior
  `measure()` call raise `ValueError`** (previously returned a fabricated
  `{'n':1,'mean':0.0,'std':0.0}`-shaped result). `correlate()` on series of
  different lengths raises `ValueError`; on a **constant series (zero
  variance)** it returns **`None`**, not `0.0` — `None` means undefined, not
  "no correlation." Internally anchored (and rescaled) before computing
  mean/std/covariance, so a huge common offset or a tiny common scale no
  longer loses precision or underflows the result — this does not change any
  value's meaning, only its numerical accuracy. `entropy()`'s 8-bin
  histogram no longer raises `ZeroDivisionError` for a very small value span,
  and no longer splits several EQUAL extreme-magnitude readings across
  different bins (both were overflow/underflow edge cases in the binning
  math, not anything about the entropy formula itself).
- **workflow:** completed+checkpointed steps are **not re-run** on recovery
  (exactly-once *internal* state). External side effects are **not** exactly-once —
  a crash after an external action but before the checkpoint re-runs the step; use an
  **idempotency key** for external effects. Each step's return dict is stored under the
  **step name** in `ctx` (`ctx["reserve"]["held"]`, not `ctx["held"]` — this now
  includes steps that returned `None`, stored as `None`, not omitted), and a
  completed step's RESTORED result always **overrides** any conflicting field
  the caller passed into `run(ctx)` — a resume reflects what actually
  happened, not whatever the caller's `ctx` claims this time. Step results are
  deep-copied going in and out — mutating a returned `ctx[name]` can no
  longer corrupt the stored result. `add(name, fn)` requires `name` to be a
  `str` (an int step name round-trips through persisted completion as a
  string, so it silently re-ran on resume) and `fn` to be callable and
  **not** an `async def` (its body would never actually run — nothing awaits
  it; this is checked again on the RETURNED value too, so a sync wrapper that
  returns a coroutine is also rejected, at `run()` time, before the step is
  marked done). `add()` also **raises `ValueError`** if called while `run()`
  is already executing on this object (registration is frozen during a run,
  so a step's own callback can no longer register new work that escapes the
  persisted manifest) and if two steps share a name on one object (previously
  both ran; only the last result was visible). A resumed object's
  not-yet-completed steps must be re-added in the **same relative order**
  they were first registered in — `run()` raises `ValueError` otherwise
  (previously steps silently executed out of their originally defined
  sequence). `run()` raises `RuntimeError` if called reentrantly (e.g. a
  step's own callback calling `run()` again on the same object — this used
  to let the in-flight step's effects run twice). A step's return value gets
  the SAME persistence validation `store.put()`'s `value` does: `run()`
  raises `TypeError`/`ValueError` and marks nothing done for a value that
  isn't JSON-serializable, a dict key of an invalid JSON type, or a dict key
  collision once stringified (previously a tuple result silently became a
  list, and a colliding dict key silently collapsed, only after a resume —
  both are now normalized/validated immediately, and a genuinely
  unserializable result is rejected before marking the step done, so a save
  failure can no longer leave memory and disk permanently inconsistent
  within one process).
  **`.open()`/`.load()` alone does NOT resume anything** — they restore which
  steps already completed but not the Python step functions (never
  serializable). ALWAYS generate code that re-adds every step by the same
  name on every code path that might resume a workflow — including steps you
  expect are already done (they're safely skipped, not re-run). If you
  forget, `run()` now raises `MissingWorkflowStepsError` (a `ValueError`
  subclass) naming exactly which step(s) are outstanding and unregistered,
  instead of silently skipping them.
  **Known, documented (not changed) behaviors:** in-place edits to the `ctx`
  dict INSIDE a step body are never durable — only each step's RETURNED
  value is persisted; a later resumed step sees merged return values, not a
  predecessor's direct `ctx` mutations. Resume is **step-name-based**: if you
  re-register a step under the same name with genuinely different logic (a
  changed approval threshold, a different policy version), an already-
  completed step is still skipped and its OLD stored result is reused as-is
  — if your application needs revalidation when the logic behind a step
  changes, version the step name explicitly (e.g. `"approve_v2"`) or add your
  own explicit check inside the step against the current policy/inputs
  before trusting a restored result. The same applies to a resumed workflow
  being re-driven with CHANGED input fields it never re-validates against an
  earlier completed step's result (e.g. an approval keyed to an order's
  contents) — if your step's effect must be bound to specific inputs, check
  that binding yourself inside the step, or use a distinct workflow instance
  per distinct input identity.
- **replay:** `append` is write-only + durable; `reconstruct` derives state by folding
  the reducer over events — never store derived state directly. `append()`
  deep-copies and validates its event is JSON-serializable (including
  rejecting NaN/Infinity, which Python's `json` module would otherwise
  silently write as nonstandard tokens a strict JSON reader can't parse),
  raises `TypeError`/`ValueError` for a dict key of an invalid JSON type or
  a dict key collision once stringified (the same class of bug already
  fixed for `store.put()`), and normalizes any tuple inside the event to a
  list immediately — all BEFORE adding it — a rejected event can no longer
  corrupt the log or block a later valid append. `events()` returns deep copies — mutating a returned
  event can no longer change stored history. `EventLog.load(path=...)` binds
  further `append()`s to the actual path loaded from (previously they went to
  the default name-derived path instead, invisible to anyone still reading
  the file actually passed in). Not cryptographically tamper-evident — a
  hand-edited save file reloads and reconstructs silently with no detection.
- **baseline:** one `AdaptiveBaseline` instance tracks ONE scalar baseline —
  the engine's feedback state (alpha/beta/ema) is a single triple, not keyed
  by series (verified by probing the raw engine, not assumed). Open a
  separate named instance per thing tracked independently. `learn()` does
  **not** auto-save (same as `store`/`signals`/`agents`). `set_rate()` raises
  `ValueError` for a non-finite alpha/beta (previously silently sanitized to
  `0.0` with no error). `nudge(delta)` shifts the baseline by exactly `delta`
  immediately (previously it fed `ema + delta` back through the EMA blend,
  applying only `beta * delta` of the requested shift). `track_entropy()`/
  `entropy_drift()` raise `ValueError` for an empty batch (an empty batch's
  entropy is `0.0`, which previously silently ratcheted the baseline down to
  0 and reported "improvement" even though nothing was observed). Use
  `baseline` instead of `signals.anomalies()` when "normal" legitimately
  drifts over time or when the signal is instability itself (flapping)
  rather than any single extreme reading — both are cases `signals`' static
  mean/std structurally cannot catch (verified in
  `apps/adaptive_baseline_monitor/`, not asserted). `entropy_drift()`/
  `track_entropy()` inherit the same histogram-spread caveat as
  `signals.entropy()` — not a severity score comparable across different
  kinds of data. **Known, documented (not changed) behavior:** a named
  engine checkpoint (`CHECKPOINT_STATE`/`RESTORE_CHECKPOINT` opcodes) is
  in-memory/session-scoped — it does NOT survive `save()`/`load()`, and a
  checkpoint taken inside an open `store.transaction()` is NOT invalidated
  by that transaction's later rollback (checkpoints are independent,
  write-ahead-log-style audit points, not transaction-scoped).

## Determinism
Same inputs ⇒ same outputs, every run. Safe to snapshot/replay. No randomness is
exposed through the public API.

## Safe-usage checklist for generated code
1. Set `persistence` before calling `save()`.
2. Catch exceptions you raise inside `transaction()`.
3. For workflow steps with external effects, pass an idempotency key.
4. Read step results from `ctx["<step_name>"]`.
5. Never import `tessera._engine`; never reference opcodes.
6. After generating, run `python -m tessera.selftest` and your own tests.

## Self-check task (recommended before trusting generated code)
Give an agent only this file + the installed package and ask it to build, using the
public API only (no engine edits, no invented methods): (1) a durable inventory
agent, (2) an offline anomaly monitor, (3) a recoverable multi-step workflow. Pass =
it completes all three and its tests pass.
