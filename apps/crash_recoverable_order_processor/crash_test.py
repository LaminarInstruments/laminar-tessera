"""
Real crash-recovery test for order_processor.py.

This does not simulate a crash by skipping a method call — it launches the
checkout as a genuine child process, waits until the `charge` step's external
effect (the ledger write) has actually happened, then sends it SIGKILL. No
cleanup, no exception handler, no graceful shutdown: the OS just ends it,
exactly like a real crash.

Run:  python3 crash_test.py
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
from order_processor import ledger_path, marker_path   # noqa: E402

sys.path.insert(0, str(HERE))


def launch(persist_dir, order_id, qty, idempotent=False):
    cmd = [sys.executable, str(HERE / "order_processor.py"), "run", persist_dir, order_id, str(qty)]
    if idempotent:
        cmd.append("--idempotent")
    return subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for_marker(persist_dir, timeout=5.0):
    deadline = time.time() + timeout
    p = marker_path(persist_dir)
    while time.time() < deadline:
        if p.exists():
            return True
        time.sleep(0.02)
    return False


def kill_mid_charge(persist_dir, order_id, qty, idempotent):
    proc = launch(persist_dir, order_id, qty, idempotent)
    try:
        assert wait_for_marker(persist_dir), "charge step never reached its marker — test harness timing is wrong"
        # The external effect (ledger write) has already happened at this
        # point. The step has NOT returned, so it is NOT checkpointed yet.
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        assert proc.returncode != 0, "process should have died from SIGKILL, not exited cleanly"
    finally:
        if proc.poll() is None:
            proc.kill()
    marker_path(persist_dir).unlink(missing_ok=True)


def resume(persist_dir, order_id, qty, idempotent):
    proc = launch(persist_dir, order_id, qty, idempotent)
    out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, f"resume failed:\n{out}\n{err}"
    return out


def charge_count(persist_dir, order_id):
    p = ledger_path(persist_dir)
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines()
               if line.strip() and json.loads(line)["order_id"] == order_id)


def reserved_event_count(persist_dir, order_id):
    from order_processor import _load_or_create_eventlog
    log = _load_or_create_eventlog(f"checkout-{order_id}-events", persist_dir)
    return sum(1 for e in log.events() if e.get("event") == "reserved")


def test_without_idempotency_key_resume_double_charges():
    persist_dir = "/tmp/crash_test_no_idempotency"
    shutil.rmtree(persist_dir, ignore_errors=True)

    kill_mid_charge(persist_dir, "A1", 3, idempotent=False)
    assert charge_count(persist_dir, "A1") == 1, "the external effect should have happened exactly once before the kill"

    from tessera.workflow import Workflow
    wf = Workflow.load(f"checkout-A1", persistence=persist_dir)
    assert wf.completed() == ["reserve"], f"charge should NOT be checkpointed yet, got {wf.completed()}"
    print("[PASS] after the kill: reserve checkpointed, charge was not — exactly as documented")

    out = resume(persist_dir, "A1", 3, idempotent=False)
    assert "'ship': {'tracking'" in out, out   # the resumed run completes all the way through
    final_count = charge_count(persist_dir, "A1")
    assert final_count == 2, f"expected the documented double-charge (2 ledger entries), got {final_count}"
    print(f"[PASS] resume WITHOUT an idempotency key re-ran charge() -> {final_count} ledger entries for one order. "
          f"This is a real, reproduced double-charge from a real SIGKILL, not a theoretical risk.")

    assert reserved_event_count(persist_dir, "A1") == 1, \
        "reserve was already checkpointed before the kill — it must NOT run again on resume"
    print("[PASS] meanwhile reserve was correctly NOT re-run on resume — only the uncheckpointed step (charge) repeated")

    shutil.rmtree(persist_dir, ignore_errors=True)


def test_with_idempotency_key_resume_does_not_double_charge():
    persist_dir = "/tmp/crash_test_with_idempotency"
    shutil.rmtree(persist_dir, ignore_errors=True)

    kill_mid_charge(persist_dir, "A2", 5, idempotent=True)
    assert charge_count(persist_dir, "A2") == 1
    print("[PASS] after the kill: exactly one ledger entry, as before")

    out = resume(persist_dir, "A2", 5, idempotent=True)
    assert "'ship': {'tracking'" in out, out
    final_count = charge_count(persist_dir, "A2")
    assert final_count == 1, f"idempotency key should have prevented a second charge, got {final_count} entries"
    print(f"[PASS] resume WITH an idempotency check -> still exactly 1 ledger entry. Same crash, same resume, no double-charge.")

    shutil.rmtree(persist_dir, ignore_errors=True)


if __name__ == "__main__":
    test_without_idempotency_key_resume_double_charges()
    test_with_idempotency_key_resume_does_not_double_charge()
    print("\nALL CRASH-RECOVERY TESTS PASSED")
