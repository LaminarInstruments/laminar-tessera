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
pip install laminar_tessera-0.1.3-cp313-cp313-macosx_10_13_universal2.whl   # Python 3.13, any Mac
# or:
pip install laminar_tessera-0.1.3-cp311-cp311-macosx_26_0_arm64.whl        # Python 3.11, Apple Silicon only
# or:
pip install laminar_tessera-0.1.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl  # Python 3.12, Linux x86-64
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
  any persisted name as single-writer.
- **agents:** `Program(name)` has **no built-in names**. With no body it records the
  run and folds `**kwargs` into state (`run(Program("x"), q=100)` ⇒ `state()["q"]==100`).
  `fork()` is an isolated deep copy; it affects the original only after `commit(branch)`.
  An `fn=`-form `Program`'s **return value is discarded** — `fn` must call
  `field.observe(...)` itself to record anything; a non-`None` return now
  triggers a `UserWarning` reminding you of this.
- **store:** `transaction()` commits on clean exit, **rolls back and re-raises on any
  exception**. It never swallows exceptions — wrap in try/except if you expect one.
  `put(key, value)` stringifies `key` internally — `put(1, ...)` and
  `put("1", ...)` now **raise `ValueError`** on the second call instead of
  silently colliding; use one consistent key type per logical key.
- **signals:** `measure` **appends**. `stats.std` is **population** std (`pstdev`).
  `anomalies` threshold is in **standard deviations**. `gate` returns
  `(escalate: bool, entropy: float)`. `entropy` is Shannon entropy (bits, 0–3) of an
  **8-bin histogram** of the series — spread across the value range, not variance.
  `stats()`/`anomalies()`/`correlate()` on a series with **no prior `measure()`
  call now raise `ValueError`** (previously returned a fabricated
  `{'n':1,'mean':0.0,'std':0.0}`-shaped result indistinguishable from real
  data) — always `measure()` before reading. `correlate()` on series of
  different lengths now raises `ValueError` instead of silently using the
  overlapping prefix. `stats()`/`anomalies()` now raise `ArithmeticError`
  (instead of silently returning `None`) if the internal computation
  overflows on extreme-magnitude input.
- **workflow:** completed+checkpointed steps are **not re-run** on recovery
  (exactly-once *internal* state). External side effects are **not** exactly-once —
  a crash after an external action but before the checkpoint re-runs the step; use an
  **idempotency key** for external effects. Each step's return dict is stored under the
  **step name** in `ctx` (`ctx["reserve"]["held"]`, not `ctx["held"]` — this now
  includes steps that returned `None`, stored as `None`, not omitted).
  Registering two steps under the same name on one object now **raises
  `ValueError`** (previously both ran their side effects; only the last
  result was visible).
  **`.open()`/`.load()` alone does NOT resume anything** — they restore which
  steps already completed but not the Python step functions (never
  serializable). ALWAYS generate code that re-adds every step by the same
  name on every code path that might resume a workflow — including steps you
  expect are already done (they're safely skipped, not re-run). If you
  forget, `run()` now raises `MissingWorkflowStepsError` (a `ValueError`
  subclass) naming exactly which step(s) are outstanding and unregistered,
  instead of silently skipping them.
- **replay:** `append` is write-only + durable; `reconstruct` derives state by folding
  the reducer over events — never store derived state directly. Not
  cryptographically tamper-evident — a hand-edited save file reloads and
  reconstructs silently with no detection.
- **baseline:** one `AdaptiveBaseline` instance tracks ONE scalar baseline —
  the engine's feedback state (alpha/beta/ema) is a single triple, not keyed
  by series (verified by probing the raw engine, not assumed). Open a
  separate named instance per thing tracked independently. `learn()` does
  **not** auto-save (same as `store`/`signals`/`agents`). Use it instead of
  `signals.anomalies()` when "normal" legitimately drifts over time or when
  the signal is instability itself (flapping) rather than any single extreme
  reading — both are cases `signals`' static mean/std structurally cannot
  catch (verified in `apps/adaptive_baseline_monitor/`, not asserted).
  `entropy_drift()`/`track_entropy()` inherit the same histogram-spread
  caveat as `signals.entropy()` — not a severity score comparable across
  different kinds of data.

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
