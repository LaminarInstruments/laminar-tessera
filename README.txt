laminar-tessera 0.1.0  —  source-protected SDK (patent(s) pending)
Created by Darreck L. Bender II, Founder, Laminar Instruments.
darreck@laminarinstruments.com · laminarinstruments.com

FREE TO USE, including commercially, while you're building — see
LICENSE.txt Section 2. A commercial license only kicks in once a product
built on this SDK is doing real revenue (current threshold: $1M/year gross,
see LICENSE.txt for the exact terms). No tier gates, no feature paywall:
every door, free, until that point.

LICENSE.txt in this directory (and bundled in both wheels' dist-info) is a
license agreement, not a formality — by installing or using this software
you agree to its terms, which reserve all patent rights separately from the
software license (no hardware/chip implementation is licensed here; see
LICENSE.txt section 3) and prohibit reverse engineering for competing
purposes. Draft pending attorney review — read it before wide distribution.

READ THIS NEXT, based on who you are:
  building an app, want working code fast  -> COOKBOOK.md
  want every door's full contract           -> DEVELOPER_GUIDE.md
  want exact method signatures              -> API_REFERENCE.md
  an AI coding agent                        -> AGENTS.md (read this FIRST, not last)

WHAT'S HERE — there is more than one wheel; pick the one matching your
`python3 --version`, don't glob them together:
  laminar_tessera-0.1.0-cp313-cp313-macosx_10_13_universal2.whl
                                CPython 3.13, macOS (x86_64 + arm64)
  laminar_tessera-0.1.0-cp311-cp311-macosx_26_0_arm64.whl
                                CPython 3.11, macOS arm64 only — built and
                                verified on this machine; NOT tested on other
                                macOS versions or Intel Macs despite the tag
  src/                          the buildable source tree (rebuild for other
                                platforms/versions). Engine source lives in
                                src/build_src/ and is COMPILE-ONLY — it is
                                never copied into any wheel.
  Both wheels ship the engine as a compiled .so only — opcode internals are
  NOT in either of them.

INSTALL & USE
  python3 --version                              # check which wheel you need
  pip install laminar_tessera-0.1.0-cp313-*.whl   # or the cp311 one, not both
  python -c "import tessera; print(tessera.engine_info())"
  python -m tessera.selftest          # all seven doors, runs on the binary engine

NEED A DIFFERENT PYTHON VERSION OR OS? Rebuild — verified to actually work:
  cd src && python -m pip wheel . --no-build-isolation -w dist
  (needs: Cython>=3.0, setuptools, wheel, a C compiler)
  This is exactly how the cp311 wheel above was produced from the cp313
  source tree — the rebuild path is real, not theoretical.

FOR ALL PLATFORMS AT ONCE
  use cibuildwheel in CI — one wheel per OS/arch/Python. Neither shipped
  wheel here was built that way; both are single-machine builds.

WHAT SHIPS vs WHAT STAYS SECRET
  shipped readable : the tessera API (names + calls, no algorithms)
  shipped compiled : the 121-opcode engine (spu121, strict_v4) as machine code
  never shipped    : the engine .py source (the opcode implementations)
  still visible     : opcode NAMES (dict keys) — the public vocabulary
