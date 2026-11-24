================================================================================
  TESSERA  —  by Laminar Instruments
================================================================================
Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com  ·  laminarinstruments.com  ·  Patent(s) pending.
--------------------------------------------------------------------------------

Tessera is one small engine for the things software has to remember: state,
relationships, measurements, decisions, durable steps, and an audit trail.
One install, no server, works offline, the same result every run.

You pick a "door" for the job you're doing and call plain methods. That's the
whole API — seven doors over one engine.

--------------------------------------------------------------------------------
LICENSE  (read LICENSE.txt — it is an agreement, not a formality)
--------------------------------------------------------------------------------
Free to use, including commercially, while you build. A commercial license is
required only once a product built on Tessera reaches real revenue (current
threshold: US$1,000,000/year gross — see LICENSE.txt for exact terms). No tier
gates, no feature paywall: every door is free until that point. Installing or
using the software constitutes acceptance of LICENSE.txt. All patent rights are
reserved separately from the software license.

--------------------------------------------------------------------------------
INSTALL
--------------------------------------------------------------------------------
Easiest — from PyPI, picks the right wheel for you automatically:

  pip install laminar-tessera

Or pick the wheel file matching your platform/Python version directly:

  python3 --version
  pip install laminar_tessera-0.1.5-cp313-cp313-macosx_10_13_universal2.whl   # Python 3.13, macOS
  # or
  pip install laminar_tessera-0.1.5-cp311-cp311-macosx_26_0_arm64.whl         # Python 3.11, macOS Apple Silicon
  # or
  pip install laminar_tessera-0.1.5-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl   # Python 3.12, Linux x86-64

Verify:
  python -c "import tessera; print(tessera.engine_info())"
  python -m tessera.selftest

Found a bug? File it: https://github.com/LaminarInstruments/laminar-tessera/issues
Need a build for another platform or Python version? Contact
darreck@laminarinstruments.com.

--------------------------------------------------------------------------------
WHERE TO START  (based on who you are)
--------------------------------------------------------------------------------
  Building an app, want working code fast  ->  COOKBOOK.md
  Want every door's full contract          ->  DEVELOPER_GUIDE.md
  Want exact method signatures             ->  API_REFERENCE.md
  An AI coding agent                       ->  AGENTS.md  (read this first)

--------------------------------------------------------------------------------
THE SEVEN DOORS
--------------------------------------------------------------------------------
  agents    remember & decide            from tessera.agents   import Field
  store     durable key/value            from tessera.store    import Store
  graph     track connections            from tessera.graph    import Graph
  signals   watch the numbers            from tessera.signals  import Signals
  workflow  finish multi-step jobs       from tessera.workflow import Workflow
  replay    prove what happened          from tessera.replay   import EventLog
  baseline  learn what "normal" is       from tessera.baseline import AdaptiveBaseline
  space     all of the above, one state  from tessera.space    import Space

Zero third-party dependencies. Private and offline — nothing leaves the machine.

© Laminar Instruments. Tessera is proprietary software. Patent(s) pending.
