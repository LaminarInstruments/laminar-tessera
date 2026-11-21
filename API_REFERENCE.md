# Tessera API Reference

Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com

Generated from the live public signatures of `tessera 0.1.2`, including inherited/class methods. Methods starting with `_` are omitted. This is the exact surface you build against — if a method you saw in a guide isn't listed here, that's a bug in this file, not permission to guess.

## tessera.agents

### `class Field`
An agent's unified state — memory, relationships, and decisions in one.

- `__init__(self, name, persistence=None, _spu=None)`
- `classmethod create(name, persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `commit(self, branch=None)`
    - Keep a decision. With a branch, adopt the future you explored on it.
- `fork(self)`
    - An isolated copy to explore a future on. Changes here do NOT touch
- `history(self)`
    - Every observe/run, in order — the replayable event log.
- `classmethod load(name, persistence='local', path=None)`
    - Loads existing state from disk. Raises `FileNotFoundError` if nothing
      was ever saved; raises `tessera.InvalidSaveFileError` if the file
      exists but is corrupted or the wrong shape.
- `observe(self, observations)`
    - Record what the agent sees. Scalars become both a descriptor (the
- `classmethod open(name, persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
      THE safe entry point for any restart path — see `COOKBOOK.md` Part 2.0.
- `run(self, program, **kwargs)`
    - Run a Program against this field, mutating its state. If `program.fn`
      returns a non-`None` value, raises a `UserWarning` (the value is
      discarded — `fn` must call `field.observe()` itself to record anything).
- `save(self, path=None)`
    - Persist durably (atomic write + fsync). Survives a crash.
- `state(self)`
    - The agent's current view: key -> latest value.

### `class Program`
A named thing an agent can run.

- `__init__(self, name, fn=None, steps=None)`

## tessera.store

### `class Store`

- `__init__(self, persistence=None, name='store', _spu=None)`
- `classmethod create(name='store', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `delete(self, key)`
- `get(self, key, default=None)`
- `items(self)`
- `keys(self)`
- `classmethod load(name='store', persistence='local', path=None)`
    - Raises `FileNotFoundError` if nothing was ever saved; raises
      `tessera.InvalidSaveFileError` if the file exists but is corrupted or
      the wrong shape.
- `classmethod open(name='store', persistence=None)`
    - Load existing state if a save already exists for (name, persistence);
      otherwise create fresh. THE safe entry point for any restart path.
- `put(self, key, value)`
    - Set key -> value. Raises `ValueError` if `key` stringifies to the same
      thing as a differently-typed key already stored (e.g. `put(1, ...)`
      after `put("1", ...)`) — keys are stringified internally.
- `save(self, path=None)`
    - Raises `ValueError` if in-memory (no `persistence` set). Can raise
      `tessera.ConcurrentWriteError` if another process saves the same
      `(name, persistence)` at the same moment.
- `transaction(self)`
    - All-or-nothing block. On any exception, every write inside is undone.

## tessera.graph

### `class Graph`

- `__init__(self, persistence=None, name='graph', _spu=None)`
- `centrality(self)`
    - node -> how central it is (0..1), by connection fraction.
- `clusters(self)`
    - Connected groups — islands of related nodes.
- `connect(self, a, b)`
    - Create an undirected relationship between a and b. Raises `ValueError`
      on a self-loop (a == b), either side being None, or either side being
      unhashable (e.g. a list).
- `classmethod create(name='graph', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `degree(self, node)`
    - How many things connect to this node.
- `disconnect(self, a, b)`
- `edges(self)`
- `classmethod load(name='graph', persistence='local', path=None)`
    - Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `neighbors(self, node)`
- `classmethod open(name='graph', persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
- `path(self, a, b)`
    - Shortest chain of relationships from a to b (or None).
- `rank(self)`
    - Nodes ordered by importance (most-connected first).
- `reach(self, node)`
    - node -> hops away from the given start (how a change ripples out).
- `save(self, path=None)`
    - Same `ValueError`/`ConcurrentWriteError` conditions as `Store.save()`.

## tessera.signals

### `class Signals`

- `__init__(self, persistence=None, name='signals', _spu=None)`
- `anomalies(self, series, threshold=3)`
    - Indices in the stream that sit more than `threshold` std from the mean.
      Raises `ValueError` if `series` was never `measure()`'d. Raises
      `ArithmeticError` if the internal computation overflows (extreme
      magnitude input).
- `correlate(self, series_a, series_b)`
    - How tightly two streams move together (-1..1). Raises `ValueError` if
      either series was never measured, or if the two series have different
      lengths.
- `classmethod create(name='signals', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `entropy(self, values)`
    - Disorder in bits: a flat/steady series is low, a wild one is high.
      Operates on raw values, not a measured series name — stateless.
- `gate(self, values, threshold)`
    - Cheap triage: (escalate?, entropy). Only escalate when disorder
      crosses the threshold. Also stateless over raw values.
- `classmethod load(name='signals', persistence='local', path=None)`
    - Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `measure(self, series, values)`
    - Add one or more readings to a named stream. `NaN`/`inf` are silently
      sanitized to `0.0` (engine-wide, intentional — see COOKBOOK.md).
- `classmethod open(name='signals', persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
- `save(self, path=None)`
    - Same `ValueError`/`ConcurrentWriteError` conditions as `Store.save()`.
- `stats(self, series)`
    - Running count / mean / std for a stream. Raises `ValueError` if
      `series` was never `measure()`'d. Raises `ArithmeticError` if the
      internal computation overflows.

## tessera.workflow

### `class Workflow`

- `__init__(self, name, persistence=None, _spu=None)`
- `add(self, name, fn)`
    - Register a step function under `name`. Raises `ValueError` if `name`
      is already registered on this object.
- `completed(self)`
    - Names of steps already done (persisted).
- `classmethod create(name, persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `classmethod load(name, persistence='local', path=None)`
    - Restores checkpoint data, NOT the Python step functions — you must
      re-add every step by name before calling `run()`. Raises
      `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `classmethod open(name, persistence=None)`
    - Load existing state if a save already exists; otherwise create fresh.
      Does not restore step functions either — same caveat as `.load()`.
- `reset(self)`
    - Clear all progress (start the job over), including the record of
      which steps this workflow is known to need.
- `run(self, ctx=None)`
    - Run every not-yet-completed step in order. Raises
      `tessera.MissingWorkflowStepsError` (a `ValueError` subclass) if a
      step this workflow needs (from an earlier run) is neither
      re-registered on this object nor already completed.
- `step(self, fn)`
    - Decorator: register a step, run in registration order. Same duplicate
      check as `add()`.

## tessera.replay

### `class EventLog`

- `__init__(self, persistence=None, name='log', _spu=None)`
- `append(self, event)`
    - Record an event. Durable immediately when persisted.
- `classmethod create(name='log', persistence=None)`
    - Create new state; raise FileExistsError if a save already exists.
- `events(self)`
    - Every event, in the order it happened.
- `classmethod load(name='log', persistence='local', path=None)`
    - Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
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
      Positive = more disordered than baseline. Same histogram-spread
      caveat as `signals.entropy()` — not a severity score across
      different kinds of data.
- `learn(self, value)`
    - Feed one new reading into the learned baseline. Returns the updated
      baseline.
- `learn_many(self, values)`
    - Feed a sequence of readings in order. Returns the final baseline.
- `classmethod load(name, persistence='local', path=None)`
    - Raises `FileNotFoundError`/`tessera.InvalidSaveFileError` as above.
- `nudge(self, delta)`
    - Manually shift the baseline by `delta`.
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
      initial value 0.5, until this is called.
- `track_entropy(self, values)`
    - Computes this batch's entropy and ratchets the tracked baseline
      forward to it. Returns `True` if entropy dropped or held relative to
      the PREVIOUS baseline.
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
    - Reload a whole Space — all doors, one state — from disk. Raises
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
