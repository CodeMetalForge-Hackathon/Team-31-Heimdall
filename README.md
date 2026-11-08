# Heimdall

**Hears who you can't see.**

Victims (phones running our web app, or small ESP32 Tags) play a coded acoustic chirp. The Heimdall station (Raspberry Pi 5 + mic array + thermal camera on a pan-tilt head) finds the chirp's direction and shows it to the drone operator on a phone web app served over the station's own Wi-Fi hotspot.

The contract for every part is [`docs/SPEC.md`](docs/SPEC.md). Read it first. The plan is [`PLAN.md`](PLAN.md).

## Team
Namig Mirzayev, Mikael Aznauryan, Erdeni Iles, Giorgi Mumladze

## Git rules
- One branch per task: `<person>/<TASK>` (e.g. `erdeni/E1-station`).
- Only commit your own paths.
- Never commit to `main`. Push your branch; Namig merges.

## Layout
```
docs/SPEC.md      the contract (frame format, angles, events, serial, LoRa)
ear/              station server (Python, runs on the Pi)
  bus.py          in-process publish/subscribe
  main.py         starts modules + server
  server.py       FastAPI: web app, /ws, /thermal.mjpg, /api/state
  config.py       one dict; HEIMDALL_MODULES overrides the module list
  modules/        one file per sensor (mock.py fakes all of them)
  tools/          make_cert.sh, net_mode.sh, heimdall.service, hw_smoke/
  certs/          TLS certs (gitignored, made on the Pi)
web/              phone web app (served by the Ear); debug.html = raw event view
firmware/         ESP32 Tag, Seeeduino servo/knock
modem/            acoustic modem (Python reference)
command/          command post (LoRa receiver)
pitch/            pitch material
```

## Running the Ear
On the Pi (`ssh heimdall@heimdall`, see "Getting into the Pi" below):
```bash
cd ~/Team-31 && source ~/heimdall-venv/bin/activate
ear/tools/make_cert.sh                      # once (certs last 30 days; --force to remake)
HEIMDALL_MODULES=mock python -m ear.main    # Ctrl-C to stop
```
On a laptop: `pip install fastapi "uvicorn[standard]" numpy opencv-python-headless`, then the same commands.

- Modules come from `ear/config.py` (`"modules": ["mock"]`) or env `HEIMDALL_MODULES=mock,thermal`.
- With `mock` plus a real module (e.g. `mock,thermal`), the mock stops faking that module's events, so you can bring sensors up one at a time.
- Test one module alone, events printed as JSON lines: `python -m ear.modules.mock`.
- As a service: see the comments in `ear/tools/heimdall.service` (installed, not enabled; `journalctl -u heimdall -f` for logs).

### Endpoints (port 8443, HTTPS)
| Path | What |
|---|---|
| `/` | `web/index.html` (redirects to `/debug.html` until it exists) |
| `/debug.html` | raw event log, victims table, thermal video, pan buttons |
| `/ws` | WebSocket. On connect: every known victim + last event of each type, then live events. Send JSON (`pantilt_cmd`, `pantilt_mode`, `heard`) and it goes on the bus as-is. Events: SPEC section 3. |
| `/thermal.mjpg` | MJPEG, up to 10 fps |
| `/api/state` | `{"victims": {...}, "last": {type: event}}` |
| `/ca.crt` | the local CA, to install on a phone (see below) |

## Module contract
Every sensor is one file in `ear/modules/`, owned by one person:
```python
# ear/modules/<name>.py
def run(bus, cfg: dict) -> None:   # blocking loop. main.py runs it in a daemon thread and restarts it
                                   # 3 s after any exception (logs the traceback, health shows "error")
if __name__ == "__main__":         # standalone test:  python -m ear.modules.<name>
    from ear.bus import PrintBus
    run(PrintBus(), {})
```
- `cfg` is that module's section of `ear/config.py` (e.g. `CONFIG["thermal"]`); `{}` in standalone tests, so have defaults.
- Publish events: `bus.publish({"t": "thermal_det", ...})`. `ts` is filled in if you leave it out. Field names and types **exactly as in `docs/SPEC.md` section 3**.
- Listen: `bus.subscribe("pantilt_cmd", fn)` (or `None` for everything). `fn(event)` runs in its own thread with a 200-event queue (oldest dropped), so keep it quick and never block the publisher.
- Video: `bus.set_frame(jpeg_bytes)`; the server streams the latest frame.
- Returning from `run()` without an exception means "nothing to do" (e.g. no device found): health shows `off` and it is not restarted. Raise if you want a retry.
- `health` (every 5 s): `ok` running, `error` crashed or import failed, `off` returned or not enabled.

## Audio (mic array)
`ear/modules/audio.py`: Seeed **reSpeaker XVF3800 USB 4-Mic Array** (round case) → HEIMDALL-AC1 decode → GCC-PHAT bearing → `bearing`, `victim`, `noise` events. Run with `HEIMDALL_MODULES=mock,audio` (the mock then stops faking those). Standalone: `python -m ear.modules.audio` (or `--wav rec.wav` to replay a 6-channel recording).

**Plug in:** the USB-C **next to the 3.5 mm jack** (the XMOS port), straight into the Pi. The other USB-C belongs to the XIAO ESP32 board and shows up as "Espressif", not as a mic. Red LED = muted (button on the case) = silence on every channel.

**Firmware:** our kit (with XIAO) shipped with **I2S firmware, which is not a USB device at all**. It is flashed with Seeed's **`respeaker_xvf3800_usb_dfu_firmware_v2.1.1_16k6ch.bin`** (6 channels, 16 kHz: ch0 conference, ch1 ASR, **ch2-5 raw mics**). To reflash: unplug, **hold the mute button while plugging it back in** (red LED blinks = Safe Mode), then `bash ear/tools/audio/flash_xvf3800.sh` (asks for the Pi password). Check: `arecord -l` lists "reSpeaker XVF3800 4-Mic Array", and `python ear/tools/audio/xvf_probe.py --list` says 6 inputs.

**Geometry** (seen from above, cable at 6 o'clock, **front = 12 o'clock = bearing 0**, +90 = right, SPEC 2). The mic holes are the corners of a **6.65 cm square** (9.35 cm diagonal):

| Channel | Hole | (x, y) m |
|---|---|---|
| ch4 | 10:30 front-left | (+0.03325, −0.03325) |
| ch5 | 1:30 front-right | (+0.03325, +0.03325) |
| ch2 | 4:30 back-right | (−0.03325, +0.03325) |
| ch3 | 7:30 back-left | (−0.03325, −0.03325) |

Mount it flat on the mast with the **cable pointing to the back of the station** and a pen mark at 12 o'clock on the front arrow. Keep anything taller than the puck 10 cm away. If the front ever reads off, set `audio.bearing_offset_deg` in `ear/config.py`.

**Calibrate / test:** `ssh -t heimdall@heimdall 'bash ~/Team-31/ear/tools/audio/calibrate.sh'`. It walks you through phone positions: on `modem_test.html`, band 1, tap **Play burst** (every 3 s), press Enter at each spot, and it prints mean ± std + decode rate and saves `~/calib/*.wav`. For one spot: `python ear/tools/audio/doa_test.py --true 90`. Unit tests: `python -m pytest ear/tools/audio/test_doa.py`.
- **Line of sight matters.** A laptop or a person between the phone and the puck made "behind" read as "front" in our tests (a reflection beats the blocked direct path). With a clear path, behind read −179°.

**Relay demo switch:** on stage the station can hear the victim's phone directly, so to show a relay: `HEIMDALL_IGNORE_DIRECT=1A2B ear/tools/restart_ear.sh`. The station drops 1A2B's **hops-0** frames (one log line each) and shows the relayed copy as "1A2B (via relay)". Turn it off with a plain `ear/tools/restart_ear.sh`. Permanent version: `audio.ignore_direct_ids` in `ear/config.py`.

**Rules it follows:** a new id is `confirmed: false` until a second frame within 60 s, then stays confirmed; an unconfirmed id is dropped after 60 s (SPEC 1.7.6). One record per id: a relayed copy only refreshes "last heard" if a direct frame came in the last 30 s. Relayed frames publish **no `bearing`** (their direction is the relaying phone's, not the victim's), so auto-aim never points at a relay. A phone's `heard` report becomes a victim with `deg: null` if the station hasn't heard that id itself in 30 s. `noise` = mean power per band of the decode channel's last second (raw mic, so levels are low: about −70 to −100 dBFS in a quiet room).

**Restart the Ear** (always this way, so pkill can't hit your own SSH session): `ear/tools/restart_ear.sh [modules]` (default `mock,audio`, log `~/ear.log`).

## Field network
- The Pi runs Wi-Fi hotspot **`HEIMDALL`**, password **`heimdallforge26`**, Pi at **`10.42.0.1`**.
- Operator / victim phones join it and open **`https://10.42.0.1:8443/`** (debug: `https://10.42.0.1:8443/debug.html`). No internet on this network.
- Two radios at once (`ear/tools/net_mode.sh dual`, already set up, survives reboots): the **ALFA USB adapter** (`rtw88_8821au`, built into the kernel) stays on the venue Wi-Fi for internet + Tailscale, the **built-in Wi-Fi** runs the hotspot.
- Without the ALFA: `net_mode.sh dev|demo` switches the built-in Wi-Fi between venue Wi-Fi and hotspot (demo cuts internet and Tailscale; reconnect via `HEIMDALL` → `ssh heimdall@10.42.0.1`).
- The venue password contains a `$`: always put it in **single quotes** in shell commands (`password 'PASS'`), or the shell eats part of it.

## Getting into the Pi (SSH)
BASE-X Guest Wi-Fi blocks devices from talking to each other, so SSH goes through **Tailscale** (free).
1. Install Tailscale on your laptop (tailscale.com/download) and accept Namig's invite (he adds you under Users → Invite in the Tailscale admin).
2. `ssh heimdall@heimdall` (password from Namig), then `ssh-copy-id heimdall@heimdall` so you don't need it again.
3. On the hotspot (no Tailscale needed): join `HEIMDALL`, `ssh heimdall@10.42.0.1`.

The Pi has no GitHub login. Code gets there from Namig's laptop: `git remote add pi heimdall@heimdall:Team-31` once, then `git push pi <branch>` and `git checkout <branch>` on the Pi.

### Certificate warning (once per phone)
Phones only allow the microphone and motion sensors on HTTPS, and our cert is self-signed, so the browser warns once.

**Android Chrome:** open `https://10.42.0.1:8443/` → "Your connection is not private" → **Advanced** → **Proceed to 10.42.0.1 (unsafe)**. Chrome remembers this for a while; repeat if it warns again.

**iPhone Safari:** open `https://10.42.0.1:8443/` → "This Connection Is Not Private" → **Show Details** → **visit this website** → **Visit Website**.

**If the page loads but stays "disconnected"** (some iOS versions block the WebSocket even after the warning), install the CA once instead:
1. Open `https://10.42.0.1:8443/ca.crt` in Safari → **Allow** (profile downloaded).
2. Settings → General → **VPN & Device Management** → Heimdall Local CA → **Install**.
3. Settings → General → About → **Certificate Trust Settings** → enable **Heimdall Local CA**.

Android equivalent: download `/ca.crt`, then Settings → Security → Encryption & credentials → Install a certificate → CA certificate.

The certs expire after 30 days; `ear/tools/make_cert.sh --force` makes new ones (phones that installed the CA must reinstall it).
