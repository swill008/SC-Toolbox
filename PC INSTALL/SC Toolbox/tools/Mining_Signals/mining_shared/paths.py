"""Single source of truth for Mining_Signals file-path resolution.

Previously the same logic was duplicated (with drift) across
``ui/app.py`` and ``scripts/signature_finder_viewer.py`` — including
a silent-fallback divergence where ``app.py`` would fall back to the
in-tool dir on a ``makedirs`` failure while the viewer kept reading
the unreachable persistent path.  Consolidating here means both
processes resolve identical paths in identical ways, eliminating
that entire bug class (audit item #2).

Both the main app (which WRITES the config) and the
``signature_finder_viewer`` popout (a separate process that READS
the config) MUST import from this module rather than recomputing
the paths locally.
"""

from __future__ import annotations

import os
from pathlib import Path

# Resolve TOOL_DIR (the Mining_Signals folder) from THIS FILE's
# location — works regardless of which process imports the module
# and regardless of where Velopack chose to deploy ``current\``.
TOOL_DIR: Path = Path(__file__).resolve().parent.parent


def _localappdata() -> str:
    """Resolve ``%LOCALAPPDATA%`` with a sane fallback for embedded
    installs where the env var isn't set."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return base


def persistent_config_dir() -> str:
    """Return the directory where the cross-upgrade config lives.

    Creates it if needed.  Falls back to the in-tool dir if
    ``%LOCALAPPDATA%`` can't be reached / created — rare in practice
    (Controlled Folder Access, locked-down corporate machines).

    The fallback is the reason this lives in a shared module: when
    the app falls back here, the viewer must follow it to the same
    location, otherwise the viewer reads the unreachable persistent
    path and the app silently writes to the in-tool path (the v2.2.9
    user-version drift class).
    """
    target = os.path.join(_localappdata(), "SC_Toolbox", "mining_signals")
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except OSError:
        # Fallback: in-tool dir.  Settings won't survive Velopack
        # upgrades from here, but the app keeps working — and the
        # viewer reaches the same place via the same fallback.
        return str(TOOL_DIR)


def config_file() -> str:
    """Path to the persistent Mining_Signals config (the file
    ``ui/app.py`` reads/writes for ``ocr_region``, ``hud_region``,
    ship loadouts, etc.).  Returns ``str`` for compatibility with the
    existing ``os.path.*`` call sites in ``ui/app.py``."""
    return os.path.join(persistent_config_dir(), "config.json")


def legacy_config_file() -> str:
    """Path to the in-tool config file shipped with the installer.

    Used as a one-shot migration source on first run after the
    v2.2.7 upgrade that introduced the persistent path.  Always
    resolves under ``TOOL_DIR`` regardless of who imports this
    module — that's the whole point of routing it through here."""
    return str(TOOL_DIR / "mining_signals_config.json")


def resolve_config_path() -> Path:
    """Pick which config file an external reader (e.g. the
    ``signature_finder_viewer`` popout) should open:

      * persistent if it exists (canonical, post-migration);
      * else legacy if it exists (pre-migration / first-run);
      * else persistent (the caller's ``is_file()`` check will fall
        through and they can handle the absence).

    Returns ``Path`` to match the popout's pre-refactor type.
    """
    persistent = Path(config_file())
    if persistent.is_file():
        return persistent
    legacy = Path(legacy_config_file())
    return legacy if legacy.is_file() else persistent
