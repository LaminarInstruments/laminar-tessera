"""
Real SIGKILL test for the Incident Response Coordinator: kill the process
for real, mid apply_mitigation (after the external effect — the mitigation
log write — but before the step's checkpoint), then verify what survived
and what didn't, and that resume completes correctly.
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
sys.path.insert(0, str(HERE))
from coordinator import marker_path, mitigation_log_path, current_incident_marker


def launch_trigger(persist_dir, service, kind):
    cmd = [sys.executable, str(HERE / "coordinator.py"), "trigger-incident", persist_dir, service, kind]
    return subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def launch_resume(persist_dir):
    cmd = [sys.executable, str(HERE / "coordinator.py"), "resume-incident", persist_dir]
    return subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for_marker(path, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


def mitigation_count(persist_dir, incident_id):
    p = mitigation_log_path(persist_dir, incident_id)
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines() if line.strip())


def main():
    persist_dir = "/tmp/irc_sigkill_test"
    shutil.rmtree(persist_dir, ignore_errors=True)

    # Trigger a real incident as a genuine child process. apply_mitigation
    # writes the real effect, drops a marker, then sleeps — kill it for
    # real the moment that marker appears, before the step can checkpoint.
    proc = launch_trigger(persist_dir, "db", "transient")
    # The incident_id (and its marker path) isn't known until the child
    # writes current_incident.json, right before running the workflow.
    info_path = current_incident_marker(persist_dir)
    assert wait_for_marker(info_path, timeout=10), "trigger-incident never recorded the incident info"
    info = json.loads(info_path.read_text())
    incident_id = info["incident_id"]

    m_path = marker_path(persist_dir, incident_id)
    try:
        assert wait_for_marker(m_path, timeout=10), "apply_mitigation step never reached its marker"
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        assert proc.returncode != 0, "process should have died from SIGKILL, not exited cleanly"
        print("[KILLED] real SIGKILL sent mid apply_mitigation, after the external effect, before checkpoint")
    finally:
        if proc.poll() is None:
            proc.kill()
    m_path.unlink(missing_ok=True)

    applied_before = mitigation_count(persist_dir, incident_id)
    assert applied_before == 1, f"expected exactly 1 mitigation-log entry before the kill, got {applied_before}"
    print(f"[PASS] exactly {applied_before} mitigation applied before the kill (the external effect)")

    from tessera.workflow import Workflow
    wf = Workflow.load(f"incident-{incident_id}", persistence=persist_dir)
    assert wf.completed() == ["page_oncall"], (
        f"page_oncall (the step BEFORE the killed one) should be checkpointed, "
        f"and apply_mitigation should NOT be — got {wf.completed()}"
    )
    print("[PASS] after the kill: page_oncall is checkpointed, apply_mitigation is NOT — exactly as the contract predicts")

    from tessera.space import Space
    space = Space.load("ops", persistence=persist_dir)
    assert "db" in space.store.get("open_incidents", {}), \
        "the open-incident record (saved before the workflow started) should have survived the kill"
    print("[PASS] the open-incident record itself survived the kill (it was saved before the workflow started)")

    # Resume — without an idempotency key, the uncheckpointed step re-runs.
    proc2 = launch_resume(persist_dir)
    out, err = proc2.communicate(timeout=15)
    assert proc2.returncode == 0, f"resume failed:\n{out}\n{err}"

    wf2 = Workflow.load(f"incident-{incident_id}", persistence=persist_dir)
    assert wf2.completed() == ["page_oncall", "apply_mitigation", "verify_recovery", "close_incident"], wf2.completed()
    print("[PASS] resume completed all four incident-response steps")

    applied_after = mitigation_count(persist_dir, incident_id)
    print(f"[RESULT] mitigation-log entries total: {applied_after} "
          f"({'skipped-on-resume via the idempotency check — correct' if applied_after == 1 else 'DOUBLE-APPLIED — unexpected'})")
    assert applied_after == 1, "apply_mitigation's idempotency check should have prevented a second external effect"

    shutil.rmtree(persist_dir, ignore_errors=True)
    print("\nALL INCIDENT-COORDINATOR SIGKILL TESTS PASSED")


if __name__ == "__main__":
    main()
