#!/usr/bin/env python3
"""
Render a reference PDF for the LEVIACC scene.

The page grids, colours and parameter index are all read out of
gen_leviasynth_scene.py's own tables, so this document cannot drift from the
scene the generator actually writes. Re-run it after changing the layout.

Needs Google Chrome for the HTML -> PDF step; pass --chrome if it lives
somewhere other than /Applications.
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

import gen_leviasynth_scene as scene

CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# One or two sentences per page, explaining why the page is shaped that way.
PAGE_NOTES: dict[str, str] = {
    "PERF": (
        "Live page. The eight macros sit above a global row and a voice row. "
        "Everything below the macros except Polyphony, Density and Unison "
        "Detune is a System MIDI control, so this page keeps working even "
        "with Parameter RX set to Off. Glide Time's <em>push</em> toggles "
        "Glide on and off (CC 65), rather than spending an encoder on it."),
    "OSC1-4": (
        "One row per oscillator — Initial Level, Pitch, Feedback — matching "
        "the synth's own per-oscillator editing pages and its panel colour "
        "coding. Column 4 stays empty: Mode, Waveform, Env Level and "
        "Keytrack have no CC."),
    "OSC5-8": (
        "Oscillators 5 to 8, same row shape. Watch the CC numbers on the "
        "Pitch column: CC 38 is Reserved, so oscillators 6, 7 and 8 are "
        "39, 40 and 41 rather than 38, 39 and 40."),
    "FILT": (
        "The densest page, and the one worth reaching for first. Digital and "
        "analog are mirrored row for row, so the same column does the same "
        "job in both: rows 1 and 3 shape tone, rows 2 and 4 set modulation "
        "depth. Column 4 of rows 2 and 4 picks up the VCA, which puts the "
        "whole digital → analog → VCA chain on one page."),
    "ENV": (
        "Envelopes 1 to 4. Rows 1 to 3 are the pre-wired envelopes, in the "
        "same order as the FILT page's rows, so the two pages line up. "
        "ENV 3's Sustain and Release are CC 96 and 97 — the chart jumps over "
        "the Dry/Wet block at 91-94."),
    "LFO": (
        "LFOs 1 to 4, in that same destination order once more. Column 4 is "
        "empty because Speed Mode, Trig Sync, Delay, Fade In and Quantize "
        "have no CC. LFO 2's Level is CC 4, well out of line with the other "
        "four — an easy one to mis-transcribe."),
    "MOD5": (
        "The fifth modulator pair: the only envelope and LFO with no "
        "pre-wired destination, so they are reachable only through the Mod "
        "Matrix. Kept in the same row shapes as the ENV and LFO pages even "
        "though it leaves the page half empty."),
    "FX": (
        "Rows follow the real signal chain: Pre-FX, Delay, Reverb, Post-FX. "
        "Row 3 does mix the delay's Dry/Wet in with the reverb, which is the "
        "one compromise on this page — it puts both sends next to each "
        "other. Pre and Post P1/P2 are soft knobs 3 and 4, so what they "
        "control follows the FX type."),
    "OSC MIX": (
        "Performance view of the oscillators: all eight levels, then all "
        "eight pitches, for balancing operators against each other in a "
        "single pass. These sixteen encoders duplicate pages 2 and 3 — "
        "harmless, since both copies simply move when feedback arrives."),
}

GROUP_LABEL: dict[str, str] = {
    "macro": "Macros",
    "global": "Global / mixer",
    "voice": "Voice",
    "dfilt": "Digital filter — and ENV 1 / LFO 1, pre-wired to it",
    "afilt": "Analog filter — and ENV 2 / LFO 2, pre-wired to it",
    "vca": "VCA — and ENV 3 / LFO 3, pre-wired to it",
    "free": "ENV 4/5 and LFO 4/5 — no pre-wired destination",
    "prefx": "Pre-FX",
    "delay": "Delay",
    "reverb": "Reverb",
    "postfx": "Post-FX",
    **{f"osc{n}": f"Oscillator {n}" for n in range(1, 9)},
}

KIND_LABEL = {
    "uni": ("", "unipolar 0–128"),
    "bip": ("±", "bipolar"),
    "enum": ("▫", "option list, not a continuous range"),
    "tog": ("▪", "Off / On"),
}


def swatch(idx: int) -> str:
    """The device's actual colour for a palette index, sampled from the
    spectrum strip in the E16 manual (section 2.8, p. 21)."""
    return scene.PALETTE[idx][0]


def palette_strip() -> str:
    cells = "".join(
        f'<div class="ps"><span style="background:{hexv}"></span>'
        f'<b>{idx}</b><i>{esc(name)}</i></div>'
        for idx, (hexv, name) in sorted(scene.PALETTE.items()))
    return f'<div class="pstrip">{cells}</div>'


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def page_locations() -> dict[str, list[str]]:
    """key -> page titles it appears on, for the parameter index."""
    where: dict[str, list[str]] = {}
    for title, rows in scene.LAYOUT:
        for row in rows:
            for key in row:
                if key != "-" and title not in where.setdefault(key, []):
                    where[key].append(title)
    return where


def render_grid(title: str, rows: list[list[str]]) -> str:
    cells = []
    for row in rows:
        for key in row:
            if key == "-":
                cells.append('<div class="cell empty"></div>')
                continue
            cc, name, abbr, kind = scene.PARAM_BY_KEY[key]
            group = scene.KEY_GROUP.get(key, "")
            color = scene.GROUP_COLOR.get(group, 0)
            mark = KIND_LABEL[kind][0]
            push = ""
            if key in scene.PUSH_TOGGLE:
                toggle_cc = scene.PARAM_BY_KEY[scene.PUSH_TOGGLE[key]][0]
                push = f'<div class="push">push → CC {toggle_cc}</div>'
            cells.append(
                f'<div class="cell" style="--hue:{swatch(color)}">'
                f'<div class="abbr">{esc(abbr)}'
                f'<span class="mark">{mark}</span></div>'
                f'<div class="name">{esc(name)}</div>'
                f'<div class="cc">CC {cc}</div>{push}</div>')
    used = sum(1 for row in rows for key in row if key != "-")
    return (f'<section class="page">'
            f'<h3><span class="pname">{esc(title)}</span>'
            f'<span class="pcount">{used} of 16 encoders</span></h3>'
            f'<div class="grid">{"".join(cells)}</div>'
            f'<p class="note">{PAGE_NOTES.get(title, "")}</p>'
            f'</section>')


def render_legend() -> str:
    seen: dict[str, int] = {}
    pages: dict[str, list[str]] = {}
    for title, rows in scene.LAYOUT:
        for row in rows:
            for key in row:
                if key == "-":
                    continue
                group = scene.KEY_GROUP.get(key, "")
                seen.setdefault(group, scene.GROUP_COLOR.get(group, 0))
                if title not in pages.setdefault(group, []):
                    pages[group].append(title)
    items = []
    for group, color in sorted(seen.items(), key=lambda kv: (kv[1], kv[0])):
        items.append(
            f'<li><span class="chip" style="background:{swatch(color)}">'
            f'</span><b>{color}</b> <i>{esc(scene.PALETTE[color][1])}</i> &middot; '
            f'{esc(GROUP_LABEL.get(group, group))}'
            f'<span class="on">{esc(", ".join(pages[group]))}</span></li>')
    return f'<ul class="legend">{"".join(items)}</ul>'


def render_index() -> str:
    where = page_locations()
    rows = []
    for cc, key, name, abbr, kind in sorted(scene.PARAMS):
        pages = ", ".join(where.get(key, [])) or "push action only"
        group = scene.KEY_GROUP.get(key, "")
        color = scene.GROUP_COLOR.get(group, 0)
        rows.append(
            f'<tr><td class="num">{cc}</td>'
            f'<td><span class="dot" style="background:{swatch(color)}">'
            f'</span>{esc(name)}</td>'
            f'<td class="mono">{esc(abbr)}</td>'
            f'<td>{esc(KIND_LABEL[kind][1])}</td>'
            f'<td>{esc(pages)}</td></tr>')
    return ('<table class="index"><thead><tr><th>CC</th><th>Parameter</th>'
            '<th>Label</th><th>Native range</th><th>Page</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


CSS = """
@page { size: A4; margin: 14mm 13mm; }
* { box-sizing: border-box; }
body { font: 10pt/1.45 -apple-system, "Helvetica Neue", Helvetica, sans-serif;
       color: #1b1d21; margin: 0; }
h1 { font-size: 21pt; margin: 0 0 2mm; letter-spacing: -.3pt; }
h2 { font-size: 12pt; margin: 7mm 0 2.5mm; padding-bottom: 1.2mm;
     border-bottom: .6pt solid #c8ccd2; letter-spacing: .3pt;
     text-transform: uppercase; }
.sub { color: #5b616b; font-size: 10.5pt; margin: 0 0 1mm; }
.meta { color: #80868f; font-size: 8.5pt; margin: 0; }
p { margin: 0 0 2.5mm; }
.lead { font-size: 10pt; }
.box { background: #f4f6f8; border-left: 2.5pt solid #5b616b;
       padding: 3mm 4mm; margin: 3mm 0 0; font-size: 9.5pt; }
.box b { font-weight: 600; }
.flow { display: flex; align-items: center; flex-wrap: nowrap; gap: 1.1mm;
        margin: 2mm 0 3mm; font-size: 7.6pt; }
.flow .blk { background: #eceff3; border: .5pt solid #c8ccd2;
             border-radius: 1.2mm; padding: 1.3mm 1.9mm; white-space: nowrap; }
.flow .arr { color: #9aa0a8; }
.page { break-inside: avoid; margin-bottom: 4.5mm; }
.page h3 { font-size: 10.5pt; margin: 0 0 1.8mm; display: flex;
           justify-content: space-between; align-items: baseline; }
.pname { font-weight: 650; letter-spacing: .4pt; }
.pcount { font-weight: 400; font-size: 8pt; color: #80868f; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.4mm; }
.cell { border: .5pt solid #d4d8de; border-left: 2.2pt solid var(--hue);
        border-radius: 1.2mm; padding: 1.6mm 2mm; min-height: 15mm;
        background: #fff; }
.cell.empty { border: .5pt dashed #dfe3e8; border-left: .5pt dashed #dfe3e8;
              background: #fafbfc; }
.abbr { font: 600 10pt/1.1 ui-monospace, "SF Mono", Menlo, monospace; }
.mark { color: #9aa0a8; font-weight: 400; margin-left: .6mm; }
.name { font-size: 7.5pt; color: #4a5059; margin-top: .5mm; line-height: 1.2; }
.cc { font: 7.5pt ui-monospace, "SF Mono", Menlo, monospace; color: #80868f;
      margin-top: .5mm; }
.push { font-size: 6.6pt; color: #1b1d21; background: #eceff3;
        border-radius: .8mm; padding: .2mm 1mm; margin-top: .8mm;
        display: inline-block; }
.note { font-size: 8.5pt; color: #4a5059; margin: 1.8mm 0 0; }
.pstrip { display: flex; gap: 1.1mm; margin: 2.5mm 0 3.5mm; }
.ps { flex: 1; text-align: center; font-size: 6.8pt; }
.ps span { display: block; height: 7mm; border-radius: 1mm;
           border: .4pt solid rgba(0,0,0,.18); margin-bottom: .8mm; }
.ps b { display: block; font-size: 7.6pt; }
.ps i { display: block; color: #80868f; font-style: normal;
        line-height: 1.15; }
.legend li i { font-style: normal; color: #80868f; }
.legend { list-style: none; padding: 0; margin: 0; columns: 2; gap: 7mm;
          font-size: 8.5pt; }
.legend li { margin-bottom: 1.3mm; break-inside: avoid; }
.on { color: #80868f; font-size: 7.4pt; display: block;
      margin-left: 4.6mm; }
.chip { display: inline-block; width: 3mm; height: 3mm; border-radius: .7mm;
        margin-right: 1.6mm; vertical-align: -.3mm; }
.dot { display: inline-block; width: 2mm; height: 2mm; border-radius: 50%;
       margin-right: 1.4mm; vertical-align: 0; }
table.index { width: 100%; border-collapse: collapse; font-size: 8pt; }
table.index th { text-align: left; border-bottom: .8pt solid #9aa0a8;
                 padding: 1.2mm 1.5mm; font-size: 7.5pt; letter-spacing: .3pt;
                 text-transform: uppercase; color: #4a5059; }
table.index td { border-bottom: .4pt solid #e4e7eb; padding: 1.1mm 1.5mm;
                 vertical-align: top; }
table.index tbody tr:nth-child(even) { background: #f7f8fa; }
.num, .mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.num { text-align: right; width: 9mm; }
ul.plain { margin: 0 0 2mm; padding-left: 4.5mm; font-size: 9.5pt; }
ul.plain li { margin-bottom: 1.2mm; }
.brk { break-before: page; }
code { font: 8.8pt ui-monospace, "SF Mono", Menlo, monospace;
       background: #eceff3; border-radius: .8mm; padding: .2mm .9mm; }
"""

FLOW = ["OSC 1-8", "Level", "Digital Flt", "Analog Flt", "VCA",
        "Pre-FX", "Delay", "Reverb", "Post-FX", "Out"]


def build_html() -> str:
    placed = [key for _t, rows in scene.LAYOUT for row in rows
              for key in row if key != "-"]
    flow = f'<span class="arr">→</span>'.join(
        f'<span class="blk">{esc(b)}</span>' for b in FLOW)
    grids = "".join(render_grid(t, rows) for t, rows in scene.LAYOUT)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{scene.SCENE_TITLE}</title>
<style>{CSS}</style></head><body>

<h1>{esc(scene.SCENE_TITLE)} &mdash; ASM Leviasynth on the OXI E16</h1>
<p class="sub">All {len(scene.PARAMS)} CC-addressable patch parameters across
{len(scene.LAYOUT)} pages.</p>
<p class="meta">Generated from gen_leviasynth_scene.py &middot; CC numbers per
the Leviasynth Desktop Owner's Manual 1.2.1, MIDI CC Charts pp. 169&ndash;172
&middot; {len(placed)} encoders used of {scene.TOTAL_PAGES * 16},
{len(placed) - len(set(placed))} deliberate duplicates</p>

<div class="box">
<b>Before it responds:</b> on the synth, go to MIDI Parameters page 3 and set
<b>Parameter RX = CC</b>. Set <b>Parameter TX = CC</b> as well if you want the
Leviasynth's own knobs to push the E16's encoders back into sync. The scene
sends on <b>MIDI channel {scene.PAGE_CHANNEL}</b> &mdash; match that to the RX
Global channel. Page&nbsp;1 is the exception: everything there except
Polyphony, Density and Unison Detune is a System MIDI control and works
regardless.
</div>

<h2>Why the layout is shaped this way</h2>
<p class="lead">Pages follow the instrument's own signal flow:</p>
<div class="flow">{flow}</div>
<p class="lead">Three modulators are pre-wired, and that pairing is the
backbone of the layout: <b>ENV&nbsp;1 and LFO&nbsp;1 feed the digital
filter</b>, <b>ENV&nbsp;2 and LFO&nbsp;2 the analog filter</b>, and
<b>ENV&nbsp;3 and LFO&nbsp;3 the VCA</b>. The FILT, ENV and LFO pages all use
the same row order, so row&nbsp;1 is always the digital-filter chain,
row&nbsp;2 the analog one and row&nbsp;3 the VCA. The colours encode the same
thing: each envelope and LFO borrows the hue of whatever it is wired to, so
row colour alone tells you the destination.</p>
<p class="lead">The oscillators get both treatments. Pages&nbsp;2 and&nbsp;3
give each oscillator its own row for per-operator editing, matching how the
synth itself is organised and how it colour-codes its panel. Page&nbsp;9
repeats all eight levels and all eight pitches side by side, because on an
eight-operator engine the relative balance between operators <em>is</em> the
timbre, and that is a gesture you want in one pass.</p>

<h2>The pages</h2>
{grids}

<h2>Colour key</h2>
<p class="lead">The E16 stores a control colour as an index from 0 to 100
&mdash; a &ldquo;colour rotation&rdquo; in the manual's words (section 2.8).
The swatches here are sampled from the spectrum strip that manual prints on
its page&nbsp;21, so they are the device's real colours:</p>
{palette_strip()}
<p class="lead">Two things about this palette are worth knowing before
assigning anything. It is <em>not</em> a hue ramp &mdash; neighbouring indices
are not neighbouring colours, so stepping an index by 10 gives an unrelated
colour rather than a shade. And it contains <em>no orange and no yellow</em>
at all.</p>
<p class="lead">The oscillators follow the Leviasynth's own panel coding,
which runs cyan, green, yellow, orange, orange, red, magenta, blue across
oscillators&nbsp;1&ndash;8. Five match exactly (1, 2, 6, 7, 8) and
oscillator&nbsp;3 takes lime as the nearest thing to yellow. Oscillators 4
and&nbsp;5 are both orange on the panel and have no match here at all, so they
take pink and slate purple &mdash; chosen to stay distinct from their
neighbours rather than to resemble the synth. The one cost of matching the
panel is that oscillator&nbsp;2's green and oscillator&nbsp;3's lime sit on
adjacent rows and are the closest neighbouring pair in the scene.</p>
<p class="lead">Hue indices repeat across pages &mdash; the oscillator colours reuse the same indices as the filter, FX and voice groups. That is deliberate and harmless: no two groups sharing a hue ever appear on the same page, so within any one page the colours stay unambiguous. Each entry below lists the pages it shows up on.</p>
{render_legend()}

<h2>What is not mapped</h2>
<ul class="plain">
<li><b>22 of the 128 CCs.</b> Eighteen the chart marks Reserved, plus bank
select MSB/LSB (0, 32), all notes off (123) and the sustain pedal (64, better
left to an actual pedal).</li>
<li><b>Parameters with no CC at all</b>, which stay device-only: digital filter
Type, Drive Pos, Vowel Order, PolyAT and D.&nbsp;Filt Level; analog filter
PolyAT; per-oscillator Mode, Waveform, Env Level and Keytrack; envelope Delay,
Hold, curves and speed modes; LFO Speed Mode, Trig Sync, Delay, Fade In and
Quantize; the Mod Matrix; and everything in the arpeggiator and
sequencer.</li>
<li><b>Higher resolution.</b> Native ranges are 0.0&ndash;128.0 and bipolar
&plusmn;64.0, but 7-bit CC gives 128 steps: the top value is unreachable and
bipolar centre lands near, not exactly on, 64. Keytrack is worst, squeezing
&minus;200%&hellip;+200% into 128 steps at roughly 3.1% per detent. NRPN would
fix this, but the manual publishes the CC chart and never the NRPN
numbers.</li>
</ul>

<h2>Known unknowns</h2>
<p class="lead">Three things could not be verified without the hardware in
front of it:</p>
<ul class="plain">
<li><code>CC_TURN_MODE = {scene.CC_TURN_MODE}</code> is what current firmware
writes for a CC encoder, taken from the stock Leviasynth scene. The older
hand-built TR1000 scene uses <code>mode 3</code>. It is a named constant at
the top of the generator &mdash; flip it if encoder tracking fights the
synth's feedback.</li>
<li><b>No bipolar display.</b> Every turn action uses
<code>display: 10</code>, because there is no verified value for a
centre-detent display. The parameters marked &plusmn; in the grids above are
the ones that want it.</li>
<li><b>Enum encoders will feel steppy</b>, and their range was deliberately
left at the full 0&ndash;127. How the synth quantises 128 CC values onto nine
polyphony modes or eleven LFO waveforms is undocumented, so narrowing the
range would be guesswork. Measure on the device first.</li>
</ul>

<h2 class="brk">Parameter index</h2>
<p class="lead">All {len(scene.PARAMS)} parameters by CC number. The &plusmn;,
&#9642; and &#9643; marks in the grids correspond to the native range column
here. Bipolar parameters are natively &plusmn;64.0, &plusmn;128.0 or
&plusmn;200% depending on which one &mdash; what matters for the E16 is that
they all want a centre detent rather than a 0-up sweep.</p>
{render_index()}

</body></html>"""


def main() -> None:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path, nargs="?",
                   default=here / f"{scene.SCENE_TITLE}_reference.pdf",
                   help="PDF to write (default: alongside this script).")
    p.add_argument("--chrome", default=CHROME,
                   help="Path to the Chrome binary.")
    p.add_argument("--keep-html", action="store_true",
                   help="Also write the intermediate HTML next to the PDF.")
    args = p.parse_args()

    scene.check_tables()
    markup = build_html()

    if args.keep_html:
        html_path = args.output.with_suffix(".html")
        html_path.write_text(markup)
        print(f"wrote {html_path}")

    chrome = Path(args.chrome)
    if not chrome.exists():
        raise SystemExit(f"Chrome not found at {chrome} — pass --chrome.")

    # Chrome will only load a file:// URL it can see, and writes the PDF
    # relative to its own cwd, so stage both in a scratch directory.
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.html"
        dst = Path(tmp) / "doc.pdf"
        src.write_text(markup)
        result = subprocess.run(
            [str(chrome), "--headless", "--disable-gpu", "--no-sandbox",
             "--no-pdf-header-footer", "--virtual-time-budget=4000",
             f"--print-to-pdf={dst}", src.as_uri()],
            capture_output=True, text=True, timeout=120)
        if not dst.exists():
            raise SystemExit("Chrome produced no PDF.\n"
                             f"{result.stdout}\n{result.stderr}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dst, args.output)

    size_kb = args.output.stat().st_size / 1024
    print(f"wrote {args.output} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
