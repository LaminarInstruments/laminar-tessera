# Tessera API Reference

Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com

Generated from the live public signatures of `tessera 0.1.6`, including inherited/class methods. Methods starting with `_` are omitted. This is the exact surface you build against — if a method you saw in a guide isn't listed here, that's a bug in this file, not permission to guess.

## tessera.agents

### `class Field`
An agent's unified state — memory, relationships, and decisions in one.

- `__init__(self, name, persistence=None, _spu=None)`
- `classmethod create(name, persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `commit(self, branch=None, force=False)`
    - Keep a decision. With a branch, adopt the future you explored on it.
      Raises `ValueError` if `branch` wasn't `fork()`'d from this field's own
      engine, or if this field has changed since the fork (a stale commit
      would otherwise silently discard whatever happened in between). This
      staleness check only applies between a branch and the EXACT object it
      was directly `fork()`'d from — committing a fork-of-a-fork
      (`field.fork().fork()`) straight onto the original falls back to just
      the lineage check instead of a false "stale" rejection; chain commits
      (leaf → intermediate → root) get the full check at every hop. Pass
      `force=True` for a deliberate whole-world replacement regardless.
- `fork(self)`
    - An isolated copy to explore a future on. Changes here do NOT touch
      this field until you `commit()` them back.
- `history(self)`
    - Every observe/run, in order — the replayable event log. Returns deep
      copies; mutating a returned entry cannot change stored history.
- `classmethod load(name, persistence='local', path=None)`
    - Loads from `path` if given, else the default (name, persistence)
      location, and binds further saves to that actual path. If the loaded
      state recorded its own logical name (every `save()` does), that name
      is used instead of the `name` argument — an explicit-path load with a
      mismatched `name` can no longer silently return an empty `state()`.
      Raises `FileNotFoundError` if nothing was ever saved; raises
      `tessera.InvalidSaveFileError` if the file exists but is corrupted or
      the wrong shape.
- `observe(self, observations)`
    - Record what the agent sees. Scalars become both a descriptor (the
      current value) and a measurement (the running series, for stats).
      `observations` may be a one-shot iterator (materialized once, safely).
      Raises `ValueError` up front — before any state is touched — for two
      keys that collide once stringified (e.g. `3` and `"3"`, including a
      collision nested inside a value), for a value that fails `float()`
      conversion, or for a numeric value with `abs(value) > 1e15` (this
      feeds the exact same shared measurement series `signals.stats()`
      reads, so it mirrors `Signals.measure()`'s own magnitude check — a
      huge value written here used to silently poison that series through
      this door instead). A failure never leaves a partial, unlogged
      mutation behind.
- `classmethod open(name, persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
      THE safe entry point for any restart path — see `COOKBOOK.md` Part 2.0.
- `run(self, program, **kwargs)`
    - Run a Program against this field, mutating its state. If `program.fn`
      returns a non-`None` value, raises a `UserWarning` (the value is
      discarded — `fn` must call `field.observe()` itself to record anything).
      For a `steps=[...]` Program, every opcode name is validated BEFORE any
      of them run (`ValueError` for an unknown opcode, nothing executed),
      and each step's raw result is recorded in the logged run event's
      payload under `"results"`.
- `save(self, path=None)`
    - Persist durably (atomic write + fsync). Survives a crash. Also records
      this field's own logical `name` inside the saved state (see `load()`).
- `state(self)`
    - The agent's current view: key -> latest value. Returns a deep copy.

### `class Program`
A named thing an agent can run.

- `__init__(self, name, fn=None, steps=None)`

## tessera.store

### `class Store`

- `__init__(self, persistence=None, name='store', _spu=None)`
- `classmethod create(name='store', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `delete(self, key)`
    - Remove key. Raises `ValueError` for the same cross-type collision
      `put()` rejects (e.g. `delete(1)` after `put("1", ...)`) — previously
      this silently removed the wrong, differently-typed entry.
- `get(self, key, default=None)`
    - Returns a deep copy; mutating the result cannot change stored state.
- `items(self)`
    - Returns deep copies.
- `keys(self)`
- `classmethod load(name='store', persistence='local', path=None)`
    - Binds further saves to the actual `path` passed (previously silently
      dropped, so a save went to the default name-derived path instead).
      Raises `FileNotFoundError` if nothing was ever saved; raises
      `tessera.InvalidSaveFileError` if the file exists but is corrupted or
      the wrong shape.
- `classmethod open(name='store', persistence=None)`
    - Load existing state if a save already exists for (name, persistence);
      otherwise create fresh. THE safe entry point for any restart path.
- `put(self, key, value)`
    - Set key -> value. Raises `ValueError` if `key` stringifies to the same
      thing as a differently-typed key already stored (e.g. `put(1, ...)`
      after `put("1", ...)`) — keys are stringified internally. `value` is
      fully validated for persistence before being stored: raises
      `ValueError` for two dict keys that would collide once stringified
      (e.g. `{1: 'a', '1': 'b'}`), raises `TypeError` for a dict key that
      isn't a valid JSON key type (e.g. a tuple) or for a value that isn't
      JSON-serializable at all (e.g. a raw `set`) — previously these were
      accepted silently and only failed later, with a raw internals error,
      at `save()` time. `value` is deep-copied on the way in (mutating your
      original afterward can't change what's stored), any tuple anywhere
      inside it is normalized to a list immediately (not only after a
      save/reload — JSON has no tuple type), and any NaN/Inf anywhere
      inside it — including nested in a dict, which the engine's sanitizer
      doesn't reach — is sanitized to `0.0`.
- `save(self, path=None)`
    - Raises `ValueError` if in-memory (no `persistence` set). Raises
      `RuntimeError` if called while a `transaction()` is still open on this
      Store (previously this wrote the uncommitted in-progress values
      straight to disk). Can raise `tessera.ConcurrentWriteError` if another
      process saves the same `(name, persistence)` at the same moment, or
      plain `FileNotFoundError` if the target directory doesn't exist.
- `transaction(self)`
    - All-or-nothing block. On any exception, every write inside is undone.
      Use `async with store.transaction():` instead of `with` for a block
      spanning `await` points — it serializes concurrent transactions on
      this Store via a shared lock, so two tasks' transactions can no
      longer interleave on the shared engine state, and is reentrant for
      the SAME task (a nested `async with` from within another on the same
      task does not deadlock). Mixing `with` and `async with` on the same
      Store now raises `RuntimeError` instead of silently proceeding
      unguarded if the other flavor currently has a transaction open — use
      one flavor consistently for a Store also accessed from async code.

## tessera.graph

### `class Graph`

- `__init__(self, persistence=None, name='graph', _spu=None)`
- `centrality(self)`
    - node -> how central it is (0..1), by connection fraction.
- `clusters(self)`
    - Connected groups — islands of related nodes.
- `connect(self, a, b)`
    - Create an undirected relationship between a and b. Raises `ValueError`
      on a self-loop (a == b), either side being `None`, or either side not
      being a `str` (an int loses its identity across a save/reload since
      JSON object keys are always strings; a tuple gets silently converted
      to a list by the shared dispatch sanitizer and the edge was dropped
      with no signal at all).
- `classmethod create(name='graph', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `degree(self, node)`
    - How many things connect to this node.
- `disconnect(self, a, b)`
    - Remove the relationship between a and b. Raises `ValueError` if either
      side isn't a `str` — same requirement as `connect()` (previously
      unchecked, asymmetric with `connect()`'s validation).
- `edges(self)`
- `classmethod load(name='graph', persistence='local', path=None)`
    - Binds further saves to the actual `path` passed (previously silently
      dropped). Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `neighbors(self, node)`
- `classmethod open(name='graph', persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
- `path(self, a, b)`
    - Shortest chain of relationships from a to b, or `None` if either
      endpoint was never `connect()`'d (previously an unregistered `a == b`
      returned a trivial one-node "path" before any membership check).
      Equal-cost ties break deterministically (neighbors visited in
      `sorted(key=str)` order) — stable across processes and reloads.
- `rank(self)`
    - Nodes ordered by importance (most-connected first).
- `reach(self, node)`
    - node -> hops away from the given start (how a change ripples out), or
      `None` if `node` was never `connect()`'d (consistent with `path()`).
- `save(self, path=None)`
    - Same `ValueError`/`ConcurrentWriteError` conditions as `Store.save()`.

## tessera.signals

### `class Signals`

- `__init__(self, persistence=None, name='signals', _spu=None)`
- `anomalies(self, series, threshold=3)`
    - Indices in the stream that sit more than `threshold` std from the mean.
      Raises `ValueError` if `series` was never `measure()`'d, or if
      `threshold` isn't a finite, nonnegative number (previously a `NaN`
      threshold was silently sanitized to `0.0`, flagging nearly everything).
      An `ArithmeticError` exists as a defensive fallback for an internal
      overflow, but is not reachable via any known input.
- `correlate(self, series_a, series_b)`
    - How tightly two streams move together (-1..1), or `None` if either
      series has zero variance (a constant series) — the Pearson
      coefficient is undefined there, not `0.0` (which was indistinguishable
      from "measured, no linear relationship"). A near-perfect correlation
      is clamped to exactly `[-1.0, 1.0]`. Internally anchored and rescaled
      before computing mean/variance/covariance, so a huge common offset or
      a tiny common scale no longer loses precision in the result — this
      does not change any value's meaning. Raises `ValueError` if either
      series was never measured, or if the two series have different
      lengths.
- `classmethod create(name='signals', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `entropy(self, values)`
    - Disorder in bits: a flat/steady series is low, a wild one is high.
      Operates on raw values, not a measured series name — stateless. The
      internal 8-bin histogram no longer raises `ZeroDivisionError` for a
      very small value span, and no longer splits several EQUAL
      extreme-magnitude readings across different bins — both were
      overflow/underflow edge cases in the binning math.
- `gate(self, values, threshold)`
    - Cheap triage: (escalate?, entropy). Only escalate when disorder
      crosses the threshold. Also stateless over raw values. Raises
      `ValueError` if `threshold` isn't a finite number (previously a `NaN`
      threshold was silently sanitized to `0.0`, which always escalated).
- `classmethod load(name='signals', persistence='local', path=None)`
    - Binds further saves to the actual `path` passed (previously silently
      dropped). Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `measure(self, series, values)`
    - Add one or more readings to a named stream. Raises `TypeError` if
      `series` isn't a `str` (a non-str series that stringifies the same as
      another silently merged with it on the next save/reload). `NaN`/`inf`
      are silently sanitized to `0.0`; any reading with `abs(value) > 1e15`
      now raises `ValueError` instead (previously also silently sanitized
      to `0.0`, engine-wide — a real, accepted finite number quietly
      becoming zero with no error; this magnitude cap now lives here
      specifically, scoped to `signals`' own statistics — `store`/`agents`
      preserve any finite float exactly).
- `classmethod open(name='signals', persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
- `save(self, path=None)`
    - Same `ValueError`/`ConcurrentWriteError` conditions as `Store.save()`.
- `stats(self, series)`
    - Running count / mean / std for a stream. Raises `ValueError` if
      `series` was never `measure()`'d.

## tessera.workflow

### `class Workflow`

- `__init__(self, name, persistence=None, _spu=None)`
- `add(self, name, fn)`
    - Register a step function under `name`. Raises `ValueError` if `name`
      is already registered on this object, or if called while `run()` is
      already executing on this object (registration is frozen during a
      run). Raises `TypeError` if `name` isn't a `str` (an int name
      round-trips through persisted completion as a string, so it silently
      re-ran on resume), if `fn` isn't callable, or if `fn` is an `async
      def` (its body would never actually run — nothing awaits it).
- `completed(self)`
    - Names of steps already done (persisted).
- `classmethod create(name, persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `classmethod load(name, persistence='local', path=None)`
    - Binds further saves to the actual `path` passed (previously silently
      dropped). Restores checkpoint data, NOT the Python step functions — you must
      re-add every step by name before calling `run()`. Raises
      `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `classmethod open(name, persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
      Does not restore step functions either — same caveat as `.load()`.
- `reset(self)`
    - Clear all progress (start the job over), including the record of
      which steps this workflow is known to need.
- `run(self, ctx=None)`
    - Run every not-yet-completed step in order. A completed step's
      restored result OVERRIDES any conflicting field in the caller's `ctx`
      (previously the caller's value won). Step results are deep-copied
      going in and out. Raises `tessera.MissingWorkflowStepsError` (a
      `ValueError` subclass) if a step this workflow needs (from an earlier
      run) is neither re-registered on this object nor already completed.
      Raises `ValueError` if this object's pending (not-yet-completed) step
      order doesn't match the order those steps were originally registered
      in. Raises `RuntimeError` if called reentrantly (e.g. a step's own
      callback calling `run()` again on this object — previously the
      in-flight step's effects could run twice). Raises `TypeError` if a
      step's return value isn't JSON-serializable, or is itself an
      awaitable (an `async def` step, or a sync function returning a
      coroutine) — rejected before marking the step complete, so memory and
      durable completion can't go out of sync. A step's return value also
      gets the same validation `store.put()`'s `value` does: `ValueError`
      for a dict key collision once stringified, `TypeError` for a dict key
      of an invalid JSON type — previously a tuple result silently became a
      list, and a colliding dict key silently collapsed, only after a
      resume; both are normalized/validated immediately now.
- `step(self, fn)`
    - Decorator: register a step, run in registration order. Same duplicate
      check as `add()`.

## tessera.replay

### `class EventLog`

- `__init__(self, persistence=None, name='log', _spu=None)`
- `append(self, event)`
    - Record an event. Durable immediately when persisted. Raises
      `TypeError` if `event` isn't JSON-serializable (including `NaN`/
      `Infinity`, which Python's `json` module would otherwise silently
      write as nonstandard tokens), if a dict key is an invalid JSON key
      type, or `ValueError` for two dict keys that collide once
      stringified (the same class of bug already fixed for `store.put()`)
      — rejected before being added, so a failed append can no longer
      corrupt the log or block a later valid append. `event` is
      deep-copied on the way in, and any tuple inside it is normalized to
      a list immediately.
- `classmethod create(name='log', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `events(self)`
    - Every event, in the order it happened. Returns deep copies; mutating
      a returned event cannot change stored history.
- `classmethod load(name='log', persistence='local', path=None)`
    - Loads from `path` if given, else the default (name, persistence)
      location, and binds further `append()`s to that actual path
      (previously an explicit-path load's appends silently went to the
      default filename instead). Raises `FileNotFoundError`/
      `tessera.InvalidSaveFileError` as above.
- `classmethod open(name='log', persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
      Important here specifically: a fresh construct-then-`append()` used to
      silently DESTROY previously saved events, not just fail to resume them.
- `reconstruct(self, reducer, initial=None)`
    - Fold the whole history into a state via reducer(state, event). Not
      cryptographically tamper-evident — a hand-edited save file reconstructs
      silently with no detection.

## tessera.baseline

### `class AdaptiveBaseline`
Learn what normal looks like, and let it move — first public door onto the
engine's adaptive feedback (EMA) and entropy-baseline capability.

- `__init__(self, name, persistence=None, _spu=None)`
- `amplify(self, gain)`
    - Manually scale the baseline by `gain`. A deliberate override, not
      something `learn()` does on its own.
- `attenuate(self, factor)`
    - Manually scale the baseline by `factor` (typically 0..1).
- `baseline_entropy(self)`
    - The current tracked entropy baseline, or `None` if `track_entropy()`
      has never been called.
- `convergence_rate(self)`
    - Mean absolute change over the last ~10 updates. Near zero means the
      baseline has settled.
- `classmethod create(name, persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `entropy_drift(self, values)`
    - This batch's entropy minus the tracked entropy baseline — read-only.
      Positive = more disordered than baseline. Raises `ValueError` for an
      empty `values` (an empty batch's entropy, `0.0`, isn't a real reading
      to compare against the baseline). Same histogram-spread caveat as
      `signals.entropy()` — not a severity score across different kinds of
      data.
- `learn(self, value)`
    - Feed one new reading into the learned baseline. Returns the updated
      baseline.
- `learn_many(self, values)`
    - Feed a sequence of readings in order. Returns the final baseline.
- `classmethod load(name, persistence='local', path=None)`
    - Binds further saves to the actual `path` passed (previously silently
      dropped). Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `nudge(self, delta)`
    - Manually shift the baseline by exactly `delta`, immediately (previously
      this fed `ema + delta` back through the EMA blend, applying only a
      fraction of the requested shift — e.g. `nudge(5)` moved the baseline
      by `1.0` at the default alpha/beta).
- `classmethod open(name, persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
- `oscillating(self, threshold=0.5)`
    - True if the baseline's recent updates are flapping rather than
      settling — catches instability that no single reading would ever
      register as a statistical outlier (verified in
      `apps/adaptive_baseline_monitor/`).
- `save(self, path=None)`
    - Raises `ValueError` if in-memory. Can raise `ConcurrentWriteError`.
- `set_rate(self, alpha, beta)`
    - `new_baseline = alpha*old + beta*reading`. Engine defaults (0.8, 0.2),
      initial value 0.5, until this is called. Raises `ValueError` if either
      coefficient isn't finite (previously a `NaN` was silently sanitized
      to `0.0` with no error).
- `track_entropy(self, values)`
    - Computes this batch's entropy and ratchets the tracked baseline
      forward to it. Returns `True` if entropy dropped or held relative to
      the PREVIOUS baseline. Raises `ValueError` for an empty `values`
      (previously this silently ratcheted the baseline down to `0.0` and
      reported "improvement" even though nothing was observed).
- `trend(self)`
    - A smoothed (3-point trailing average) view of the full feedback
      history.
- `value(self)`
    - The current learned baseline (`0.5` if `learn()` has never been
      called).

**Contract:** one instance tracks ONE scalar baseline — the engine's
feedback state (alpha/beta/ema) is a single triple, not keyed by series
name (verified by direct probing of the raw engine). Open a separate named
`AdaptiveBaseline` per thing tracked independently, same as every other
door.

## tessera.space

### `class Space`
Seven doors sharing one engine and one unit of state.

- `__init__(self, name: str = 'space', persistence: Union[str, bool, None] = None, _spu: Optional[SPU121] = None)`
- `classmethod create(name: str = 'space', persistence: Union[str, bool] = None) -> Space`
    - Create new state; raise FileExistsError if a save already exists.
- `classmethod load(name: str = 'space', persistence: Union[str, bool] = 'local', path: Optional[str] = None) -> Space`
    - Reload a whole Space — all doors, one state — from disk. Binds further
      saves to the actual `path` passed (previously silently dropped). Raises
      `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `classmethod open(name: str = 'space', persistence: Union[str, bool] = None) -> Space`
    - Load existing state if a save already exists; otherwise create fresh.
      Especially important for `Space`: a fresh `Space()` on a restart
      silently discards EVERY door's state at once, not just one.
- `save(self, path: Optional[str] = None) -> str`
    - Persist the WHOLE shared state (every door) atomically to one file.
      **Inside a `Space`, `replay`/`workflow` do NOT auto-persist the way
      they do standalone** — nothing in a `Space` is durable until this is
      called (see `COOKBOOK.md` Part 2.2). Can raise `ConcurrentWriteError`.

## Exceptions

All raised exceptions are either builtins (`ValueError`, `TypeError`,
`FileNotFoundError`, `FileExistsError`, `ArithmeticError`, `UserWarning`) or
one of these, importable from top-level `tessera`:

- `tessera.MissingWorkflowStepsError` (subclass of `ValueError`) — raised by
  `Workflow.run()` when a step this workflow needs is neither re-registered
  nor already completed.
- `tessera.ConcurrentWriteError` (subclass of `RuntimeError`) — raised when
  two processes `save()` the same persisted `(name, persistence)` at the
  same moment and the underlying atomic rename collides.
- `tessera.InvalidSaveFileError` (subclass of `ValueError`) — raised by any
  door's `.load()`/`.open()` when the target file exists but is corrupted or
  not shaped like a Tessera save.

## Module-level

- `tessera.program(fn)` → `Program` — decorator form of `Program(fn.__name__, fn=fn)`.
- `tessera.engine_info()` → dict — what engine backs the SDK and its properties.
