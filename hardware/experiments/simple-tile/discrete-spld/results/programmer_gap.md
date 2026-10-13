# ATF22LV10C programmer gap — upstream evidence + bench plan

Task: inspect the upstream Afterburner and minipro sources for the exact
ATF22LV10C programming gap; do NOT program hardware, do NOT patch a
programmer, do NOT guess VPP values.  All evidence below is verbatim from
read-only clones made 2026-10-12:

* `afterburner_ds`  = github.com/ole00/afterburner @ 7636cc724163 (2026-09-21)
* `minipro_ds`      = gitlab.com/DavidGriffith/minipro @ 3e2f4911fa86 (2026-09-21)

## 1. What the two open-source codebases support today

### afterburner (Arduino-UNO GAL programmer)

* Supported list (afterburner.ino header comment, lines 24-30): Lattice
  GAL16V8/GAL20V8/GAL22V10B, plus Atmel ATF16V8B/C, **ATF22V10B**,
  **ATF22V10CQZ** (device enum lines 178-190: `ATF22V10B`, `ATF22V10C`).
  The ATF22V10C database row (line 430): `5892 fuses, 24 pins, 44 cols,
  132 rows, UES at 5828` — geometrically identical to our decoder
  (tools/jeddec.py) and to the galette fuse map.
* ATF22V10C-specific serial behaviour is special-cased: row addressing is
  MSb-first for ATF22V10C while other 22V10s are LSb-first
  (afterburner.ino comment + switch at lines ~1295-1310), and there is
  dedicated ATF22V10C handling at lines 618, 1358, 1434, 1538, 1851.
* VPP for the ATF family: `setGalDefaults()` lines 1511-1514 sets
  `vpp = 42 /* 10.5V */`; `parsePes()` lines 1538-1548 may override to
  15.5-16.5V from PES contents; `setVPP()` lines 1010-1046 indexes the
  MCP4131 digital pot.  (These are the 5V-class parts' values; nothing to
  infer LV values from.)
* **No `LV10`/`ATF22LV10C` string exists anywhere in the repo** (grep -ri
  over all tracked files: 0 hits).  ATF22LV10C is simply absent.

### minipro (TL866 family)

* `infoic.xml` contains ATF22V10C entries (lines 34946-35069 and duplicates):
  DIP/SOIC24/TSSOP24/PLCC28 packages, `protocol_id=0x2c`,
  `code_memory_size=0x16c4` (= 5892 fuses, matches our .jed QF5892),
  `page_size=0x0084` (= 132 rows), `variant=0xc10c/0xc20c/...`,
  `voltages=0x6200` / `0x2200` (UES variants), `pulse_delay=0x64`,
  `config="atf22v10c_acw"`.
* There are three entry families: plain, `(UES)`, and `EXT` — none for
  ATF22LV10C: `grep -c "ATF22LV10" infoic.xml` = **0** (`LV10` matches are
  12 unrelated strings, e.g. "GAL16LV8" no such).  So minipro-driven TL866
  units cannot select ATF22LV10C today.

## 2. Datasheet facts for the LV part (doc0780M, Microchip)

* ATF22LV10C: 3.0-5.5 V operating VCC, inputs 5V-tolerant; JEDEC fuse array
  identical architecture (5892 fuses, 64-bit user signature, pin/timing in
  QZ option per doc0735-class figures).
* Programming section (doc0780M §6) explicitly defers: "Programming/erasing
  is performed using standard PLD programmers. See CMOS PLD Programming
  Hardware & Software Support for information on software/programming." →
  the definitive pin/voltage/timing spec lives in that Atmel applicaton doc.
* Absolute maximum during programming: input pins to +14.0 V
  (doc0780M §3) — the LV part still needs a high-voltage-*tolerant*
  programming window; the NOMINAL VPP/level set is NOT printed in doc0780M.

## 3. The exact gap, stated precisely

1. ATF22LV10C is absent from every open programmer database inspected
   (zero entries in afterburner, zero in minipro).
2. The electrical frame difference that a profile would have to encode is:
   3.3 V supply and logic thresholds during programming (both open tools
   assume 5V-class VCC for the 22V10 family; afterburner's VPP defaults and
   PES parsing are calibrated/tested only for 5V parts, and its PCB
   reference design ties VCC to 5 V).
3. The definitive LV programming parameters (VPP value, program/erase
   pulse widths at 3.3 V) are in the Atmel "CMOS PLD Programming Hardware &
   Software Support" applications doc referenced by doc0780M §6 — NOT
   obtainable here; inventing them = forbidden guess.
4. Positive note: the *fuse-map* layer needs no new work — minipro's
   ATF22V10C entry and afterburner's row/UES geometry both agree with our
   independent decoder (results/jeddec_*.txt), and galette's output matches
   byte-for-byte what these tools expect for 22V10-class parts.

## 4. Bench plan (only when hardware exists; nothing programmed now)

Preconditions: one sacrificial ATF22LV10C-10XU (TSSOP-24), a passive
TSSOP-24 adapter, a TL866II+ (minipro ≥ 2026-09-21) AND an afterburner shield
for cross-checking; current-limited bench supply.

1. **Read-only first.** PES/signature read attempt with the ATF22V10C
   profile, current limit ≤ 10 mA, watch VCC actually delivered with a
   DMM/scope.  ABORT if VCC > 5.5 V at the part pins (abs-max) or if the
   tool asserts VPP for the read (afterburner's READPES path does raise
   VPP — see afterburner.ino 1015-1023 — so for afterburner, intercept at
   the CLI test command only, no source edits in this scope).
2. **Verify decode path.**  If (or as far as) a raw read works, compare the
   flash fuse image against tools/jeddec.py decode — this alone validates
   the toolchain→device model chain without writing.
3. **Write+verify is BLOCKED** on the missing LV profile: do not enable the
   ATF22V10C write path on an LV part.  The gap closure is an UPSTREAM
   profile addition (documented parameters from the Atmel appnote), then
   single-pattern write+verify of logic/pld/results/tile_glue_truez.jed
   (checksum *C92a4, validated here against source equations).
4. **Reporting.**  Log scope traces of VPP/SCLK/SDIN during the program
   burst at 3.3 V, 100 erase/write cycles max per doc0780M's rated limit.

No hardware was touched in this work package; no programmer source was
modified; no VPP value for the LV part is asserted anywhere in the repo —
all LV-side electrical numbers above are marked either 'datasheet' (with
section) or 'appnote not obtainable' (explicit gap).
