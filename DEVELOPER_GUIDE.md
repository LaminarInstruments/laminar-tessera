# Building with Tessera

Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com

Tessera is one small engine for the things software has to *remember*: state,
relationships, measurements, decisions, durable steps, and an audit trail.
One install, no server, works offline, same result every run.

**You never touch the engine internals.** You pick a *door* for the job you're
doing and call plain methods. That's the whole API.

Every example below is copy-and-run correct and is checked by the package
self-test (`python -m tessera.selftest`).

---

## Install

It's a proprietary package, source-protected, but it IS published to PyPI —
`pip install laminar-tessera` works and pulls the right wheel for your
platform automatically. Or install a specific wheel file directly:

```bash
python3 --version   # check first — there's more than one wheel now
pip install laminar_tessera-0.1.2-cp313-cp313-macosx_10_13_universal2.whl  # Python 3.13, macOS
# or:
pip install laminar_tessera-0.1.2-cp311-cp311-macosx_26_0_arm64.whl       # Python 3.11, macOS arm64
# or:
pip install laminar_tessera-0.1.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl  # Python 3.12, Linux x86-64
```

Zero third-party dependencies. The *source* supports Python 3.9+, but **each
prebuilt wheel only installs on the exact CPython version/platform in its
filename** (verified: the `cp313` wheel fails outright on 3.11 with `"is not
a supported wheel on this platform"`). The `cp311` macOS wheel and the
`cp312` manylinux2014 Linux wheel were each produced by rebuilding from
`src/`, proving the rebuild path works for more than one platform — the
Linux wheel was verified inside an actual manylinux_2_28 container (self-test,
all four `apps/` suites, and the real `SIGKILL` crash-recovery harness all
pass there). For any other Python version or OS, rebuild from `src/` per the
README's REBUILD section, or ship a wheel per target via `cibuildwheel`.

```python
import tessera
tessera.engine_info()   # {'engine': ..., 'opcodes': 121, 'deterministic': True, ...}
```

---

## Read this before anything else: the load-vs-construct trap

**Every door silently destroyed previously saved state if you constructed it
fresh instead of calling `.load()`, with no error.** Verified for all six
doors: `Store(persistence=d, name=n)` after a prior save, followed by any
write and a `.save()`, overwrote the old file's contents entirely — not
merged, not appended, gone. This included `replay`, whose whole purpose is
durable history.

**Fixed in this release: every door now has `.open()`.** Use it on any
restart path instead of the plain constructor:

```python
from tessera.store import Store

store = Store.open(name="inventory", persistence="local")   # loads if it
                                                               # exists, creates
                                                               # fresh otherwise
```

`.open()` exists on `Store`, `Graph`, `Signals`, `Field`, `Workflow`,
`EventLog`, and `Space` — same name, same safe behavior everywhere. There's
also `.create(name, persistence)`, which raises `FileExistsError` instead of
silently resuming, for the cases where accidentally resuming old state would
itself be a bug (e.g. provisioning a brand-new entity). The plain
constructor is unchanged (still starts fresh unconditionally) for backward
compatibility — prefer `.open()` for anything that might run more than once
against the same persisted name. See `COOKBOOK.md` Part 2.0 for the full
writeup, including what `.open()` does under the hood.

## The mental model

**One engine, seven doors. Open the door that matches your job. Mix them freely —
it's the same engine underneath, so they compose.**

| Your job | Door | Import |
|---|---|---|
| Remember & decide | agents | `from tessera.agents import Field, Program` |
| Keep data safe | store | `from tessera.store import Store` |
| Track connections | graph | `from tessera.graph import Graph` |
| Watch the numbers | signals | `from tessera.signals import Signals` |
| Finish multi-step jobs | workflow | `from tessera.workflow import Workflow` |
| Prove what happened | replay | `from tessera.replay import EventLog` |
| Learn what normal looks like, let it move | baseline | `from tessera.baseline import AdaptiveBaseline` |
| **All of the above on one shared state** | **space** | `from tessera.space import Space` |

---

## 1. agents — remember & decide

```python
from tessera.agents import Field, Program

agent = Field("warehouse", persistence="local")   # persisted under ~/.tessera
agent.observe({"stock": 120, "demand": 145})        # record what you see

branch = agent.fork()                               # explore a choice safely
branch.run(Program("restock"), quantity=100)        # ...on an isolated copy
agent.commit(branch)                                 # keep that choice

agent.save()
reloaded = Field.load("warehouse", persistence="local")
reloaded.state()      # {'stock': 120, 'demand': 145, 'quantity': 100}
reloaded.history()    # [{'kind':'observe',...}, {'kind':'run',...}]  (ordered)
```

### `Program` — how `run` works (important for AI agents)

There are **no built-in program names**. `Program(name)` takes a name you choose,
in one of three forms:

| Form | Behavior |
|---|---|
| `Program("restock")` (no body) | Records the run as an event **and folds the keyword args into the field's state**. So `run(Program("restock"), quantity=100)` sets `state["quantity"] = 100`. |
| `Program("restock", fn=func)` | Runs `func(field, **kwargs)` — your own Python. |
| `Program("restock", steps=[(op, kwargs), ...])` | Runs an explicit sequence of engine operations. |

**Contract:** `state()` returns a `dict` of the field's current key→value
descriptors. After the no-body example above, `state()["quantity"] == 100`.
`fork()` returns an isolated `Field` (a deep copy); changes on it do not touch
the original until `commit(branch)`.

## 2. store — keep it safe (atomic transactions)

```python
from tessera.store import Store

s = Store(persistence="local", name="inventory")
s.put("widgets", 120)

try:
    with s.transaction():            # all-or-nothing
        s.put("widgets", 80)
        raise RuntimeError("simulated failure")
except RuntimeError:
    pass

assert s.get("widgets") == 120       # the failed block rolled back
s.save()
```

**Contract:** `transaction()` is a context manager. On a clean exit it commits;
**on any exception it rolls the whole block back and re-raises** (it never
swallows your exception — catch it yourself, as above). `get(key, default=None)`
returns the stored value or the default.

## 3. graph — track connections

```python
from tessera.graph import Graph

g = Graph()
g.connect("order", "payment").connect("payment", "ledger")
g.degree("payment")          # 2
g.path("order", "ledger")    # ['order', 'payment', 'ledger']  (shortest, or None)
g.rank()                      # nodes by degree, most-connected first
g.reach("order")              # {node: hops_from 'order'}
```

**Contract:** edges are **undirected**. `path` returns the shortest node list or
`None`. `centrality()` returns `{node: fraction_of_other_nodes_connected}`.
`connect(a, b)` **raises `ValueError`** if `a == b` (self-loop) or either side is
`None` — these are rejected loudly, not silently dropped.

## 4. signals — watch the numbers

```python
from tessera.signals import Signals

sig = Signals()
sig.measure("hr", [72, 75, 71, 80, 69, 77])   # APPENDS to the "hr" series
sig.stats("hr")                      # {'n':6, 'mean':74.0, 'std':3.7}
sig.anomalies("hr", threshold=3)     # indices whose value is >3 std from the mean
escalate, entropy = sig.gate([70, 250, 71], threshold=1.0)
```

**Contracts:**
- `measure(series, values)` **appends** to the series (it does not replace).
- `stats` returns `{'n', 'mean', 'std'}` where **`std` is the *population*
  standard deviation** (`statistics.pstdev`).
- `anomalies(series, threshold=3)` returns the **indices** `i` where
  `abs(value[i] - mean) / population_std > threshold` — the threshold is in
  **standard deviations**.
- `gate(values, threshold)` returns a `(escalate: bool, entropy: float)` tuple;
  `escalate` is `True` when `entropy > threshold`.
- `entropy(values)` is the **Shannon entropy, in bits, of the series after it is
  placed into an 8-bin equal-width histogram**. It ranges from `0` (every value
  falls in one bin) to `3` bits (values spread evenly across all 8 bins).
  Because it is computed over that histogram, "disorder" here means *spread
  across the value range* — it is not the same as statistical variance. Feed it
  the raw series; the binning is done for you.

## 5. workflow — finish the job (resumes after a crash)

```python
from tessera.workflow import Workflow

def reserve(ctx): return {"held": ctx["qty"]}
def charge(ctx):  return {"paid": True}
def ship(ctx):    return {"tracking": "XZ-1"}

def build(wf):
    wf.add("reserve", reserve)
    wf.add("charge", charge)
    wf.add("ship", ship)
    return wf

wf = build(Workflow.open("checkout", persistence="local"))
wf.run({"qty": 3})
# If the process dies after charge() was durably recorded, a fresh process
# must re-register every step by name BEFORE calling run() again — including
# the ones already completed, which are safely skipped, not re-run:
resumed = build(Workflow.open("checkout", persistence="local"))
resumed.run({"qty": 3})   # resumes AT ship()
```

**`Workflow.load(name, persistence=...).run(ctx)` with no steps re-registered
used to silently fail — it's now a loud, catchable error.** `.load()`/`.open()`
restore checkpoint data but not the Python step functions themselves (those
were never serializable to begin with). Previously, a one-liner
`Workflow.load(...).run(...)` with nothing added first *looked* like it
worked (no exception, a normal-looking `ctx` came back) while silently
skipping every step that hadn't already completed. **Fixed:** `run()` now
raises `MissingWorkflowStepsError` (a `ValueError` subclass) naming exactly
which step(s) are outstanding and unregistered, instead of returning early.
Always re-register every step, by the same names, on every process that
might resume a workflow — not just the first one; `MissingWorkflowStepsError`
is your signal if you forget.

**Recovery contract (read this carefully):**
- A step is marked complete and checkpointed **after it returns**, and the state
  is saved to disk at that moment.
- **Completed, durably-checkpointed steps are not re-executed on recovery.** That
  guarantees exactly-once *internal state transitions*.
- It does **not** automatically guarantee exactly-once *external side effects*. If
  a step performs an external action (charging a card, sending an email) and the
  process crashes **after** the external action but **before** the checkpoint is
  written, the step will run again on restart. For external effects, use an
  **idempotency key** so the downstream system de-duplicates the repeat.

**Context contract:** each step's return dict is stored **under the step's name**,
and on resume those prior results are restored into `ctx`. So `reserve()`'s result
is available as `ctx["reserve"]` (i.e. `ctx["reserve"]["held"]`) — not as
`ctx["held"]`.

## 6. replay — prove what happened (event sourcing)

```python
from tessera.replay import EventLog

log = EventLog(persistence="local", name="account")
log.append({"type": "deposit",  "amount": 100})
log.append({"type": "withdraw", "amount": 30})

def balance(acc, e):
    acc = acc or 0
    return acc + e["amount"] if e["type"] == "deposit" else acc - e["amount"]

log.reconstruct(balance, initial=0)   # 70 — derived from the events, auditable
```

**Contract:** `append` is write-only and durable (atomic write on each append
when persisted). `reconstruct(reducer, initial)` folds `reducer(state, event)`
over every event in order and returns the final state; the state is *derived*
from the log, never stored directly — that is what makes it auditable.

---

## 7. baseline — learn what normal looks like, and let it move

```python
from tessera.baseline import AdaptiveBaseline

b = AdaptiveBaseline.open("server-1-latency", persistence="local")
b.set_rate(alpha=0.85, beta=0.15)   # higher beta = adapts faster, noisier
for reading in [12, 13, 11, 14, 40, 41, 39, 42]:   # a real regime shift partway through
    b.learn(reading)

b.value()              # the current learned baseline — tracks the shift, not a stale average
b.convergence_rate()   # how much it's still moving; near 0 once it's settled
b.oscillating()        # True if recent updates are flapping, not settling
b.save()
```

**Why this door exists, not just `signals`:** `signals.anomalies()` compares a
new reading to a static mean/std over a series' *entire* history. Verified
(not assumed) that this structurally misses two real cases: a smooth,
legitimate drift (e.g. latency climbing 10ms→50ms over weeks) never crosses
a 3σ threshold at any single point, and the static mean ends up averaging
the whole climb — a stale estimate of "normal now." Separately, a series
flapping between two individually-ordinary values never registers as an
outlier either, because no single reading is extreme; the *instability* is
the signal, and a static mean/std has no way to see it. `AdaptiveBaseline`
closes both gaps — see `apps/adaptive_baseline_monitor/` for the full
side-by-side proof, run for real, not asserted.

**Contract:** one `AdaptiveBaseline` instance tracks ONE scalar baseline —
the engine's underlying feedback state (alpha/beta/ema) is a single triple,
not a dict keyed by series name (confirmed by direct probing of the raw
engine). Open a separate named instance per thing you want to track
independently, the same pattern every other door uses.
`entropy_drift()`/`track_entropy()` wrap the engine's entropy-baseline
opcodes and inherit the same histogram-spread caveat as `signals.entropy()`
(Cookbook Recipe 5) — "more disordered" means spread further across a
batch's own value range, not a severity score comparable across different
kinds of data.

---

## 8. space — all seven doors on ONE shared state

This is Tessera's core proposition. Instead of wiring seven systems together,
open one `Space`; every door operates on the **same** engine and state. One
`save()` persists all of it; one `load()` brings it all back.

```python
from tessera.space import Space

space = Space("warehouse", persistence="local")
space.signals.measure("stock", [120, 95, 60])
space.graph.connect("warehouse", "supplier")
space.store.put("reorder_point", 100)
space.agents.observe({"stock": 60})
space.replay.append({"event": "shortage"})
space.save()                                     # ALL of it, one file

space = Space.load("warehouse", persistence="local")
space.store.get("reorder_point")                 # 100 — everything restored
```

A full worked example (shortage detection → supplier lookup → fork two purchase
options → pick one → durable PO → auditable history → crash-and-reload) ships as:

```bash
python -m tessera.examples.warehouse
```

**Note on shared state:** inside a `Space`, numeric fields passed to
`agents.observe({...})` are also recorded as measurement series under the same
key name — so `agents.observe({"stock": 60})` and `signals.measure("stock", ...)`
write to the same `"stock"` series. That is the point of one shared state; just
be aware the namespaces are shared across doors.

---

## What you can rely on (the guarantees)

- **Deterministic** — same inputs, same outputs, every run.
- **Offline** — no server, no cloud, nothing phones home.
- **Durable** — `save()` is an atomic write (temp file + fsync + atomic rename);
  it does not protect against a lying storage controller (a hardware property).
- **Transactional** — `store.transaction()` is all-or-nothing on internal state.
- **Zero dependencies** — one package, nothing else to install.

## Persistence, in one line

- `persistence="local"` → saved under `~/.tessera`
- `persistence="/some/dir"` → saved there
- `persistence=None` (default) → in-memory only (nothing written; `save()` raises)

## Errors you may see

- `ValueError` — calling `save()` on an in-memory object (no persistence set).
- `FileNotFoundError` — `load()` when no saved file exists yet.
- Your own exceptions inside a `store.transaction()` roll the block back and
  propagate (by design).

---

That's the entire surface. No opcodes, no engine, no config files. Pick a door,
call the methods, ship.

Patent(s) pending · Laminar Instruments · Created by Darreck L. Bender II, Founder.
darreck@laminarinstruments.com · laminarinstruments.com
Free to use, including commercially, until your revenue scales — see LICENSE.txt.
