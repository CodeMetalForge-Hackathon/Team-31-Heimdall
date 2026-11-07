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
On the Pi (`ssh heimdall@heimdall.local`):
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

## Field network
- The Pi runs Wi-Fi hotspot **`HEIMDALL`**, password **`heimdallforge26`**, Pi at **`10.42.0.1`**.
- Operator / victim phones join it and open **`https://10.42.0.1:8443/`** (debug: `https://10.42.0.1:8443/debug.html`). No internet on this network.
- `ear/tools/net_mode.sh dev|demo|status` switches the built-in Wi-Fi between venue Wi-Fi (dev, SSH at `heimdall.local`) and the hotspot (demo). SSH over venue Wi-Fi drops when you switch to demo; reconnect via the hotspot (`ssh heimdall@10.42.0.1`) or Ethernet.

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
