# Persistent Agent Memory

## Problem

An AI coding assistant (or any long-lived agent) working on a project across
multiple separate runs needs to remember what it already decided — without
re-deriving it, re-asking the user, or silently forgetting prior context
every time the process restarts.

## Tessera components

| Door | Role |
|---|---|
| `tessera.agents.Field` | `observe()` what the agent currently sees, `fork()`/`commit()` a decision the same way the project's own `agents.py` contract works |
| `tessera.store.Store` | A durable, queryable decision log, keyed by decision name, independent of the agent's own state |

## Sample input / output

```python
mem = ProjectMemory("acme-migration", persistence="/tmp/demo")
mem.remember({"target_db": "postgres", "rows": 4_200_000, "risk": "medium"})
mem.decide("migration_strategy", approach="dual-write", cutover_window_days=14)
mem.save()
```

A second, completely separate process run later:

```python
mem2 = ProjectMemory.resume("acme-migration", persistence="/tmp/demo")
mem2.recall()
# {'target_db': 'postgres', 'rows': 4200000, 'risk': 'medium'}
mem2.decisions.get("migration_strategy")
# {'approach': 'dual-write', 'cutover_window_days': 14}
```

Run the full three-session walkthrough: `python3 memory.py demo`

## Failure-recovery demonstration

`test_memory.py` proves the real failure mode with two genuinely separate OS
processes (`subprocess`, not an in-process simulation): a session that
`remember()`s and `decide()`s but never calls `.save()` loses everything —
the next process gets `FileNotFoundError` on resume, not partial data. The
same scenario with one added `.save()` call survives completely. This is the
standalone-door persistence rule from the Cookbook, proven here in a new
domain rather than just asserted.

Run it: `python3 test_memory.py`

## Deployment limitations

- No encryption at rest — the decision log and agent state are plain JSON on
  disk. Don't put secrets in `remember()`/`decide()` payloads.
- Single-writer. Two processes resuming and saving the same project
  concurrently will race (last `save()` wins); there's no lock.
- `decide()`'s fork/commit pattern protects against a *bad decision* (you can
  inspect `branch` before committing), not against a crash *during*
  `commit()` itself — `commit()` is a single in-memory deep-copy assignment,
  then you still need to call `.save()` afterward.
