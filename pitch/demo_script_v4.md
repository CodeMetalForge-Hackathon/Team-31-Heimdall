# HEIMDALL · Demo script v4 (about 75 seconds)

Built from v3 at 03:40 Sunday for the 05:00 run (Giorgi reviews when he's up). Giorgi narrates. Mika and Erdeni run the hardware. Namig runs the laptop and the backup video.
Operator phone mirrored on the big screen. Anything in `[TBD: ...]` is waiting on someone; do not say it until it's filled in.

## What changed since v3
- **Cut, and never claimed as working:** LoRa to the command post (the closing line now says "next"), knock-back on the Tag, flying the drone (it stays on the table).
- **Victim B is "the Tag"** (id A001), our hardware Tag. If it fails its go/no-go, Victim B is a phone and Namig sets the station to ignore that phone's id instead.
- **Phone A's relay is OFF.** If phone A also relays the Tag, the station can take the Tag's direction from pile A and aim at the wrong pile. Only phone C relays.
- **The Tag starts at least 3 minutes before phone A's SOS.** Once both victims are still and injured, the list and the head rank the one with more minutes since SOS first. That has to be the Tag, or the head never swings to it.
- **Phone C runs "relay only"** (`victim.html?mode=relay`). It listens and passes on, sends nothing of its own, and never shows up as a victim.
- **Everything moves 8 s earlier** without the drone flight. The Tag goes down at 0:20 and flips to "stopped moving" between 0:41 and 0:52.

## T minus 15 minutes: setup checklist

**Positions (tape marks on the floor)**
- [ ] Station on tape **X**, front arrow pointing between the two piles.
- [ ] Pile A on its mark, about 2 m away, about 35° left of the front arrow. Opening faces the station.
- [ ] Pile B on its mark, about 2 m away, about 35° right. Opening faces the station. Erdeni's knock board on pile B.
- [ ] Relay phone C on its mark next to pile B, speaker facing the station.
- [ ] Nothing that chirps behind the station. Judges' table not behind it either if we can help it.
- [ ] Drone on the table next to the station.

**The Tag, then the phones (in this order)**
- [ ] **T-15 or earlier: the Tag on its power bank.** It starts beaconing by itself, status Injured. Mika holds it.
- [ ] **Phone A, at least 3 minutes after the Tag:** victim page, settings: **relay OFF**, status **Injured**. Tap SOS. Propped up in pile A's opening, speaker toward the station.
- [ ] **Phone C:** open `https://10.42.0.1:8443/victim.html?mode=relay` and tap SOS. The screen says "Relay only". On its mark next to pile B.
- [ ] Every phone: volume to max, iPhone silent switch **off**, Auto-Lock: Never, page open.
- [ ] Every phone and the operator laptop: on the **HEIMDALL** Wi-Fi, with auto-join **off** for every other network (after a power cut they otherwise drift back to the venue Wi-Fi).

**Station and screens**
- [ ] Namig: `ear/tools/demo_up.sh --relay A001` [TBD: `--bands` / `--acc` from Namig's direction check]. No fake data.
- [ ] Camera head in **AUTO**.
- [ ] Operator phone mirrored to the projector. Both victim cards solid (not "unconfirmed"); the Tag's card says **via 1 relay**.
- [ ] Backup video paused at 0:00 on the laptop, one key away. Laptop on charge.
- [ ] Stopwatch ready (Giorgi).

## The 75 seconds

| Time | Who does what | Judges see | Giorgi says | Fallback |
|---|---|---|---|---|
| 0:00 to 0:08 | Mika crouches at pile B holding the Tag in the opening, moving it gently. | Two piles of rubble. | "Two people are trapped here. One has a phone. One has our Tag." | None needed. |
| 0:08 to 0:20 | Erdeni carries the station in, sets it on X, steps back. The head turns about 35° left to Victim A. | The camera head turning by itself. Thermal box on the warm target. | "In the field a small drone scouts ahead; venue rules keep ours on the table today. The station hears the chirp, works out the direction, and turns the thermal camera to look." | No turn within 15 s: Namig switches to the backup video. "Here is the same run from tonight." Thermal not live on the Pi: "the thermal view comes from the camera's phone app today" [TBD: thermal live on Pi, Erdeni]. |
| 0:20 | **Cue:** when Erdeni steps back, Mika sets the Tag down in the opening, lets go, and doesn't touch it again. | Nothing yet. | (keep talking) | None. |
| 0:20 to 0:32 | Namig points at the screen. | Operator phone: arrow "TURN LEFT 35°". Triage list: A and the Tag, both injured. | "The operator sees which way to walk. And a list of who's trapped, how hurt, and how many people are with them." | Arrow missing: point at the head instead. "The camera already points the way." |
| 0:32 to 0:42 | Namig points at relay phone C, then at the Tag's purple "via 1 relay". | The Tag's card with **via 1 relay**. | "One honest note. This room is small, so the station would hear everyone directly. We set it to ignore the Tag's own signal. It only gets through because this phone heard it and passed it on. That's how a signal gets out from deep inside." | No relayed frames: open phone C's relay log on screen: "Passed on … hop 1". |
| 0:42 to 0:54 | Nobody touches anything. The Tag has been still for over 20 s. | The Tag's card pulses red **STOPPED MOVING** and jumps to the top. **The head swings right from A to the Tag by itself.** | "This person just stopped moving. That makes them the most urgent. Watch the camera: nobody is touching it. It decides on its own who to look at first." | Not flipped yet: "In a few seconds this card jumps to the top" and wait up to 8 s. Card flips but the head doesn't swing: point at the card and the arrow, move on. |
| 0:54 to 1:04 | Erdeni knocks 3 times on the knock board on pile B. [TBD: knock board works, Erdeni] | Knock card: "3 knocks". | "The station also feels a rescuer's knocks. Next, the Tag will buzz so the person can knock back." | Knock card doesn't appear: skip the line, go to the close. Knock board not working at the 05:00 run: cut this beat. |
| 1:04 to 1:12 | Giorgi points at the operator phone. | The triage list. | "Today the operator sees all of this here, over the station's own Wi-Fi, no internet needed. Next, each station reports to command over long-range radio." | None. |

**Global fallback:** if sound fails at any point (noisy room, judges talking over it), Namig plays the backup video and Giorgi narrates the same lines over it. Never debug live.

## Cue words
- Giorgi: **"Let's show you."** starts the demo and the stopwatch.
- Erdeni stepping back from the station: **Mika sets the Tag down.**
- Namig: **"Backup."** (quietly) means switching to the video.
- Giorgi: **"Next, each station reports to command over long-range radio."** is the last demo line; hand back to the close.

## Checks at the 05:00 and 06:30 runs
- [ ] Two full runs with a stopwatch; write down every step that fails or runs long.
- [ ] The head finds A within 12 s of the station landing on X.
- [ ] The Tag's card says "via 1 relay" the whole time.
- [ ] The Tag flips to "stopped moving" between 0:41 and 0:52 when set down at 0:20, and the head swings by itself.
- [ ] Nobody touched the operator phone's cards during the run.
- [ ] The relay sentence sounds calm, not like an excuse.
- [ ] Backup video recorded from the first good full run (wide shot from behind the station + operator phone screen recording).
