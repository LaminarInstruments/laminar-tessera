"""
Laminar Health Triage — a tessera demo program.

Two watches stream heart-rate readings into one ward. For each patient:
signals flags whether the stream is too disordered to trust, graph finds
who's on call for that watch, agents forks two responses and commits the
one the decision rule picks, store records the alert durably, workflow
runs the (resumable) paging steps for anyone who got escalated, and
replay keeps the whole decision trail as an auditable event log.

One Space, six doors, one file. Kill the process after save() and the
whole ward state — graph, streams, decisions, alerts, workflow progress,
and the audit log — comes back exactly as it was.

Run:  python3 health_triage.py
"""
import tempfile

from tessera.space import Space
from tessera.agents import Program

ESCALATE_ENTROPY = 1.5  # bits; above this the HR stream is too disordered to trust

PATIENTS = {
    "patient-01": [74, 75, 74, 73, 74, 75, 74, 74],        # steady
    "patient-02": [60, 180, 65, 175, 70, 170, 160, 75],    # wild swings
}


def ingest(space, patient, hr_readings):
    """A watch's HR stream lands. Is it disordered enough to escalate?"""
    series = f"hr:{patient}"
    space.signals.measure(series, hr_readings)
    stats = space.signals.stats(series)
    escalate, entropy = space.signals.gate(hr_readings, threshold=ESCALATE_ENTROPY)
    print(f"[signals] {patient}: hr={hr_readings}")
    print(f"          mean={stats['mean']:.1f} std={stats['std']:.1f} "
          f"entropy={entropy:.2f} bits -> escalate={escalate}")
    return escalate, stats, entropy


def route(space, patient):
    """Walk patient -> watch -> on-call caregiver."""
    caregiver = None
    for device in space.graph.neighbors(patient):
        for neighbor in space.graph.neighbors(device):
            if neighbor != patient:
                caregiver = neighbor
    print(f"[graph]   {patient} -> caregiver={caregiver}")
    return caregiver


def decide(space, patient, stats, entropy, caregiver, escalate):
    """Observe, fork both responses to compare them, commit the one the rule picks."""
    agent = space.agents
    agent.observe({"mean_hr": stats["mean"], "entropy": entropy})

    watch_only = agent.fork()
    watch_only.run(Program("watch_only"), patient=patient)

    page_caregiver = agent.fork()
    page_caregiver.run(Program("page_caregiver"), patient=patient, caregiver=caregiver)

    chosen = page_caregiver if (escalate and caregiver) else watch_only
    agent.commit(chosen)
    decision = "page_caregiver" if chosen is page_caregiver else "watch_only"
    print(f"[agents]  {patient}: forked watch_only + page_caregiver -> committed {decision}")
    return decision


def record(space, patient, decision, stats):
    """Durable alert, all-or-nothing."""
    with space.store.transaction():
        space.store.put(f"alert:{patient}", {
            "decision": decision, "mean_hr": round(stats["mean"], 1), "status": "open",
        })
    print(f"[store]   alert:{patient} ->", space.store.get(f"alert:{patient}"))


def queue_escalation(space, patient, caregiver, mean_hr):
    """Register this patient's paging steps on the ward's shared workflow —
    resumable if the process dies mid-page."""
    def page(ctx):
        return {"caregiver": caregiver, "mean_hr": mean_hr}

    def log_vitals(ctx):
        space.replay.append({"event": "vitals_logged", "patient": patient, "mean_hr": mean_hr})
        return {"logged": True}

    space.workflow.add(f"page:{patient}", page)
    space.workflow.add(f"log_vitals:{patient}", log_vitals)


def main():
    tmp = tempfile.mkdtemp()
    space = Space("triage-ward-3", persistence=tmp)

    space.graph.connect("patient-01", "watch-01").connect("watch-01", "nurse-amy")
    space.graph.connect("patient-02", "watch-02").connect("watch-02", "nurse-amy")

    escalated = []
    for patient, hr in PATIENTS.items():
        escalate, stats, entropy = ingest(space, patient, hr)
        caregiver = route(space, patient)
        decision = decide(space, patient, stats, entropy, caregiver, escalate)
        record(space, patient, decision, stats)
        space.replay.append({"event": "triage_decided", "patient": patient, "decision": decision})
        if decision == "page_caregiver":
            escalated.append((patient, caregiver, stats["mean"]))

    for patient, caregiver, mean_hr in escalated:
        queue_escalation(space, patient, caregiver, mean_hr)

    if escalated:
        space.workflow.run({})
        print("[workflow] completed ->", space.workflow.completed())

    space.save()
    print("\n[save]    one file holds graph + signals + agents + store + workflow + replay")

    # ---- force a restart: reload EVERYTHING from the single file ----
    reloaded = Space.load("triage-ward-3", persistence=tmp)
    print("\n[restart] reloaded one Space; every door's state is intact:")
    for patient in PATIENTS:
        print(f"   store.alert:{patient}  =", reloaded.store.get(f"alert:{patient}"))
    print("   workflow.completed      =", reloaded.workflow.completed())

    def trail(acc, e):
        acc = acc or []
        return acc + [e["event"]]
    print("   replay.history          =", reloaded.replay.reconstruct(trail, []))

    assert reloaded.store.get("alert:patient-02")["decision"] == "page_caregiver"
    assert reloaded.store.get("alert:patient-01")["decision"] == "watch_only"
    assert "page:patient-02" in reloaded.workflow.completed()
    assert reloaded.replay.reconstruct(trail, []).count("triage_decided") == 2

    print("\nOK — signals -> graph -> agents -> store -> workflow -> replay, one Space, one file.")


if __name__ == "__main__":
    main()
