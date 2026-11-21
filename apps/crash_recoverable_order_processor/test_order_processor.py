"""
Correctness tests for order_processor.py (no crash involved — see
crash_test.py for the real SIGKILL recovery demonstration).

Run:  python3 test_order_processor.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from order_processor import run_checkout, ledger_path


def test_clean_run_completes_all_three_steps():
    d = "/tmp/order_proc_test_clean"
    shutil.rmtree(d, ignore_errors=True)
    wf, ctx = run_checkout(d, "T1", 3, idempotent=False)
    assert wf.completed() == ["reserve", "charge", "ship"]
    assert ctx["reserve"]["held"] == 3
    assert ctx["charge"]["paid"] is True
    assert ctx["ship"]["tracking"] == "XZ-T1"
    shutil.rmtree(d, ignore_errors=True)
    print("[PASS] clean run completes reserve -> charge -> ship in order")


def test_rerunning_a_completed_order_does_not_recharge():
    """Documented workflow gotcha, checked directly: re-running after full
    completion does not re-execute any step, with or without the idempotency
    flag — completed() already covers every step."""
    d = "/tmp/order_proc_test_rerun"
    shutil.rmtree(d, ignore_errors=True)
    run_checkout(d, "T2", 1, idempotent=False)
    assert sum(1 for _ in open(ledger_path(d))) == 1

    run_checkout(d, "T2", 1, idempotent=False)   # run again, nothing left to do
    assert sum(1 for _ in open(ledger_path(d))) == 1, "a fully-completed workflow must not redo charge()"
    shutil.rmtree(d, ignore_errors=True)
    print("[PASS] re-running a fully completed order is a safe no-op")


def test_two_different_orders_do_not_share_state():
    d = "/tmp/order_proc_test_isolation"
    shutil.rmtree(d, ignore_errors=True)
    run_checkout(d, "T3", 2, idempotent=False)
    run_checkout(d, "T4", 9, idempotent=False)
    lines = [l for l in open(ledger_path(d)) if l.strip()]
    assert len(lines) == 2
    shutil.rmtree(d, ignore_errors=True)
    print("[PASS] two different order_ids get two independent workflow histories")


if __name__ == "__main__":
    test_clean_run_completes_all_three_steps()
    test_rerunning_a_completed_order_does_not_recharge()
    test_two_different_orders_do_not_share_state()
    print("\nALL CORRECTNESS TESTS PASSED (run crash_test.py separately for the SIGKILL recovery demo)")
