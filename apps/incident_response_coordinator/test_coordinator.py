"""
Test suite for the Incident Response Coordinator — the all-seven-doors
flagship. Covers each door's specific contribution in isolation, then the
full coordinated run.

Run:  python3 test_coordinator.py
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from coordinator import (
    SERVICES, EDGES, TRANSIENT_SPIKE_ROUND, CHRONIC_DRIFT_SERVICE,
    _open_space, _open_baselines, setup_topology, reading_for, blast_radius,
    check_transient, check_chronic, run_simulation, reconstruct_timeline,
)
from tessera.baseline import BaselineSet


def _fresh(name):
    tmp = f"/tmp/irc_test_{name}"
    shutil.rmtree(tmp, ignore_errors=True)
    return tmp


def test_topology_and_blast_radius():
    tmp = _fresh("topology")
    space = _open_space(tmp)
    setup_topology(space)

    assert sorted(space.graph.neighbors("db")) == ["api", "payments"]
    # api is 1 hop from auth/db/cache; payments (via auth or db) is 2 hops
    assert blast_radius(space, "db") >= 2, "db has real downstream fanout (api, payments) -> must be P1-eligible"
    assert blast_radius(space, "cache") >= 1, "cache feeds api -> at least 1 hop downstream"
    print("[PASS] graph topology wired correctly; blast_radius reflects real dependency fanout")

    setup_topology(space)  # idempotent re-call must not duplicate edges
    assert space.graph.degree("db") == 2
    print("[PASS] setup_topology() is idempotent")
    shutil.rmtree(tmp, ignore_errors=True)


def test_signals_catches_transient_not_chronic():
    """The division of labor between signals and baseline, proven directly:
    a single spike gets flagged by signals; a slow, sustained drift of the
    same eventual magnitude does NOT (population stats absorb it) — the
    exact reason baseline exists as its own door."""
    tmp = _fresh("division_of_labor")
    space = _open_space(tmp)
    setup_topology(space)

    for r in range(TRANSIENT_SPIKE_ROUND + 2):
        reading = reading_for("db", r, __import__("random").Random(1))
        space.signals.measure("db", reading)
    flagged = space.signals.anomalies("db", threshold=2.5)
    assert flagged, "the scripted one-round spike on db must be caught by signals"
    print("[PASS] signals flags the transient db spike")

    for r in range(10):
        reading = reading_for(CHRONIC_DRIFT_SERVICE, r, __import__("random").Random(2))
        space.signals.measure("payments-control", reading)
    flagged_chronic = space.signals.anomalies("payments-control", threshold=2.5)
    assert not flagged_chronic, (
        "a steadily DRIFTING series must NOT look anomalous to a static population "
        "check once enough of it sits at the elevated level — this is exactly why "
        "baseline exists as a separate door, not a defect in signals"
    )
    print("[PASS] signals, as expected, does NOT catch the chronic drift on its own")
    shutil.rmtree(tmp, ignore_errors=True)


def test_baseline_catches_the_chronic_drift_signals_misses():
    tmp = _fresh("baseline_catch")
    baselines = BaselineSet.open("baseline", persistence=tmp)
    baseline = baselines["payments-check"]
    baseline.set_rate(alpha=0.5, beta=0.5)
    rng = __import__("random").Random(3)
    hard_cap = 400.0
    tripped_at = None
    for r in range(20):
        reading = reading_for(CHRONIC_DRIFT_SERVICE, r, rng)
        if check_chronic(baseline, reading, hard_cap):
            tripped_at = r
            break
    assert tripped_at is not None, "the scripted chronic drift must eventually trip the hard cap"
    print(f"[PASS] baseline correctly detects the chronic drift (tripped at round {tripped_at})")
    shutil.rmtree(tmp, ignore_errors=True)


def test_fork_commit_only_persists_on_real_recovery():
    """The actual payoff of fork()/commit(): a decision that does NOT lead
    to recovery must never show up in live agent state — proven directly,
    not just implied by the simulation's own (always-recovers) script."""
    tmp = _fresh("fork_commit")
    space = _open_space(tmp)
    setup_topology(space)
    from coordinator import open_incident, resolve_incident
    from tessera.agents import Program

    branch, incident_id, action = open_incident(space, "db", "transient", "P1")
    assert "incident" not in space.agents.state(), "an UNcommitted branch must not be visible in live state yet"

    resolve_incident(space, branch, incident_id, "db", succeeded=False)
    assert "incident" not in space.agents.state(), "a FAILED recovery's decision must be discarded, not committed"
    print("[PASS] a failed-recovery decision is correctly discarded, never touching live agent state")

    branch2, incident_id2, action2 = open_incident(space, "db", "transient", "P1")
    resolve_incident(space, branch2, incident_id2, "db", succeeded=True)
    assert space.agents.state().get("incident") == incident_id2, "a SUCCESSFUL recovery's decision must be committed"
    print("[PASS] a successful-recovery decision is correctly committed into live agent state")
    shutil.rmtree(tmp, ignore_errors=True)


def test_full_simulation_coordinates_all_seven_doors():
    tmp = _fresh("full_run")
    space, incidents = run_simulation(tmp, rounds=16)

    kinds = {inc["kind"] for inc in incidents}
    assert "transient" in kinds, "the scripted db spike must produce at least one transient incident"
    assert "chronic" in kinds, "the scripted payments drift must produce at least one chronic incident"
    assert all(inc["recovered"] for inc in incidents), "this simulation's mitigations always succeed by design"

    timeline = reconstruct_timeline(space)
    committed = [line for line in timeline if "decision_committed" in line]
    assert len(committed) == len(incidents), (
        "replay's reconstructed timeline must account for EVERY incident "
        "the live run produced — the audit trail has to be complete, not partial"
    )
    print(f"[PASS] full run: {len(incidents)} incidents across {kinds}, "
          f"all recovered, replay timeline matches exactly")
    shutil.rmtree(tmp, ignore_errors=True)


def test_determinism():
    tmp_a, tmp_b = _fresh("det_a"), _fresh("det_b")
    _, incidents_a = run_simulation(tmp_a, rounds=16, seed=11)
    _, incidents_b = run_simulation(tmp_b, rounds=16, seed=11)
    strip = lambda incs: [(i["service"], i["kind"], i["action"], i["recovered"]) for i in incs]
    assert strip(incidents_a) == strip(incidents_b), "same seed must produce the identical incident sequence"
    print("[PASS] same seed -> identical incident sequence across two independent runs")
    shutil.rmtree(tmp_a, ignore_errors=True)
    shutil.rmtree(tmp_b, ignore_errors=True)


if __name__ == "__main__":
    test_topology_and_blast_radius()
    test_signals_catches_transient_not_chronic()
    test_baseline_catches_the_chronic_drift_signals_misses()
    test_fork_commit_only_persists_on_real_recovery()
    test_full_simulation_coordinates_all_seven_doors()
    test_determinism()
    print("\nALL TESTS PASSED")
