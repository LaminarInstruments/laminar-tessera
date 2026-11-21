"""
Persistent Agent Memory — a coding assistant that remembers project decisions
across separate sessions (separate process runs), not just within one.

Problem: an AI agent (or any long-lived assistant) working on a project needs
to recall what it already decided last time it ran, without re-deriving it
from scratch or asking the user again. Tessera components used:

    agents (tessera.agents.Field)  — observe facts, fork a decision, commit it
    store  (tessera.store.Store)   — a durable decision log, independent of
                                      the agent's own state, queryable by key

Run the full two-session demo:  python3 memory.py demo
Run the test suite:             python3 test_memory.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.agents import Field, Program
from tessera.store import Store


class ProjectMemory:
    """Wraps Field + Store so an agent can remember a project across restarts."""

    def __init__(self, project_name, persistence):
        self.project_name = project_name
        self.persistence = persistence
        self.field = Field(project_name, persistence=persistence)
        self.decisions = Store(persistence=persistence, name=f"{project_name}-decisions")

    @classmethod
    def resume(cls, project_name, persistence):
        """Load a project's memory from a previous session. Raises
        FileNotFoundError if this project was never saved."""
        mem = cls.__new__(cls)
        mem.project_name = project_name
        mem.persistence = persistence
        mem.field = Field.load(project_name, persistence=persistence)
        mem.decisions = Store.load(name=f"{project_name}-decisions", persistence=persistence)
        return mem

    def remember(self, facts: dict):
        """Record what the agent currently sees/knows about the project."""
        self.field.observe(facts)
        return self

    def decide(self, name, **kwargs):
        """Explore a decision on an isolated fork, then commit it as the
        agent's real choice. This is the actual Tessera agents contract:
        fork() is a deep copy, nothing on the live field changes until
        commit(branch)."""
        branch = self.field.fork()
        branch.run(Program(name), **kwargs)
        self.field.commit(branch)
        self.decisions.put(name, kwargs)
        return self

    def recall(self):
        """The agent's current view of the project: key -> latest value."""
        return self.field.state()

    def timeline(self):
        """Every observe/run this project has ever done, in order."""
        return self.field.history()

    def save(self):
        self.field.save()
        self.decisions.save()
        return self


def demo():
    import shutil
    tmp = "/tmp/tessera_agent_memory_demo"
    shutil.rmtree(tmp, ignore_errors=True)   # demo() must be repeatable, not accumulate across runs

    print("=== SESSION 1 (first run, fresh process) ===")
    mem = ProjectMemory("acme-migration", persistence=tmp)
    mem.remember({"target_db": "postgres", "rows": 4_200_000, "risk": "medium"})
    mem.decide("migration_strategy", approach="dual-write", cutover_window_days=14)
    mem.save()
    print("remembered:", mem.recall())
    print("decisions made this session: migration_strategy")
    print("--- process 1 exits here ---\n")

    print("=== SESSION 2 (separate process, loads session 1's memory) ===")
    mem2 = ProjectMemory.resume("acme-migration", persistence=tmp)
    print("recalled from disk:", mem2.recall())
    assert mem2.recall()["risk"] == "medium"
    assert mem2.decisions.get("migration_strategy")["approach"] == "dual-write"
    print("agent did NOT need to be told the strategy again — it remembered.")

    mem2.remember({"rows": 4_350_000})          # project moved on; update what it sees
    mem2.decide("rollback_plan", trigger="error_rate>2%", action="revert_to_single_write")
    mem2.save()
    print("session 2 added a new decision:", mem2.decisions.get("rollback_plan"))

    print("\n=== SESSION 3 (proves BOTH decisions survive, across two restarts) ===")
    mem3 = ProjectMemory.resume("acme-migration", persistence=tmp)
    print("full timeline length:", len(mem3.timeline()), "events")
    assert mem3.decisions.get("migration_strategy")["approach"] == "dual-write"
    assert mem3.decisions.get("rollback_plan")["action"] == "revert_to_single_write"
    assert mem3.recall()["rows"] == 4_350_000     # latest observation wins
    print("OK — both decisions and the latest observations survived two full restarts.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        print(__doc__)
