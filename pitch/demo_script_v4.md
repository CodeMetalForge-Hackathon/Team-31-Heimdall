# HEIMDALL · Demo script v4 (about 75 seconds)

Built from v3 at 03:40 Sunday; relay moved from the Tag to phone A at 06:45 (Giorgi reviews when he's up). Giorgi narrates. Mika and Erdeni run the hardware. Namig runs the laptop and the backup video.
The operator page runs on the laptop, full screen on the projector (thermal, direction and triage side by side). Anything in `[TBD: ...]` is waiting on someone; do not say it until it's filled in.

## What changed since v3
- **Cut, and never claimed as working:** LoRa to the command post (the closing line now says "next"), knock-back on the Tag, flying the drone (it stays on the table).
- **Victim B is "the Tag"** (id A001), our hardware Tag, heard directly by the station. If it fails its go/no-go, Victim B is a second phone (relay OFF, status Injured).
- **The relay carries phone A, not the Tag.** Phones can't decode the Tag's sound (the station can), so phone C sits next to pile A and passes phone A's call on, and the station ignores phone A's own signal (`--relay 1429`). The Tag is heard directly, so it has its own direction for the swing. Phone A's relay stays OFF; only phone C relays.
- **Phone A's Beacon ID is 1429.** If another phone plays phone A: Settings, Beacon ID 1429, Save, and close the old 1429 page.
- **No minute rule anymore (07:45).** Someone who just stopped moving goes to the top of the list and gets the camera, whatever the minutes since SOS. The Tag and phone A can start in any order, and switching the Tag off and on is harmless as long as it's beeping before the run.
- **Phone C runs "relay only"** (`victim.html?mode=relay`). It listens and passes on, sends nothing of its own, and never shows up as a victim.
- **Everything moves 8 s earlier** without the drone flight. The Tag goes down at 0:20 and flips to "stopped moving" between 0:41 and 0:52.

## T minus 15 minutes: setup checklist

**Positions (tape marks on the floor)**
- [ ] Station on tape **X**, front arrow pointing between the two piles.
- [ ] Pile A on its mark, about 2 m away, about 35° left of the front arrow. Opening faces the station.
- [ ] Pile B on its mark, about 2 m away, about 35° right. Opening faces the station. Erdeni's knock board on pile B.
- [ ] Relay phone C on its mark next to pile A, about half a meter from phone A, speaker facing the station.
- [ ] Nothing that chirps behind the station. Judges' table not behind it either if we can help it.
- [ ] Drone on the table next to the station.

**The Tag, then the phones (in this order)**
- [ ] **T-15 or earlier: the Tag on its power bank.** It starts beaconing by itself, status Injured. Mika holds it.
- [ ] **Never press the Tag's SOS button after power-on:** one press turns its beacon off. Hold the Tag by the board edge, not the touch pad (a touch changes its status; it starts as Injured).
- [ ] Before the run: check the Tag's 5V wire and speaker plug. Both came loose once.
- [ ] **Phone A:** victim page, Beacon ID **1429** at the top, settings: **relay OFF**, status **Injured**. Tap SOS. Propped up in pile A's opening, speaker toward the station.
- [ ] **Phone C:** open `https://10.42.0.1:8443/victim.html?mode=relay` and tap **Start relay**. The button then says Relaying. On its mark next to pile A.
- [ ] Every phone: volume to max, iPhone silent switch **off**, Auto-Lock: Never, page open.
- [ ] Every phone and the operator laptop: on the **HEIMDALL** Wi-Fi, with auto-join **off** for every other network (after a power cut they otherwise drift back to the venue Wi-Fi).

**Station and screens**
- [ ] Namig or Erdeni, on the Pi: `ear/tools/demo_up.sh --relay 1429 --bands 0,3 --acc 3 --boot` (audio, pantilt and thermal; no fake data). If phone A's page shows another Beacon ID, put that id after `--relay`. Bands 0 and 3 only: on demo morning bands 1 and 2 put the Tag on the mirror side about one frame in three.
- [ ] Camera head: its servo direction and zero live in `ear/config.py` (`pan_dir -1`, `pan_offset_deg 30`, measured 09:20 Sunday with the camera taped to the servo horn). If anyone has turned the camera on its servo since, recalibrate first (README, "Demo day").
- [ ] Camera head in **AUTO**.
- [ ] Laptop on the projector: `https://10.42.0.1:8443/operator.html`, full screen, browser zoom until the three panels fill the screen. Both victim cards solid (not "Unconfirmed"); phone A's card says **Via relay**.
- [ ] Backup video paused at 0:00 on the laptop, one key away. Laptop on charge.
- [ ] Stopwatch ready (Giorgi).

## The 75 seconds

| Time | Who does what | Judges see | Giorgi says | Fallback |
|---|---|---|---|---|
| 0:00 to 0:08 | Mika crouches at pile B holding the Tag in the opening, moving it gently. | Two piles of rubble. | "Two people are trapped here. One has a phone. One has our Tag." | None needed. |
| 0:08 to 0:20 | Erdeni carries the station in, sets it on X, steps back. The head turns left to Victim A. | The camera head turning by itself. Thermal box on the warm target. | "In the field a small drone scouts ahead; venue rules keep ours on the table today. The station hears the chirp, works out the direction, and turns the thermal camera to look." | No turn within 15 s: Namig switches to the backup video. "Here is the same run from tonight." Thermal is live on the Pi (checked 09:25 Sunday); picture missing: reload the operator page. |
| 0:20 | **Cue:** when Erdeni steps back, Mika sets the Tag down in the opening, lets go, and doesn't touch it again. | Nothing yet. | (keep talking) | None. |
| 0:20 to 0:32 | Namig points at the screen. | Operator screen: banner "about 27° left" and the blue line to pile A. Triage list: A and the Tag, both injured. | "The operator sees which way to walk. And a list of who's trapped, how hurt, and how many people are with them." | Arrow missing: point at the head instead. "The camera already points the way." |
| 0:32 to 0:42 | Namig points at relay phone C (at pile A), then at phone A's **Via relay** tag. | Phone A's card with **Via relay**. | "One honest note. This room is small, so the station would hear everyone directly. We set it to ignore this person's phone. Its call only gets through because this other phone heard it and passed it on. That's how a signal gets out from deep inside." | No relayed frames: open phone C's relay log on screen: "Passed on 1429 → hop 1". |
| 0:42 to 0:54 | Nobody touches anything. The Tag has been still for over 20 s. | The Tag's row jumps to the top with a pulsing red ring and **Stopped moving**. **The head swings right from A to the Tag by itself, and the operator arrow swings with it.** | "This person just stopped moving. That makes them the most urgent. Watch the camera: nobody is touching it. It decides on its own who to look at first." | Not flipped yet: "In a few seconds this card jumps to the top" and wait up to 8 s. Card flips but the head doesn't swing: point at the card and the arrow, move on. |
| 0:54 to 1:04 | Erdeni knocks 3 times on the knock board on pile B. [TBD: knock board works, Erdeni] | Knock card: "3 knocks". | "The station also feels a rescuer's knocks. Next, the Tag will buzz so the person can knock back." | Knock card doesn't appear: skip the line, go to the close. Knock board not working at the 05:00 run: cut this beat. |
| 1:04 to 1:12 | Giorgi points at the operator screen. | The triage list. | "Today the operator sees all of this here, over the station's own Wi-Fi, no internet needed. Next, each station reports to command over long-range radio." | None. |

**Global fallback:** if sound fails at any point (noisy room, judges talking over it), Namig plays the backup video and Giorgi narrates the same lines over it. Never debug live.

## Cue words
- Giorgi: **"Let's show you."** starts the demo and the stopwatch.
- Erdeni stepping back from the station: **Mika sets the Tag down.**
- Namig: **"Backup."** (quietly) means switching to the video.
- Giorgi: **"Next, each station reports to command over long-range radio."** is the last demo line; hand back to the close.

## Checks at every full run
- [ ] Two full runs with a stopwatch; write down every step that fails or runs long.
- [ ] The head finds A within 12 s of the station landing on X.
- [ ] Phone A's card says "Via relay" the whole time, and the Tag's card has a direction (no "No direction").
- [ ] The Tag flips to "stopped moving" between 0:41 and 0:52 when set down at 0:20, and the head swings by itself.
- [ ] Nobody clicked the cards on the operator screen during the run.
- [ ] The relay sentence sounds calm, not like an excuse.
- [ ] Backup video recorded from the first good full run (wide shot from behind the station + a screen recording of the laptop's operator page, Cmd+Shift+5).
