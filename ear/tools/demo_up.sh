#!/usr/bin/env bash
# Start the Ear in DEMO configuration as the systemd service (survives SSH, restarts on crash, starts on boot).
#   ear/tools/demo_up.sh                      audio,pantilt,thermal, no mock, no relay trick
#   ear/tools/demo_up.sh --relay A001         relay demo: ignore A001's direct frames (only relays get through)
#   ear/tools/demo_up.sh --acc 4              bearing = sum of the last 4 frames per id (N6 smoothing)
#   ear/tools/demo_up.sh --bands 1,2          bearings only from these bands; other frames keep the last one (N7)
#   ear/tools/demo_up.sh --modules audio      other module list
#   ear/tools/demo_up.sh --boot               also enable the service at boot (power-cut proof)
#   ear/tools/demo_up.sh --stop               stop the service (and disable boot start); back to restart_ear.sh
# NO mock in the demo: it would put fake radar/drone/heading data in front of the judges.
# Settings go to ~/heimdall.env, which heimdall.service reads (EnvironmentFile).
# No password prompts: install ear/tools/heimdall.sudoers once (instructions inside it).
set -u
cd "$(dirname "$0")/../.."
MODS="audio,pantilt,thermal" RELAY="" ACC="1" BANDS="" BOOT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --relay) RELAY="${2:?--relay needs an id, e.g. A001}"; shift 2 ;;
    --acc) ACC="${2:?--acc needs a number}"; shift 2 ;;
    --bands) BANDS="${2:?--bands needs a list, e.g. 1,2}"; shift 2 ;;
    --modules) MODS="${2:?--modules needs a list}"; shift 2 ;;
    --boot) BOOT=1; shift ;;
    --stop) sudo systemctl disable --now heimdall 2>/dev/null; echo "service stopped and disabled; use ear/tools/restart_ear.sh for dev runs"; exit 0 ;;
    *) echo "unknown option $1 (see the top of this file)"; exit 2 ;;
  esac
done

# 1. hotspot
if nmcli -t -f NAME con show --active 2>/dev/null | grep -qx "heimdall-hotspot"; then
  echo "hotspot: HEIMDALL is up (10.42.0.1)"
else
  echo "WARNING: hotspot heimdall-hotspot is NOT active. Phones can't connect. Fix: ear/tools/net_mode.sh dual (or demo)"
fi

# 2. settings for the service
cat > ~/heimdall.env <<EOF
HEIMDALL_MODULES=$MODS
HEIMDALL_IGNORE_DIRECT=$RELAY
HEIMDALL_DOA_ACCUMULATE=$ACC
HEIMDALL_DOA_BANDS=$BANDS
EOF
echo "settings (~/heimdall.env): modules=$MODS relay=${RELAY:-off} acc=$ACC bands=${BANDS:-all}"

# 3. install the unit if it changed, stop manual runs, (re)start the service
if ! cmp -s ear/tools/heimdall.service /etc/systemd/system/heimdall.service; then
  sudo cp "$PWD/ear/tools/heimdall.service" /etc/systemd/system/heimdall.service && sudo systemctl daemon-reload
  echo "installed ear/tools/heimdall.service"
fi
PAT='[p]ython -m ear.main'
if ! systemctl is-active --quiet heimdall && pgrep -f "$PAT" >/dev/null; then
  echo "stopping the manual (restart_ear.sh) run first"
  pkill -f "$PAT"; for _ in $(seq 1 50); do pgrep -f "$PAT" >/dev/null || break; sleep 0.1; done
  pgrep -f "$PAT" >/dev/null && pkill -9 -f "$PAT"
fi
sudo systemctl restart heimdall
if [ "$BOOT" = 1 ]; then
  sudo systemctl enable heimdall >/dev/null 2>&1 && echo "service enabled at boot"
elif systemctl is-enabled --quiet heimdall 2>/dev/null; then
  echo "note: the service is still enabled at boot (from an earlier --boot); --stop disables it"
fi
echo "branch: $(git branch --show-current) $(git log --oneline -1 | cut -c1-60)"

# 4. health after 8 s
sleep 8
if ! systemctl is-active --quiet heimdall; then
  echo "FAILED: the service isn't running. Last log lines:"; journalctl -u heimdall -n 20 --no-pager; exit 1
fi
curl -sk --max-time 5 https://localhost:8443/api/state | python3 -c '
import json, sys
try:
    s = json.load(sys.stdin)
except Exception:
    print("no answer from https://localhost:8443/api/state yet; journalctl -u heimdall -f"); sys.exit()
h = (s.get("last") or {}).get("health") or {}
print("modules:", ", ".join(f"{k}={v}" for k, v in (h.get("modules") or {}).items()) or "(no health event yet)")
print("victims:", ", ".join(sorted((s.get("victims") or {}).keys())) or "none yet")'
echo "phones:   https://10.42.0.1:8443/victim.html   operator: https://10.42.0.1:8443/operator.html"
echo "logs:     journalctl -u heimdall -f"
