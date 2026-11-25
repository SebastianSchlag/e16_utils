#!/usr/bin/env python3
"""
MicroMonsta 2 -> OXI E16 fetch bridge.

Sends the MM2 'fetch active timbre' SysEx, decodes the 176-byte patch
dump that comes back, and re-emits every parameter as NRPN on the E16's
input so the E16's MIDI feedback updates each knob to match the patch
currently loaded on the MM2.

Run `python mm2_bridge.py --list` first to discover port names.

Dependencies:  pip install mido python-rtmidi
"""

from __future__ import annotations

import argparse
import sys
import time

import mido


FETCH_HEADER = bytes([0xF0, 0x00, 0x21, 0x22, 0x4D, 0x02])
FETCH_TERM = 0xF7
DUMP_HEADER = bytes([0xF0, 0x00, 0x21, 0x22, 0x4D, 0x02, 0x03, 0x10])
DUMP_LEN = 176


# (sysex_offset, nrpn_number, is_14bit, key, title)
PARAMS: list[tuple[int, int, bool, str, str]] = [
    ( 16,   9, False, "cat", "Category"),
    ( 17,  10, False, "knf", "F Knob Assignment"),
    ( 18,  11, False, "knq", "Q Knob Assignment"),
    ( 19,  12, False, "knm", "M Knob Assignment"),
    ( 20,  13, False, "en1", "Encoder 1 Assignment"),
    ( 21,  14, False, "en2", "Encoder 2 Assignment"),
    ( 22,  15, False, "en3", "Encoder 3 Assignment"),
    ( 23,  16, False, "en4", "Encoder 4 Assignment"),
    ( 24,  17, False, "mix", "Program Volume"),
    ( 25,  18, True , "bpm", "Program Tempo"),
    ( 27,  19, False, "vde", "Voice Detune"),
    ( 28,  20, False, "ode", "Oscillator Detune"),
    ( 29,  21, False, "psp", "Pan Spread"),
    ( 30,  22, False, "gld", "Glide Time"),
    ( 31,  23, False, "bdo", "Pitch Bend Down"),
    ( 32,  24, False, "bup", "Pitch Bend Up"),
    ( 33,  25, False, "vcs", "VCA Velocity Sensitivity"),
    ( 34,  26, False, "fes", "Filter Env Velocity Sensitivity"),
    ( 35,  27, False, "o1a", "Oscillator 1 Algorithm"),
    ( 36,  28, False, "o1s", "Oscillator 1 Shape"),
    ( 37,  29, False, "o1c", "Oscillator 1 Coarse Tuning"),
    ( 38,  30, False, "o1f", "Oscillator 1 Fine Tuning"),
    ( 39,  31, False, "o2a", "Oscillator 2 Algorithm"),
    ( 40,  32, False, "o2s", "Oscillator 2 Shape"),
    ( 41,  33, False, "o2c", "Oscillator 2 Coarse Tuning"),
    ( 42,  34, False, "o2f", "Oscillator 2 Fine Tuning"),
    ( 43,  35, False, "o3a", "Oscillator 3 Algorithm"),
    ( 44,  36, False, "o3s", "Oscillator 3 Shape"),
    ( 45,  37, False, "o3c", "Oscillator 3 Coarse Tuning"),
    ( 46,  38, False, "o3f", "Oscillator 3 Fine Tuning"),
    ( 47,  39, False, "mx1", "Oscillator 1 Mix"),
    ( 48,  40, False, "mx2", "Oscillator 2 Mix"),
    ( 49,  41, False, "mx3", "Oscillator 3 Mix"),
    ( 50,  42, False, "nze", "White Noise Mix"),
    ( 51,  43, True , "cut", "Filter Cutoff Frequency"),
    ( 53,  44, False, "res", "Filter Resonance"),
    ( 54,  45, True , "fen", "Filter Envelope Amount"),
    ( 56,  46, False, "fkb", "Filter Keyboard Tracking"),
    ( 57,  47, False, "ffm", "Filter FM Amount from OSC 3"),
    ( 58,  48, False, "drv", "Drive"),
    ( 59,  49, False, "e1a", "Envelope 1 Attack"),
    ( 60,  50, False, "e1d", "Envelope 1 Decay"),
    ( 61,  51, False, "e1s", "Envelope 1 Sustain"),
    ( 62,  52, False, "e1r", "Envelope 1 Release"),
    ( 63,  53, False, "e2a", "Envelope 2 Attack"),
    ( 64,  54, False, "e2d", "Envelope 2 Decay"),
    ( 65,  55, False, "e2s", "Envelope 2 Sustain"),
    ( 66,  56, False, "e2r", "Envelope 2 Release"),
    ( 67,  57, False, "e3a", "Envelope 3 Attack"),
    ( 68,  58, False, "e3d", "Envelope 3 Decay"),
    ( 69,  59, False, "e3s", "Envelope 3 Sustain"),
    ( 70,  60, False, "e3r", "Envelope 3 Release"),
    ( 71,  61, False, "l1w", "LFO 1 Waveform"),
    ( 72,  62, True , "l1s", "LFO 1 Speed"),
    ( 74,  63, False, "l1m", "LFO 1 Trigger Mode"),
    ( 75,  64, False, "l2w", "LFO 2 Waveform"),
    ( 76,  65, True , "l2s", "LFO 2 Speed"),
    ( 78,  66, False, "l2m", "LFO 2 Trigger Mode"),
    ( 79,  67, False, "l3w", "LFO 3 Waveform"),
    ( 80,  68, True , "l3s", "LFO 3 Speed"),
    ( 82,  69, False, "l3m", "LFO 3 Trigger Mode"),
    ( 83,  70, False, "m1s", "Matrix 1 Source"),
    ( 84,  71, False, "m1d", "Matrix 1 Destination"),
    ( 85,  72, True , "m1a", "Matrix 1 Amount"),
    ( 87,  73, False, "m2s", "Matrix 2 Source"),
    ( 88,  74, False, "m2d", "Matrix 2 Destination"),
    ( 89,  75, True , "m2a", "Matrix 2 Amount"),
    ( 91,  76, False, "m3s", "Matrix 3 Source"),
    ( 92,  77, False, "m3d", "Matrix 3 Destination"),
    ( 93,  78, True , "m3a", "Matrix 3 Amount"),
    ( 95,  79, False, "m4s", "Matrix 4 Source"),
    ( 96,  80, False, "m4d", "Matrix 4 Destination"),
    ( 97,  81, True , "m4a", "Matrix 4 Amount"),
    ( 99,  82, False, "m5s", "Matrix 5 Source"),
    (100,  83, False, "m5d", "Matrix 5 Destination"),
    (101,  84, True , "m5a", "Matrix 5 Amount"),
    (103,  85, False, "m6s", "Matrix 6 Source"),
    (104,  86, False, "m6d", "Matrix 6 Destination"),
    (105,  87, True , "m6a", "Matrix 6 Amount"),
    (107,  88, False, "m7s", "Matrix 7 Source"),
    (108,  89, False, "m7d", "Matrix 7 Destination"),
    (109,  90, True , "m7a", "Matrix 7 Amount"),
    (111,  91, False, "m8s", "Matrix 8 Source"),
    (112,  92, False, "m8d", "Matrix 8 Destination"),
    (113,  93, True , "m8a", "Matrix 8 Amount"),
    (115,  94, False, "m9s", "Matrix 9 Source"),
    (116,  95, False, "m9d", "Matrix 9 Destination"),
    (117,  96, True , "m9a", "Matrix 9 Amount"),
    (119,  97, False, "m0s", "Matrix 10 Source"),
    (120,  98, False, "m0d", "Matrix 10 Destination"),
    (121,  99, True , "m0a", "Matrix 10 Amount"),
    (123, 100, False, "g1s", "Lag Operator 1 Source"),
    (124, 101, False, "g1a", "Lag Operator 1 Time"),
    (125, 102, False, "t1a", "Mult Operator 1 Source A"),
    (126, 103, False, "t1b", "Mult Operator 1 Source B"),
    (127, 104, False, "t2a", "Mult Operator 2 Source A"),
    (128, 105, False, "t2b", "Mult Operator 2 Source B"),
    (130, 107, True , "xeq", "EQ Frequency"),
    (132, 108, True , "xdt", "Delay Time"),
    (134, 109, False, "xdf", "Delay Feedback"),
    (135, 110, False, "xdl", "Delay Send Level"),
    (136, 111, False, "xrt", "Reverb Decay Time"),
    (137, 112, False, "xrm", "Reverb Modulation Amount"),
    (138, 113, False, "xrl", "Reverb Send Level"),
    (139, 114, False, "ast", "Arpeggiator Style"),
    (140, 115, False, "agl", "Arpeggiator Gate Length"),
    (141, 116, False, "asp", "Arpeggiator Speed"),
    (142, 117, False, "vmo", "Voice Assignment Mode"),
    (143, 118, False, "vun", "Voice Unison"),
    (144, 119, False, "psm", "Pan Spread Mode"),
    (145, 120, False, "e1x", "Envelope 1 Reset"),
    (146, 121, False, "e2x", "Envelope 2 Reset"),
    (147, 122, False, "e3x", "Envelope 3 Reset"),
    (149, 124, False, "osx", "Oscillator Phase Reset"),
    (150, 125, False, "fty", "Filter Type"),
    (151, 126, False, "fch", "Filter Character"),
    (152, 127, False, "xch", "Chorus Mode"),
    (153, 128, False, "xdm", "Delay Mode"),
    (155, 130, False, "aen", "Enable Arpeggiator"),
    (156, 131, False, "ala", "Arpeggiator Latch"),
    (157, 132, False, "aos", "Arpeggiator Ocatve Spread"),
    (158, 133, False, "ale", "Arpeggiator Pattern Length"),
    (159, 134, False, "a01", "Arpeggiator Step 1"),
    (160, 135, False, "a02", "Arpeggiator Step 2"),
    (161, 136, False, "a03", "Arpeggiator Step 3"),
    (162, 137, False, "a04", "Arpeggiator Step 4"),
    (163, 138, False, "a05", "Arpeggiator Step 5"),
    (164, 139, False, "a06", "Arpeggiator Step 6"),
    (165, 140, False, "a07", "Arpeggiator Step 7"),
    (166, 141, False, "a08", "Arpeggiator Step 8"),
    (167, 142, False, "a09", "Arpeggiator Step 9"),
    (168, 143, False, "a10", "Arpeggiator Step 10"),
    (169, 144, False, "a11", "Arpeggiator Step 11"),
    (170, 145, False, "a12", "Arpeggiator Step 12"),
    (171, 146, False, "a13", "Arpeggiator Step 13"),
    (172, 147, False, "a14", "Arpeggiator Step 14"),
    (173, 148, False, "a15", "Arpeggiator Step 15"),
    (174, 149, False, "a16", "Arpeggiator Step 16"),
]


def list_ports() -> None:
    print("Inputs:")
    for n in mido.get_input_names():
        print(f"  {n}")
    print("\nOutputs:")
    for n in mido.get_output_names():
        print(f"  {n}")


def find_port(name_fragment: str, available: list[str]) -> str:
    matches = [n for n in available if name_fragment.lower() in n.lower()]
    if not matches:
        raise SystemExit(f"No MIDI port matches {name_fragment!r}. "
                         f"Run with --list to see available ports.")
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous port {name_fragment!r}: {matches}")
    return matches[0]


def fetch_dump(mm2_in, mm2_out, slot: int, timeout: float) -> bytes:
    """Send fetch SysEx and wait for the 176-byte dump."""
    # Drain any stale messages.
    while mm2_in.poll() is not None:
        pass

    msg = mido.Message("sysex", data=list(FETCH_HEADER[1:]) + [0x41 + slot])
    mm2_out.send(msg)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = mm2_in.poll()
        if m is None:
            time.sleep(0.005)
            continue
        if m.type != "sysex":
            continue
        # mido strips the leading F0 and trailing F7 from data; rebuild.
        raw = bytes([0xF0]) + bytes(m.data) + bytes([0xF7])
        if len(raw) == DUMP_LEN and raw.startswith(DUMP_HEADER):
            return raw
        print(f"  ignored SysEx (len={len(raw)}, header={raw[:8].hex()})",
              file=sys.stderr)
    raise TimeoutError(f"No valid dump received within {timeout}s.")


def decode_param(dump: bytes, sysex_offset: int, is_14bit: bool) -> int:
    if is_14bit:
        return (dump[sysex_offset] << 7) + dump[sysex_offset + 1]
    return dump[sysex_offset]


def nrpn_messages(channel: int, nrpn: int, value: int, is_14bit: bool):
    """Yield CC messages forming a complete NRPN frame."""
    yield mido.Message("control_change", channel=channel, control=99,
                       value=(nrpn >> 7) & 0x7F)
    yield mido.Message("control_change", channel=channel, control=98,
                       value=nrpn & 0x7F)
    yield mido.Message("control_change", channel=channel, control=6,
                       value=(value >> 7) & 0x7F if is_14bit else value & 0x7F)
    if is_14bit:
        yield mido.Message("control_change", channel=channel, control=38,
                           value=value & 0x7F)


def push_to_e16(dump: bytes, e16_out, channel: int, gap_ms: float,
                verbose: bool) -> None:
    sleep_s = gap_ms / 1000.0
    for sysex_offset, nrpn, is_14bit, key, title in PARAMS:
        value = decode_param(dump, sysex_offset, is_14bit)
        if verbose:
            tag = "14b" if is_14bit else " 7b"
            print(f"  [{tag}] NRPN {nrpn:>3} = {value:>5}  "
                  f"({key} — {title})")
        for m in nrpn_messages(channel, nrpn, value, is_14bit):
            e16_out.send(m)
            if sleep_s:
                time.sleep(sleep_s)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true",
                   help="List available MIDI ports and exit.")
    p.add_argument("--mm2-in", help="MM2 MIDI input port name (substring).")
    p.add_argument("--mm2-out", help="MM2 MIDI output port name (substring).")
    p.add_argument("--e16-out", help="E16 MIDI output port name (substring).")
    p.add_argument("--channel", type=int, default=1,
                   help="MIDI channel for NRPN to E16 (1-16, default 1).")
    p.add_argument("--slot", type=int, default=0,
                   help="MM2 active slot index, 0=A, 1=B, ... (default 0).")
    p.add_argument("--timeout", type=float, default=2.0,
                   help="Seconds to wait for the dump (default 2).")
    p.add_argument("--gap-ms", type=float, default=1.0,
                   help="Delay between MIDI messages, ms (default 1).")
    p.add_argument("--watch", action="store_true",
                   help="Loop: press Enter to re-fetch, Ctrl-C to quit.")
    p.add_argument("--dry-run", action="store_true",
                   help="Decode and print, but don't send NRPN.")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if args.list:
        list_ports()
        return

    for required in ("mm2_in", "mm2_out", "e16_out"):
        if getattr(args, required) is None and not args.dry_run:
            raise SystemExit(f"--{required.replace('_', '-')} is required "
                             f"(or pass --list).")

    if not 1 <= args.channel <= 16:
        raise SystemExit("--channel must be 1-16.")
    if args.slot < 0:
        raise SystemExit("--slot must be >= 0.")

    mm2_in_name = find_port(args.mm2_in, mido.get_input_names())
    mm2_out_name = find_port(args.mm2_out, mido.get_output_names())
    if not args.dry_run:
        e16_out_name = find_port(args.e16_out, mido.get_output_names())

    print(f"MM2 in:  {mm2_in_name}")
    print(f"MM2 out: {mm2_out_name}")
    if not args.dry_run:
        print(f"E16 out: {e16_out_name}")
    print(f"channel: {args.channel}  slot: {args.slot}")

    channel_idx = args.channel - 1

    with mido.open_input(mm2_in_name) as mm2_in, \
         mido.open_output(mm2_out_name) as mm2_out:
        e16_out_ctx = (mido.open_output(e16_out_name)
                       if not args.dry_run else None)
        try:
            while True:
                print("\nFetching...")
                try:
                    dump = fetch_dump(mm2_in, mm2_out, args.slot, args.timeout)
                except TimeoutError as e:
                    print(f"  {e}", file=sys.stderr)
                else:
                    name = dump[8:16].decode("ascii", errors="replace").rstrip()
                    print(f"  got dump, patch name: {name!r}")
                    if args.dry_run:
                        for sx, nrpn, is_14bit, key, title in PARAMS:
                            v = decode_param(dump, sx, is_14bit)
                            print(f"    NRPN {nrpn:>3} = {v:>5}  ({key})")
                    else:
                        push_to_e16(dump, e16_out_ctx, channel_idx,
                                    args.gap_ms, args.verbose)
                        print(f"  sent {len(PARAMS)} parameters as NRPN.")
                if not args.watch:
                    break
                try:
                    input("\nPress Enter to re-fetch (Ctrl-C to quit)... ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
        finally:
            if e16_out_ctx is not None:
                e16_out_ctx.close()


if __name__ == "__main__":
    main()
