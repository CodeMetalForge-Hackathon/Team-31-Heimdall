# HEIMDALL · Q&A drill (Saturday 17:30 facts)

The 12 hardest questions for us right now. Two sentences each, confirmed facts only.
Rule for every answer: **say the number, then name the limit.** Anything in `[TBD: ...]` waits for an engineer.

**1. What's the range?**
In this noisy hall, with a phone speaker into a laptop microphone, we decoded 100% of frames at 3 m, 81% at 6 m, and 72% with the phone inside a backpack. The station's own range is [TBD: station range], and real rubble is our first field test.

**2. How accurate is the direction?**
The station's 4-microphone array gives [TBD: direction accuracy]. Move the station and take a second reading, and the two lines cross at the victim.

**3. Do you detect breathing with radar?**
Radar is on our roadmap, not in this demo [update if confirmed by 01:00]. Today the station has the chirp, a thermal camera that turns to it, and a knock sensor; radar adds people who have no device at all.

**4. What is the AI accelerator doing?**
Right now all processing runs on the station, offline, and nothing runs on the accelerator yet. Our next step is to use it to recognize human sounds like tapping and voices, so the station finds people who have no phone or Tag.

**5. What does it cost?**
The microphone array is $79.90 and the Tag's speaker parts cost $4.95 to $26.99 each; the full Tag is [TBD: Tag cost] and the station is [TBD: station parts cost]. Professional listening kits cost tens of thousands of dollars, so this can go to every team, not one per city. *(Say the competitor figure only if asked; source: pitch_kit S13.)*

**6. How long does the battery last?**
[TBD: Tag battery hours]. In normal mode the chirp plays 2.13 seconds every 30 seconds, so the speaker is on about 7% of the time.

**7. How do you avoid false alarms?**
Every frame has a checksum plus extra checks, and a new beacon shows as "unconfirmed" until the station hears it a second time. With two phones chirping at once in our laptop-microphone test, we got zero wrong frames.

**8. What about many victims at once?**
Beacons spread over 4 frequency bands with random timing, and with two phones at once we still decoded 75% and 88% of frames (laptop microphone). Each victim keeps their own ID and the triage list sorts them; crowds are not tested yet.

**9. Why is the station carried and not flown?**
The venue only allows small drones, and the mic array, thermal camera and pan-tilt head are too heavy for one. A microphone on a drone also hears mostly its own rotors, so the drone scouts and the rescuer brings the ears.

**10. Why sound and not radio?**
Every phone already has a speaker and a microphone, and rescuers already stop and listen for sound. Radio needs a working network or a radio the victim already carries, so we use radio only where it's strong: LoRa from the station to command.

**11. What about privacy?**
The chirp carries a random 4-character ID, never a name, a phone number or a location, and it only plays after an SOS. Everything stays on the station's own Wi-Fi and the command post; there is no internet connection to send it anywhere.

**12. What's next?**
Range tests in real rubble with a search-and-rescue team, then sound recognition on the accelerator and radar for people with no device. After that, a native app so a phone can chirp with the screen off.

## Words to avoid on stage
- "AI on the station" (say: "all processing runs on the station, offline").
- "Through concrete" (say: "through gaps and voids").
- "First ever" (say: "we found no system that does this").
- Any range number without "laptop microphone" until the station numbers are in.
