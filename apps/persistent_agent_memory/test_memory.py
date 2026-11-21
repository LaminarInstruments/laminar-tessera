"""
Test suite + failure-recovery demonstration for persistent_agent_memory.

Run:  python3 test_memory.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(code):
    """Run `code` as a brand-new Python process (a real separate session,
    not just a function call in this same interpreter)."""
    return subprocess.run([sys.executable, "-c", code], cwd=HERE,
                           capture_output=True, text=True)


def test_basic_demo_runs_and_asserts_pass():
    r = run("import memory; memory.demo()")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK — both decisions and the latest observations survived" in r.stdout
    print("[PASS] demo() runs end-to-end across 3 simulated sessions")


def test_recall_without_remembering_returns_empty_state():
    tmp = "/tmp/tessera_agent_memory_test_empty"
    shutil.rmtree(tmp, ignore_errors=True)
    r = run(f"""
from memory import ProjectMemory
mem = ProjectMemory("fresh-project", persistence="{tmp}")
print(mem.recall())
""")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "{}"
    print("[PASS] a brand-new project has empty recall(), not an error")


def test_forgetting_save_loses_the_session():
    """The real failure-recovery lesson for THIS app: unlike `workflow`/
    `replay`, Field/Store do not auto-save. A session that crashes before
    save() loses everything from that session — verified with two separate
    OS processes, not a simulated condition."""
    tmp = "/tmp/tessera_agent_memory_test_crash"
    shutil.rmtree(tmp, ignore_errors=True)

    # Process A: remembers something, decides something, then "crashes"
    # (process ends) WITHOUT calling save().
    r1 = run(f"""
from memory import ProjectMemory
mem = ProjectMemory("no-save-project", persistence="{tmp}")
mem.remember({{"status": "in_progress"}})
mem.decide("approach", method="rewrite")
# no mem.save() call — process exits here, simulating a crash
""")
    assert r1.returncode == 0, r1.stderr

    # Process B: tries to resume. Nothing should be there.
    r2 = run(f"""
from memory import ProjectMemory
try:
    mem = ProjectMemory.resume("no-save-project", persistence="{tmp}")
    print("UNEXPECTED: resumed successfully:", mem.recall())
except FileNotFoundError as e:
    print("EXPECTED: nothing to resume —", type(e).__name__)
""")
    assert r2.returncode == 0, r2.stderr
    assert "EXPECTED: nothing to resume" in r2.stdout, r2.stdout
    print("[PASS] forgetting save() in session A genuinely loses the session — proven with a real second process, not assumed")

    # Now the fixed version: same scenario, but WITH save().
    tmp2 = "/tmp/tessera_agent_memory_test_crash_fixed"
    shutil.rmtree(tmp2, ignore_errors=True)
    r3 = run(f"""
from memory import ProjectMemory
mem = ProjectMemory("saved-project", persistence="{tmp2}")
mem.remember({{"status": "in_progress"}})
mem.decide("approach", method="rewrite")
mem.save()
""")
    assert r3.returncode == 0, r3.stderr
    r4 = run(f"""
from memory import ProjectMemory
mem = ProjectMemory.resume("saved-project", persistence="{tmp2}")
print(mem.recall()["status"])
""")
    assert r4.returncode == 0, r4.stderr
    assert r4.stdout.strip() == "in_progress"
    print("[PASS] calling save() before the crash point fixes it — same code, one extra call")

    for d in (tmp, tmp2):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_basic_demo_runs_and_asserts_pass()
    test_recall_without_remembering_returns_empty_state()
    test_forgetting_save_loses_the_session()
    print("\nALL TESTS PASSED")
