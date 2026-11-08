# HEIMDALL · Q&A drill (updated Saturday night with station test numbers)

The 13 hardest questions for us right now. Two sentences each, confirmed facts only.
Rule for every answer: **say the number, then name the limit.** Anything in `[TBD: ...]` waits for an engineer.

**1. What's the range?**
With the microphone array on the station, we decode 95% of chirps at 2 m when the phone's speaker faces the station, and about 22% straight ahead at 4 m. So today it's a 2 m system in one room, and real rubble plus a second array are our next tests.
*(Backup if asked about the modem alone: "Phone into a laptop mic in this hall, 81% decoded at 6 m.")*

**2. How accurate is the direction?**
Within 10° at 2 m in every direction we tried, and within about 4° ahead and to the side at 4 m. Move the station and take a second reading, and the two lines cross at the victim.

**3. Do you detect breathing with radar?**
Radar is on our roadmap, not in this demo [update if confirmed by 01:00]. Today the station has the chirp, a thermal camera that turns to it, and a knock sensor; radar adds people who have no device at all.

**4. What is the AI accelerator doing?**
Right now all processing runs on the station, offline, using under 2% of one processor core, and nothing runs on the accelerator yet. Our next step is to use it to recognize human sounds like tapping and voices, so the station finds people who have no phone or Tag.

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

**13. What are the limits?**
It needs a fairly clear path to the phone: from directly behind the station it decoded only 16% of chirps, and if the speaker faces away or a pile blocks it completely, it can point at an echo off a wall. That's why our next steps are a second microphone array and tests in real rubble.

## Words to avoid on stage
- "AI on the station" (say: "all processing runs on the station, offline").
- "Through concrete" (say: "through gaps and voids").
- "First ever" (say: "we found no system that does this").
- A laptop-microphone number as if it were the station's. Station range is 2 m today; say "laptop microphone" whenever you quote 6 m, 75% or 88%.
- "Works from any direction" (from behind it hears poorly).
