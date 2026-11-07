# HEIMDALL · Pitch kit

**"Hears who you can't see."** Code Metal Forge 2026, BASE X Boston, sponsored by USSOCOM.
Presenter: Giorgi. Draft v1, Sat Nov 7 2026. For Namig to review before G3 (deck, demo script, rehearsal).

How to read this: every number has a source link in brackets. **[EST]** marks our own estimates. **[CONFIRM]** marks a fact the engineers must check before we say it on stage. The source list is at the end.

---

## 1. One-liner and 30-second elevator pitch

**One-liner (13 words):**
> Heimdall turns any phone into a rescue beacon that works with no network.

Backup one-liner: *A coded SOS chirp that finds trapped people when GPS and networks are gone.*

**30-second elevator pitch (about 80 words):**
> When buildings fall, the networks fall with them. During the Maui fire, 19 of 21 cell sites in the area were down. Rescuers still search the old way: stop, knock, listen.
> Heimdall makes that sound carry data. A phone or a small tag plays a coded chirp: who you are, how hurt you are, how many people are with you. Other phones pass it outward. Our station hears it, aims a thermal camera at it, and radios the report to command.
> No cell. No GPS. No cloud.

Sources: Maui cell sites [S2].

---

## 2. Problem slide content (3 cases)

| Case | The number | What it shows | Source |
|---|---|---|---|
| **Maui wildfire, Aug 2023** | **19 of 21** cell sites in the area out of service (FCC, Aug 13 to 14) | Networks fail exactly when people need them. Maui County alleges at least 14 evacuation alerts "were never received". | [S2] FCC figure; [S3] county allegation |
| **Surfside collapse, June 2021** | **98** people died | Microphones "won't pick up cries for help" from a victim who is unconscious but alive. | [S5] toll; [S4] microphone quote |
| **San José mine, Chile, 2010** | **17 days** before anyone knew the 33 miners were alive | They were found by a probe that detected tapping. Sound was the only channel left. | [S6] |

On-slide wording (short):
- Maui 2023: **19 of 21** cell sites down.
- Surfside 2021: **98** dead. Microphones can't hear the unconscious.
- Chile 2010: **17 days** until tapping was heard.

Wording rules from fact-checking:
- Maui: say "cell sites in the area were out" (FCC). "All 21 towers failed" is Maui County's lawsuit claim; if used, say "Maui County says". Death toll: say "more than 100" or "102" [S3b]; sources differ (101 vs 102).
- Helene (backup, not on the slide): "More than 1,000 people in Buncombe County were unaccounted for while cell service was down" [S1]. Do **not** say they were missing *because* of the outage; the number dropped fast once service came back.
- Do not quote a "72-hour survival rate" as hard data. We found only expert estimates in news coverage, no primary study. If needed, say: "Experts say survival odds fall sharply after the first three days" [S7].

---

## 3. Three-minute pitch script

Speakers: **Giorgi** opens and closes. **Namig** explains the technology. **Mika** and **Erdeni** run the hardware during the demo; Giorgi narrates.

### [0:00 to 0:30] GIORGI: the hook
> In 2010, thirty-three miners were trapped in a mine in Chile.
> For seventeen days, nobody knew if they were alive.
> They were found because a probe picked up tapping.
>
> Today, rescuers still search the same way. Stop. Knock. Listen.
> And when disaster hits, the networks go down. In the Maui fire, nineteen of twenty-one cell sites were out.
>
> In Norse myth, Heimdall is the watchman who hears grass grow.
> We built Heimdall. It hears who you can't see.

*(Myth line source: the Prose Edda says Heimdall "hears how grass grows on the earth or wool on sheep" [S8].)*

### [0:30 to 1:10] NAMIG: how it works
> Here's how it works.
> A victim taps one button on their phone. Or they wear our tag, which starts by itself after a hard fall.
> It plays a two-second chirp every few seconds. That chirp carries data: an ID, the floor, how hurt they are, how many people are with them, and whether they're still moving.
> Other phones that hear it repeat it. So a signal from deep inside can hop outward. No network.
> The rescuer carries our station: a Raspberry Pi with an AI accelerator, a microphone array, and a thermal camera on a motorized head.
> It finds where the chirp came from, turns the camera there, and ranks every victim on the operator's phone.
> Everything runs on the device. Reports go to command over long-range LoRa radio.

### [1:10 to 2:40] DEMO (90 seconds, see section 4)
Giorgi narrates. Mika and Erdeni run the hardware. The operator phone is mirrored on the screen.

### [2:40 to 3:00] GIORGI: the close
> Everything you just saw ran with no internet, no GPS, and no cell network.
> Today it covers one room and two victims. Next: range tests in real rubble, with a rescue team.
> Every phone already has a speaker and a microphone. Heimdall gives them something to say.
> Thank you.

Timing check: about 80 + 100 + narration + 50 words. Rehearse with a timer; if long, cut the myth line, not the numbers.

---

## 4. 90-second live demo choreography

**Set-up before we start (T minus 2 min):**
- Two "rubble" piles of cardboard boxes, 2 to 4 m from where the station will stand [CONFIRM distance that works], one left, one right.
- **Victim A (phone)** behind the left pile, propped up, SOS already started (the button needs a tap, so Mika taps it at T minus 30 s).
- **Victim B (hardware Tag)** behind the right pile. Mika holds it, moving it gently, until the demo starts.
- **Relay phone C** placed so it hears Victim B. See the relay note below.
- Operator phone mirrored to the projector. Command post screen visible.
- Backup video loaded on the laptop, paused at 0:00, one key press away.

| Time | Who does what | Judges see | Giorgi says | Fallback if it fails |
|---|---|---|---|---|
| 0:00 to 0:08 | Mika sets Tag B down behind the right pile and leaves it still (starts its 60 s "not moving" clock). | Two piles of rubble. | "Two people are trapped here. One has a phone. One has our tag." | None needed. |
| 0:08 to 0:20 | Mika flies the small drone over the piles and lands it beside them. | The drone scouting. | "The drone scouts ahead and finds the area." | Flying not allowed at that moment: the drone stays on the table. Say: "Venue rules keep the drone on the table; in the field it scouts ahead." |
| 0:20 to 0:35 | Erdeni carries the station in and sets it down facing the piles. Pan-tilt head turns toward Victim A. | Camera head turning by itself. On screen: thermal view with a box on the warm target. | "The station hears the chirp, finds the direction, and turns the thermal camera to look." | No bearing within 15 s: Namig switches the screen to the backup video at this step. Say: "Here is the same run from this morning." |
| 0:35 to 0:50 | Nobody moves. | Operator phone: big arrow "TURN LEFT 30°", triage queue with two cards. | "The operator sees which way to go, and a list of who is trapped, how hurt, and how many people with them." | Thermal feed down: point at the arrow and the queue only. |
| 0:50 to 1:05 | Mika presses the Tag's status button: critical [CONFIRM button flow]. | Victim B's card turns red and moves up. | "This person just reported critical. They go first." | Button not read: skip, keep talking. |
| 1:05 to 1:15 | Tag B has now been still for 60 s. | Victim B's card pulses red: **STOPPED MOVING**, top of the list. | "And this person stopped moving. That's the one we worry about most. They jump to the top." | Flag hasn't flipped yet: keep talking for 8 more seconds, it updates on the next chirp. If not, say it and move on. |
| 1:15 to 1:22 | Erdeni knocks 3 times on the right pile. Tag B vibrates. Mika taps back on the box. | Knock card shows "3 knocks". Next frame from Tag B shows "heard knock". | "A rescuer knocks. The tag feels it and tells the victim to tap back. Now we know they're conscious." | Tag doesn't react: show the knock sensor card only. Say: "The station felt the knock." |
| 1:22 to 1:27 | Relay phone C repeats Victim B's beacon. | A card with purple "via 1 relay". | "This phone wasn't hurt. It heard the tag and passed it on. That's how a signal gets out from deep inside." | No relay frame: open phone C's relay log and show "Passed on … hop 1". |
| 1:27 to 1:30 | Namig points at the command post screen. | Reports arriving over LoRa on the command post screen. | "And command already knows. Over radio. No cell network." | LoRa down: point at the LoRa card ("packets sent") on the operator phone. |

Total: 90 seconds. Rehearse the exact second counts at Gate C.

**Global fallback:** if sound fails at any point (noisy room, judges talking), switch to the recorded run and narrate over it. Never debug live.

**Relay note for the engineers:** the station prefers frames heard directly (SPEC 1.6). If the station hears Tag B directly, the relayed copy won't show. Either put Tag B in a closed foam box out of the station's reach, or add a demo switch that ignores direct frames from one ID [CONFIRM].

**"Stopped moving" note:** the motion bit means "moved in the last 60 s" (SPEC 1.3). Putting the Tag down at 0:00 is what makes the flag flip at about 1:05. If that's too slow, ask Mika for a demo-mode window of 20 s [CONFIRM].

---

## 5. Judge Q&A: 26 hard questions

**1. Why sound instead of radio?**
Every phone already has a speaker and a microphone, and rescuers already listen for sound. Radio needs a matching receiver on both ends, and cell networks are often the first thing to fail [S2]. We do use radio where it's strong: LoRa from the station to command.

**2. Doesn't concrete block high-pitched sound?**
Yes. Solid walls block high frequencies more than low ones [S20]. Our chirp relies on air gaps and voids in the rubble, and phones relay around obstacles. Range through real rubble is our first field test.

**3. What about an unconscious victim?**
A shout stops when someone passes out. Our beacon doesn't. The Tag starts on its own after a hard fall and keeps chirping, and "stopped moving" puts that person at the top of the list.

**4. What if the victim has no tag and no phone?**
Then Heimdall is a better listening station. It classifies human sounds like speech, coughing and tapping, feels knocks, aims the thermal camera, and the radar looks for breathing [CONFIRM radar status]. Dogs and radar like FINDER still matter; we add to them.

**5. What's the range through rubble?**
We haven't measured it in real rubble. In our indoor demo it works at about [CONFIRM] metres. That is our first test with a rescue team.

**6. Won't the drone's rotors drown out the chirp?**
The drone scouts and lands before the station listens. The station listens from the ground, and it looks for one known chirp shape, which pulls it out of noise. The operator screen shows when it's quiet enough.

**7. Why is the station carried instead of flown?**
The venue allows only small drones, and the mic array, thermal camera and pan-tilt head are too heavy for one. A flying microphone also hears mostly its own rotors. In the field the same software could ride a larger drone or a ground robot.

**8. How does a victim get a Tag?**
Operators carry it as standard gear, like an avalanche beacon. Mines and industrial sites could issue it to workers. Civilians use the phone app.

**9. How does a civilian load a web app with no network?**
Honestly, this is our biggest adoption question. Today the app has to be opened before the disaster, or loaded from the station's own Wi-Fi when it's in range. The real path is to build it into an emergency app or the phone's operating system so it works offline.

**10. What about privacy?**
The chirp carries a random 4-character ID. No name, no phone number, no location. It only plays after an SOS, and the data stays on the station and the command post, never a cloud.

**11. Can someone fake a beacon?**
Today the checksum catches errors but doesn't prove who sent it. A fake beacon wastes rescuer time, the same way a prank call does today. Signed beacons for operator tags are on the roadmap.

**12. What does a Tag cost?**
[EST] Under $40 in parts at prototype quantities: an ESP32-S3 board is about $13 [S21], plus a speaker, motion sensor, barometer and battery. Engineers to confirm the full bill of materials [CONFIRM].

**13. How long does the battery last?**
Not measured yet [CONFIRM]. In normal mode the chirp plays 2.1 seconds every 30 seconds, so the speaker is on about 7% of the time (SPEC 1.2, 1.5). On a phone, the browser has to stay open, which costs more; a native app would fix that.

**14. How do you avoid false alarms?**
Every frame has a checksum, so corrupted frames are dropped. The fall trigger waits for stillness and gives a 10-second cancel. The operator sees signal strength and confidence for every direction.

**15. What happens with many victims at once?**
Beacons spread across 4 frequency bands with random timing, so two beacons don't collide every time. Each victim keeps their own ID and the triage list sorts them. We've demoed two at once; crowds are untested.

**16. How do you locate people without GPS?**
The mic array measures tiny time differences between microphones to get a direction. The Tag's barometer gives the floor; phone users set their floor by hand. Move the station and take a second reading, and the two lines cross at the victim.

**17. How does this scale to a city block?**
Several stations each report to command over LoRa, which can reach a couple of kilometres without obstacles [S15]. Phones relay up to 3 hops. We have not tested this at scale.

**18. Why edge AI?**
There's no cloud in a disaster zone. Sound classification and thermal detection run on the station's 26 TOPS accelerator [CONFIRM which models run on it], so one station works alone. That's the problem Code Metal works on: AI on the hardware itself [S10].

**19. How does this beat existing tools?**
Listening devices like the Delsar need a quiet site and a victim who can still make noise, and a kit costs about $37,000 to $43,000 [S13]. FINDER radar finds a heartbeat but can't tell you who it is [S12]. Heimdall tells you who, how hurt, and how many people, before you dig.

**20. Hasn't someone done this already?**
Close work exists: a University of Tokyo team uses sound the other way, from rescuer to the victim's phone [S18], and RescuePal uses sound to wake a phone's Wi-Fi [S19]. We found no system where phones send a coded acoustic SOS and other phones relay it. "We found none" is not proof, so we'd check patents before claiming it's new.

**21. Why audible sound and not ultrasound?**
Phone speakers and microphones are built for audible sound, and higher frequencies lose even more energy through walls [S20]. Audible also means a rescuer can hear it with their own ears if every device fails.

**22. Isn't it loud and annoying?**
It plays for about two seconds every 8 to 30 seconds, only after an SOS. For someone trapped, that's the point.

**23. What's next?**
Range tests in real rubble with a search-and-rescue team, a native app, signed operator tags, a second station to cross-fix direction, and the radar fully integrated.

**24. What's the path to deployment?**
First, a pilot at an urban search-and-rescue training site. Second, operator tags for special operations teams, who already carry beacons. Third, publish the chirp format so phone makers and emergency apps can add it.

**25. What's real today and what's mocked?**
[Fill in at Gate C, honestly.] Example: "The chirp, direction, camera aiming, triage and LoRa are live. Radar is [live / roadmap]. The drone scouts with its own camera." Judges trust teams that say this before they ask.

**26. What did you build this weekend versus before?**
All of it was built this weekend: the chirp format, the phone app, the Tag firmware, the station software and the command post. Off-the-shelf parts: Raspberry Pi, sensors, radios, the drone.

---

## 6. Competitive landscape

| Approach | What it does | What it needs | Where it fails | Heimdall's difference | Source |
|---|---|---|---|---|---|
| **Avalanche transceiver** (457 kHz) | Victim's beacon transmits; rescuers' unit points to it. | Victim wears an active beacon; trained rescuers. | Range about 40 to 80 m by spec sheet; useless if not worn; tells you nothing about the person. | Works on a phone people already carry; the signal carries status, people count, floor. | [S11] |
| **RECCO** | Passive reflector in clothing; handheld or helicopter detector finds it. | Victim wears gear with a reflector; rescuers with a detector. | Only finds people wearing RECCO gear; no data about the victim. | No special clothing; the victim can say how hurt they are. | [S14] |
| **NASA JPL FINDER** | Microwave radar senses breathing and heartbeat through rubble. | Trained operator with the unit; nothing on the victim. | No identity or status; one spot at a time. Claimed up to 30 ft of rubble. | Tells who and how hurt; ranks many victims. A radar like this belongs on our station. | [S12] |
| **Seismic/acoustic listening** (Delsar LifeDetector) | Sensors turn rubble into a microphone; probe allows two-way talk. | Trained operator, a quiet site, a victim who can make noise. Kit about $37k to $43k. | Fails with noise and with weak or unconscious victims. | The beacon keeps chirping after the victim can't; costs a fraction [EST]. | [S13] |
| **Apple Emergency SOS via satellite** | Sends an emergency text from iPhone 14 or later via satellite. | Clear view of the sky; outdoors. | Doesn't work indoors or under rubble. | Works under a roof, through gaps; no sky needed. | [S16] |
| **Meshtastic / LoRa mesh** | Off-grid text messaging over radios that relay each other. | Everyone needs a LoRa radio in advance. | Brick and concrete cut range sharply; victims rarely carry one. | Uses phones people already have; we use LoRa only for station to command. | [S15] |
| **Phone-locating drones** (Centum Lifeseeker) | Acts as a fake cell tower; finds phones that try to connect. | Victim's phone on with its cell radio working; drone or aircraft. | Needs the phone's radio to reach the sky; tells you where, not who or how hurt. | Works on sound through gaps; carries triage data. | [S17] |
| **Research prior art** (U. Tokyo, ASA 2025) | Rescuer plays sounds; victim's phone hears them and radios its position. | A working radio link from the phone. | Early research; sound goes rescuer to phone, not the other way. | Our phone speaks first and phones relay with no radio at all. | [S18] |

Positioning line: **"We don't replace dogs, radar or listening devices. We give the victim a voice that keeps talking."**

---

## 7. Eight-slide deck outline

**Slide 1: Title**
- On slide: **HEIMDALL. Hears who you can't see.** Team-31: Namig, Mika, Erdeni, Giorgi. Code Metal Forge 2026.
- Notes: Hold it for 3 seconds. The logo eye on black. No talking over it until you're ready.

**Slide 2: Problem**
- On slide: **Maui 2023: 19 of 21 cell sites down. Surfside 2021: 98 dead. Chile 2010: 17 days of silence.**
- Notes: The three cases from section 2. One sentence each. End with: "Networks fail. Victims go quiet. Rescuers are left listening."

**Slide 3: Insight**
- On slide: **Rescuers already listen. Victims are told to bang on pipes. Sound survives when networks don't.**
- Notes: FEMA rescue manuals describe calling out and listening [S9]; preparedness pages tell trapped people to bang on a pipe or use a whistle [S9b]. "We didn't invent a new channel. We made the one that works carry data."

**Slide 4: Solution**
- On slide: four boxes: **Victim: phone or Tag chirps. Station: hears, aims, sees. Operator: arrow + triage. Command: LoRa.**
- Notes: Walk left to right with one sentence each. Point to the real objects on the table.

**Slide 5: Live demo**
- On slide: **Live. No internet. No GPS. No cell.**
- Notes: Hand over to the demo (section 4). The slide stays up as a backdrop while the operator phone is mirrored.

**Slide 6: How it works**
- On slide: **2-second chirp. 48 bits: ID, floor, status, people, motion. 4 bands. Phones relay. AI on the station.**
- Notes: Namig's slide if a judge asks for depth. Diagram: victim, then phone relay, then station (mic array, thermal, radar, knock), then LoRa to command. Mention 1.5 to 6.5 kHz and the checksum.

**Slide 7: Why it wins**
- On slide: **Impact: finds silent victims. Function: working today. Feasibility: off-the-shelf parts. Scale: any phone.**
- Notes: These are the four criteria Code Metal judged on last year [S10b]. One proof point each. Cost line: station parts under $1,000 [EST] against listening kits at about $37k to $43k [S13].

**Slide 8: Roadmap, ask, team**
- On slide: **Next: real-rubble range tests, native app, signed tags. Ask: a rescue team to test with. Team photo.**
- Notes: Name our limits first: one room, two victims, small drone. Then the ask: introductions to a USAR task force and to USSOCOM units that carry beacons. Team: Namig (computer engineering, lead), Mika and Erdeni (mechanical engineering, hardware), Giorgi (business, pitch).

---

## 8. Props and staging

**Props**
- 2 rubble piles: 6 to 8 cardboard boxes each, some crushed, gray tape or spray for a concrete look. Mika owns.
- 1 foam-lined closed box for the relay trick (if used).
- Printed sign on each pile: "VICTIM A · phone" and "VICTIM B · tag" (small, for judges at the back).
- Phone stand for Victim A; Tag B; relay phone C; operator phone with screen mirroring; command post screen (Pi Zero display or laptop).
- Station on a tray or board with a handle, so Erdeni can carry it in one move.
- Small drone, charged batteries, landing spot marked with tape.
- Laptop with the backup video, paused, plugged into the projector (HDMI tested).
- Power banks charged, spare USB-C cables, tape, a printed copy of this script.
- A visible countdown timer for Giorgi (phone on a stand facing the stage, or a teammate holding up 60 s / 30 s cards).

**Who stands where (stage view from the judges)**
```
            [ screen: operator phone mirrored ]        [ command post screen ]

   [rubble A]                                   [rubble B]
       Mika (behind, crouched, runs Victim A + Tag B + drone)

                      [ station spot: tape X ]
                        Erdeni (carries station in from the right, knocks)

   Giorgi (front left, narrates, never blocks the screen)      Namig (front right, laptop + backup video)
```

**Timing and cues**
- Giorgi gives the cue "Let's show you." to start the demo.
- Namig watches the operator screen. If nothing appears by 0:35, Namig calls "backup" quietly and switches to the video.
- Ask organizers before the demo: noise level in the room, whether we can fly, projector input, power outlet location.

---

## Facts the engineers must confirm (before we say them)

1. **Range:** distance at which the station decodes a phone chirp and a Tag chirp in the demo room. (Namig, Mika)
2. **Direction accuracy:** typical bearing error in degrees. (Namig)
3. **Radar:** live, partial, or roadmap? Which module (TinyRad or MR60BHA2)? (R1 owner)
4. **What runs on the 26 TOPS accelerator:** sound classifier? thermal detection? If nothing runs on it yet, we must not claim it. (Namig)
5. **Tag:** final parts list, cost per Tag, battery capacity, measured hours in demo and normal mode. (Mika)
6. **Tag status button and fall trigger:** do both work for the demo? (Mika)
7. **Knock-back:** does the Tag vibrate on a knock and does the station report it? (Mika, Erdeni)
8. **Relay demo:** will the station show "via 1 relay" if it can also hear the original? Need the foam box or a demo switch. (Namig)
9. **"Stopped moving" timing:** 60 s window; do we want a 20 s demo window? (Mika, Namig)
10. **LoRa:** measured range today; does the command post screen show reports live? (Erdeni)
11. **Station weight** and **total station parts cost**. Pi 5 prices have changed several times this year [S22]; use what we actually paid. (Erdeni)
12. **Drone:** model, whether we may fly in the demo room, what it carries. (Erdeni, Mika)
13. **Thermal camera:** 256x192 model name, and whether it streams live on the Pi or we show the phone app. (Erdeni)

---

## What the research changed about our story

- **Maui:** "all 21 towers failed" is the county's lawsuit claim. We lead with the FCC number (19 of 21) instead.
- **Helene:** we can't say people were missing *because* phones were down. Moved to backup.
- **Physics:** high frequencies are blocked more by solid walls, not less. We say "through gaps and voids", never "through concrete".
- **Prior art exists nearby** (U. Tokyo 2025, RescuePal 2016). We say "we found no system that does this", not "first ever".
- **72-hour rule:** only expert estimates, no hard study. We don't put a survival percentage on a slide.
- **Copiapó** turned out to be a better opener than expected: the miners were found by tapping. That is our whole thesis in one story.

---

## Sources

- [S1] Fox Weather, Helene and Buncombe County: https://foxweather.com/extreme-weather/death-north-carolina-helene-flooding-cell-service
- [S2] RCR Wireless on FCC outage data, Maui: https://rcrwireless.com/20230814/public-safety/fcc-95-of-cell-sites-out-in-areas-affected-by-mauis-wildfires
- [S3] CBS News, Maui County lawsuit (21 towers, 14 alerts): https://www.cbsnews.com/amp/news/maui-wildfires-cellphone-carriers-lawsuit-alerts
- [S3b] ABC News 4 / AP, Maui death toll 102: https://abcnews4.com/news/local/report-finds-no-evidence-hawaii-officials-prepared-for-wildfire-that-killed-102-people-lahaina-maui-wciv-abc-news-4-2024
- [S4] NBC New York, Surfside search technology: https://www.nbcnewyork.com/news/national-international/explainer-how-is-technology-aiding-miami-rescuers-search/3126767/
- [S5] The New Daily, Surfside toll 98: https://thenewdaily.com.au/news/world/us-news/2021/07/27/miami-apartment-98-dead/ ; search end: https://www.cbsnews.com/amp/news/surfside-condo-collapse-search-ends
- [S6] Britannica Kids, Chile mine rescue of 2010: https://kids.britannica.com/kids/article/Chile-mine-rescue-of-2010/543402
- [S7] KFF Health News, survival after collapse (expert estimates): https://kffhealthnews.org/MTYyMDI2NA
- [S8] Prose Edda, Gylfaginning XXVII, Brodeur translation 1916 (public domain): https://sacred-texts.com/book/the-prose-edda/gylfaginning
- [S9] FEMA US&R appendix (call out and listen): https://fema.gov/pdf/emergency/usr/appen_a.pdf ; Fire Engineering, technical search: https://www.fireengineering.com/technical-rescue/building-collapse-rescue-operations-technical-search-capabilities/
- [S9b] Be Ready Utah (bang on a pipe, use a whistle): https://bereadyutah.gov/?p=4067
- [S10] SiliconANGLE, Code Metal (edge AI development): https://siliconangle.com/2024/07/23/code-metal-launches-16-5m-optimize-enterprise-software-edge-devices/
- [S10b] BusinessWire, Code Metal 2025 hackathon (judged on impact, function, feasibility, scalability): https://www.businesswire.com/news/home/20250325591815/en
- [S11] Avalanche transceiver buying guide: https://www.snowandrock.com/expert-advice-and-inspiration/buying-guides/how-to-choose-an-avalanche-transceiver.html
- [S12] NASA JPL, FINDER in Nepal: https://www.jpl.nasa.gov/news/finder-search-and-rescue-technology-helped-save-lives-in-nepal/
- [S13] Delsar LifeDetector: https://www.firehouse.com/rescue/technical-rescue/structural-collapse/product/10181928/con-space-communications-delsar-life-detector ; kit prices: https://www.safewarecontracts.com/itemdetail/SAV%206000-22-001 ; UK NFCC study: https://nfcc.org.uk/wp-content/uploads/2023/10/Publication-6_92-Detection-Devices-for-Hidden-or-Buried-Casualties.pdf
- [S14] RECCO: https://recco.com/what-is-recco/
- [S15] Meshtastic antenna and range docs: https://meshtastic.org/docs/hardware/antennas/antenna-testing/
- [S16] Apple, Emergency SOS via satellite: https://support.apple.com/en-euro/101573
- [S17] Lifeseeker Mini S10: https://volatusdrones.com/products/lifeseeker-mini-s10
- [S18] Acoustical Society of America, smartphones for disaster search (Takada, 2025): https://acoustics.org/using-smartphones-to-improve-disaster-search-and-rescue/
- [S19] RescuePal (WoWMoM 2016): https://scholarsmine.mst.edu/comsci_facwork/750
- [S20] NRC Canadian Building Digest 239, sound through walls (mass law): https://web.mit.edu/parmstr/Public/NRCan/CanBldgDigests/cbd239_e.html
- [S21] Digi-Key, ESP32-S3-DevKitC-1: https://www.digikey.de/en/products/detail/espressif-systems/ESP32-S3-DEVKITC-1-N8R2/15199627
- [S22] Raspberry Pi, memory-driven price rises: https://raspberrypi.com/news/more-memory-driven-price-rises ; AI HAT+ 26 TOPS ($110): https://www.canakit.com/raspberry-pi-ai-hat-26.html ; Topdon TC001 thermal ($230): https://www.topdon.us/products/tc001

Note on sourcing: several figures (Surfside 98, Maui FCC 19 of 21, Delsar kit prices, competitor ranges) were checked through search results rather than by opening the page. Open each link once before it goes on a slide.
