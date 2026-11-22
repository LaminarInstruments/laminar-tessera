# Tessera Cookbook — ship an app the day you install it

Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com

This is the task-shaped doc. `DEVELOPER_GUIDE.md` teaches each door in order;
this one starts from "what are you building" and gets you to working code,
including the gotchas that aren't obvious from a method signature. Every code
block in this document has actually been executed against the installed
package — none of it is illustrative pseudocode.

```bash
pip install laminar-tessera                                # easiest: pulls the right wheel from PyPI
python -m tessera.selftest                                 # must print "ALL SEVEN DOORS REAL"
```

Or install a specific wheel file directly:

```bash
python3 --version                                         # check this FIRST — three wheels ship now
pip install laminar_tessera-0.1.3-cp313-cp313-macosx_10_13_universal2.whl  # Python 3.13, any Mac
# or:
pip install laminar_tessera-0.1.3-cp311-cp311-macosx_26_0_arm64.whl       # Python 3.11, Apple Silicon only
# or:
pip install laminar_tessera-0.1.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl  # Python 3.12, Linux x86-64
```

**Each wheel installs on exactly the Python version/platform in its
filename, nothing else.** Verified: installing the `cp313` wheel under
Python 3.11 fails immediately with `ERROR: ... is not a supported wheel on
this platform` — no partial install, no fallback, just a dead stop. The
`cp311` macOS wheel and the `cp312` manylinux2014 Linux wheel were each
built and verified from source specifically to prove those paths work (see
README's REBUILD section) — they're real, tested (the Linux wheel was
verified inside an actual manylinux_2_28 container: selftest, all four
`apps/` suites, and the real `SIGKILL` crash-recovery harness all pass),
but still only cover what's listed above. If your platform/Python version
isn't one of the three, you need to rebuild before any of the rest of
this document is reachable.

---

## Part 1 — The mental model

Tessera is one deterministic engine (`tessera._engine.spu121.SPU121`, 121 opcodes)
with seven thin Python doors on top of it. "Thin" is literal: every door method
is a few lines that validate input and call one opcode. Nothing is
reimplemented per door, which is why they compose — `agents`, `store`,
`graph`, `signals`, `workflow`, and `replay` can all point at the *same*
engine instance (that's what `Space` is), and a number you record through one
door is visible to the others without any syncing code.

Two properties fall out of this and matter for how you build:

- **Deterministic.** Same constructor + same sequence of calls ⇒ same state,
  every time, on every machine. This is what makes "test by calling it and
  reading the result" a reliable strategy — the behavior you observe today is
  the behavior you'll get in production.
- **Offline, zero dependencies.** No server, no network call, nothing phones
  home. `save()`/`load()` are local files. This also means there is **no
  built-in encryption, access control, or multi-writer coordination** — if you
  need those, you're building them on top, not getting them for free.

---

## Part 2 — The persistence model, fully explained

This is the single most consequential section in this document. Get it wrong
and your application loses data silently, with no exception to catch.

### 2.0 Read this one even if you skip everything else: the load-vs-construct trap

**Fixed in this release: every door now has `.open()`.** Use it on any
restart path and the rest of this section is historical:

```python
from tessera.store import Store

store = Store.open(name="inventory", persistence="local")
# loads existing state if a save exists for (name, persistence); otherwise
# creates fresh. Identical on Store, Graph, Signals, Field, Workflow,
# EventLog, and Space.
```

There's also `.create(name, persistence)`, which raises `FileExistsError`
instead of silently resuming — use it when accidentally resuming old state
would itself be a bug (provisioning a brand-new entity that must not collide
with an existing one of the same name). `.load(name, persistence)` is
unchanged: raises `FileNotFoundError` if nothing was ever saved. The plain
constructor is also unchanged, for backward compatibility — it still always
starts fresh unconditionally, which is exactly the footgun below if you use
it on a restart path instead of `.open()`.

**The bug `.open()` fixes, for the record: every door, with no exception,
used to silently destroy previously saved state if you constructed it fresh
instead of calling `.load()` — no error, no warning, happening on the very
next `.save()`.** This was found while building the flagship applications in
`apps/` and was, concretely, the single biggest risk in this entire SDK for
anyone writing a long-running or restart-safe program. Verified directly,
for every door, using the plain constructor on purpose to show the trap:

```python
from tessera.store import Store
s = Store(persistence="/tmp/demo", name="inv")
s.put("a", 1); s.save()

s2 = Store(persistence="/tmp/demo", name="inv")   # fresh constructor, NOT .load()
s2.put("b", 2); s2.save()

s3 = Store.load("inv", persistence="/tmp/demo")
print(s3.items())   # {'b': 2}  <- 'a' is GONE. Not merged, not orphaned. Destroyed.
```

The same result was verified for `Graph`, `Signals`, `Field` (`agents`),
`Workflow`, and `EventLog` — **including `replay`**, whose entire purpose is
"durable append-only history." A fresh `EventLog(persistence=dir,
name=...).append(...)` does not fail to resume old events — it **overwrites
them with just the new ones** on its very next auto-save.

**Why this mattered more than it looked like it should:** nothing about the
method names suggested it. `Store(persistence="local", name="inv")` reads as
"open my inventory store," the same way `open(path)` does for a file — and
`open()` doesn't truncate an existing file just because you didn't pass a
special flag. The plain constructor silently behaved like `"w"` mode, with
`.load()` the only way to get `"r+"` behavior. Every single one of the three
flagship apps in `apps/` had to build an explicit "does a save already
exist? load it; otherwise construct fresh" helper to avoid this before
`.open()` existed — that helper is, in fact, exactly what `.open()` now does
for you:

```python
from pathlib import Path
from tessera.store import Store

def open_store(name, persist_dir):   # this is what Store.open() now does internally
    path = Path(persist_dir) / f"{name}.store.json"
    if path.exists():
        return Store.load(name, persistence=persist_dir)
    return Store(persistence=persist_dir, name=name)
```

Prefer `Store.open(name, persist_dir)` over hand-rolling this — it's
identical across all eight entry points (`Store`, `Graph`, `Signals`,
`Field`, `Workflow`, `EventLog`, `AdaptiveBaseline`, `Space`), so you don't
need to remember each one's file suffix (`.store.json` / `.graph.json` /
`.signals.json` / `.tessera.json` / `.workflow.json` / `.log.json` /
`.baseline.json` / `.space.json`).

### 2.1 Standalone doors: two behaviors, same-looking calls

| Door | Auto-saves on every write? |
|---|---|
| `replay` (`EventLog.append`) | **Yes** — durable the instant you call it |
| `workflow` (`Workflow.run`) | **Yes** — checkpointed after every step |
| `store`, `graph`, `signals`, `agents`, `baseline` | **No** — you must call `.save()` |

Proven, not assumed:

```python
from tessera.store import Store
s = Store(persistence="local", name="inv")
s.put("widgets", 120)
# process dies here, no .save() call
# -> Store.load("inv", persistence="local") raises FileNotFoundError.
# The file was never created. Nothing was written. Silently.
```

```python
from tessera.replay import EventLog
log = EventLog(persistence="local", name="acct")
log.append({"type": "deposit", "amount": 100})
# process dies here too — but append() already wrote and fsynced the file.
reloaded = EventLog.load("acct", persistence="local")
assert reloaded.events() == [{"type": "deposit", "amount": 100}]   # survives
```

**Rule of thumb for standalone doors:** if it isn't `replay` or `workflow`,
treat every write as in-memory-only until `.save()` runs. Call it after every
meaningful batch of writes — don't wait for program exit.

### 2.2 Inside a `Space`, this changes completely — verified

This is the architectural question worth asking explicitly: when `replay` or
`workflow` are opened *through* a `Space` instead of standalone, do they keep
auto-saving independently, or does `Space` take over?

**Verified: `Space` takes over entirely.** Every door loses its standalone
auto-save behavior and becomes gated behind one `space.save()` call. Proof:

```python
from tessera.space import Space

space = Space("ward", persistence="/tmp/space_persist_test")
space.store.put("alert", {"status": "ok"})
space.replay.append({"event": "checked_in"})      # looks identical to the standalone call above
# process dies here — space.save() was never called
print(space.replay._path)   # None  <- this is WHY: Space binds EventLog with
                             #         no persistence of its own, so append()'s
                             #         internal `if self._path: save()` never fires.
```

Reload in a fresh process: `Space.load("ward", persistence="/tmp/space_persist_test")`
raises `FileNotFoundError` — **the event was never written.** Not partially
written, not written-but-orphaned. Nothing hit disk. The same is true for
`space.workflow` — a completed step inside a `Space` is not checkpointed to
its own file either; it waits for `space.save()` exactly like `store` and
`graph` do.

**What this means in practice:** a `Space` is one atomic unit from a
persistence standpoint. You will never end up with an event in your audit log
describing a state change that itself never got saved — because *nothing* in
a `Space` saves until you explicitly call `space.save()`, including the
audit log itself. That's actually the safer property (no partial commits
across doors) — but it is the opposite of what the standalone-door table
above would lead you to assume, so don't mix the two mental models.

**Rule of thumb inside a `Space`:** exactly one save discipline — call
`space.save()` after every meaningful unit of work, the same way you would
have called `.save()` on a single standalone `store` or `graph`. The fact
that `replay`/`workflow` auto-save when used standalone does **not** carry
over. `Space.open(name, persistence)`/`Space.create(...)` exist too, with
the same load-or-create / fail-if-exists semantics as every other door —
use `Space.open()` on any restart path instead of the plain constructor,
since `Space` is especially exposed to the load-vs-construct trap (a fresh
`Space()` on a restart silently discards *every* door's state at once, not
just one).

### 2.3 Persistence targets, in one line

- `persistence="local"` → saved under `~/.tessera`
- `persistence="/some/dir"` → saved there
- `persistence=None` (the default) → in-memory only; `save()` raises
  `ValueError` (verified: `Store().save()` → `"In-memory Store: construct
  with persistence='local' or save(path=...)."`)
- `persistence=""` raises `ValueError` — it used to silently resolve to the
  current working directory (fixed; previously a real save file would land
  wherever the process happened to be run from, with no warning).
- Two writers `save()`ing the same `(name, persistence)` at the same time can
  raise `tessera.ConcurrentWriteError` instead of an uncaught,
  internals-leaking `FileNotFoundError` (fixed — this does not add
  multi-writer coordination, it just makes the failure clear and catchable;
  treat any persisted name as single-writer regardless).

---

## Part 3 — Recipe map

| You're building | Door(s) | Recipe |
|---|---|---|
| Settings, inventory, config that must survive a crash | `store` | 4 |
| Something that watches a number and flags trouble | `signals` | 5 |
| Something that tracks who's connected to what | `graph` | 6 |
| A job with steps that must not double-run after a crash | `workflow` | 7 |
| An audit trail / "prove what happened" | `replay` | 8 |
| Something that remembers, forks a decision, and commits it | `agents` | 9 |
| Something whose "normal" legitimately drifts over time | `baseline` | 10 |
| All of the above, sharing one piece of state | `space` | 11 |

---

## Recipe 4 — Durable key/value (`store`)

```python
from tessera.store import Store

s = Store.open(persistence="local", name="inventory")   # loads if it exists, creates if not
s.put("widgets", 120)

try:
    with s.transaction():          # all-or-nothing
        s.put("widgets", 80)
        raise RuntimeError("payment failed")   # stand-in for any external failure
except RuntimeError:
    pass                            # transaction already rolled back — widgets is still 120

assert s.get("widgets") == 120
s.save()                            # <-- do not forget this; put()/transaction() do not auto-save
```

**Gotcha:** `transaction()` re-raises whatever you raise inside it — it rolls
back, then lets the exception through. Catch it yourself; it will not be
swallowed for you.

---

## Recipe 5 — Anomaly / health watcher (`signals`)

```python
from tessera.signals import Signals

sig = Signals(persistence="local", name="vitals")
sig.measure("hr:patient-01", [74, 75, 74, 73, 74, 75])
stats = sig.stats("hr:patient-01")          # {'n','mean','std'} — std is population std
bad_indices = sig.anomalies("hr:patient-01", threshold=3)   # std-devs from the mean

sig.save()
```

**Gotcha 1 — `entropy()`/`gate()` do NOT measure "is this patient worse than
normal."** They measure how spread-out a series is across *its own*
min-to-max range, via an 8-bin histogram. A tight, steady series (74,75,74...)
scores differently than a free-floating one not because of danger level, but
because of how many of its own bins it fills. Two patients with different
baselines are **not comparable** by raw entropy value. If you want "is this
abnormal for this specific stream," use `anomalies()`/`stats().std` against
that stream's own history — not `entropy()` as a severity score across
different people or sensors.

**Gotcha 2 — neither `entropy()` nor `anomalies()` is a clinical judgment.**
Both are generic statistical detectors: a histogram-spread computation and a
standard-deviations-from-mean threshold, respectively. `anomalies()` will
flag a value because it's numerically far from the series' own mean — it has
no concept of what's medically dangerous versus what's a normal, benign
outlier for a given condition. If Tessera backs a health product (it does —
this is Laminar Instruments' CQDAM stack), treat `signals` output as an input
to a decision, not the decision itself. Clinical significance requires
separate, domain-specific validation before anything downstream acts on it
unsupervised.

**Gotcha 3 — NaN and infinite values are silently replaced with `0.0`, not
rejected.** Verified:

```python
from tessera.signals import Signals

sig2 = Signals()
sig2.measure("hr", [70, float("nan"), 75, float("inf"), 72])
print(sig2.stats("hr"))
# {'n': 5, 'mean': 43.4, 'std': 35.47...}
# NaN and inf both became 0.0 before the mean/std were computed — no error,
# no warning. A disconnected sensor sending NaN will silently read as "0",
# dragging your mean down, not as a flagged bad reading.
```

If your sensor/data source can produce `NaN`/`inf` (a very common real-world
case — disconnected leads, divide-by-zero upstream), **filter those out
yourself before calling `measure()`.** Tessera will not tell you it happened.

---

## Recipe 6 — Relationship / routing engine (`graph`)

```python
from tessera.graph import Graph

g = Graph(persistence="local", name="ward")
g.connect("patient-01", "watch-01").connect("watch-01", "nurse-amy")
g.neighbors("patient-01")     # ['watch-01']
g.rank()                      # nodes by degree, most-connected first
g.save()
```

**Gotcha:** `connect(a, b)` raises `ValueError` if `a == b`, either side is
`None`, or either side is unhashable (e.g. a list). Catch this at your
data-ingestion boundary if node ids come from user input or external systems
where a duplicate/missing/malformed id is possible — e.g. two different
upstream records that turn out to hash to the same id. (Earlier builds of
this SDK silently dropped all three cases with zero signal — no exception,
no edge, node just never appeared in `neighbors()`/`clusters()`/
`centrality()`. Fixed in this release; if you're on an older wheel, upgrade.)

---

## Recipe 7 — Crash-safe multi-step job (`workflow`)

```python
from tessera.workflow import Workflow

wf = Workflow("checkout", persistence="local")

@wf.step
def reserve(ctx): return {"held": ctx["qty"]}

@wf.step
def charge(ctx):
    # call your payment provider here, passing an idempotency key so a
    # resume-after-crash doesn't charge twice, e.g.:
    #   charge_card(amount=..., idempotency_key=f"checkout-{ctx['order_id']}-charge")
    return {"paid": True}

ctx = wf.run({"qty": 3, "order_id": "A1"})
assert ctx["reserve"]["held"] == 3
```

**Gotcha 1:** Completed steps are **not re-run** on resume (exactly-once
internal state). But if a step performs an **external** action and the
process dies after that action but before the checkpoint writes, the step
**will run again** on restart. Pass an idempotency key to anything external.

**Gotcha 2 — `Workflow.load(...).run(...)` alone does NOT resume your
workflow. This used to fail silently; it now raises instead.** `.load()`
restores which steps already completed, but **not the Python step functions
themselves** (those were never serializable). Earlier builds of this SDK let
you call `.run()` on a freshly-loaded `Workflow` with no steps re-added and
it would return immediately, looking completely normal, having silently run
nothing you hadn't already completed. **Fixed in this release:** `run()` now
tracks which step names this workflow has ever needed and raises
`MissingWorkflowStepsError` if one of them is neither re-registered nor
already done — turning the silent skip into a loud, catchable error. Verified
with a real crash (not just a short write): a step killed by `SIGKILL`
mid-execution, then resumed with the broken pattern, raises; resumed
correctly, it completes.

```python
from tessera.workflow import Workflow, MissingWorkflowStepsError

wf = Workflow("checkout_demo", persistence="/tmp/wf_resume_demo")
wf.add("reserve", lambda ctx: {"held": ctx["qty"]})
wf.add("charge", lambda ctx: {"paid": True})
def ship(ctx):
    raise RuntimeError("simulated crash mid-ship")   # stand-in for a real process kill
wf.add("ship", ship)
try:
    wf.run({"qty": 3})
except RuntimeError:
    pass
assert wf.completed() == ["reserve", "charge"]   # ship never finished

# fresh "process": load with NO steps re-registered, exactly the broken pattern
resumed_wrong = Workflow.load("checkout_demo", persistence="/tmp/wf_resume_demo")
try:
    resumed_wrong.run({"qty": 3})
    raise AssertionError("should have raised")
except MissingWorkflowStepsError as e:
    assert "ship" in str(e)   # names exactly what's missing

# the only correct pattern: re-add EVERY step, by the same names, every time
resumed_right = Workflow.load("checkout_demo", persistence="/tmp/wf_resume_demo")
resumed_right.add("reserve", lambda ctx: {"held": ctx["qty"]})   # already done, safely skipped
resumed_right.add("charge", lambda ctx: {"paid": True})           # already done, safely skipped
resumed_right.add("ship", lambda ctx: {"tracking": "XZ-1"})        # the one that actually runs
result2 = resumed_right.run({"qty": 3})
assert result2["ship"]["tracking"] == "XZ-1"
```

Always re-register every step, by name, on every code path that might load
and resume a workflow — including the ones you believe already completed
(they're safely skipped, not re-run). `MissingWorkflowStepsError` is a
`ValueError` subclass, so existing broad `except ValueError` handlers still
catch it.

**Gotcha 3:** Each step's result lands in `ctx` **under the step's name**:
`ctx["reserve"]["held"]`, not `ctx["held"]`.

**Gotcha 4 — calling `run()` again with different input does not update
completed steps.** Verified:

```python
from tessera.workflow import Workflow

wf2 = Workflow("x", persistence="local")
wf2.add("a", lambda ctx: {"v": ctx.get("qty")})
wf2.run({"qty": 1})            # step "a" completes, records v=1
r2 = wf2.run({"qty": 999})     # re-run with DIFFERENT input
print(r2["a"])                  # {'v': 1}  <- still 1, the 999 was ignored for "a"
```

If you need to retry a workflow with corrected input, `reset()` it first —
`run()` alone will silently keep every already-completed step's original
result no matter what you pass in on the next call.

No `.save()` needed for a **standalone** `Workflow` — `run()` checkpoints to
disk after every step. (Inside a `Space`, see Part 2.2 — this auto-checkpoint
does not apply; `space.save()` is required.)

---

## Recipe 8 — Audit trail (`replay`)

```python
from tessera.replay import EventLog

log = EventLog(persistence="local", name="acct")
log.append({"type": "deposit", "amount": 100})   # durable immediately, no .save() needed

def balance(acc, e):
    acc = acc or 0
    return acc + e["amount"] if e["type"] == "deposit" else acc - e["amount"]

log.reconstruct(balance, initial=0)
```

Never store the derived state directly — always recompute it from
`reconstruct()`. That's what makes it auditable: the log is the only source
of truth, assuming the log itself hasn't been altered (see next section).

### Is the log tamper-evident, or just reconstructable?

These are different guarantees, and it matters which one you're getting.
Verified by inspecting the on-disk format directly and hand-editing it:

```python
import json
from tessera.replay import EventLog

log = EventLog(persistence="/tmp/tamper_demo", name="acct")
log.append({"type": "deposit", "amount": 100})
log.append({"type": "withdraw", "amount": 30})

path = "/tmp/tamper_demo/acct.log.json"
raw = json.load(open(path))
print(raw["cache"]["__eventlog__"])
# [{'type': 'deposit', 'amount': 100}, {'type': 'withdraw', 'amount': 30}]
# plain JSON — no hash, no checksum, no sequence seal of any kind.

raw["cache"]["__eventlog__"][1]["amount"] = 3000   # hand-edit: 30 -> 3000
json.dump(raw, open(path, "w"))

def balance(acc, e):
    acc = acc or 0
    return acc + e["amount"] if e["type"] == "deposit" else acc - e["amount"]

reloaded = EventLog.load(name="acct", persistence="/tmp/tamper_demo")
print(reloaded.reconstruct(balance, 0))   # -2900, computed from the tampered
                                            # value with NO error, NO warning,
                                            # NO detection of any kind.
```

**Plain answer: `replay` is reconstructable and inspectable, not
cryptographically tamper-evident.** There is no hash chaining between
records, no sequence-number seal, no signed digest, and no detection of
edited, reordered, or deleted events. If your application needs a *provable*,
non-repudiable history (compliance audit trail, dispute resolution, anything
where "the log says so" has to hold up against someone with filesystem
access), `replay` alone does not give you that — you'd need to add your own
hash-chaining (e.g. each event carries a hash of the previous event) or an
externally-retained checkpoint/signature on top of it. As shipped, treat
`replay` as "this is what the application believes happened," not as a
forensic-grade ledger.

---

## Recipe 9 — Agent memory + decisions (`agents`)

```python
from tessera.agents import Field, Program

agent = Field("warehouse", persistence="local")
agent.observe({"stock": 120, "demand": 145})

branch = agent.fork()                       # isolated deep copy — live state untouched
branch.run(Program("restock"), quantity=100)
agent.commit(branch)                         # only now does the live field change
agent.save()
```

**Gotcha:** `Program("name")` with no `fn=`/`steps=` isn't a no-op — it
records the run **and folds your kwargs straight into state**:
`run(Program("restock"), quantity=100)` sets `state()["quantity"] = 100`. If
you wanted a pure no-op marker event, you still got a state write.

---

## Recipe 10 — Something whose "normal" legitimately drifts (`baseline`)

```python
from tessera.baseline import AdaptiveBaseline
from tessera.signals import Signals

ramp = [10 + 40 * (i / 39) for i in range(40)]   # a legitimate climb, 10ms -> 50ms

sig = Signals(); sig.measure("latency", ramp)
assert sig.anomalies("latency", threshold=3) == []   # misses the whole thing — verified, not assumed
stale_mean = sig.stats("latency")["mean"]              # ~30 — averages the whole climb

b = AdaptiveBaseline("latency-adaptive")
b.set_rate(alpha=0.85, beta=0.15)
for v in ramp:
    b.learn(v)
assert abs(b.value() - ramp[-1]) < abs(stale_mean - ramp[-1])   # tracks current reality, not the average
```

**Why not just `signals.anomalies()`:** that compares a new reading to a
static mean/std over a series' *entire* history. Proven above: a smooth
10ms→50ms climb never crosses even a 3σ threshold at any point, and the
resulting "normal" (~30ms) is a stale average of the whole climb — wrong
for what's actually normal *now* (~50ms). `AdaptiveBaseline` tracks the
current level instead of the historical average.

**Gotcha — this also catches something `signals` structurally cannot:**
flapping between two individually-ordinary values (verified:
`[20,24,20,24,...]` never trips `anomalies()`, since no single reading is
extreme) is exactly what `oscillating()` is for — it looks at whether
*recent updates* are flapping, not whether any one reading looks odd:

```python
from tessera.baseline import AdaptiveBaseline
from tessera.signals import Signals

flap = [20, 24, 20, 24, 20, 24, 20, 24]
sig2 = Signals(); sig2.measure("flap", flap)
assert sig2.anomalies("flap", threshold=3) == []   # every reading looks normal

b2 = AdaptiveBaseline("flap-adaptive")
b2.set_rate(alpha=0.5, beta=0.5)
for v in flap:
    b2.learn(v)
assert b2.oscillating(threshold=0.5) is True   # the instability pattern itself is the signal
```

**Contract:** one instance tracks ONE scalar baseline — the engine's
feedback state (alpha/beta/ema) is a single triple, not keyed by series
name (verified by probing the raw engine directly, not assumed). Open a
separate named `AdaptiveBaseline` per thing you track independently, same
as every other door. `entropy_drift()`/`track_entropy()` wrap the engine's
entropy-baseline opcodes and inherit the exact same histogram-spread
caveat as `signals.entropy()` (Recipe 5) — "more disordered" means spread
further across a batch's own value range, not a comparable severity score.

Full worked version with both scenarios run side-by-side:
`apps/adaptive_baseline_monitor/`.

---

## Recipe 11 — Everything together (`space`) — all seven doors, not five

One engine, all seven doors, one save/load. This is the whole pitch: no
integration stack, same state, every door composes. Below is all seven
working on one shared `Space`, not just the five or six that tend to get
shown (it's easy to write this example and quietly forget a door —
`workflow` went missing from the shipped `tessera.examples.warehouse` until
an earlier round of fixes; this round adds the seventh).

```python
from tessera.space import Space

space = Space.open("ward", persistence="local")   # loads if it exists, creates if not

space.graph.connect("patient-01", "watch-01")                      # 1 graph
space.signals.measure("hr:patient-01", [74, 75, 74])                # 2 signals
space.agents.observe({"hr:patient-01": 75})                         # 3 agents (NOTE below)
space.store.put("alert:patient-01", {"status": "ok"})                # 4 store
space.baseline.learn(75)                                              # 5 baseline

def log_check(ctx):                                                  # 6 workflow
    space.replay.append({"event": "checked_in"})                     # 7 replay
    return {"done": True}

space.workflow.add("log_check", log_check)
space.workflow.run()

space.save()                                     # the ONLY save() call you need — all doors
```

Full worked version of this pattern (with a real branching decision instead
of a straight line) lives at `health_triage.py` and
`python -m tessera.examples.warehouse`.

**Gotcha 1:** inside a `Space`, numeric values passed to `agents.observe({...})`
are *also* recorded as a measurement series under that same key — so
`agents.observe({"hr": 75})` and `signals.measure("hr", [...])` write to the
**same** `"hr"` series. That's the point of shared state, but it means your
key names are a shared namespace across every door in the `Space`, not
private to `agents`.

**Gotcha 2:** see Part 2.2 — `replay.append()` and `workflow.run()` do **not**
auto-persist when accessed through `space.replay`/`space.workflow`, even
though they do when constructed standalone. Only `space.save()` persists
anything.

---

## Part 3.5 — Findings from independent adversarial testing (verified, now fixed)

Four independent AI coding agents were each given only the shipped wheel and
these docs, told nothing about each other or about prior findings, and asked
to build a real application and then try to break it. Every claim below was
independently re-verified before being written here — not taken on an
agent's word. All eight are now fixed except the one noted as intentional.

- **FIXED — `signals.stats()`/`anomalies()`/`correlate()` on a series that
  was never measured (or only measured with an empty list) used to return a
  fabricated, indistinguishable-from-real result** —
  `{'n': 1, 'mean': 0.0, 'std': 0.0}` — instead of erroring. A typo'd series
  name looked exactly like "one real reading of zero." Independently found
  by three of the four agents. **Now raises `ValueError`** naming the
  series and telling you to `measure()` it first.
- **FIXED — `signals.stats()`/`anomalies()` could silently return `None`,
  and `entropy()` could crash with an internals-leaking `ValueError`, on
  extreme-but-finite magnitude input** — not the documented NaN/inf case,
  valid floats whose internal sum/variance overflows. Root cause for
  `entropy()` was actually in the plain-Python `histogram8()` helper
  (`hi - lo` overflowing to `inf`, then `inf/inf = nan`, then
  `int(nan)` raising) — fixed with a rank-based binning fallback for
  non-finite ranges, well-defined at any magnitude. `stats()`/`anomalies()`
  **now raise `ArithmeticError`** with a clear message instead of silently
  returning `None`.
- **Not a bug — by design, and engine-wide, not limited to
  `signals.measure()`.** NaN/Inf→`0.0` sanitization is confirmed identical in
  `store.put()` and `agents.Field.observe()`. Per the engine's own internal
  spec (not shipped with this SDK): *"every kwarg is sanitized before
  dispatch — NaN/inf → 0.0, recursively... prevents state poisoning."* This
  is intentional robustness, not a defect — left as documented behavior,
  not "fixed."
- **FIXED — `store.put()` stringifies every key.** `put(1, "a")` then
  `put("1", "b")` used to silently overwrite the first with no signal.
  **Now raises `ValueError`** on the second call if the stringified key
  already maps to a different-typed original key — confirmed also for
  `None` vs. `"None"` and list/tuple keys.
- **FIXED — `persistence=""` used to silently resolve to the current working
  directory** (undocumented, only discoverable by reading
  `tessera/core.py`'s `persist_dir()`). **Now raises `ValueError`.**
  `True`/`False` remain accepted, as already documented (`True` → `~/.tessera`,
  `False` → memory-only).
- **MITIGATED — concurrent writers to the same persisted name used to
  produce an uncaught crash**, not just a race: a real two-process test
  produced an unhandled `FileNotFoundError` from inside the compiled engine
  (a shared, non-unique temp-file rename colliding), with an internal engine
  path leaking into the traceback. **Every door's `save()` now catches this
  and raises `tessera.ConcurrentWriteError`** instead — a clear, catchable
  error. This does **not** add multi-writer coordination or prevent lost
  updates; it only replaces a confusing crash with an honest one. Treat "no
  multi-writer coordination" as a hard single-writer requirement regardless.
- **MITIGATED — `agents.Program(name, fn=...)`'s return value is discarded.**
  Unlike a `workflow` step (whose return is automatically stored under the
  step's name), an `fn`-form `Program`'s `return {...}` goes nowhere — `fn`
  must call `field.observe()` itself to record anything. Left as designed
  (an `fn`-form `Program` is meant to be "your own Python," not an
  auto-applied result), but **a non-`None` return now triggers a
  `UserWarning`** naming the program and reminding you the value is unused —
  no more silent discard.
- **FIXED — `signals.correlate()` on two series of different lengths used to
  silently compute a value from the overlapping prefix.** **Now raises
  `ValueError`** stating both series' actual lengths.
- **FIXED — a `workflow` step that returns `None` used to be checkpointed as
  completed but have its result dropped from `ctx` entirely** (not even
  stored as `None` — the key was simply absent). **Now `ctx[name]` is always
  set**, including to `None` — "did it run" and "is its result present" mean
  the same thing.

**Also fixed this round, found by re-reading the SDK's own resume
documentation literally (see Part 3 Recipe 7 Gotcha 2 and the error
reference below):** `workflow`'s silent-skip-on-forgotten-step-registration,
and silent double-execution when two steps share a name.

## Part 4 — Error reference

Every row below was triggered on purpose and the exact exception/behavior
recorded — not guessed from the method name.

| You did this | What actually happens |
|---|---|
| Constructing any door fresh (not `.open()`/`.load()`) when a save already exists, then saving again | **Previously saved state is silently destroyed** — no error. Use `.open()` (Part 2.0) |
| `graph.connect(a, a)`, `connect(a, None)`, or either side unhashable (e.g. a list) | Raises `ValueError` |
| `workflow.add("x", fn)` called twice with the same name on one object | Raises `ValueError` — previously both functions silently ran their side effects, only the last result was visible |
| `workflow.run()` after `.open()`/`.load()` without re-adding a step that isn't done yet | Raises `MissingWorkflowStepsError` naming the missing step(s) — previously silently skipped them |
| `store.save()` / `graph.save()` / etc. with `persistence=None` | Raises `ValueError` ("In-memory ... construct with persistence=...") |
| `persistence=""` | Raises `ValueError` — previously silently resolved to the current working directory |
| Two writers `save()`ing the same persisted name concurrently | Can raise `tessera.ConcurrentWriteError` — previously an uncaught, internals-leaking `FileNotFoundError` |
| `Store.load(...)` / `Field.load(...)` / etc. when the file doesn't exist | Raises `FileNotFoundError` |
| `.load()`/`.open()` on a corrupted, wrong-shape, or schema-empty (e.g. `"{}"`) save file | Raises `tessera.InvalidSaveFileError` — previously a raw `JSONDecodeError`/`AttributeError`, or (for `"{}"`) silently loaded as "a legitimate empty save" |
| `Store.create(...)` / etc. when a save already exists | Raises `FileExistsError` |
| `store.put(1, "a")` then `store.put("1", "b")` | Raises `ValueError` on the second call — previously silently overwrote the first (keys are stringified internally) |
| `signals.stats()`/`anomalies()`/`correlate()` on a series never `measure()`'d | Raises `ValueError` — previously returned a fabricated `{'n':1,'mean':0.0,'std':0.0}`-shaped result |
| `signals.correlate()` on series of different lengths | Raises `ValueError` — previously silently used the overlapping prefix |
| `signals.stats()`/`anomalies()` on extreme-magnitude input that overflows internally | Raises `ArithmeticError` — previously silently returned `None` |
| Exception raised inside `store.transaction()` | Rolled back, then **re-raised** — never swallowed |
| `signals.measure(series, [NaN, inf, ...])`, `store.put(k, nan)`, `agents.observe({"x": nan})` | Silently sanitized to `0.0` per value, engine-wide — by design, not a bug |
| `agents.Program(name, fn=...)`'s `fn` returns a non-`None` value | A `UserWarning` is raised (the value is still discarded — `fn` must call `field.observe()` itself) |
| `workflow.run(ctx)` called again after a step already completed, with different `ctx` values | The already-completed step's stored result is unchanged; new input for that step is ignored until `reset()` |
| `replay`/`workflow` writes made through `space.replay`/`space.workflow` without calling `space.save()` | Nothing is persisted — `Space` overrides their standalone auto-save (Part 2.2) |
| A saved event-log/JSON file hand-edited on disk | Loads and reconstructs the tampered value with no detection (Recipe 8) |

---

## Part 5 — Known limitations (read before relying on this for production)

Stated plainly rather than implied, so you can decide if they matter for your
use case:

- **No encryption at rest.** Persisted files are plain JSON. Anyone with
  filesystem access can read or edit them (see the tamper test above).
- **No tamper-evidence on `replay`.** Reconstructable, not cryptographically
  provable. See Recipe 8.
- **No multi-process/multi-writer coordination.** Nothing here is a lock or a
  distributed consensus mechanism; it's a local, single-writer, atomic-file
  persistence layer. Two processes writing to the same persisted name at the
  same time will race — `save()` now raises a clear `ConcurrentWriteError`
  instead of an internals-leaking crash, but that's a better failure mode,
  not coordination; lost updates are still possible.
- **`signals.anomalies()`'s threshold is still static** (a caller-supplied
  `threshold=` standard-deviations cutoff) — if you need a threshold that
  learns and moves over time instead of one you hardcode, that's what the
  `baseline` door (`tessera.baseline.AdaptiveBaseline`) is for; see Part 1's
  door table.
- **Found a bug, or an undocumented edge case?** File it at
  https://github.com/LaminarInstruments/laminar-tessera/issues — public,
  no account needed to read it, a free GitHub account to file one.
- **Not a clinical decision system.** `signals.entropy()`/`anomalies()` are
  generic statistics, not medically validated risk scores (Recipe 5).
- **Each wheel installs on exactly one Python version/platform** — `cp313`
  for Python 3.13 on any Mac, `cp311` for Python 3.11 on Apple Silicon only
  (built and verified on this machine; not tested elsewhere despite the
  macOS version in its tag). Neither covers Linux, Windows, Intel Mac, or
  any other Python version — rebuild from `src/` for those (verified to
  actually work — that's exactly how the `cp311` wheel was produced).

None of these are defects in what's documented — they're boundaries worth
knowing before you build something that assumes otherwise.

---

## Part 6 — Day-one checklist

- [ ] Ran `python -m tessera.selftest` — saw `ALL SEVEN DOORS REAL`.
- [ ] Using `.open()` (not the plain constructor) on every restart path —
      the plain constructor still silently destroys prior state on the next
      save if a save already exists (Part 2.0).
- [ ] For `workflow` specifically: re-adding every step after `.open()`, even
      ones you believe are already done — `run()` raises
      `MissingWorkflowStepsError` if you forget one that isn't done yet.
- [ ] Chose `persistence=` deliberately per door (`"local"`, a specific dir, or
      `None` for memory-only) — know which one you picked.
- [ ] For `store`/`graph`/`signals`/`agents`, and for **everything** inside a
      `Space` (including `replay`/`workflow`): calling `.save()` after every
      meaningful write, not just at program exit.
- [ ] Catching exceptions raised inside `store.transaction()` — it never
      swallows them.
- [ ] Every `workflow` step with an external side effect has an idempotency
      key.
- [ ] Reading workflow results as `ctx["<step_name>"]`, not flat keys.
- [ ] Not comparing `signals.entropy()` across different series/baselines as
      if it were a normalized severity score — it isn't one.
- [ ] Not treating `signals.anomalies()`/`entropy()` as a clinical or safety
      judgment without separate domain validation.
- [ ] Filtering `NaN`/`inf` out of your own data before `measure()`/`put()`/
      `observe()` — this is engine-wide, by design, and will silently zero
      them instead of flagging them.
- [ ] Catching `ValueError` from `graph.connect()` at the boundary where node
      ids come from outside your own code.
- [ ] Using one consistent type per logical `store` key — `put(1, ...)` and
      `put("1", ...)` now raise on the second call instead of colliding.
- [ ] Not relying on `replay` for a legally/contractually non-repudiable
      audit trail without adding your own integrity layer on top.

## Part 7 — Where to go next

- `apps/` — three fully worked, fully tested flagship applications (persistent
  agent memory, a crash-recoverable order processor with a real `SIGKILL`
  test, and a service dependency/anomaly monitor), each with its own README
  covering problem, components, sample I/O, tests, a failure-recovery
  demonstration, and deployment limitations.
- `API_REFERENCE.md` — every public method signature.
- `DEVELOPER_GUIDE.md` — the authoritative per-door contracts.
- `AGENTS.md` — if you're an AI coding agent, read this one first.
- Bugs and anything not covered by the four docs above:
  https://github.com/LaminarInstruments/laminar-tessera/issues — or
  darreck@laminarinstruments.com (laminarinstruments.com) directly.
