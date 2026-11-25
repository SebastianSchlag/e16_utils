#!/usr/bin/env python3
"""
Generate MMNRPMFULL.oxie16 — an OXI E16 scene that drives every MicroMonsta 2
parameter via NRPN, laid out exactly per ../E16/mm_nrpm_layout.txt.

All NRPN turn_actions use the proven shape (type=9, mode=7, upper=16383,
output=12) that survives the bridge's CC 6/38 frame without snapping to 0.
The Off/On parameters in the layout (e1x, e2x, e3x) get a push_action that
flips between 0 and 1 instead of a turn.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mm2_bridge import PARAMS

SCENE_FILENAME = "MMNRPMFULL.oxie16"

# Where the scene goes is per-machine, so it comes in on the command line.
# Set $E16_SCENE_DIR to your E16 Scenes folder to skip typing it every time.
SCENE_DIR_ENV = "E16_SCENE_DIR"

# 32-byte E16 scene icon (8x8x2 bitmap). Lifted from MMNRPM.oxie16 so the
# scene shows up with the same MicroMonsta-style glyph in the device picker.
SCENE_ICON: list[int] = [
    0, 0, 4, 8, 32, 128, 4, 36, 1, 0, 72, 72, 0, 0, 234, 174,
    218, 182, 182, 218, 0, 0, 238, 238, 238, 238, 222, 246, 222, 246, 0, 0,
]

# MIDI channel for the layout pages — matches the channel mm2_bridge.py sends
# on by default (`--channel 1` ⇒ channel index 0; pages override per encoder
# but Electra also expects a sensible page-level value).
LAYOUT_PAGE_CHANNEL = 5

# key -> (nrpn, is_14bit, title)
PARAM_BY_KEY = {key: (nrpn, long, title)
                for _sx, nrpn, long, key, title in PARAMS}

# Off/On params from nrpn_mappings.md — only e1x/e2x/e3x appear in the layout,
# but the full set is listed so the generator stays correct if the layout grows.
ONOFF_KEYS = {"e1x", "e2x", "e3x", "osx", "aen", "ala"}

# Layout to produce.
LAYOUT: list[tuple[str, list[list[str]]]] = [
    ("OSC", [
        ["o1a", "o1s", "o1c", "o1f"],
        ["o2a", "o2s", "o2c", "o2f"],
        ["o3a", "o3s", "o3c", "o3f"],
        ["mx1", "mx2", "mx3", "nze"],
    ]),
    ("FLT", [
        ["fty", "cut", "res", "fen"],
        ["drv", "fkb", "ffm", "fch"],
        ["fes", "vcs", "-",   "-"  ],
        ["-",   "-",   "-",   "-"  ],
    ]),
    ("FX", [
        ["xdl", "xdf", "xdt", "xdm"],
        ["xrl", "xrm", "xrt", "-"  ],
        ["xch", "xeq", "-",   "-"  ],
        ["-",   "-",   "-",   "-"  ],
    ]),
    ("ENV", [
        ["e1a", "e1d", "e1s", "e1r"],
        ["e2a", "e2d", "e2s", "e2r"],
        ["e3a", "e3d", "e3s", "e3r"],
        ["e1x", "e2x", "e3x", "-"  ],
    ]),
    ("LFO", [
        ["l1w", "l1s", "l1m", "-"  ],
        ["l2w", "l2s", "l2m", "-"  ],
        ["l3w", "l3s", "l3m", "-"  ],
        ["-",   "-",   "-",   "-"  ],
    ]),
    ("PERF", [
        ["mix", "bpm", "bdo", "bup"],
        ["vde", "ode", "vun", "vmo"],
        ["psp", "psm", "gld", "-"  ],
        ["t1a", "t1b", "t2a", "t2b"],
    ]),
    # 10 mod-matrix slots × 3 cells (src/dest/amount) → one row per slot,
    # 4 slots per page → 3 pages (last one half-empty).
    ("MOD1", [
        ["m1s", "m1d", "m1a", "-"],
        ["m2s", "m2d", "m2a", "-"],
        ["m3s", "m3d", "m3a", "-"],
        ["m4s", "m4d", "m4a", "-"],
    ]),
    ("MOD2", [
        ["m5s", "m5d", "m5a", "-"],
        ["m6s", "m6d", "m6a", "-"],
        ["m7s", "m7d", "m7a", "-"],
        ["m8s", "m8d", "m8a", "-"],
    ]),
    ("MOD3", [
        ["m9s", "m9d", "m9a", "-"],
        ["m0s", "m0d", "m0a", "-"],
        ["-",   "-",   "-",   "-"],
        ["-",   "-",   "-",   "-"],
    ]),
]

# Conceptual groups — each group gets one OXI palette hue (multiples of 10).
# Encoders that "belong together" on a page share a hue so the layout reads at
# a glance. Hues are intentionally spread (not adjacent) within a page.
KEY_GROUP: dict[str, str] = {
    # OSC page — one hue per oscillator + one for the mix row.
    "o1a": "osc1", "o1s": "osc1", "o1c": "osc1", "o1f": "osc1",
    "o2a": "osc2", "o2s": "osc2", "o2c": "osc2", "o2f": "osc2",
    "o3a": "osc3", "o3s": "osc3", "o3c": "osc3", "o3f": "osc3",
    "mx1": "mix",  "mx2": "mix",  "mx3": "mix",  "nze": "mix",
    # FLT page — filter core vs. velocity sensitivities.
    "cut": "filter", "res": "filter", "fty": "filter", "drv": "filter",
    "fen": "filter", "fkb": "filter", "ffm": "filter", "fch": "filter",
    "fes": "vel",    "vcs": "vel",
    # FX page — one hue per effect block.
    "xdl": "delay",  "xdf": "delay",  "xdt": "delay",  "xdm": "delay",
    "xrl": "reverb", "xrm": "reverb", "xrt": "reverb",
    "xch": "fx",     "xeq": "fx",
    # ENV page — one hue per envelope (ADSR + reset all together).
    "e1a": "env1", "e1d": "env1", "e1s": "env1", "e1r": "env1", "e1x": "env1",
    "e2a": "env2", "e2d": "env2", "e2s": "env2", "e2r": "env2", "e2x": "env2",
    "e3a": "env3", "e3d": "env3", "e3s": "env3", "e3r": "env3", "e3x": "env3",
    # LFO page — one hue per LFO.
    "l1w": "lfo1", "l1s": "lfo1", "l1m": "lfo1",
    "l2w": "lfo2", "l2s": "lfo2", "l2m": "lfo2",
    "l3w": "lfo3", "l3s": "lfo3", "l3m": "lfo3",
    # PERF page — global, voice, pan/glide, mult ops as four blocks.
    "mix": "perf_master", "bpm": "perf_master",
    "bdo": "perf_master", "bup": "perf_master",
    "vde": "perf_voice",  "ode": "perf_voice",
    "vun": "perf_voice",  "vmo": "perf_voice",
    "psp": "perf_pan",    "psm": "perf_pan",    "gld": "perf_pan",
    "t1a": "mult", "t1b": "mult", "t2a": "mult", "t2b": "mult",
    # MOD pages — one hue per matrix slot so source/dest/amount of a slot pair.
    "m1s": "mat1", "m1d": "mat1", "m1a": "mat1",
    "m2s": "mat2", "m2d": "mat2", "m2a": "mat2",
    "m3s": "mat3", "m3d": "mat3", "m3a": "mat3",
    "m4s": "mat4", "m4d": "mat4", "m4a": "mat4",
    "m5s": "mat5", "m5d": "mat5", "m5a": "mat5",
    "m6s": "mat6", "m6d": "mat6", "m6a": "mat6",
    "m7s": "mat7", "m7d": "mat7", "m7a": "mat7",
    "m8s": "mat8", "m8d": "mat8", "m8a": "mat8",
    "m9s": "mat9", "m9d": "mat9", "m9a": "mat9",
    "m0s": "mat10", "m0d": "mat10", "m0a": "mat10",
    # Mult/Lag amounts not in the current layout — kept for future moves.
    "g1s": "lag", "g1a": "lag",
}

GROUP_COLOR: dict[str, int] = {
    "osc1": 0, "osc2": 20, "osc3": 40, "mix": 70,
    "filter": 50, "vel": 80,
    "delay": 30, "reverb": 60, "fx": 80,
    "env1": 40, "env2": 60, "env3": 80,
    "lfo1": 30, "lfo2": 60, "lfo3": 90,
    "perf_master": 0, "perf_voice": 30,
    "perf_pan": 60, "mult": 80,
    # Matrix slots: spread across all 10 hues so neighbouring slots don't blur.
    "mat1": 0,  "mat2": 10, "mat3": 20, "mat4": 30, "mat5": 40,
    "mat6": 50, "mat7": 60, "mat8": 70, "mat9": 80, "mat10": 90,
    "lag": 90,
}


def color_for_key(key: str) -> int:
    return GROUP_COLOR.get(KEY_GROUP.get(key, ""), 0)

# Short titles fit the device's tiny page-tab area.
TITLE_OVERRIDES = {
    "mx1": "Osc 1 Lv", "mx2": "Osc 2 Lv", "mx3": "Osc 3 Lv", "nze": "Noise Lv",
    "o1a": "Osc 1 Al", "o1s": "Osc 1 Sh", "o1c": "Osc 1 Tu", "o1f": "Osc 1 Ft",
    "o2a": "Osc 2 Al", "o2s": "Osc 2 Sh", "o2c": "Osc 2 Tu", "o2f": "Osc 2 Ft",
    "o3a": "Osc 3 Al", "o3s": "Osc 3 Sh", "o3c": "Osc 3 Tu", "o3f": "Osc 3 Ft",
    "cut": "Cutoff",   "res": "Reso",     "fty": "Flt Type", "drv": "Drive",
    "fen": "Flt Env",  "fkb": "Flt Kbd",  "ffm": "Flt FM",   "fch": "Flt Char",
    "fes": "FEnv Vel", "vcs": "VCA Vel",
    "xdl": "Dly Send", "xdf": "Dly Fdbk", "xdt": "Dly Time", "xdm": "Dly Mode",
    "xrl": "Rev Send", "xrm": "Rev Mod",  "xrt": "Rev Dec",
    "xch": "Chorus",   "xeq": "EQ Freq",
    "e1a": "E1 Atk",   "e1d": "E1 Dec",   "e1s": "E1 Sus",   "e1r": "E1 Rel",
    "e2a": "E2 Atk",   "e2d": "E2 Dec",   "e2s": "E2 Sus",   "e2r": "E2 Rel",
    "e3a": "E3 Atk",   "e3d": "E3 Dec",   "e3s": "E3 Sus",   "e3r": "E3 Rel",
    "e1x": "E1 Reset", "e2x": "E2 Reset", "e3x": "E3 Reset",
    "l1w": "L1 Wave",  "l1s": "L1 Speed", "l1m": "L1 Trig",
    "l2w": "L2 Wave",  "l2s": "L2 Speed", "l2m": "L2 Trig",
    "l3w": "L3 Wave",  "l3s": "L3 Speed", "l3m": "L3 Trig",
    "mix": "Volume",   "bpm": "Tempo",    "bdo": "Bend Dn",  "bup": "Bend Up",
    "vde": "VoiceDet", "ode": "Osc Det",  "vun": "Unison",   "vmo": "VoiceMod",
    "psp": "PanSprd",  "psm": "Pan Mode", "gld": "Glide",
    "t1a": "Mlt 1A",   "t1b": "Mlt 1B",   "t2a": "Mlt 2A",   "t2b": "Mlt 2B",
}

ABBR_OVERRIDES = {
    "o1a": "O1Al", "o1s": "O1Sh", "o1c": "O1Tu", "o1f": "O1Ft",
    "o2a": "O2Al", "o2s": "O2Sh", "o2c": "O2Tu", "o2f": "O2Ft",
    "o3a": "O3Al", "o3s": "O3Sh", "o3c": "O3Tu", "o3f": "O3Ft",
    "mx1": "O1Lv", "mx2": "O2Lv", "mx3": "O3Lv", "nze": "NsLv",
    "cut": "Cut",  "res": "Res",  "fty": "FTyp", "drv": "Drv",
    "fen": "FEnv", "fkb": "FKbd", "ffm": "FFM",  "fch": "FCha",
    "fes": "FEVS", "vcs": "VEVS",
    "xdl": "DlSn", "xdf": "DlFb", "xdt": "DlTm", "xdm": "DlMd",
    "xrl": "RvSn", "xrm": "RvMd", "xrt": "RvDc",
    "xch": "Chrs", "xeq": "EqFq",
    "e1a": "E1At", "e1d": "E1Dc", "e1s": "E1Su", "e1r": "E1Re",
    "e2a": "E2At", "e2d": "E2Dc", "e2s": "E2Su", "e2r": "E2Re",
    "e3a": "E3At", "e3d": "E3Dc", "e3s": "E3Su", "e3r": "E3Re",
    "e1x": "E1Rx", "e2x": "E2Rx", "e3x": "E3Rx",
    "l1w": "L1Wv", "l1s": "L1Sp", "l1m": "L1Tg",
    "l2w": "L2Wv", "l2s": "L2Sp", "l2m": "L2Tg",
    "l3w": "L3Wv", "l3s": "L3Sp", "l3m": "L3Tg",
    "mix": "Vol",  "bpm": "BPM",  "bdo": "BDn",  "bup": "BUp",
    "vde": "VDet", "ode": "ODet", "vun": "Uni",  "vmo": "VMod",
    "psp": "PSpr", "psm": "PMod", "gld": "Glid",
    "t1a": "Mu1A", "t1b": "Mu1B", "t2a": "Mu2A", "t2b": "Mu2B",
    "m1s": "M1S",  "m1d": "M1D",  "m1a": "M1A",
    "m2s": "M2S",  "m2d": "M2D",  "m2a": "M2A",
    "m3s": "M3S",  "m3d": "M3D",  "m3a": "M3A",
    "m4s": "M4S",  "m4d": "M4D",  "m4a": "M4A",
    "m5s": "M5S",  "m5d": "M5D",  "m5a": "M5A",
    "m6s": "M6S",  "m6d": "M6D",  "m6a": "M6A",
    "m7s": "M7S",  "m7d": "M7D",  "m7a": "M7A",
    "m8s": "M8S",  "m8d": "M8D",  "m8a": "M8A",
    "m9s": "M9S",  "m9d": "M9D",  "m9a": "M9A",
    "m0s": "M10S", "m0d": "M10D", "m0a": "M10A",
}


# For 14-bit ("long") NRPN params: turn-action `upper` must match the param's
# real range so each detent steps by ~1 unit instead of ~64. Falls back to
# 16382 (full 14-bit minus 1) for the wide-range params, matching the old
# MMNRPM scene the user had working.
LONG_UPPER = {
    "bpm": 255,    # tempo: 0-255 (offset -40)
    "cut": 255,    # cutoff: 0-255
    "fen": 227,    # filter env amount: 29-227 (bipolar via offset 128)
    "l1s": 16382, "l2s": 16382, "l3s": 16382,   # LFO speed (free + sync)
    "xeq": 16382, "xdt": 16382,                 # EQ freq, delay time
    # Matrix amounts: same 29-227 bipolar range as `fen`, so use 227 to keep
    # one-detent-per-unit feel rather than the 64-unit jumps of full 14-bit.
    "m1a": 227, "m2a": 227, "m3a": 227, "m4a": 227, "m5a": 227,
    "m6a": 227, "m7a": 227, "m8a": 227, "m9a": 227, "m0a": 227,
}


def nrpn_turn_action(key: str, nrpn: int, is_14bit: bool) -> dict:
    """7-bit params: mode=7 + upper=16383 (the bridge-feedback fix the user
    discovered). 14-bit params: mode=1 + the param's real upper bound, so
    a single detent moves by ~1 unit on the synth."""
    if is_14bit:
        mode = 1
        upper = LONG_UPPER.get(key, 16382)
    else:
        mode = 7
        upper = 16383
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 9,
        "display": 10,
        "mode": mode,
        "channel": 0,
        "lower": 0,
        "upper": upper,
        "defaultValue": 0,
        "nr1": nrpn,
        "nr2": 0,
        "output": 12,
    }


def nrpn_push_toggle(nrpn: int) -> dict:
    """Push-action that toggles an NRPN between 0 and 1.
    Push-action constraints (firmware-validated):
      - `display` must be 0 (10 is only valid on turn_actions).
      - `mode` must be 1 (7 is only valid on turn_actions); `lower`/`upper`
        define the swap pair, mirroring TR1000.oxie16's Master FX toggle
        but with type=9 (NRPN) instead of type=2 (CC)."""
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 9,
        "display": 0,
        "mode": 1,
        "channel": 0,
        "lower": 0,
        "upper": 1,
        "nr1": nrpn,
        "nr2": 0,
        "output": 12,
    }


def inert_push(slot_idx: int) -> dict:
    """Placeholder push_action (matches the no-op shape used in working scenes)."""
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 0,
        "display": 0,
        "mode": 0,
        "channel": 0,
        "lower": 0,
        "upper": 0,
        "nr1": slot_idx + 1,
        "nr2": slot_idx + 1,
        "output": 15,
    }


def inert_turn() -> dict:
    """Placeholder turn_action (firmware requires defaultValue + the same shape
    as a real turn_action, otherwise it null-derefs an int field on load).
    Matches the secondary turn_action found on every encoder in MMNRPM."""
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 0,
        "display": 10,
        "mode": 3,
        "channel": 0,
        "lower": 0,
        "upper": 127,
        "defaultValue": 0,
        "nr1": 0,
        "nr2": 0,
        "output": 12,
    }


def make_encoder(key: str, slot_idx: int) -> dict:
    if key == "-":
        return {
            "name": "",
            "abbr": "",
            "color": 0,
            "push_action": inert_push(slot_idx),
            "turn_actions": [inert_turn()],
            "color2": 0,
        }

    if key not in PARAM_BY_KEY:
        raise SystemExit(f"Unknown key {key!r} — not in mm2_bridge.PARAMS.")
    nrpn, is_14bit, default_title = PARAM_BY_KEY[key]
    name = TITLE_OVERRIDES.get(key, default_title)[:8]
    abbr = ABBR_OVERRIDES.get(key, key.upper())[:4]
    color = color_for_key(key)

    if key in ONOFF_KEYS:
        return {
            "name": name,
            "abbr": abbr,
            "color": color,
            "push_action": nrpn_push_toggle(nrpn),
            "turn_actions": [inert_turn()],
            "color2": 0,
        }

    return {
        "name": name,
        "abbr": abbr,
        "color": color,
        "push_action": inert_push(slot_idx),
        "turn_actions": [nrpn_turn_action(key, nrpn, is_14bit)],
        "color2": 0,
    }


TOTAL_PAGES = 12  # E16 firmware expects a fixed 12-page array.


def build_page(title: str, channel: int, encoders: list[dict]) -> dict:
    return {
        "title": title,
        "output": 0,
        "channel": channel,
        "encoders": encoders,
    }


def build_pages() -> list[dict]:
    pages: list[dict] = []
    for title, rows in LAYOUT:
        encoders: list[dict] = []
        for row_idx, row in enumerate(rows):
            for col_idx, key in enumerate(row):
                slot_idx = row_idx * 4 + col_idx
                encoders.append(make_encoder(key, slot_idx))
        pages.append(build_page(title, LAYOUT_PAGE_CHANNEL, encoders))
    for extra_idx in range(len(pages), TOTAL_PAGES):
        encoders = [make_encoder("-", slot) for slot in range(16)]
        pages.append(build_page(f"P.{extra_idx + 1}", 0, encoders))
    return pages


def resolve_scene_dir(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scene_dir", type=Path, nargs="?",
                   default=os.environ.get(SCENE_DIR_ENV),
                   help=f"E16 Scenes directory to write {SCENE_FILENAME} "
                        f"into. Defaults to ${SCENE_DIR_ENV}.")
    args = p.parse_args(argv)

    if args.scene_dir is None:
        raise SystemExit(f"Pass a scene directory, or set ${SCENE_DIR_ENV}.")
    if not args.scene_dir.is_dir():
        raise SystemExit(f"Not a directory: {args.scene_dir}")
    return args.scene_dir


def main() -> None:
    output = resolve_scene_dir() / SCENE_FILENAME

    scene = {
        "title": "MMNRPMFULL",
        "icon": SCENE_ICON,
        "selectedPreset": 0,
        "code": {"code": ""},
        "pages": build_pages(),
    }
    payload = json.dumps(scene, separators=(",", ":"))
    json.loads(payload)  # round-trip validation
    output.write_text(payload)

    print(f"wrote {output}")
    for page_idx, (title, rows) in enumerate(LAYOUT):
        print(f"\nPage {page_idx + 1} {title}:")
        for row_idx, row in enumerate(rows):
            cells = []
            for col_idx, key in enumerate(row):
                if key == "-":
                    cells.append("    -      ")
                else:
                    nrpn = PARAM_BY_KEY[key][0]
                    tag = "*" if key in ONOFF_KEYS else " "
                    cells.append(f"{key:>3}{tag}({nrpn:>3})")
            print("  " + "  ".join(cells))


if __name__ == "__main__":
    main()
