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
