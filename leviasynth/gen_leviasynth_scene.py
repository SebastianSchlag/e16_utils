#!/usr/bin/env python3
"""
Generate LEVIACC.oxie16 — an OXI E16 scene that drives every CC-addressable
ASM Leviasynth parameter, laid out to follow the synth's own signal flow.

All 106 patch parameters from the manual's MIDI CC Charts (p. 169-172) are
mapped. The 22 CCs left out are the 18 the chart marks Reserved plus four that
are not patch parameters: bank select MSB/LSB (0, 32), all notes off (123) and
the sustain pedal (64, better left to an actual pedal).

CC is the only option here: the manual documents the full CC chart but never
publishes NRPN numbers, it only says Parameter TX/RX can be set to NRPN.

On the synth, set MIDI Parameters page 3 > Parameter RX = CC. Set Parameter
TX = CC as well if you want the Leviasynth's own knobs to push the E16's
encoders back into sync.

Action shapes are lifted from two scenes the device itself accepts:
Leviasynth.oxie16 (the factory default, written by current firmware — the
source of the newer `scriptId` / `fullScript` schema and the CC turn_action)
and TR1000.oxie16 (hand-built, the source of the CC push-toggle shape).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Deliberately not Leviasynth.oxie16: that name holds the factory-default
# scene (CC1-16 on 12 pages). Delete or rename it once this one is proven.
SCENE_TITLE = "LEVIACC"
SCENE_FILENAME = f"{SCENE_TITLE}.oxie16"

# Where the scene goes is per-machine, so it comes in on the command line.
# Set $E16_SCENE_DIR to your E16 Scenes folder to skip typing it every time.
SCENE_DIR_ENV = "E16_SCENE_DIR"

# 32-byte E16 scene icon (8x8x2 bitmap), lifted from the stock Leviasynth
# scene so this one keeps the same glyph in the device picker.
SCENE_ICON: list[int] = [
    56, 28, 84, 34, 146, 69, 146, 73, 130, 65, 68, 34, 56, 28, 0, 0,
    0, 0, 56, 28, 68, 34, 162, 65, 146, 73, 130, 69, 68, 34, 56, 28,
]

# Single mode sends and receives everything on the TX/RX Global channel, so
# one channel covers the whole scene. In Multi mode the Upper/Lower parts also
# respond here; give duplicated pages their own channel to address parts
# independently. Encoder actions use channel 0, meaning "inherit the page".
PAGE_CHANNEL = 1

# CC turn_actions: mode 14 is what current firmware writes for a CC encoder
# (see the stock Leviasynth scene). The older hand-built TR1000 uses mode 3;
# flip this if encoder tracking feels wrong against the synth's feedback.
CC_TURN_MODE = 14


# (cc, key, name, abbr, kind) — name is truncated to 8 chars by the device's
# parameter area, abbr to 4 by the encoder label.
#
# kind is documentation, not behaviour: "bip" marks the parameters whose native
# range is bipolar (+/- 64.0, +/- 128.0 or +/- 200%), "enum" the ones that are
# really a short option list, "tog" the one Off/On switch. 7-bit CC cannot
# represent any of these exactly — see the range notes in main().
PARAMS: list[tuple[int, str, str, str, str]] = [
    # --- Global / performance -------------------------------------------
    (  1, "mwh", "Mod Whl",  "MWhl", "uni"),
    (  7, "vol", "Volume",   "MVol", "uni"),
    ( 11, "exp", "Express",  "Expr", "uni"),
    (  8, "bal", "Balance",  "Bal",  "bip"),
    # --- Macros ---------------------------------------------------------
    ( 16, "mc1", "Macro 1",  "Mac1", "uni"),
    ( 17, "mc2", "Macro 2",  "Mac2", "uni"),
    ( 18, "mc3", "Macro 3",  "Mac3", "uni"),
    ( 19, "mc4", "Macro 4",  "Mac4", "uni"),
    ( 20, "mc5", "Macro 5",  "Mac5", "uni"),
    ( 21, "mc6", "Macro 6",  "Mac6", "uni"),
    ( 22, "mc7", "Macro 7",  "Mac7", "uni"),
    ( 23, "mc8", "Macro 8",  "Mac8", "uni"),
    # --- Voice ----------------------------------------------------------
    (  9, "ply", "Polyphny", "Poly", "enum"),
    ( 10, "den", "Density",  "Dens", "enum"),
    ( 95, "det", "Uni Detu", "Detu", "uni"),
    (  5, "gld", "Glide Tm", "Glid", "uni"),
    ( 65, "gtg", "Glide On", "GlOn", "tog"),
    # --- VCA ------------------------------------------------------------
    (  2, "vca", "VCA Levl", "VCA",  "uni"),
    (  3, "vl3", "VCA LFO3", "VL3",  "bip"),
    # --- Oscillator initial levels --------------------------------------
    ( 24, "o1l", "Osc1 Lvl", "O1Lv", "uni"),
    ( 25, "o2l", "Osc2 Lvl", "O2Lv", "uni"),
    ( 26, "o3l", "Osc3 Lvl", "O3Lv", "uni"),
    ( 27, "o4l", "Osc4 Lvl", "O4Lv", "uni"),
    ( 28, "o5l", "Osc5 Lvl", "O5Lv", "uni"),
    ( 29, "o6l", "Osc6 Lvl", "O6Lv", "uni"),
    ( 30, "o7l", "Osc7 Lvl", "O7Lv", "uni"),
    ( 31, "o8l", "Osc8 Lvl", "O8Lv", "uni"),
    # --- Oscillator pitch (CC 38 is Reserved, so Osc 6-8 are 39/40/41) --
    ( 33, "o1p", "Osc1 Pit", "O1Pt", "bip"),
    ( 34, "o2p", "Osc2 Pit", "O2Pt", "bip"),
    ( 35, "o3p", "Osc3 Pit", "O3Pt", "bip"),
    ( 36, "o4p", "Osc4 Pit", "O4Pt", "bip"),
    ( 37, "o5p", "Osc5 Pit", "O5Pt", "bip"),
    ( 39, "o6p", "Osc6 Pit", "O6Pt", "bip"),
    ( 40, "o7p", "Osc7 Pit", "O7Pt", "bip"),
    ( 41, "o8p", "Osc8 Pit", "O8Pt", "bip"),
    # --- Oscillator feedback --------------------------------------------
    ( 42, "o1f", "Osc1 Fbk", "O1Fb", "uni"),
    ( 43, "o2f", "Osc2 Fbk", "O2Fb", "uni"),
    ( 44, "o3f", "Osc3 Fbk", "O3Fb", "uni"),
    ( 45, "o4f", "Osc4 Fbk", "O4Fb", "uni"),
    ( 46, "o5f", "Osc5 Fbk", "O5Fb", "uni"),
    ( 47, "o6f", "Osc6 Fbk", "O6Fb", "uni"),
    ( 48, "o7f", "Osc7 Fbk", "O7Fb", "uni"),
    ( 49, "o8f", "Osc8 Fbk", "O8Fb", "uni"),
    # --- Digital filter (Morph on SEM/Vowel types, Drive on the other 16)
    ( 55, "dct", "D Cutoff", "DCut", "uni"),
    ( 56, "drs", "D Reso",   "DRes", "uni"),
    ( 50, "dmd", "D Mrp/Dr", "DMrp", "uni"),
    ( 51, "dkt", "D Keytrk", "DKtk", "bip"),
    ( 54, "de1", "D ENV1",   "DE1",  "bip"),
    ( 52, "dl1", "D LFO1",   "DL1",  "bip"),
    ( 53, "dvl", "D Vel>En", "DVel", "bip"),
    # --- Analog filter --------------------------------------------------
    ( 74, "act", "A Cutoff", "ACut", "uni"),
    ( 71, "ars", "A Reso",   "ARes", "uni"),
    ( 57, "apd", "A PreDrv", "ADrv", "uni"),
    ( 58, "akt", "A Keytrk", "AKtk", "bip"),
    ( 61, "ae2", "A ENV2",   "AE2",  "bip"),
    ( 59, "al2", "A LFO2",   "AL2",  "bip"),
    ( 60, "avl", "A Vel>En", "AVel", "bip"),
    # --- Envelopes (ENV 3 sustain/release jump the Dry/Wet block) -------
    ( 81, "e1a", "E1 Attac", "E1A",  "uni"),
    ( 82, "e1d", "E1 Decay", "E1D",  "uni"),
    ( 83, "e1s", "E1 Sustn", "E1S",  "uni"),
    ( 84, "e1r", "E1 Relse", "E1R",  "uni"),
    ( 85, "e2a", "E2 Attac", "E2A",  "uni"),
    ( 86, "e2d", "E2 Decay", "E2D",  "uni"),
    ( 87, "e2s", "E2 Sustn", "E2S",  "uni"),
    ( 88, "e2r", "E2 Relse", "E2R",  "uni"),
    ( 89, "e3a", "E3 Attac", "E3A",  "uni"),
    ( 90, "e3d", "E3 Decay", "E3D",  "uni"),
    ( 96, "e3s", "E3 Sustn", "E3S",  "uni"),
    ( 97, "e3r", "E3 Relse", "E3R",  "uni"),
    (102, "e4a", "E4 Attac", "E4A",  "uni"),
    (103, "e4d", "E4 Decay", "E4D",  "uni"),
    (104, "e4s", "E4 Sustn", "E4S",  "uni"),
    (105, "e4r", "E4 Relse", "E4R",  "uni"),
    (106, "e5a", "E5 Attac", "E5A",  "uni"),
    (107, "e5d", "E5 Decay", "E5D",  "uni"),
    (108, "e5s", "E5 Sustn", "E5S",  "uni"),
    (109, "e5r", "E5 Relse", "E5R",  "uni"),
    # --- LFOs (LFO 2 Level is CC 4, out of line with the others) --------
    ( 72, "l1r", "L1 Rate",  "L1Rt", "uni"),
    ( 70, "l1l", "L1 Level", "L1Lv", "uni"),
    (110, "l1w", "L1 Wave",  "L1Wv", "enum"),
    ( 73, "l2r", "L2 Rate",  "L2Rt", "uni"),
    (  4, "l2l", "L2 Level", "L2Lv", "uni"),
    (111, "l2w", "L2 Wave",  "L2Wv", "enum"),
    ( 76, "l3r", "L3 Rate",  "L3Rt", "uni"),
    ( 75, "l3l", "L3 Level", "L3Lv", "uni"),
    (112, "l3w", "L3 Wave",  "L3Wv", "enum"),
    ( 78, "l4r", "L4 Rate",  "L4Rt", "uni"),
    ( 77, "l4l", "L4 Level", "L4Lv", "uni"),
    (113, "l4w", "L4 Wave",  "L4Wv", "enum"),
    ( 80, "l5r", "L5 Rate",  "L5Rt", "uni"),
    ( 79, "l5l", "L5 Level", "L5Lv", "uni"),
    (114, "l5w", "L5 Wave",  "L5Wv", "enum"),
    # --- FX: Pre/Post P1 and P2 are soft knobs 3 and 4, so what they do
    #     follows the FX type (Rate/Depth on Chorus, Drive/Tone on Distort...)
    ( 12, "pp1", "Pre P1",   "PrP1", "uni"),
    ( 13, "pp2", "Pre P2",   "PrP2", "uni"),
    ( 93, "pdw", "Pre D/W",  "PrDW", "uni"),
    ( 68, "qp1", "Post P1",  "PsP1", "uni"),
    ( 69, "qp2", "Post P2",  "PsP2", "uni"),
    ( 94, "qdw", "Post D/W", "PsDW", "uni"),
    ( 15, "dlt", "Dly Time", "DlTm", "uni"),
    ( 14, "dlf", "Dly Fdbk", "DlFb", "uni"),
    ( 62, "dft", "Dly FbTn", "DlFT", "uni"),
    ( 63, "dwt", "Dly WetT", "DlWT", "bip"),
    ( 92, "ddw", "Dly D/W",  "DlDW", "uni"),
    ( 66, "rvt", "Rev Time", "RvTm", "uni"),
    ( 67, "rvn", "Rev Tone", "RvTn", "bip"),
    ( 91, "rdw", "Rev D/W",  "RvDW", "uni"),
]

# key -> (cc, name, abbr, kind)
PARAM_BY_KEY = {key: (cc, name, abbr, kind)
                for cc, key, name, abbr, kind in PARAMS}

# Encoders that get a push_action toggling a second CC between 0 and 127.
# Glide Time's push flips Glide on/off, the way the MMNRPM scene puts the
# envelope-reset switches on a push instead of spending a slot on them.
PUSH_TOGGLE: dict[str, str] = {"gld": "gtg"}

# Keys reached only through a push_action, so the coverage check in main()
# does not expect them to own an encoder of their own.
PUSH_ONLY = set(PUSH_TOGGLE.values())

# Layout to produce. Oscillators get one row each (Level, Pitch, Feedback) so
# a row matches the synth's own per-oscillator colour coding and editing pages;
# the OSC MIX page late in the scene repeats all eight levels and pitches
# side by side for the balance-across-operators gesture. Duplicating a CC on
# two encoders is harmless — both simply move when feedback arrives.
LAYOUT: list[tuple[str, list[list[str]]]] = [
    # Live page. Everything below the macros except Poly/Density/Detune is a
    # System MIDI control, so this page still works with Parameter RX = Off.
    ("PERF", [
        ["mc1", "mc2", "mc3", "mc4"],
        ["mc5", "mc6", "mc7", "mc8"],
        ["vol", "bal", "exp", "mwh"],
        ["ply", "den", "det", "gld"],
    ]),
    ("OSC1-4", [
        ["o1l", "o1p", "o1f", "-"],
        ["o2l", "o2p", "o2f", "-"],
        ["o3l", "o3p", "o3f", "-"],
        ["o4l", "o4p", "o4f", "-"],
    ]),
    ("OSC5-8", [
        ["o5l", "o5p", "o5f", "-"],
        ["o6l", "o6p", "o6f", "-"],
        ["o7l", "o7p", "o7f", "-"],
        ["o8l", "o8p", "o8f", "-"],
    ]),
    # Digital and analog mirror each other row for row: same column is the
    # same job, rows 1/3 shape tone, rows 2/4 set modulation depth. Column 4
    # of rows 2/4 picks up the VCA, so the whole filter > VCA chain is here.
    ("FILT", [
        ["dct", "drs", "dmd", "dkt"],
        ["de1", "dl1", "dvl", "vca"],
        ["act", "ars", "apd", "akt"],
        ["ae2", "al2", "avl", "vl3"],
    ]),
    # Rows 1-3 are the pre-wired envelopes, in the same order as the FILT
    # page's rows: ENV 1 > digital, ENV 2 > analog, ENV 3 > VCA.
    ("ENV", [
        ["e1a", "e1d", "e1s", "e1r"],
        ["e2a", "e2d", "e2s", "e2r"],
        ["e3a", "e3d", "e3s", "e3r"],
        ["e4a", "e4d", "e4s", "e4r"],
    ]),
    # Same row order again for the pre-wired LFOs. Column 4 stays empty:
    # Speed Mode, Trig Sync, Delay, Fade In and Quantize have no CC.
    ("LFO", [
        ["l1r", "l1l", "l1w", "-"],
        ["l2r", "l2l", "l2w", "-"],
        ["l3r", "l3l", "l3w", "-"],
        ["l4r", "l4l", "l4w", "-"],
    ]),
    # The fifth free modulator pair, kept in the same row shapes as above.
    ("MOD5", [
        ["e5a", "e5d", "e5s", "e5r"],
        ["l5r", "l5l", "l5w", "-"],
        ["-",   "-",   "-",   "-"],
        ["-",   "-",   "-",   "-"],
    ]),
    # Rows follow the real chain: Pre-FX > Delay > Reverb > Post-FX.
    ("FX", [
        ["pp1", "pp2", "pdw", "-"],
        ["dlt", "dlf", "dft", "dwt"],
        ["ddw", "rvt", "rvn", "rdw"],
        ["qp1", "qp2", "qdw", "-"],
    ]),
    # Performance view of the oscillators: all eight levels, then all eight
    # pitches, for balancing operators against each other in one pass.
    ("OSC MIX", [
        ["o1l", "o2l", "o3l", "o4l"],
        ["o5l", "o6l", "o7l", "o8l"],
        ["o1p", "o2p", "o3p", "o4p"],
        ["o5p", "o6p", "o7p", "o8p"],
    ]),
]

# Conceptual groups — each gets one OXI palette hue (multiples of 10).
KEY_GROUP: dict[str, str] = {
    "mc1": "macro", "mc2": "macro", "mc3": "macro", "mc4": "macro",
    "mc5": "macro", "mc6": "macro", "mc7": "macro", "mc8": "macro",
    "vol": "global", "bal": "global", "exp": "global", "mwh": "global",
    "ply": "voice", "den": "voice", "det": "voice", "gld": "voice",
    "vca": "vca", "vl3": "vca",
    # One hue per oscillator, so a row on OSC1-4 / OSC5-8 reads as a unit.
    **{f"o{n}{p}": f"osc{n}" for n in range(1, 9) for p in "lpf"},
    "dct": "dfilt", "drs": "dfilt", "dmd": "dfilt", "dkt": "dfilt",
    "de1": "dfilt", "dl1": "dfilt", "dvl": "dfilt",
    "act": "afilt", "ars": "afilt", "apd": "afilt", "akt": "afilt",
    "ae2": "afilt", "al2": "afilt", "avl": "afilt",
    # Envelopes and LFOs borrow the hue of whatever they are pre-wired to, so
    # the colour itself tells you ENV 1 / LFO 1 land on the digital filter,
    # ENV 2 / LFO 2 on the analog filter, ENV 3 / LFO 3 on the VCA. The two
    # free pairs share a neutral hue.
    "e1a": "dfilt", "e1d": "dfilt", "e1s": "dfilt", "e1r": "dfilt",
    "e2a": "afilt", "e2d": "afilt", "e2s": "afilt", "e2r": "afilt",
    "e3a": "vca",   "e3d": "vca",   "e3s": "vca",   "e3r": "vca",
    "e4a": "free",  "e4d": "free",  "e4s": "free",  "e4r": "free",
    "e5a": "free",  "e5d": "free",  "e5s": "free",  "e5r": "free",
    "l1r": "dfilt", "l1l": "dfilt", "l1w": "dfilt",
    "l2r": "afilt", "l2l": "afilt", "l2w": "afilt",
    "l3r": "vca",   "l3l": "vca",   "l3w": "vca",
    "l4r": "free",  "l4l": "free",  "l4w": "free",
    "l5r": "free",  "l5l": "free",  "l5w": "free",
    "pp1": "prefx",  "pp2": "prefx",  "pdw": "prefx",
    "qp1": "postfx", "qp2": "postfx", "qdw": "postfx",
    "dlt": "delay",  "dlf": "delay",  "dft": "delay",
    "dwt": "delay",  "ddw": "delay",
    "rvt": "reverb", "rvn": "reverb", "rdw": "reverb",
}

GROUP_COLOR: dict[str, int] = {
    "macro": 80, "global": 0, "voice": 30,
    "dfilt": 50, "afilt": 20, "vca": 70, "free": 10,
    "prefx": 30, "delay": 60, "reverb": 90, "postfx": 80,
    # A monotonic ramp across the eight oscillators, which reads as a gradient
    # down the OSC pages and across the OSC MIX rows. The synth colour-codes
    # its oscillators too (Osc 1 cyan, Osc 2 green, manual p. 32) but only
    # names those two, so re-order these if you want them to match the panel.
    **{f"osc{n}": (n - 1) * 10 for n in range(1, 9)},
}


def color_for_key(key: str) -> int:
    return GROUP_COLOR.get(KEY_GROUP.get(key, ""), 0)


def cc_turn_action(cc: int) -> dict:
    """CC turn_action, shaped as current firmware writes one (see the stock
    Leviasynth scene): type=2 is CC on a push_action but type=3 on a turn,
    and both nr1 and nr2 carry the CC number."""
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 3,
        "display": 10,
        "mode": CC_TURN_MODE,
        "channel": 0,
        "lower": 0,
        "upper": 127,
        "defaultValue": 0,
        "nr1": cc,
        "nr2": cc,
        "output": 12,
        "scriptId": 0,
    }


def cc_push_toggle(cc: int, slot_idx: int) -> dict:
    """Push-action that flips a CC between 127 and 0, copied from TR1000's
    Master FX on / Analog FX on switches: type=2 (CC on a push), mode=1,
    display=0, lower/upper hold the swap pair the other way round, and
    output=0 rather than the 15 an inert push uses."""
    return {
        "instrument": 127,
        "parameter": 0,
        "type": 2,
        "display": 0,
        "mode": 1,
        "channel": 0,
        "lower": 127,
        "upper": 0,
        "nr1": cc,
        "nr2": slot_idx + 1,
        "output": 0,
        "scriptId": 0,
    }


def inert_push(slot_idx: int) -> dict:
    """Placeholder push_action, matching the no-op shape every unassigned
    encoder carries in TR1000 and MMNRPM."""
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
        "scriptId": 0,
    }


def inert_turn() -> dict:
    """Trailing placeholder turn_action. Every encoder in both reference
    scenes carries exactly two turn_actions, and the firmware wants the full
    shape including defaultValue here or it null-derefs an int on load."""
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
        "scriptId": 0,
    }


def make_encoder(key: str, slot_idx: int) -> dict:
    if key == "-":
        return {
            "name": "",
            "abbr": "",
            "color": 0,
            "push_action": inert_push(slot_idx),
            "turn_actions": [inert_turn(), inert_turn()],
            "color2": 0,
        }

    if key not in PARAM_BY_KEY:
        raise SystemExit(f"Unknown key {key!r} — not in PARAMS.")
    cc, name, abbr, _kind = PARAM_BY_KEY[key]

    if key in PUSH_TOGGLE:
        toggle_cc = PARAM_BY_KEY[PUSH_TOGGLE[key]][0]
        push = cc_push_toggle(toggle_cc, slot_idx)
    else:
        push = inert_push(slot_idx)

    return {
        "name": name[:8],
        "abbr": abbr[:4],
        "color": color_for_key(key),
        "push_action": push,
        "turn_actions": [cc_turn_action(cc), inert_turn()],
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
        pages.append(build_page(title, PAGE_CHANNEL, encoders))
    # Spare pages, left clear for the Mod Matrix and Multi-mode parts.
    for extra_idx in range(len(pages), TOTAL_PAGES):
        encoders = [make_encoder("-", slot) for slot in range(16)]
        pages.append(build_page(f"P.{extra_idx + 1}", 0, encoders))
    return pages


def check_tables() -> None:
    """Catch the mistakes that are invisible once the scene is on the device:
    a CC typo'd onto two parameters, a layout cell naming nothing, or a
    parameter that never made it onto a page."""
    keys = [key for _cc, key, _n, _a, _k in PARAMS]
    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise SystemExit(f"Duplicate PARAMS keys: {dupes}")

    ccs = [cc for cc, *_ in PARAMS]
    if len(set(ccs)) != len(ccs):
        dupes = sorted({c for c in ccs if ccs.count(c) > 1})
        raise SystemExit(f"Duplicate PARAMS CC numbers: {dupes}")

    # CCs the manual lists as Reserved, plus the ones that are bank select or
    # all-notes-off rather than a patch parameter.
    off_limits = ({0, 32, 123, 6, 38, 98, 99, 100, 101}
                  | set(range(115, 123)) | set(range(124, 128)))
    if clash := sorted(set(ccs) & off_limits):
        raise SystemExit(f"PARAMS uses Reserved/system CCs: {clash}")

    placed = {key for _t, rows in LAYOUT for row in rows for key in row
              if key != "-"}
    if unknown := sorted(placed - set(keys)):
        raise SystemExit(f"LAYOUT names unknown keys: {unknown}")
    if missing := sorted(set(keys) - placed - PUSH_ONLY):
        raise SystemExit(f"PARAMS never placed in LAYOUT: {missing}")

    for title, rows in LAYOUT:
        if len(rows) != 4 or any(len(row) != 4 for row in rows):
            raise SystemExit(f"Page {title!r} is not 4x4.")


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
    check_tables()
    output = resolve_scene_dir() / SCENE_FILENAME

    scene = {
        "title": SCENE_TITLE,
        "icon": SCENE_ICON,
        "selectedPreset": 0,
        "color": 80,
        "transmitMode": 0,
        "pcOnEntry": 0,
        "bankOnEntry": 65535,
        "recentPage": 0,
        "recentPreset": 0,
        "transmitOnSceneEntry": 0,
        "transmitOnPageSwitch": 0,
        "transmitOnPresetLoad": 0,
        "smartTransmit": 15,
        "outputOnEntry": 0,
        "holdMode": 0,
        "acceleration": 3,
        "code": {"code": "", "fullScript": "", "scriptName": ""},
        "pages": build_pages(),
    }
    payload = json.dumps(scene, separators=(",", ":"))
    json.loads(payload)  # round-trip validation
    output.write_text(payload)

    print(f"wrote {output}")
    for page_idx, (title, rows) in enumerate(LAYOUT):
        print(f"\nPage {page_idx + 1} {title}:")
        for row in rows:
            cells = []
            for key in row:
                if key == "-":
                    cells.append("     -     ")
                else:
                    cc, _n, abbr, kind = PARAM_BY_KEY[key]
                    tag = "*" if key in PUSH_TOGGLE else " "
                    cells.append(f"{abbr:>4}{tag}({cc:>3}){kind[0]}")
            print("  " + " ".join(cells))

    placed = [key for _t, rows in LAYOUT for row in rows for key in row
              if key != "-"]
    print(f"\n{len(PARAMS)} parameters mapped, "
          f"{len(placed)} encoders used of {TOTAL_PAGES * 16}, "
          f"{len(placed) - len(set(placed))} deliberate duplicates.")
    print("* = push toggles a second CC.  "
          "Trailing u/b/e = unipolar / bipolar / enum native range.")
    print("\nOn the synth: MIDI Parameters page 3 > Parameter RX = CC "
          "(and TX = CC for knob feedback).")
    print(f"Scene sends on MIDI channel {PAGE_CHANNEL} "
          "— match the RX Global channel.")


if __name__ == "__main__":
    main()
