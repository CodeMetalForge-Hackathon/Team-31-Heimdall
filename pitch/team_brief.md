# Heimdall: the team brief

Read this once, then talk about Heimdall the same way as the other three. Written Sunday 11:10 from `main`. The code is the truth: where this file and the repo disagree, the repo wins. Anything marked "check with" is not confirmed. Do not say it to a judge until it is.

## 1. Heimdall in one breath

Heimdall hears who you can't see.

A trapped person's phone, or our small Tag, plays a coded chirp. A station on the ground works out where the chirp comes from, turns a thermal camera to look, and shows the rescuer which way to walk and who is most urgent. No internet, no cell network, no cloud.

## 2. The mission we chose

The problem. After a collapse, or in an area where networks are down or jammed, survivors are under rubble and out of sight. Cell and radio are the first things to fail. Searchers still stop, knock and listen.

Who it is for. Rescue teams working a pile, and the people under it. The person under the pile needs nothing new: a phone with our page open, or a Tag if they have no phone.

Why sound. Everyone already carries a speaker and a microphone. Sound gets through gaps and voids that light and line of sight can't. Rescuers already listen for it. We make that sound carry data: who, how hurt, how many, how long since the SOS, still moving or not.

## 3. Code Metal Forge, and our reading of it

The event is Code Metal Forge 2026, "Build for the Mission", a rapid prototyping hackathon at BASE X in Boston, sponsored by USSOCOM. Code Metal's own work is turning research code into code that runs on small, trusted hardware at the edge.

Our reading of the theme: build for a real mission, put the clever part on hardware a rescuer can carry, and need nothing from a server. Everything in Heimdall runs on the devices in the room: a Raspberry Pi 5, an ESP32, phone browsers. No cloud at any step.

The link to Code Metal's work, as we see it. We wrote the acoustic modem once, in Python with numpy. That same code runs on the Pi. Then we carried it to JavaScript for the phone browser and to C++ for the ESP32 Tag. The Python and JavaScript decoders pass the same test vectors (SPEC 1.4) and decode each other's recordings (`modem/tests/test_cross.py`). The C++ encoder matches the Python one sample for sample (`firmware/tag/heimdall_ac1.h`). Research code moved to the edge and checked. That is the problem Code Metal works on, done by hand in a weekend.

## 4. Why "Heimdall"

In Norse myth Heimdall is the watchman of the gods. He guards the bridge Bifrost, needs less sleep than a bird, sees a hundred leagues by night and day, and hears grass growing on the earth and wool growing on sheep. When danger comes he blows the horn Gjallarhorn. (Prose Edda, Gylfaginning.) Our station is the small human version: it listens for the faintest call and raises the alarm.

## 5. How it works in six steps

1. Chirp. The phone or Tag plays a 2.13 second frame every 8 seconds, give or take 1 second. It is a 200 ms preamble chirp, then 48 bits as 40 ms up or down chirps. The bits carry the ID, floor if known, minutes since SOS, moving or still, status (ok, injured, critical, no response), how many people, battery, relay hops, a knock bit, and a CRC-8.
2. Bands. Four bands between 1.5 and 6.5 kHz. Each frame moves to the next band and the start time jitters, so two callers rarely collide twice.
3. Relay. A phone that hears another phone's frame waits 1.5 to 4 seconds, then plays it again with hops plus one, two bands up. Up to 3 hops. A normal phone relays only while its own SOS is on. On stage phone C runs "relay only": it passes calls on and never shows up as a victim.
4. Direction. The station times the chirp's arrival at 4 raw mics (GCC-PHAT), fits the bearing, sums the last 3 frames per caller, and drops anything more than 95 degrees from the front arrow as a reflection. A new ID shows "Unconfirmed" until a second frame arrives within 60 seconds.
5. Look and rank. The head turns the thermal camera to the most urgent confirmed victim: critical, then injured, then no response, then ok. Within a status, someone who just stopped moving (last 5 minutes), then still, then moving. Then the longest wait since SOS.
6. Show. The operator page (a phone or laptop on the station's own Wi-Fi, HEIMDALL) shows the direction like a navigation banner ("27 degrees left" and a line), the thermal picture with warm spots boxed, and the triage list with tags: Stopped moving, Via relay, Unconfirmed.

## 6. The sensors

| Device | Part | What it gives us | Live or next |
|---|---|---|---|
| Station | XMOS XVF3800 4-mic array (USB, 6 channels) | the chirp, and its direction from the 4 raw mics | live |
| Station | USB thermal camera, 640x512, on a pan-tilt head | a heat picture of the pile the head points at, warm spots boxed by brightness | live (no temperatures) |
| Station | 2 servos + Seeeduino controller | the head turns by itself to the most urgent victim, plus or minus 90 degrees | live |
| Station | SW-420 vibration sensor (knock board) | a rescuer's knocks | built; in the demo only if it passes its check (check with Erdeni) |
| Station | Raspberry Pi 5 | runs everything, serves the app over its own Wi-Fi | live |
| Tag | Seeed XIAO ESP32S3 Plus + Grove speaker | plays the chirp | live |
| Tag | ISM330DHCX IMU (accelerometer + gyro) | moving or still | wired and in the firmware; "stopped moving" on stage: check with Mika |
| Tag | touch pad, SOS button, vibration motor | next status, beacon on or off, 1 to 3 buzzes as feedback | live |
| Phone | speaker, microphone, motion sensors, browser | beacon, relay, moving or still, forwards what it heard to the station | live |
| Kit on the table | LoRa radio (RFM95W), 24 GHz radar (TinyRad), a small drone | link to a command post, a silent person's chest motion, scouting | next (the LoRa format is in SPEC 6, `command/` is empty) |

UWB kits are in the facts file but nowhere in the repo. Do not mention them unless Erdeni confirms.

## 7. Getting a signal out of noise

There is no machine learning in Heimdall. None. If a judge asks, the real story is better than a buzzword.

We tried the XMOS chip's built-in speech processing channel. It is built to keep voices and remove steady tones, so it treated our chirps as noise. Side by side at 2 to 4 meters, the processed channel decoded 29 to 48 percent of frames. A raw mic decoded 87 to 96 percent (`ear/config.py`). So we decode from a raw mic and clean the signal ourselves:

Chirp spread spectrum, the idea behind LoRa, in sound. A matched filter pulls a frame out of noise you can hear over it. Each symbol is 40 ms because a quick simulation with room reverb decoded about 95 percent of frames at 40 ms against about 75 percent at 25 ms (SPEC 1.2).

Four bands with hopping, a CRC-8 on every frame, extra gates on preamble and symbol quality, and a second frame before an ID counts as confirmed.

For direction: partial PHAT whitening, 16 times upsampled correlation, the last 3 frames summed per caller, only the bands that agreed with the tape marks on demo morning (bands 0 and 3), and anything behind the station dropped as a reflection.

## 8. Numbers we can stand behind

Each one with where it comes from.

- Direction at 2 m (true angle, then what we read): 0 reads +1.4 ± 0.4; +45 reads +53.7 ± 1.0; +90 reads +86.6 ± 0.9; −90 reads −99.7 ± 0.5 degrees. At 4 m: 0 reads within 4 degrees; +90 reads +89.5 ± 1.5. (README, Audio.)
- Behind the station: about −177 degrees, but only 16 percent of frames decoded. (README, Audio.)
- On the stage piles: the kept bands read within 15 degrees of the tape marks at both piles. The piles at about 35 degrees read about 27 degrees, so the banner says "27 left". Bands 1 and 2 put the Tag on the mirror side about one frame in three, so the demo uses bands 0 and 3 only. (README, Demo day; demo_script_v4.)
- Decoding: 87 to 96 percent of frames at 2 to 4 m on a raw mic, against 29 to 48 percent on the chip's speech channel. (`ear/config.py`.) One older number disagrees: the Saturday night Q&A drill says about 22 percent straight ahead at 4 m. Check with Namig which run to quote. Until then say "2 m is solid, 4 m depends on the angle".
- Decoder cost: under 2 percent of one Pi 5 core. The Ear logs its own CPU share every 30 seconds. (qa_drill; `ear/modules/audio.py`.) The facts file says about 1.5 percent.
- From plug-in to the first decoded frame after a power cut: 51 seconds, hotspot included. (README, Demo day.)
- Frame: 2.13 seconds, 48 bits, every 8 ± 1 seconds in demo mode, 30 seconds in normal mode. (SPEC 1.2, 1.5.)
- False frames: the CRC plus checks still let about 1 in 1024 garbage decodes through, so the second-frame rule exists. In 30 minutes of adversarial noise the modem produced 1 bad frame before that rule. (SPEC 1.7.6.)
- Laptop microphone numbers, always labelled as such: 81 percent decoded at 6 m in the hall; two phones at once, 75 and 88 percent, zero wrong frames. (qa_drill.)

## 9. Live today, next, and words we never say

Live today: chirps from phones and the Tag. Direction finding. The head that turns by itself and starts straight. The thermal picture with warm boxes. The triage list. Relay between phones, with phone C as relay only.

Next, and we say "next": LoRa to a command post. Knock sensing and knock-back to the Tag. Radar. Flying the drone. Temperatures in degrees. Phones relaying the Tag (phones can't decode the Tag's sound yet; the station can). Fall detection, the Tag's floor from a barometer, and the Tag's battery level (cut from the firmware at 02:00 Sunday).

Check before claiming: the Tag's "stopped moving". At 07:50 it sent "still" in every frame. Mika has a fix or we use the one-touch "Critical" fallback. Ask Mika before the run.

Words we never say: "ML denoising". "AI on the station" (say: all processing runs on the station, offline). "Temperatures". "LoRa works". "The drone flies". "Phones relay the Tag". "The Tag detects a fall". "Through concrete" (say: through gaps and voids). "First ever" (say: we found no system that does this). "Works from any direction". A laptop microphone number as if it were the station's.

## 10. Who talks about what

Giorgi: the story and the mission.
- Networks fail exactly when buildings fall. Rescuers still stop, knock and listen. We make that listening carry data.
- What the rescuer gets: a direction, a heat picture, and a ranked list, on their own phone, with no network of any kind.
- Honest scope: today it is one room and two victims. Next is real rubble with a rescue team.

Namig: the signal and the software.
- The chirp: 2.13 seconds, 48 bits, chirp spread spectrum across 4 bands, CRC-8, and an ID counts only after its second frame.
- No machine learning. The chip's speech denoiser cut decoding to 29 to 48 percent, a raw mic gave 87 to 96. So: matched filter, whitening, summed frames, kept bands.
- One modem, three languages, same test vectors. The whole decoder uses under 2 percent of one Pi core.

Erdeni: the station, the head and thermal.
- The station: Pi 5, XMOS 4-mic array, 640x512 thermal camera on a two-servo head driven by a Seeeduino, its own Wi-Fi, back on its own 51 seconds after a power cut.
- The head: auto mode aims at the most urgent confirmed victim, plus or minus 90 degrees, starts straight ahead. Its direction and zero were measured at 09:20 Sunday with the camera taped to the horn.
- Thermal: warm spots boxed by brightness, no temperatures. The knock board is built; it is in the demo only if it passes its check.

Mika: the Tag.
- XIAO ESP32S3 Plus and a Grove speaker. It chirps from power-on every 8 seconds, starts as "injured", the touch pad cycles the status with 1 to 3 buzzes, the SOS button turns the beacon off and on. Never press it after power-on.
- The IMU: "moved in the last 20 seconds", same thresholds as the phones (0.08 g or 20 degrees per second). The "stopped moving" flip on stage is the open item.
- Honest cuts: fall detection, knock-back, barometer floor and battery level are not in this version. The speaker plays a square-wave version of the chirp; it decoded 20 of 20 frames on all 4 bands in simulation.

## 11. Ten likely judge questions

1. Did you use machine learning? No, and we tried the chip's built-in speech denoiser first: it cut decoding from 87 to 96 percent down to 29 to 48 percent because it treats chirps as noise. We use a matched filter, four hopping bands, a CRC and a second-frame rule instead.
2. What's the range? With the mic array on the station we decode about 95 percent of frames at 2 m when the speaker faces the station, and direction holds at 4 m to the side. Today it is a 2 m system in one room; real rubble is the next test.
3. What if two people chirp at once? Each frame hops to the next of four bands and the timing jitters by a second, so a collision does not repeat, and every frame carries its own ID and CRC. In a laptop microphone test with two phones at once we decoded 75 and 88 percent with zero wrong frames.
4. Why not radio? Every phone already has a speaker and a microphone, and rescuers already stop and listen; radio needs a working network or a radio the victim already carries. We use radio only where it is strong, and that is the next step: the station to a command post over LoRa.
5. What does it cost? We haven't costed the full system. The mic array is $79.90; everything else is an estimate, so we don't quote it.
6. How do you avoid false alarms? Every frame has a CRC-8 and quality gates, and a new ID shows as unconfirmed until the station hears it a second time within 60 seconds. In 30 minutes of adversarial noise the modem let one bad frame through before that rule.
7. What is the AI accelerator doing? Nothing today; all processing runs on the Pi's CPU, offline, under 2 percent of one core. Whether an accelerator is mounted on the stage station: check with Erdeni before answering further.
8. What about someone with no phone and no Tag? Today they are outside what we find; the thermal camera only looks where a chirp points it. Next is human sound recognition on the station and a radar for breathing.
9. What about privacy? The chirp carries a random 4-character ID, never a name, number or location, and it only plays after an SOS. Everything stays on the station's own Wi-Fi; there is no internet connection to send it anywhere.
10. What are the limits? It needs a fairly clear path to the phone: from behind the station only 16 percent of frames decoded, and a speaker facing away can point us at an echo off a wall. That is why the next steps are a second mic array and tests in real rubble.
