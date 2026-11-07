#!/usr/bin/env bash
# Restart the Ear on the Pi in the background (survives the SSH session).
#   ear/tools/restart_ear.sh [modules]      default: mock,audio      log: ~/ear.log
# The [p] in the pattern stops pkill/pgrep from matching a shell whose command line contains the pattern
# (e.g. the ssh command that runs this), which would kill your own session.
set -u
MODS="${1:-mock,audio}"
cd "$(dirname "$0")/../.."
PAT='[p]ython -m ear.main'

if pgrep -f "$PAT" >/dev/null; then
  pkill -f "$PAT"
  for _ in $(seq 1 50); do pgrep -f "$PAT" >/dev/null || break; sleep 0.1; done
  if pgrep -f "$PAT" >/dev/null; then echo "still running after 5 s; killing hard"; pkill -9 -f "$PAT"; sleep 0.5; fi
fi

echo "starting Ear: HEIMDALL_MODULES=$MODS ($(git branch --show-current) $(git log --oneline -1 | cut -c1-60))"
HEIMDALL_MODULES="$MODS" setsid nohup ~/heimdall-venv/bin/python -m ear.main > ~/ear.log 2>&1 < /dev/null &
sleep 4
tail -n 10 ~/ear.log
