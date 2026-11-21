"""
Crash-Recoverable Order Processor — a checkout pipeline that resumes after a
real process kill, and a concrete demonstration of the idempotency-key gotcha
documented in the Cookbook: a step with an external side effect (charging a
card) that crashes AFTER the effect but BEFORE its checkpoint WILL re-run on
resume. Without an idempotency key, that double-charges. With one, it doesn't.

Tessera components used:
    workflow (tessera.workflow.Workflow) — resumable reserve -> charge -> ship
    replay   (tessera.replay.EventLog)   — durable trail of what happened

Usage:
    python3 order_processor.py run <persist_dir> <order_id> <qty> [--idempotent]

`charge` simulates a real external payment call by appending one line to
<persist_dir>/charges.log — a stand-in for "the money actually moved." It
then writes a marker file and sleeps briefly, giving an external harness a
window to SIGKILL this process mid-step (see crash_test.py).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.workflow import Workflow
from tessera.replay import EventLog

CHARGE_WINDOW_SECONDS = 2.0


def ledger_path(persist_dir):
    return Path(persist_dir) / "charges.log"


def marker_path(persist_dir):
    return Path(persist_dir) / "charging.marker"


def already_charged(persist_dir, order_id):
    p = ledger_path(persist_dir)
    if not p.exists():
        return False
    for line in p.read_text().splitlines():
        if line.strip() and json.loads(line)["order_id"] == order_id:
            return True
    return False


def append_charge(persist_dir, order_id, qty):
    with open(ledger_path(persist_dir), "a") as f:
        f.write(json.dumps({"order_id": order_id, "qty": qty}) + "\n")


def _load_or_create_workflow(name, persist_dir):
    """Workflow(name, persistence=dir) does NOT auto-resume prior progress —
    it silently starts a blank workflow and overwrites the checkpoint file on
    the next save. The only safe pattern is: load if a save exists, else
    construct fresh. Get this wrong and "resumable" quietly becomes "always
    restarts from zero" with no error to tell you."""
    path = Path(persist_dir) / f"{name}.workflow.json"
    if path.exists():
        return Workflow.load(name, persistence=persist_dir)
    return Workflow(name, persistence=persist_dir)


def _load_or_create_eventlog(name, persist_dir):
    """Same trap as above, for EventLog — a fresh construct-then-append
    silently overwrites (destroys) any previously saved event history."""
    path = Path(persist_dir) / f"{name}.log.json"
    if path.exists():
        return EventLog.load(name, persistence=persist_dir)
    return EventLog(persistence=persist_dir, name=name)


def run_checkout(persist_dir, order_id, qty, idempotent):
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    wf = _load_or_create_workflow(f"checkout-{order_id}", persist_dir)
    log = _load_or_create_eventlog(f"checkout-{order_id}-events", persist_dir)

    def reserve(ctx):
        log.append({"event": "reserved", "order_id": order_id, "qty": ctx["qty"]})
        return {"held": ctx["qty"]}

    def charge(ctx):
        if idempotent and already_charged(persist_dir, order_id):
            # the external effect already happened on a previous attempt —
            # do NOT repeat it, just record that this step is now satisfied.
            return {"paid": True, "charge_skipped_already_done": True}

        append_charge(persist_dir, order_id, ctx["qty"])   # <-- the external effect
        marker_path(persist_dir).write_text("charging")     # signal: effect is done
        time.sleep(CHARGE_WINDOW_SECONDS)                    # crash-test window
        log.append({"event": "charged", "order_id": order_id})
        return {"paid": True}

    def ship(ctx):
        log.append({"event": "shipped", "order_id": order_id})
        return {"tracking": f"XZ-{order_id}"}

    wf.add("reserve", reserve)
    wf.add("charge", charge)
    wf.add("ship", ship)
    ctx = wf.run({"qty": qty, "order_id": order_id})
    return wf, ctx


if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] != "run":
        print(__doc__)
        sys.exit(1)
    _, _, persist_dir, order_id, qty = sys.argv[:5]
    idempotent = "--idempotent" in sys.argv
    wf, ctx = run_checkout(persist_dir, order_id, int(qty), idempotent)
    print("completed steps:", wf.completed())
    print("ctx:", ctx)
