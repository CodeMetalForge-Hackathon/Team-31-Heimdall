# PROJECT HEIMDALL: master plan + checklist
"Hears who you can't see." Code Metal Forge 2026, BASE X Boston.

**Hard deadlines:** submissions close **Sun 12:00 PM** (the repo is the submission). Demos right after. Closing 4:30 PM.
**Our deadlines:** code freeze **Sun 09:00**. Only demo-saving fixes after that.

---

## 0. How we work (read once)

1. **Namig = PM + programmer.** Every task is a prompt file (`N1_…md`, `M1_…md` …). Namig sends the file to the person. They paste everything below the line into their AI tool.
2. Every prompt ends with a **REPORT** block. When done, the person sends the filled-in report (+ photos/screen recording) to Namig.
3. Namig saves it as `reports/<TASK>.md` in `Desktop/CodeMetalForge/` and tells Claude "check reports". Claude checks it (and the pushed branch) and writes the next prompt. Namig merges the branch.
4. **One owner per file.** Never edit a file you don't own (table below). If you need a change in someone else's file, message them.
5. **Stuck for 20 minutes = tell Namig.** Don't sink an hour.
6. Every contract (chirp format, events, serial commands, LoRa) lives in `docs/SPEC.md`. Code follows SPEC. If SPEC is wrong, tell Namig. Never "fix" it silently.

### Git
- Repo: **https://github.com/CodeMetalForge-Hackathon/Team-31** (our submission). Everyone clones it to the Desktop: `~/Desktop/Team-31`.
- **One branch per task:** `<person>/<TASK>`, e.g. `mika/M1-tag-a`, `erdeni/E1-station`, `giorgi/G1-web-screens`, `namig/N2-modem`. Start every new task from fresh `main`:
  ```bash
  cd ~/Desktop/Team-31 && git checkout main && git pull && git checkout -b <person>/<TASK>
  ```
- Commit only your own paths (`git add <your paths>`, never `git add -A` or `git add .`). Push your branch: `git push -u origin <branch>`. Push at least every 2 hours.
- **Never commit to `main`, never merge.** Namig merges every branch into `main` after checking the report. Only N1 part 0 (the skeleton) goes straight to `main`.
- Namig runs two Claude Code sessions at once with a git worktree (`git worktree add ../Team-31-modem -b namig/N2-modem main`) so they don't share one checkout.
- The Pi has its own clone at `~/Team-31` and normally runs `main`.
- Giorgi: Claude Code does the git commands for him (it's in his prompts).

---

## 1. What we're building (v2, after the inventory check)

```
 VICTIMS                          RESCUERS (field)                          COMMAND POST
 ┌────────────────────┐  sound   ┌──────────────────────────────┐  LoRa    ┌───────────────────┐
 │ Phone web app      │ ───────► │ HEIMDALL STATION ("the Ear")    │ ───────► │ Command post              │
 │  (victim role):    │  chirps  │ carried by a rescuer, follows │ 915 MHz  │ Pi Zero 2 W +     │
 │  chirps + relays   │          │ the small drone               │          │ RFM95W + page     │
 │  other phones      │          │ Pi 5 + AI HAT+ (26 TOPS)      │          └───────────────────┘
 │ Hardware Tag A/B   │          │ mic array → direction         │
 │  XIAO ESP32S3/C5   │ ◄─knock─ │ thermal on pan-tilt (aims)    │  Wi-Fi hotspot (HTTPS)
 │  speaker, baro,    │          │ knock sensor on the structure │ ───────► Operator phone
 │  IMU, buttons      │          │ radar (TinyRad / MR60BHA2)    │          (drone operator role):
 └────────────────────┘          │ LoRa radio                    │          thermal, arrow, triage
                                 └──────────────────────────────┘
 SMALL DRONE: scouts ahead; payload decided at 18:00 (light pod or none). Venue rules: small drone only.
```

**Core demo (must work):** phone victim chirps → station finds the direction → operator phone shows the arrow + the victim card → pan-tilt turns the thermal camera to that direction.
**Full demo (promised):** + hardware Tag with fall trigger + phone relay (hop 1) + knock-back + triage "stopped moving" + LoRa to Command post + radar + drone.

---

## 2. Team, tools, ownership

| Person | Strength | AI tool | Default model | Owns (files/folders) |
|---|---|---|---|---|
| **Namig** | computer eng., PM | Claude 20x (Claude Code, several sessions in parallel) | Opus 5.5 high | `ear/bus.py main.py server.py config.py`, `ear/modules/mock.py audio.py lora_link.py`, `ear/tools/net_mode.sh`, `modem/`, `docs/`, `web/debug.html`, `web/js/heimdall-modem.js victim-logic.js operator-live.js`, repo root |
| **Mika** | mech. eng., electronics | Claude Pro (Claude Code) | Sonnet 5.5 medium | `firmware/tag_smoke/`, `firmware/tag/`, demo rubble props |
| **Erdeni** | mech. eng., electronics | Cursor (edu) | Agent mode, Auto (prompts include full code) | `firmware/servo_knock/`, `ear/tools/hw_smoke/`, `ear/modules/pantilt.py thermal.py knock.py`, `command/`, station + drone pod build |
| **Giorgi** | business, presenting | Claude 5x | Opus 5.5 medium (UI), Opus 5.5 high (pitch) | `web/index.html victim.html operator.html`, `web/css/`, `web/js/ui-victim.js ui-operator.js mock.js`, `pitch/` |

Repo layout (`~/Desktop/Team-31`):
```
Team-31/
  README.md  PLAN.md  .gitignore
  docs/SPEC.md
  modem/                 (Namig) Python reference modem + tests
  ear/  bus.py main.py server.py config.py
        modules/ mock.py audio.py lora_link.py (Namig) | pantilt.py thermal.py knock.py (Erdeni) | radar.py (later)
        tools/   net_mode.sh (Namig) | hw_smoke/ (Erdeni)
        certs/   (gitignored)
  firmware/ tag_smoke/ tag/ (Mika) | servo_knock/ (Erdeni)
  web/      index.html victim.html operator.html css/ js/ui-*.js js/mock.js (Giorgi) | debug.html js/heimdall-modem.js js/victim-logic.js js/operator-live.js (Namig)
  command/  (Erdeni) command post
  pitch/    (Giorgi)
```

---

## 3. Timeline + checklist

### Phase 0 · now → 13:15 · parts triage (Namig)
- [ ] Ask the library desk: **mic array order arrived?** (ReSpeaker USB Mic Array v2.0 or XVF3800)
- [ ] Ask for / Micro Center list: **MR60BHA2 radar, MAX98357A ×2 + 3 W speakers ×2, USB audio adapter with mic in, power banks ×3, zip ties/velcro/foam tape/hot glue, cardboard boxes**
- [ ] Ask the organizers: **which small drones are allowed, payload, where we can fly**
- [ ] N1 part 0: skeleton pushed to `main` → message the team "main is up"
- [ ] Send wave 1 prompts: N1, N2 (Namig), M1 (Mika), E1 (Erdeni), G1 + G2 (Giorgi)
- [ ] Create `reports/` in `Desktop/CodeMetalForge/`

### Wave 1 · 13:15 → 15:30
| ID | Who | Task | Done when |
|---|---|---|---|
| N1 | Namig | Pi 5 setup, hotspot + HTTPS, server skeleton with mock data | phone on `HEIMDALL` sees mock events at `https://10.42.0.1:8443/debug.html` |
| N2 | Namig (2nd session) | Python modem HEIMDALL-AC1 + JS port, test vectors, laptop-mic live decode | both test vectors pass in Python + JS; a WAV made by JS decodes in Python; laptop mic decodes a phone chirp at 2 m |
| M1 | Mika | Build Tag A (XIAO ESP32S3 Plus), smoke-test firmware | speaker sweep audible at 1 m, IMU + baro read, buttons, shock print |
| E1 | Erdeni | Seeeduino servo+knock firmware, pan-tilt build, station frame, Pi hardware probes, solder LoRa antennas | `P 30 10` moves the head smoothly; `KNOCK 3` prints; thermal frame saved on the Pi (UVC yes/no) |
| G1 | Giorgi | Web app screens with mock data (role picker, victim, drone operator) | both roles work in mock on a phone-size screen |
| G2 | Giorgi | Pitch kit (story, script, Q&A, competitors, deck outline) | `pitch/pitch_kit.md` delivered |

**GATE A · 15:30** (everyone reports; Claude writes wave 2)
- [ ] Modem: Python + JS pass the test vectors; laptop decodes a phone chirp
- [ ] Pi serves the mock UI to a phone over HTTPS
- [ ] Tag A hardware alive
- [ ] Pan-tilt moves from serial; knock lines appear
- [ ] Thermal camera on the Pi: **works as UVC: yes / no** (decides plan B)
- [ ] UI mock done; pitch kit draft done
- [ ] **Mic array here: yes / no** → if no by 16:00, build "head scan" (1 mic on the pan servo)

### Wave 2 · 15:45 → 20:00 (prompts written at Gate A)
| ID | Who | Task |
|---|---|---|
| N3 | Namig | `ear/modules/audio.py`: live capture, decode, direction (GCC-PHAT), victim records; head-scan mode if no array |
| N4 | Namig (2nd session) | `web/js/heimdall-modem.js` live in the browser: victim page chirps + listens + **relays**; `operator-live.js` WebSocket → UI |
| M2 | Mika | Tag A real firmware: HEIMDALL-AC1 beacon, fall trigger, buttons, barometer floor, haptics |
| E2 | Erdeni | `pantilt.py` (auto-aim at the bearing), `thermal.py` (MJPEG + hotspots), `knock.py`; wire both LoRa radios to Pi 5 + Pi Zero |
| G3 | Giorgi | Deck v1 (8 slides), demo script with timings, record b-roll video, Q&A drill |
| R1 | Namig 3rd session or Mika | TinyRad spike, 90 min hard limit: presence + distance + chest motion → `radar` events. Stop if no result. |
| D1 | Erdeni + Mika, 18:00 | Drone decision: model, payload, what it carries, demo choreography |

**GATE B · 20:00**
- [ ] **Core demo live:** phone victim → station bearing → operator arrow + victim card
- [ ] Pan-tilt auto-aims the thermal camera at the bearing; thermal on the operator page
- [ ] Tag A chirps are decoded by the station
- [ ] Relay: phone B repeats phone A, the operator sees "via 1 relay"
- [ ] Deck v1 reviewed

### Wave 3 · 20:15 → 01:00
| ID | Who | Task |
|---|---|---|
| N5 | Namig | Integration: all modules in `main.py`, triage logic, LoRa link, `systemd` autostart, end-to-end tests |
| M3 | Mika | Tag B (XIAO ESP32C5) + knock-back on both Tags; build the demo rubble |
| E3 | Erdeni | Command post on Pi Zero 2 W (LoRa receive + simple page); drone pod/mount per D1 |
| G4 | Giorgi | Rehearsal #1 with real hardware, timing, backup demo video recording plan |
| R2 | whoever ran R1 | Radar integration (TinyRad result or MR60BHA2 if it arrived) |

**GATE C · 01:00**
- [ ] Full demo run end-to-end, twice in a row
- [ ] LoRa reaches Command post
- [ ] Knock-back works on at least one Tag
- [ ] Radar: in or out (decided)
- [ ] Drone choreography decided

### Night · 01:00 → 07:00
- Two people awake at a time. Suggested: **Mika + Giorgi sleep 01:00–04:00**, **Namig + Erdeni sleep 04:00–07:00**.
- Awake pair: bug fixes from the Gate C list only. No new features.

### Sunday
- [ ] 07:00 everyone up, run the full demo once, list bugs
- [ ] **09:00 CODE FREEZE**, tag the repo `v1.0`
- [ ] 09:00–11:00 rehearse 3×, record the backup demo video, finish README (what it is, how to run, team)
- [ ] 11:30 submit (repo link + video), check everything is pushed
- [ ] 12:00 deadline → demos

---

## 4. Wiring reference (same diagrams are in the prompts)

### 4.1 Tag A: XIAO ESP32S3 Plus (Mika)
```
                 XIAO ESP32S3 Plus, top view, USB-C at the top
                         +----[USB-C]----+
 Grove Speaker SIG <- D0 | o           o | 5V   -> Grove Speaker VCC, Vibration motor VCC
 Grove Button SIG  -> D1 | o           o | GND  -> every GND
 Grove Touch SIG   -> D2 | o           o | 3V3  -> Button VCC, Touch VCC, IMU 3V3, BME280 3.3V
 Vib. motor SIG    <- D3 | o           o | D10  (free: MAX98357A DIN later)
 SDA (IMU + BME)  <-> D4 | o           o | D9   (free: MAX98357A LRC later)
 SCL (IMU + BME)   -> D5 | o           o | D8   (free: MAX98357A BCLK later)
            (free)    D6 | o           o | D7   (free)
                         +---------------+
 Grove wire colors: yellow = SIG, white = 2nd signal (unused here), red = VCC, black = GND
 I2C addresses: ISM330DHCX 0x6B, MMC5983MA 0x30, BME280 0x77
```

### 4.2 Station: Seeeduino servo + knock controller (Erdeni)
```
 Seeeduino (Uno layout). Set the 3V3/5V switch to 5V. Do NOT mount the Grove Base Shield (wire straight to the headers).
   D5  -> PAN servo  orange/yellow wire
   D6  -> TILT servo orange/yellow wire
   D2  <- Grove Vibration Sensor (SW-420) SIG (yellow)
   5V  -> SW-420 VCC (red)      GND -> SW-420 GND (black)
   GND -> breadboard "-" rail   (common ground with the servo supply: REQUIRED)

 Servo power (never from the Seeeduino or the Pi):
   external 5 V (+) -> breadboard "+" rail -> both servo RED wires
   external GND (-) -> breadboard "-" rail -> both servo BROWN wires
   external 5 V = bench supply set to 5.0 V / 1.5 A limit, or a USB power bank through a USB breakout
```

### 4.3 LoRa radio (Adafruit RFM95W) on the Pi 5 (station) and the Pi Zero 2 W (Command post): same pins
```
 Pi header, board flat, header along the top edge. Pin 1 = square pad, inner row, end AWAY from the USB ports.
 Odd pins = inner row, even pins = outer row (board edge).

   RFM95W   ->  Pi pin (signal)
   VIN      ->  1  (3V3)
   GND      ->  6  (GND)
   SCK      ->  23 (GPIO11 SCLK)
   MISO     ->  21 (GPIO9  MISO)
   MOSI     ->  19 (GPIO10 MOSI)
   CS       ->  26 (GPIO7  CE1)
   RST      ->  22 (GPIO25)
   G0       ->  15 (GPIO22)   optional
 Antenna: 78 mm solid wire soldered to the ANT pad. NEVER power the radio without it.
 Pi: enable SPI with `sudo raspi-config nonint do_spi 0`.
```

---

## 5. Risks and fallbacks
| Risk | Check by | Fallback |
|---|---|---|
| Mic array doesn't arrive | 16:00 | Head scan: 1 mic on the pan servo + burst mode (SPEC 1.5). Needs a USB mic/adapter, so buy one now. |
| Hti thermal isn't UVC on Linux | E1 (15:00) | Operator view shows "thermal: phone app" + we screen-record the Hti phone app for the demo |
| ALFA Wi-Fi driver fails | N1 | `net_mode.sh dev|demo` on built-in Wi-Fi, or Ethernet via the UGREEN switch for dev |
| Phones block mic/audio | N2/N4 | HTTPS + tap-to-start (already in the design); test Android Chrome first, then iPhone Safari |
| Grove Speaker too quiet / distorted | M1 | MAX98357A from Micro Center; phones as the main beacons |
| TinyRad too hard | R1 (90 min) | MR60BHA2 request; else radar = "roadmap" slide |
| Drone can't carry anything | D1 | Drone scouts with its own camera; the station follows on foot; say so in the pitch |
| Two chirps collide | Gate B | Jitter (SPEC 1.5) + CRC; demo with 2 beacons max at the same time |

## 6. Open decisions
- [ ] Mic array arrival (Gate A)
- [ ] Radar: TinyRad vs MR60BHA2 (Gate B)
- [ ] Drone model + payload (18:00)
- [ ] Where the ISM330DHCX IMU goes: Tag A (shock + knock, current plan) vs station heading (operator phone compass covers heading for now)
