# Flagship Applications

Four complete, independently tested applications — not snippets — each
exercising a different combination of Tessera doors, each with a real
failure-recovery or correctness demonstration (not a simulated one), and
three of the four discovered at least one real, previously-undocumented
behavior while being built. That's not incidental: it's why these are built
as full applications instead of more cookbook snippets — some gotchas only
surface under multi-process, multi-session use, which a 10-line recipe
doesn't exercise.

| App | Doors | Failure-recovery proof | Found while building it |
|---|---|---|---|
| [`persistent_agent_memory`](persistent_agent_memory/) | `agents`, `store` | Two real OS processes; a session that never calls `.save()` loses everything on resume | — |
| [`crash_recoverable_order_processor`](crash_recoverable_order_processor/) | `workflow`, `replay` | A real `SIGKILL` mid-step, via `subprocess`/`os.kill` | — |
| [`service_dependency_monitor`](service_dependency_monitor/) | `graph`, `signals` | Two real OS processes extending the same graph/signal history | Baseline self-contamination (outliers inflate the std they're judged against) |
| [`adaptive_baseline_monitor`](adaptive_baseline_monitor/) | `baseline`, `signals` | Restart-and-resume via `.open()`; a scoping test proving the engine's feedback state is NOT keyed by series | Two confirmed gaps in static detection (drift, flapping) that `signals` alone can never close |

All four also independently rediscovered and now correctly guard against
**the load-vs-construct trap** (`COOKBOOK.md` Part 2.0): every door silently
destroys previously saved state if constructed fresh instead of loaded, on
any restart. Each app's `_load_or_create_*` helper (or `.open()` directly,
for the newer apps) is the reference pattern for avoiding it.

`adaptive_baseline_monitor` is the odd one out, deliberately: it's not
demonstrating a bug or a gotcha, it's demonstrating the **seventh door** —
`tessera.baseline.AdaptiveBaseline`, the first public interface onto the
engine's adaptive feedback (EMA) and entropy-baseline capability. It exists
because the other six doors, however well-built, only ever expose static
statistics — and static statistics have a real, demonstrated ceiling (see
its README for the two scenarios proven, not assumed, to break them).

Each app directory contains:
- The implementation (a small, focused class wrapping the relevant doors).
- A test suite (`test_*.py`) covering normal-path correctness.
- A failure-recovery demonstration, either inline in the test suite or as its
  own script (`crash_test.py` for the order processor).
- A `README.md`: problem statement, components used, sample input/output,
  how to run the tests, and deployment limitations.

Run any app's tests directly, e.g.:

```bash
cd persistent_agent_memory && python3 test_memory.py
cd crash_recoverable_order_processor && python3 test_order_processor.py && python3 crash_test.py
cd service_dependency_monitor && python3 test_monitor.py
cd adaptive_baseline_monitor && python3 test_baseline_demo.py
```

All four have been verified end-to-end in a clean virtual environment
installed only from the shipped `.whl` — not against any dev source tree.
