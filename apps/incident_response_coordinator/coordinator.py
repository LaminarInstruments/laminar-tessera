"""
Incident Response Coordinator — the "everything together" flagship: every
one of Tessera's seven doors, coordinating on ONE shared Space, each one's
output feeding the next door's decision (not seven doors touched in
isolation).

Tessera components used, and how they actually depend on each other here:
    graph    (space.graph)    service dependency topology -> blast radius,
                               which sets incident PRIORITY
    signals  (space.signals)  per-service latency measurement -> flags a
                               TRANSIENT spike
    baseline (space.baseline) the SAME latency, tracked separately -> flags
                               a CHRONIC drift signals' static mean/std can
                               never catch (see apps/adaptive_baseline_monitor)
    agents   (space.agents)   fork()s a mitigation DECISION (which action,
                               what priority) in isolation; only commit()'d
                               if the workflow below actually resolves it —
                               "try a decision, keep it only if it works"
    workflow (standalone,     page_oncall -> apply_mitigation -> verify ->
              per incident)   close, crash-safe, the oncall/action it runs
                               with come from store (roster) and agents
                               (the forked decision)
    store    (space.store)    on-call roster + per-service hard latency caps
                               + which services currently have an open
                               incident (durable config + coordination state)
    replay   (space.replay)   every decision/step logged; reconstruct() at
                               the end rebuilds the whole incident timeline
                               from events ALONE, independent of live state

WHY workflow is standalone, not space.workflow: a Workflow instance tracks
step-completion by step NAME on one object. Sharing space.workflow across
multiple incidents would mean incident 2's "page_oncall" reads as
already-done the moment incident 1's checkpoints — wrong (same lesson as
crash_recoverable_order_processor's per-order workflow). Each incident gets
its own Workflow, persisted alongside the Space.

Usage:
    python3 coordinator.py run <persist_dir> <rounds>
    python3 coordinator.py trigger-incident <persist_dir> <service> <transient|chronic>
    python3 coordinator.py resume-incident <persist_dir>
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tessera.space import Space
from tessera.agents import Program
from tessera.workflow import Workflow
from tessera.baseline import BaselineSet

MITIGATION_WINDOW_SECONDS = 2.0

# Dependency topology: (a, b) means a calls b.
EDGES = [
    ("api", "auth"), ("api", "db"), ("api", "cache"),
    ("payments", "db"), ("payments", "auth"),
]
SERVICES = sorted({s for edge in EDGES for s in edge})
ROSTER = {"api": "nina", "auth": "nina", "cache": "nina",
          "db": "marcus", "payments": "marcus"}
HARD_CAP_MS = 400.0          # chronic-drift ceiling, per service
TRANSIENT_SPIKE_ROUND = 6    # a single-round latency spike on "db"
NORMAL_LATENCY = {"api": 80, "auth": 40, "cache": 15, "db": 60, "payments": 90}
CHRONIC_DRIFT_SERVICE = "payments"   # creeps upward every round (a "leak")
CHRONIC_DRIFT_PER_ROUND = 28


def mitigation_log_path(persist_dir, incident_id):
    return Path(persist_dir) / f"mitigation_{incident_id}.log"


def marker_path(persist_dir, incident_id):
    return Path(persist_dir) / f"mitigating_{incident_id}.marker"


def already_mitigated(persist_dir, incident_id):
    return mitigation_log_path(persist_dir, incident_id).exists()


def _open_space(persist_dir, name="ops"):
    return Space.open(name, persistence=persist_dir)


def _open_baselines(persist_dir):
    """One BaselineSet tracks all five services' latency baselines
    independently — the engine's feedback state (alpha/beta/ema) is a
    single triple per AdaptiveBaseline, not keyed by series (see
    AGENTS.md's baseline contract; BaselineSet.open()'s own docstring
    explains why it manages one AdaptiveBaseline per key rather than one
    shared engine). Using space.baseline directly for all five services
    would silently mix their readings into one shared drift signal.

    Replaces an earlier hand-rolled {service: AdaptiveBaseline.open(...)}
    dict (the first real caller that motivated adding BaselineSet)."""
    baselines = BaselineSet.open("baseline", persistence=persist_dir)
    for s in SERVICES:
        baselines[s].set_rate(alpha=0.5, beta=0.5)   # adapt fast enough to
                                                        # catch the drift
                                                        # within this demo's
                                                        # round count
    return baselines


def setup_topology(space):
    """Idempotent: only wires the graph/roster/caps once per Space."""
    if space.store.get("topology_ready"):
        return
    for a, b in EDGES:
        space.graph.connect(a, b)
    space.store.put("roster", dict(ROSTER))
    space.store.put("hard_caps", {s: HARD_CAP_MS for s in SERVICES})
    space.store.put("open_incidents", {})
    space.store.put("topology_ready", True)
    space.save()


def reading_for(service, round_i, rng, drift_reset_at=0):
    """Deterministic (seeded) synthetic latency reading for one service in
    one round — a scripted transient spike on `db`, a chronic upward drift
    on `payments`, ordinary jitter on everything else. Not random noise
    pretending to be real data: these two scripted conditions are exactly
    what signals vs. baseline are each supposed to catch, so the demo
    actually exercises the thing it claims to.

    `drift_reset_at` is the round the service's last chronic incident was
    resolved at (0 if none yet) — the drift term counts from THAT round,
    not from absolute time, so a scale_up that actually fixed the problem
    is reflected in the next round's reading instead of the synthetic data
    immediately re-triggering another incident regardless of the fix."""
    base = NORMAL_LATENCY[service]
    jitter = rng.uniform(-6, 6)
    if service == "db" and round_i == TRANSIENT_SPIKE_ROUND:
        return base + 260 + jitter   # one-round spike, back to normal after
    if service == CHRONIC_DRIFT_SERVICE:
        return base + CHRONIC_DRIFT_PER_ROUND * (round_i - drift_reset_at) + jitter
    return base + jitter


def blast_radius(space, service):
    """How many OTHER services are within 2 hops in the dependency graph —
    the graph door's output, used to set incident priority."""
    reach = space.graph.reach(service) or {}
    return sum(1 for node, hops in reach.items() if node != service and hops <= 2)


def check_transient(space, service, known_flagged_count):
    """signals' job: did a NEW spike just show up relative to this series'
    own history? `anomalies()` is a population check over the WHOLE
    series, so a single real spike stays in the flagged list forever
    after — checking "is anything flagged" would fire every round from
    then on, not once. Checking "did the flagged COUNT just increase"
    fires exactly once per new anomaly instead (still subject to
    anomalies()'s one-reading latency: a spike at index i is only
    reflected once a reading after it exists, so this fires the round
    AFTER the actual spike, not the same round — verified, not assumed).
    Returns (is_new, new_count)."""
    try:
        flagged = space.signals.anomalies(service, threshold=2.5)
    except ValueError:
        return False, known_flagged_count
    return len(flagged) > known_flagged_count, len(flagged)


def check_chronic(baseline, reading, hard_cap):
    """baseline's job: is the LEARNED, drift-following average creeping
    past a hard ceiling? signals' static mean/std cannot catch this — once
    enough of the series sits at an elevated level, that level stops
    looking anomalous (see apps/adaptive_baseline_monitor's own finding).
    `baseline` is the per-SERVICE standalone instance (see _open_baselines)."""
    baseline.learn(reading)
    return baseline.value() > hard_cap


def open_incident(space, service, kind, priority):
    """agents' job: FORK the live state and try a mitigation decision in
    isolation. Nothing here is visible outside the branch until
    resolve_incident() commits it — if the workflow below fails to
    actually recover the service, the decision is simply discarded,
    never polluting the live Space with a mitigation that didn't work."""
    action = "restart" if kind == "transient" else "scale_up"
    incident_id = f"{service}-{kind}-{int(time.time() * 1000)}"
    branch = space.agents.fork()
    branch.run(Program("decide_mitigation"), incident=incident_id,
               service=service, kind=kind, action=action, priority=priority)
    return branch, incident_id, action


def run_incident_workflow(persist_dir, space, incident_id, service, action, rng):
    """The standalone, crash-safe workflow. `apply_mitigation` is the one
    step with a real external effect (a mitigation-log write) — marked with
    a marker file + sleep window so an external harness can SIGKILL this
    process mid-step (see crash_test.py), and guarded by an idempotency
    check so a resume after that kill does not repeat the real effect."""
    name = f"incident-{incident_id}"
    path = Path(persist_dir) / f"{name}.workflow.json"
    wf = Workflow.load(name, persistence=persist_dir) if path.exists() else Workflow(name, persistence=persist_dir)

    def page_oncall(ctx):
        oncall = space.store.get("roster", {}).get(ctx["service"], "unknown")
        space.replay.append({"event": "paged", "incident": incident_id,
                              "service": ctx["service"], "oncall": oncall})
        space.save()
        return {"paged": oncall}

    def apply_mitigation(ctx):
        if already_mitigated(persist_dir, incident_id):
            return {"applied": ctx["action"], "skipped_already_done": True}
        with open(mitigation_log_path(persist_dir, incident_id), "a") as f:
            f.write(json.dumps({"incident": incident_id, "action": ctx["action"]}) + "\n")
        marker_path(persist_dir, incident_id).write_text("mitigating")
        time.sleep(MITIGATION_WINDOW_SECONDS)
        space.replay.append({"event": "mitigation_applied", "incident": incident_id,
                              "action": ctx["action"]})
        space.save()
        return {"applied": ctx["action"]}

    def verify_recovery(ctx):
        # post-mitigation reading: back to normal, proving the action worked
        recovered_reading = NORMAL_LATENCY[ctx["service"]] + rng.uniform(-6, 6)
        space.signals.measure(ctx["service"], recovered_reading)
        recovered = recovered_reading < HARD_CAP_MS
        space.replay.append({"event": "recovery_verified", "incident": incident_id,
                              "recovered": recovered})
        space.save()
        return {"recovered": recovered}

    def close_incident(ctx):
        space.replay.append({"event": "incident_closed", "incident": incident_id,
                              "recovered": ctx["verify_recovery"]["recovered"]})
        space.save()
        return {"closed": True}

    wf.add("page_oncall", page_oncall)
    wf.add("apply_mitigation", apply_mitigation)
    wf.add("verify_recovery", verify_recovery)
    wf.add("close_incident", close_incident)
    return wf, wf.run({"service": service, "action": action})


def resolve_incident(space, branch, incident_id, service, succeeded):
    """Commit the forked decision only if the workflow actually recovered
    the service — the real payoff of fork()/commit() over just mutating
    live state directly.

    No force=True needed: commit()'s staleness check now compares a
    per-field generation counter (bumped only by observe()/run() calls
    against agents' OWN unit), not the whole engine's op count — so the
    workflow's own signals.measure()/replay.append() calls in between
    fork() and here no longer make this look stale. (An earlier version
    of this app needed force=True here; that was itself the finding that
    motivated fixing the staleness check to be per-field instead of
    engine-wide.)"""
    open_incidents = space.store.get("open_incidents", {})
    if succeeded:
        space.agents.commit(branch)
        space.replay.append({"event": "decision_committed", "incident": incident_id})
    else:
        space.replay.append({"event": "decision_discarded", "incident": incident_id})
    open_incidents.pop(service, None)
    space.store.put("open_incidents", open_incidents)
    space.save()


def run_simulation(persist_dir, rounds, seed=7):
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    space = _open_space(persist_dir)
    setup_topology(space)
    rng = random.Random(seed)
    baselines = _open_baselines(persist_dir)
    drift_reset_at = {s: 0 for s in SERVICES}
    flagged_count = {s: 0 for s in SERVICES}

    incidents = []
    for r in range(rounds):
        open_incidents = space.store.get("open_incidents", {})
        for service in SERVICES:
            reading = reading_for(service, r, rng, drift_reset_at[service])
            space.signals.measure(service, reading)
            hard_cap = space.store.get("hard_caps", {})[service]

            if service in open_incidents:
                continue  # already being handled this run

            transient, flagged_count[service] = check_transient(space, service, flagged_count[service])
            chronic = check_chronic(baselines[service], reading, hard_cap)
            baselines[service].save()
            if not (transient or chronic):
                continue

            kind = "transient" if transient else "chronic"
            priority = "P1" if blast_radius(space, service) >= 2 else "P2"
            space.replay.append({"event": "anomaly_detected", "service": service,
                                  "round": r, "kind": kind, "priority": priority})

            branch, incident_id, action = open_incident(space, service, kind, priority)
            open_incidents[service] = incident_id
            space.store.put("open_incidents", open_incidents)
            space.save()

            wf, ctx = run_incident_workflow(persist_dir, space, incident_id, service, action, rng)
            recovered = ctx["verify_recovery"]["recovered"]
            resolve_incident(space, branch, incident_id, service, recovered)
            if recovered and kind == "chronic":
                drift_reset_at[service] = r + 1
            incidents.append({"incident": incident_id, "service": service, "kind": kind,
                               "priority": priority, "action": action,
                               "recovered": recovered})
            open_incidents = space.store.get("open_incidents", {})

    return space, incidents


def reconstruct_timeline(space):
    """Prove replay is a real, self-sufficient audit trail: rebuild the
    whole incident history from events ALONE (never from live state) and
    hand back one line per incident lifecycle event."""
    def fold(timeline, event):
        timeline = list(timeline)
        timeline.append(f"[{event['event']}] {json.dumps({k: v for k, v in event.items() if k != 'event'})}")
        return timeline
    return space.replay.reconstruct(fold, initial=[])


def current_incident_marker(persist_dir):
    return Path(persist_dir) / "current_incident.json"


def trigger_one_incident(persist_dir, service, kind):
    """Used by crash_test.py: open and run exactly ONE incident end-to-end,
    outside the round-based simulation loop, so an external harness has a
    precise, single target to SIGKILL mid-workflow. Writes the incident_id
    + action to a known file before running the workflow, so a resumed
    process (see resume_one_incident) knows what it's resuming."""
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    space = _open_space(persist_dir)
    setup_topology(space)
    priority = "P1" if blast_radius(space, service) >= 2 else "P2"
    branch, incident_id, action = open_incident(space, service, kind, priority)
    current_incident_marker(persist_dir).write_text(
        json.dumps({"incident_id": incident_id, "service": service, "action": action}))
    open_incidents = space.store.get("open_incidents", {})
    open_incidents[service] = incident_id
    space.store.put("open_incidents", open_incidents)
    space.save()

    rng = random.Random(1)
    wf, ctx = run_incident_workflow(persist_dir, space, incident_id, service, action, rng)
    resolve_incident(space, branch, incident_id, service, ctx["verify_recovery"]["recovered"])
    return wf, ctx


def resume_one_incident(persist_dir):
    """Resume (or run fresh) just the one incident recorded by
    trigger_one_incident — used after a SIGKILL to prove the workflow
    picks back up correctly without re-running the already-checkpointed
    external effect."""
    info = json.loads(current_incident_marker(persist_dir).read_text())
    space = _open_space(persist_dir)
    rng = random.Random(1)
    wf, ctx = run_incident_workflow(persist_dir, space, info["incident_id"],
                                     info["service"], info["action"], rng)
    print("completed steps:", wf.completed())
    return wf, ctx


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "run":
        _, _, persist_dir, rounds = sys.argv[:4]
        space, incidents = run_simulation(persist_dir, int(rounds))
        print(f"\n{len(incidents)} incident(s) handled:")
        for inc in incidents:
            print(f"  {inc['service']:9s} {inc['kind']:9s} {inc['priority']} "
                  f"-> {inc['action']:10s} recovered={inc['recovered']}")
        print(f"\nward-wide committed decisions: {space.agents.state()}")
        print(f"\n--- reconstructed timeline (from replay alone) ---")
        for line in reconstruct_timeline(space):
            print(" ", line)
    elif cmd == "trigger-incident":
        _, _, persist_dir, service, kind = sys.argv[:5]
        wf, ctx = trigger_one_incident(persist_dir, service, kind)
        print("completed steps:", wf.completed())
    elif cmd == "resume-incident":
        _, _, persist_dir = sys.argv[:3]
        resume_one_incident(persist_dir)
    else:
        print(__doc__)
        sys.exit(1)
