# REPORT M2 · Mika · Tag A beacon (HEIMDALL-AC1)

**Time:** ✏️ _fill in_
**Status:** 🟡 **PARTIAL**: becomes DONE once the decode counts below are filled in
**Branch:** `mika/M2-tag-beacon` (last code commit `6c4f9c1`)

---

## Summary

| Item | Result |
|---|---|
| Files | ✅ Hashes matched the task before any edit (`heimdall_ac1.h` `8a30fb20…`, `tag.ino` `0a6e738c…`) |
| Compile + upload | ✅ Core 3.3.12, `esp32:esp32:XIAO_ESP32S3_Plus` (after one compile fix, see below) |
| Beacon | ✅ `TX id=A001` every 8 ± 1 s, bands 1 → 2 → 3 → 0, first frame `A0010008E0E3` as specified |
| IMU | ✅ OK, \|a\| at rest **0.999 g** |
| Audio | Plan A (PWM, **square-wave mode**), knob at ✏️ __ |
| Laptop decode, 1 m | ✏️ __/10 |
| Laptop decode, 2 m | ✏️ __/10 |
| Motion: STILL | ✅ `STILL 20s` after ~20 s |
| Motion: MOVE on gentle rocking | ✏️ yes / no |
| False MOVE from own sound/motor | ✅ none: ~5 min still (36 frames), no `MOVE`. No threshold changed. |
| Touch cycles status | ✅ ok → injured → critical → no_response → ok |
| SOS button toggles | ✅ off: frames stop · on: `TX` within 0.5 s |
| Power bank start | ✏️ yes / no |

An earlier decode run with a loose 5V wire gave **5/10** (band 1: 3/3, band 0: 0/3). The counts above are from after that wire was fixed.

---

## Changes to `tag.ino` (header untouched)

1. **Compile fix** (`b98bba2`): `struct Debounced` moved above the first function. Arduino's auto-generated prototype for `pressed()` was inserted before the type existed. No logic change.
2. **Touch pad ignored during own sound** (`852496d`): while a frame plays and for `QUIET_AFTER_MS` (300 ms) after. The speaker drive made the TTP223 fire once per frame and cycle the status by itself. Verified on hardware: 11 frames with no false status change.
3. **`PWM_SQUARE = true`** (`6c4f9c1`): each sample is sent as full on / full off, a square wave at the chirp frequency. The sampled 8-bit PWM was too quiet on the Grove Speaker (no decodes at all); square-wave decodes. Simulated with `modem/heimdall_ac1.py`: 20/20 frames on all four bands. Set `PWM_SQUARE = false` for the original behaviour.

---

## Problems and how they were solved

| Problem | Fix |
|---|---|
| Compile error: `'Debounced' was not declared in this scope` | Moved the struct above the first function (change 1) |
| Touch pad changed status by itself, once per frame | Ignore touch during own frame + 300 ms (change 2) |
| Speaker and motor silent | **5V rail dead**: the XIAO 5V → rail wire was loose. Reseated. |
| Speaker played only when the Tag was tilted | Loose contact on the speaker / 5V wiring. Reseated and taped. |
| Sampled PWM too quiet to decode | Square-wave output (change 3) |
| SOS / status toggled unexpectedly during tests | Commands were pasted into the serial monitor: every `s`, `b`, `h`, digit is a Tag command. Only single-letter commands go there. |

---

## Notes for the demo

- **`min` counts from the last SOS on.** Don't press the SOS button after power-on, or the Tag restarts at 0 minutes and loses its "longest since SOS" rank.
- Status starts as **injured** at power-on. Touch = next status. To set it back from the laptop, type `2` in the monitor.
- Wires are taped. Re-check the 5V wire and the speaker plug before the run: both came loose once.

---

## Files

| File | Notes |
|---|---|
| `firmware/tag/heimdall_ac1.h` | byte-identical to the task |
| `firmware/tag/tag.ino` | task version + the 3 changes above |
| `firmware/tag/REPORT_M2.md` | this report |

**Questions for Namig:** square-wave output works with this speaker but has more overtones than the sampled signal. OK for the demo, or do you want Plan B (Speaker Bonnet) if there is time?
