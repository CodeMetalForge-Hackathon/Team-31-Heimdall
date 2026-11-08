# HEIMDALL SPEC v1.1 (shared contract)

Every part of Heimdall (Tag firmware in C++, phone web app in JS, Ear in Python, command post) must follow this file **exactly**. If something here is wrong or impossible, tell Namig. Don't silently change it in your own code.

Owner: Namig. Version: **v1.1**, Sat Nov 7, 17:30. Changes from v1 are marked **(v1.1)**: the motion window (1.3, 1.5), relay timing (1.6), receiver steps 5, 6 and 8 (1.7), `victim.confirmed` and the `thermal_det` box corner (section 3). The air format and the test vectors did not change.

---

## 1. Acoustic frame "HEIMDALL-AC1"

One frame = **preamble + gap + 48 data symbols**. All parts are linear frequency chirps.

### 1.1 Bands
| Band | f_lo (Hz) | f_hi (Hz) |
|---|---|---|
| 0 | 1500 | 2500 |
| 1 | 2500 | 3500 |
| 2 | 3500 | 4500 |
| 3 | 5000 | 6500 |

Everything stays below 7 kHz so a 16 kHz recording (the mic array's rate) captures it.

### 1.2 Timing
| Part | Duration | Content |
|---|---|---|
| Preamble | 200 ms | up-chirp f_lo → f_hi |
| Gap | 10 ms | silence |
| 48 symbols | 40 ms each (1920 ms) | bit 1 = up-chirp f_lo → f_hi, bit 0 = down-chirp f_hi → f_lo. Contiguous, no gaps. |
| **Total** | **2130 ms** | |

Why 40 ms symbols: a quick simulation (white noise 5 dB SNR, room reverb RT60 0.4 s, direct-to-reverberant ratio −5 dB) decoded ~95% of frames with 40 ms symbols vs ~75% with 25 ms (8 trials per band, rough numbers). Indoor halls are reverberant, so we pay 0.7 s of airtime for reliability.

- Chirp phase for one segment of length T, from f0 to f1: `phi(t) = 2*pi*(f0*t + (f1 - f0) * t*t / (2*T))`, `0 <= t < T`. **Phase restarts at 0 for every segment.** Sample = `A * w(t) * sin(phi(t))`.
- Fade `w(t)`: raised-cosine ramp up and down at both ends of each segment: **5 ms** for the preamble, **2 ms** for each symbol. `w = 0.5 - 0.5*cos(pi * x / ramp)` on the ramps, 1 in between.
- Peak amplitude `A = 0.8` of full scale.
- **Sample rate:** any rate ≥ 16000 Hz. The math is in continuous time. Tag plays at 16000 Hz, the web app at the AudioContext rate (usually 48000), and receivers build their own templates at their capture rate.

### 1.3 Payload (48 bits = 6 bytes)
Bytes 0..4 are a 40-bit big-endian integer `P`. Byte 5 is the CRC.

| Field | Bits | Position in P (bit 39 = MSB) | Encoding |
|---|---|---|---|
| id | 16 | 39..24 | beacon ID, shown as 4 uppercase hex digits ("1A2B") |
| floor | 5 | 23..19 | 0 = unknown; else floor = code − 2 (so −1 … 29) |
| min2 | 6 | 18..13 | minutes since SOS ÷ 2, rounded down, capped at 63 (so 0 … 126 min) |
| motion | 1 | 12 | 1 = moved in the last 60 s (normal mode) or 20 s (demo mode) **(v1.1)** |
| status | 2 | 11..10 | 0 no_response, 1 ok, 2 injured, 3 critical |
| people | 3 | 9..7 | 0 … 7 (7 means 7+) |
| battery | 2 | 6..5 | 0 … 3 (quarters) |
| hops | 2 | 4..3 | 0 = original, 1..3 = relayed that many times |
| knock | 1 | 2 | 1 = this beacon heard rescuer knocks (last 2 min) |
| reserved | 2 | 1..0 | 0 |

- **CRC-8:** polynomial 0x07, init 0x00, no reflection, no final XOR (CRC-8/SMBUS), computed over bytes 0..4. Check value: CRC of ASCII `"123456789"` = **0xF4**.
- **Bit order on air:** byte 0 first, **MSB first** within each byte. Symbol k (0..47) carries bit k of that stream.

### 1.4 Test vectors (every implementation must reproduce these exactly)
| Input | Bytes (hex) |
|---|---|
| id 0x1A2B, floor 2, minutes 14, motion 1, status injured (2), people 2, battery 3, hops 0, knock 0 | `1A 2B 20 F9 60 66` |
| id 0x77C1, floor unknown, minutes 61, motion 0, status critical (3), people 1, battery 1, hops 1, knock 1 | `77 C1 03 CC AC EA` |

Bit stream of vector 1: `000110100010101100100000111110010110000001100110`

### 1.5 When to transmit
- Period: **8 s** in demo mode (default for the hackathon), 30 s in normal mode. Demo mode also shortens the motion window to 20 s (1.3). **(v1.1)**
- Add random jitter of ±1.0 s to every period, so two beacons don't collide forever.
- Band for transmission number k (k = 0, 1, 2 …): `band = (k + id) % 4`.
- **Burst mode** (test only, e.g. direction calibration): period 3 s, same band every time (band 1). **(v1.1: wording only)**

### 1.6 Relay rule (phones only)
A phone in victim mode with "relay" on:
1. Decodes a frame with a valid CRC, `hops < 3`, and an id that isn't its own.
2. Has not relayed that id in the last 30 s.
3. Waits a random 1.5 to 4.0 s. If it hears any preamble during that wait, it waits again (max 3 times, then drops it).
4. Transmits the **same payload with hops + 1** (recompute the CRC) on band `(received band + 1) % 4`.
5. Never plays two frames at once: if its own beacon is playing or due in the next 2.5 s, it sends the relay right after its own frame ends. A phone never decodes or relays its own id. **(v1.1)**

The Ear keeps one record per id, prefers hops 0, and labels relayed records "via relay".

### 1.7 Receiver guidance (non-binding, but proven to work)
1. Band-pass each band (4th-order Butterworth, f_lo − 200 … f_hi + 200 Hz).
2. Matched-filter against the preamble template for each band (FFT correlation).
3. Detection: peak of |corr| divided by the median of |corr| over the last 2 s > **8.0**.
4. The peak marks the preamble end. Symbol k starts at `t_end_preamble + 0.010 + k * 0.040`.
5. For each symbol, compute the **non-coherent** correlation magnitude `|<analytic signal, complex template>|` with the up template and with the down template. Bigger one wins. Coherent (real-valued) correlation fails under reverb. **Track timing (v1.1):** a 0.1% clock error drifts about 1.9 ms by the last symbol, so fit the symbol timing as offset + drift over all 48 symbols, then search ±0.25 ms around that line. `modem/` does exactly this.
6. Check the CRC and drop bad frames. Also drop frames whose 2 reserved bits aren't 0, or whose preamble correlation or symbol quality is weak (the gates in `modem/`). **Confirmation (v1.1):** the CRC plus the reserved bits still pass about 1 in 1024 garbage decodes, and the extra gates don't catch them all (N2 saw 1 bad frame in 30 min of adversarial noise), so a receiver treats a new id as **unconfirmed** until a second valid frame with the same id arrives within 60 s. The Ear publishes an unconfirmed victim with `"confirmed": false` and forgets it after 60 s if no second frame comes. Once confirmed, an id stays confirmed.
7. Report: id, all fields, band, `snr_db = 20*log10(peak/median)`, time of arrival.
8. **Direction (Ear):** GCC-PHAT between every mic pair, limited to the frame's band, on the 200 ms preamble or on the whole frame. **(v1.1)** At 16 kHz one sample is 2.1 cm of sound travel, so interpolate the correlation (upsample at least 16×) before reading delays. Then fit the bearing: try every angle from −180 to 180° in 1° steps, keep the one whose predicted pair delays score the highest summed correlation, and refine around it. Bearing convention below.

---

## 2. Angles
- **Bearing 0 = the station's front arrow** (the way the pan-tilt faces at center). Positive = clockwise seen from above = to the right. Range −180 … 180.
- Pan = same convention. Tilt 0 = level, positive = up.

---

## 3. Ear events (WebSocket `/ws`, JSON, one object per message)
Every event has `"t"` (type) and `"ts"` (unix seconds, float).
```
bearing     {"t":"bearing","ts":..,"deg":-35.0,"conf":0.82,"band":1,"snr_db":18.5,"src":"tag","id":"1A2B"}
              src "tag" = decoded beacon, "sound" = human sound from the classifier (id null), "scan" = head-scan result
victim      {"t":"victim","ts":..,"id":"1A2B","floor":2,"minutes":14,"motion":true,"status":"injured",
             "people":2,"battery":3,"hops":0,"knock":false,"deg":-35.0,"band":1,"snr_db":18.5,"confirmed":true}
              confirmed (v1.1): false until a second frame with this id arrives (1.7 step 6); hide it after 60 s.
              deg may be null (v1.1) when the Ear only knows this victim from a phone's "heard" report.
thermal_det {"t":"thermal_det","ts":..,"pan_deg":-30.0,"max_c":34.1,
             "hotspots":[{"x":0.41,"y":0.55,"w":0.12,"h":0.30,"temp_c":33.8,"deg":-32.5}]}
              x,y = TOP-LEFT corner of the box, w,h = its size, all normalized 0..1 to the thermal image (v1.1)
pantilt     {"t":"pantilt","ts":..,"pan":-30.0,"tilt":10.0,"mode":"auto"}           mode auto|manual
radar       {"t":"radar","ts":..,"presence":true,"breath_bpm":14.2,"heart_bpm":null,"dist_m":1.1,"src":"tinyrad"}
knock       {"t":"knock","ts":..,"source":"sw420","count":3,"level_db":null}
sound       {"t":"sound","ts":..,"label":"Speech","score":0.71,"deg":40.0}
noise       {"t":"noise","ts":..,"band_db":[-48.1,-51.0,-55.2,-60.3],"quiet":false}
heading     {"t":"heading","ts":..,"yaw_deg":212.0}
lora        {"t":"lora","ts":..,"tx":12,"last_ok":true}
drone       {"t":"drone","ts":..,"link":"ok","note":"perched"}          (placeholder until the drone is chosen)
health      {"t":"health","ts":..,"modules":{"audio":"ok","thermal":"error","radar":"off"}}
```
Client → server:
```
pantilt_cmd  {"t":"pantilt_cmd","pan":-30.0,"tilt":10.0}      puts the head in manual
pantilt_mode {"t":"pantilt_mode","mode":"auto"}
heard        {"t":"heard","id":"77C1","fields":{...victim fields...},"band":2,"snr_db":12.0,"via":"phone-1A2B"}
              (a phone forwards what it decoded, when it's on the station Wi-Fi)
```
Thermal video: MJPEG at `/thermal.mjpg`.

---

## 4. Station servo + knock controller (Seeeduino, USB serial 115200, lines end with `\n`)
Pi → Seeeduino:
| Command | Meaning | Reply |
|---|---|---|
| `PING` | alive? | `PONG` |
| `P <pan> <tilt>` | integer degrees, pan −90…90, tilt −30…60 (slews smoothly) | `OK P <pan> T <tilt>` |
| `R <ch> <raw>` | raw servo angle 0…180 (ch 0 = pan, 1 = tilt), for calibration | `OK R <ch> <raw>` |
| `C <pan_center_raw> <tilt_level_raw>` | set calibration until reboot | `OK C <a> <b>` |
| `?` | state | `STATE P <pan> T <tilt> C <a> <b> IDLE <0/1>` |

Seeeduino → Pi (unprompted):
| Line | Meaning |
|---|---|
| `HELLO HEIMDALL-SERVO 1` | after boot |
| `KNOCK <count>` | a group of knocks ended (hits ≥ 120 ms apart, group ends after 1.5 s quiet) |

---

## 5. Hardware Tag serial log (115200, for debugging only)
`TX id=1A2B band=1 k=12 bytes=1A2B20F96066`, `SHOCK 3.10g`, `STILL 60s`, `KNOCK 3`, `BTN SOS`, `BTN STATUS injured`, `BARO 1012.4hPa alt=12.3m floor=2`.

---

## 6. LoRa (Ear → command post)
- Radio: Adafruit RFM95W, **915.0 MHz**, SF9, BW 125 kHz, CR 4/5, TX power 13 dBm, CRC on. **Antenna must be attached before power.**
- Ear sends one packet every 10 s (and right away when a new victim appears or a status changes), ASCII, max 240 bytes:
  `HMD1|<seq>|<id>,<status>,<people>,<floor>,<minutes>,<motion>,<deg>,<hops>;<id>,...`
  status as one letter: N no_response, O ok, I injured, C critical. floor `?` if unknown. motion 1/0. deg integer.
  Example: `HMD1|42|1A2B,I,2,2,14,1,-35,0;77C1,C,1,?,61,0,40,1`
- Command post replies `ACK|<seq>` (optional).
