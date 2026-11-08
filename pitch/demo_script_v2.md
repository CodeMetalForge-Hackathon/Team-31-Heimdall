# HEIMDALL · Demo script v2 (90 seconds)

Re-timed from `pitch_kit.md` section 4 with the facts as of Saturday 17:30.
Giorgi narrates. Mika and Erdeni run the hardware. Namig runs the laptop and the backup video.
Operator phone mirrored on the big screen. Anything in `[TBD: ...]` is waiting on an engineer; do not say it until it's filled in.

## What changed since v1
- "Stopped moving" now flips **about 20 to 30 s** after the Tag is set down (20 s demo window plus up to one 8 s chirp). It now shows up together with the triage reveal, not as its own step.
- The relay step uses a **station setting that ignores Victim B's direct signal**. We say this out loud. Judges trust it more when we tell them first.
- New beacons show as **unconfirmed** until the station hears them twice. Expect each card to look dimmed for its first 8 s.
- We never say "AI on the station". We say "all processing runs on the station, offline".

## Before we start (T minus 2 min)
- Rubble pile A (left) and pile B (right), [TBD: station range] from the station spot.
- **Victim A (phone)** behind pile A, on the station Wi-Fi, SOS tapped at T minus 30 s so its card is already confirmed.
- **Victim B (Tag)** in Mika's hand, moving gently. SOS started at T minus 30 s [TBD: Tag SOS button works, Mika].
- **Relay phone C** near pile B, relay on. Station setting "ignore Victim B direct" ON (Namig).
- Backup video paused at 0:00 on the laptop, one key away.

## The 90 seconds

| Time | Who does what | Judges see | Giorgi says | Fallback |
|---|---|---|---|---|
| 0:00 to 0:08 | Mika sets Tag B down behind pile B and leaves it still. This starts the 20 s "stopped moving" clock. | Two piles of rubble. | "Two people are trapped here. One has a phone. One has our tag." | None needed. |
| 0:08 to 0:18 | Mika flies the small drone over the piles and lands it. [TBD: drone model, can we fly, Giorgi 18:00] | The drone scouting. | "A small drone scouts ahead and finds the area." | Not allowed to fly: drone stays on the table. "Venue rules keep it on the table. In the field it scouts ahead." |
| 0:18 to 0:33 | Erdeni carries the station in and sets it on the tape X. The pan-tilt head turns toward Victim A. | The camera head turning by itself. Thermal view with a box on the warm target. | "The station hears the chirp, works out the direction, and turns the thermal camera to look." | No turn within 15 s: Namig switches to the backup video. "Here is the same run from this afternoon." Thermal not live on the Pi: "the thermal view comes from the camera's phone app today" [TBD: thermal live on Pi, Erdeni]. |
| 0:33 to 0:50 | Nobody moves. Namig points at the screen. | Operator phone: arrow "TURN LEFT 30°" and the triage queue. Victim B is on top with a pulsing red **STOPPED MOVING**. | "The operator sees which way to walk. And a list of who's trapped, how hurt, and how many people are with them. This person stopped moving. They go first." | B not flipped yet: keep talking 8 more seconds, it updates on the next chirp. Still not: "In about ten seconds this card jumps to the top" and move on. |
| 0:50 to 1:02 | Erdeni knocks 3 times on pile B. Mika taps back on a box. [TBD: knock-back on the Tag, Mika] | Knock card: "3 knocks". Victim B's card: "heard knock". | "A rescuer knocks. The tag feels it and tells the person to tap back. Now we know they're conscious." | Tag doesn't react: show only the station's knock card. "The station felt the knock." |
| 1:02 to 1:17 | Namig points at relay phone C. | A card with purple **via 1 relay**. | "One honest note. This room is small, so the station hears everyone directly. We set the station to ignore this tag's own signal. The only way it gets through now is this phone, which heard the tag and passed it on. That's how a signal gets out from deep inside." | No relayed frame: open phone C's relay log on screen: "Passed on … hop 1". |
| 1:17 to 1:30 | Erdeni points at the command post screen. [TBD: command post screen live, Erdeni] | Reports arriving over LoRa. | "And command already knows. Over long-range radio. No internet, no cell network, no GPS." | LoRa down: point at the LoRa card on the operator phone ("packets sent"). |

**Global fallback:** if sound fails at any point (noisy room, judges talking over it), Namig plays the backup video and Giorgi narrates the same lines over it. Never debug live.

## Cue words
- Giorgi: **"Let's show you."** starts the demo.
- Namig: **"Backup."** (quietly) means switching to the video.
- Giorgi: **"And command already knows."** is the last demo line; hand back to the close.

## Rehearsal checks (Gate C)
- [ ] Time all 7 steps with a stopwatch, twice in a row.
- [ ] Confirm "stopped moving" appears between 0:33 and 0:50 when the Tag goes down at 0:00.
- [ ] Practice the relay sentence word for word; it must sound calm, not like an excuse.
- [ ] Backup video recorded from a full good run, same order as this table.
