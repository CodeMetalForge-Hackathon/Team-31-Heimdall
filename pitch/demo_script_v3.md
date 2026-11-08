# HEIMDALL · Demo script v3 (90 seconds)

Built from v2 with tonight's station numbers. Giorgi narrates. Mika and Erdeni run the hardware. Namig runs the laptop and the backup video.
Operator phone mirrored on the big screen. Anything in `[TBD: ...]` is waiting on someone; do not say it until it's filled in.

## What changed since v2
- **Stage geometry:** both piles about **2 m** from the station, both **in front**: pile A about 35° left, pile B about 35° right. Knee-high, with an opening toward the station. The station hears poorly from behind (16% of chirps), so nothing goes behind it.
- **New beat: the head picks the most urgent victim by itself.** In automatic mode it goes to critical first, then "stopped moving". When Tag B stops moving, the head swings from A to B with nobody touching anything.
- **Tag B goes down at 0:28, not 0:00.** "Stopped moving" flips 20 to 28 s after the Tag is set down. If it flipped before the station arrived, the head would go straight to B and we'd lose the A beat.
- **The relay is on from the start.** The station setting ignores Tag B's direct signal, so Victim B's card shows "via 1 relay" the whole time. We explain it while we wait for B to stop moving.
- **Nobody taps victim cards on the operator phone during the demo.** A tap aims the camera by hand and switches the head to manual, which kills the automatic swing.

## T minus 10 minutes: setup checklist

**Positions (tape marks on the floor)**
- [ ] Station on tape **X**, front arrow pointing between the two piles.
- [ ] Pile A on its mark, about 2 m away, about 35° left of the front arrow. Opening faces the station.
- [ ] Pile B on its mark, about 2 m away, about 35° right. Opening faces the station. Erdeni's knock board on pile B.
- [ ] Relay phone C on its mark next to pile B, speaker facing the station.
- [ ] Nothing that chirps behind the station. Judges' table not behind it either if we can help it.

**Phones**
- [ ] Victim A phone, Victim B Tag, relay phone C: volume to max, speakers facing the station.
- [ ] iPhones: silent switch **off**. Screens set to stay on (Auto-Lock: Never) and the victim page open.
- [ ] Victim A phone sits in pile A's opening, propped up. Status **Injured**. SOS started.
- [ ] Victim B Tag: status **Injured** (not critical, or the head goes to B first). SOS started [TBD: Tag SOS button works, Mika]. Mika holds it in pile B's opening, moving it gently.
- [ ] Relay phone C: relay **on**, SOS **off** (it only passes on Tag B).

**Station and screens**
- [ ] Station setting "ignore Tag B direct" **on** (Namig).
- [ ] Camera head in **AUTO**.
- [ ] Operator phone mirrored to the projector; both victim cards solid (not "unconfirmed") before we start.
- [ ] Command post screen on and visible [TBD: command post screen live, Erdeni].
- [ ] Backup video paused at 0:00 on the laptop, one key away. Laptop on charge.
- [ ] Drone charged and on its landing mark [TBD: may we fly, Giorgi].
- [ ] Stopwatch ready (Giorgi).

## The 90 seconds

| Time | Who does what | Judges see | Giorgi says | Fallback |
|---|---|---|---|---|
| 0:00 to 0:08 | Mika crouches at pile B holding the Tag in the opening, moving it gently. | Two piles of rubble. | "Two people are trapped here. One has a phone. One has our tag." | None needed. |
| 0:08 to 0:18 | Mika flies the small drone over the piles and lands it. [TBD: drone model, may we fly] | The drone scouting. | "A small drone scouts ahead and finds the area." | Not allowed to fly: drone stays on the table. "Venue rules keep it on the table. In the field it scouts ahead." |
| 0:18 to 0:30 | Erdeni carries the station in and sets it on X, then steps back. The head turns about 35° left to Victim A. | The camera head turning by itself. Thermal box on the warm target. | "The station hears the chirp, works out the direction, and turns the thermal camera to look." | No turn within 15 s: Namig switches to the backup video. "Here is the same run from tonight." Thermal not live on the Pi: "the thermal view comes from the camera's phone app today" [TBD: thermal live on Pi, Erdeni]. |
| 0:28 | **Cue:** when Erdeni steps back, Mika sets Tag B down in the opening and lets go. | Nothing yet. | (keep talking) | None. |
| 0:30 to 0:42 | Namig points at the screen. | Operator phone: arrow "TURN LEFT 35°". Triage list: A and B, both injured. | "The operator sees which way to walk. And a list of who's trapped, how hurt, and how many people are with them." | Arrow missing: point at the head instead. "The camera already points the way." |
| 0:42 to 0:54 | Namig points at relay phone C, then at B's purple "via 1 relay". | B's card with **via 1 relay**. | "One honest note. This room is small, so the station would hear everyone directly. We set it to ignore this tag's own signal. It only gets through because this phone heard it and passed it on. That's how a signal gets out from deep inside." | No relayed frames: open phone C's relay log on screen: "Passed on … hop 1". |
| 0:54 to 1:06 | Nobody touches anything. Tag B has been still for over 20 s. | B's card pulses red **STOPPED MOVING** and jumps to the top. **The head swings right from A to B by itself.** | "This person just stopped moving. That makes them the most urgent. Watch the camera: nobody is touching it. It decides on its own who to look at first." | Not flipped yet: "In a few seconds this card jumps to the top" and wait up to 8 s. Card flips but head doesn't swing: point at the card and the arrow, move on. |
| 1:06 to 1:18 | Erdeni knocks 3 times on the knock board on pile B. Mika taps back on a box. [TBD: knock-back on the Tag, Mika] | Knock card: "3 knocks". B's card: "heard knock". | "A rescuer knocks. The tag feels it and tells the person to tap back. Now we know they're conscious." | Tag doesn't react: show only the station's knock card. "The station felt the knock." |
| 1:18 to 1:30 | Erdeni points at the command post screen. [TBD: command post screen live, Erdeni] | Reports arriving over LoRa. | "And command already knows. Over long-range radio. No internet, no cell network, no GPS." | LoRa down: point at the LoRa card on the operator phone ("packets sent"). |

**Global fallback:** if sound fails at any point (noisy room, judges talking over it), Namig plays the backup video and Giorgi narrates the same lines over it. Never debug live.

## Cue words
- Giorgi: **"Let's show you."** starts the demo and the stopwatch.
- Erdeni stepping back from the station: **Mika sets Tag B down.**
- Namig: **"Backup."** (quietly) means switching to the video.
- Giorgi: **"And command already knows."** is the last demo line; hand back to the close.

## Rehearsal #1 checks
- [ ] Two full runs in a row with a stopwatch; write down every step that fails or runs long.
- [ ] Head finds A within 12 s of the station landing on X.
- [ ] B flips between 0:48 and 1:00 when set down at 0:28, and the head swings by itself.
- [ ] Nobody touched the operator phone's cards during the run.
- [ ] The relay sentence sounds calm, not like an excuse.
- [ ] Backup video recorded from the first good full run (wide shot from behind the station + operator phone screen recording).
