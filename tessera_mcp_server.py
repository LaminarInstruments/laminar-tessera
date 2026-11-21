#!/usr/bin/env python3
"""
Tessera Memory — an MCP server that gives an AI assistant a real, persistent
memory backed by the Tessera SDK (laminar-tessera).

Plug this into Claude Desktop (or any MCP client) and the assistant can:
  - remember facts and recall them in a brand-new conversation, days later
  - keep a running journal of notes
  - track numbers over time and spot when one is off
  - record how things relate

Everything is stored on disk by Tessera, so it survives across chats and
restarts. Nothing leaves the machine.

Memory lives in one shared Tessera Space at:  ~/.tessera/claude_memory.space.json
"""
import os
from mcp.server.fastmcp import FastMCP
from tessera.space import Space

mcp = FastMCP("tessera-memory")

# One shared Tessera Space, loaded from disk if it already exists (.open()),
# created fresh otherwise. All tools read/write this same persisted state.
MEM_NAME = "claude_memory"
# Memory location: ~/.tessera by default; override with TESSERA_MEMORY_DIR.
_persistence = os.environ.get("TESSERA_MEMORY_DIR") or "local"
space = Space.open(name=MEM_NAME, persistence=_persistence)


def _persist():
    try:
        space.save()
    except Exception:
        pass  # in-memory fallback should never happen here, but never crash a tool


# ---------------------------------------------------------------- facts (store)
@mcp.tool()
def remember(key: str, value: str) -> str:
    """Save a fact to long-term memory under a short key.
    Use this whenever the user shares something worth remembering later
    (a name, a preference, a date, a goal). Example: remember("daughter_birthday", "March 3")."""
    space.store.put(str(key), value)
    _persist()
    return f"Remembered: {key} = {value}"


@mcp.tool()
def recall(key: str) -> str:
    """Look up a fact saved earlier with remember(). Returns the stored value or a 'not found' note."""
    val = space.store.get(str(key), default=None)
    return f"{key} = {val}" if val is not None else f"I have nothing stored under '{key}'."


@mcp.tool()
def list_memories() -> str:
    """List every fact currently in long-term memory (all key = value pairs)."""
    items = space.store.items()
    if not items:
        return "Long-term memory is empty."
    return "\n".join(f"- {k} = {v}" for k, v in items.items())


@mcp.tool()
def forget(key: str) -> str:
    """Permanently delete a remembered fact by its key."""
    space.store.delete(str(key))
    _persist()
    return f"Forgot '{key}'."


# ---------------------------------------------------------------- journal (replay)
@mcp.tool()
def note(text: str) -> str:
    """Append a note to the user's ongoing journal/timeline. Use for events, decisions,
    or anything worth keeping a dated record of."""
    import datetime
    space.replay.append({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "text": text})
    _persist()
    return "Noted."


@mcp.tool()
def timeline(limit: int = 20) -> str:
    """Show the most recent journal notes (newest last). `limit` caps how many are returned."""
    events = space.replay.events()
    if not events:
        return "The journal is empty."
    recent = events[-int(limit):]
    return "\n".join(f"[{e.get('ts','?')}] {e.get('text','')}" for e in recent)


# ---------------------------------------------------------------- numbers (signals)
@mcp.tool()
def track(metric: str, value: float) -> str:
    """Record one numeric reading for a named metric over time
    (e.g. track("resting_hr", 58)). Readings accumulate; use trend() to analyze."""
    space.signals.measure(str(metric), [float(value)])
    _persist()
    return f"Tracked {metric} = {value}"


@mcp.tool()
def trend(metric: str) -> str:
    """Summarize a tracked metric: count, average, spread, and any readings that look unusual
    (more than 3 standard deviations from the average)."""
    try:
        s = space.signals.stats(str(metric))
    except Exception:
        return f"No readings yet for '{metric}'. Use track('{metric}', <number>) first."
    try:
        odd = space.signals.anomalies(str(metric), threshold=3)
    except Exception:
        odd = []
    out = f"{metric}: {s['n']} readings · average {s['mean']:.2f} · spread {s['std']:.2f}"
    if odd:
        out += f" · unusual reading indices: {odd}"
    return out


# ---------------------------------------------------------------- relationships (graph)
@mcp.tool()
def relate(a: str, b: str) -> str:
    """Record that two things are connected (e.g. relate("Project X", "Alice")).
    Build up a web of relationships you can query later with connections()."""
    try:
        space.graph.connect(str(a), str(b))
        _persist()
        return f"Linked {a} <-> {b}"
    except ValueError as e:
        return f"Could not link: {e}"


@mcp.tool()
def connections(thing: str) -> str:
    """List everything directly connected to `thing` in the relationship web."""
    nbrs = space.graph.neighbors(str(thing))
    return f"{thing} is connected to: {', '.join(map(str, nbrs))}" if nbrs else f"'{thing}' has no recorded connections."


# ---------------------------------------------------------------- status
@mcp.tool()
def memory_status() -> str:
    """Summarize everything currently in memory: how many facts, journal notes,
    and relationships are stored. Backed by the Tessera SDK."""
    facts = len(space.store.items())
    notes = len(space.replay.events())
    things = space.graph.rank()
    import tessera
    return (f"Tessera memory ({tessera.__version__}): "
            f"{facts} facts · {notes} journal notes · "
            f"{len(things)} connected things.")


if __name__ == "__main__":
    mcp.run()   # stdio transport — what Claude Desktop speaks
