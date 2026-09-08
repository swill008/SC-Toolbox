"""Settings + cross-process summary persistence for the PlayTime Calculator.

Everything lives under ``~/.sctoolbox/playtime/`` (matching the convention used
by the Mission Database scanner):

    settings.json        user prefs: linked folder, preferred time format, cap
    summary.json         last computed headline — read by the launcher main menu
    sessions_cache.json  per-log-file parse cache so re-scans are near-instant
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

_DIR = os.path.join(os.path.expanduser("~"), ".sctoolbox", "playtime")
_SETTINGS_PATH = os.path.join(_DIR, "settings.json")
_SUMMARY_PATH = os.path.join(_DIR, "summary.json")
_CACHE_PATH = os.path.join(_DIR, "sessions_cache.json")

_DEFAULTS: dict[str, Any] = {
    "sc_folder": "",          # linked Star Citizen folder (root or channel)
    "time_format": "hours",   # "hours" | "days" | "calendar"
    "session_cap_hours": 0,   # 0 = off; otherwise clamp AFK sessions to N hours
    "scan_subfolders": True,  # recurse to pick up every channel (LIVE/PTU/...)
}


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("playtime: could not read %s: %s", path, exc)
        return {}


def _write_json(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except (OSError, TypeError) as exc:
        log.warning("playtime: could not write %s: %s", path, exc)


# ── User settings ────────────────────────────────────────────────────────────

def load_settings() -> dict:
    s = dict(_DEFAULTS)
    s.update(_read_json(_SETTINGS_PATH))
    # Coerce / clamp
    if s.get("time_format") not in ("hours", "days", "calendar"):
        s["time_format"] = "hours"
    try:
        s["session_cap_hours"] = max(0, float(s.get("session_cap_hours", 0)))
    except (TypeError, ValueError):
        s["session_cap_hours"] = 0
    s["scan_subfolders"] = bool(s.get("scan_subfolders", True))
    return s


def save_settings(s: dict) -> None:
    _write_json(_SETTINGS_PATH, s)


def get_sc_folder() -> str:
    return load_settings().get("sc_folder", "")


def set_sc_folder(folder: str) -> None:
    s = load_settings()
    s["sc_folder"] = (folder or "").replace("\\", "/")
    save_settings(s)


# ── Cross-process summary (read by the launcher) ─────────────────────────────

def write_summary(summary: dict) -> None:
    """Persist the headline so the launcher can show the total without rescanning."""
    summary = dict(summary)
    summary["updated_at"] = time.time()
    _write_json(_SUMMARY_PATH, summary)


def read_summary() -> dict:
    return _read_json(_SUMMARY_PATH)


# ── Per-file parse cache ─────────────────────────────────────────────────────

def load_cache() -> dict:
    return _read_json(_CACHE_PATH)


def save_cache(cache: dict) -> None:
    _write_json(_CACHE_PATH, cache)


def cache_path() -> str:
    return _CACHE_PATH


# ── Fun-stats per-file cache (full-content event scan) ───────────────────────

_FUN_CACHE_PATH = os.path.join(_DIR, "fun_cache.json")


def load_fun_cache() -> dict:
    return _read_json(_FUN_CACHE_PATH)


def save_fun_cache(cache: dict) -> None:
    _write_json(_FUN_CACHE_PATH, cache)
