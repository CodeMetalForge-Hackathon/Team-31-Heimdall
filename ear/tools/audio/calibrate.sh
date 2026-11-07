#!/usr/bin/env bash
# Guided direction calibration (Part D.1). Run on the Pi in a terminal you can type into:
#   ssh -t heimdall@heimdall 'bash ~/Team-31/ear/tools/audio/calibrate.sh'
# For each position: put the phone there, press "Play burst" on modem_test.html, press Enter here.
# Each run stops after 10 decoded frames (or Ctrl-C) and saves ~/calib/<name>.wav + a row in ~/calib/calib.csv.
set -u
cd "$(dirname "$0")/../../.."
mkdir -p ~/calib
PY=~/heimdall-venv/bin/python
POSITIONS=${POSITIONS:-"2m:0 2m:90 2m:180 2m:-90 2m:45 4m:0 4m:90"}
for pos in $POSITIONS; do
  dist=${pos%%:*}; deg=${pos##*:}
  name="${dist}_${deg}"
  echo
  echo "=================================================================="
  echo " NEXT: phone ${dist} away at ${deg} deg   (0 = front, 90 = right, -90 = left, 180 = behind)"
  echo " Burst playing on the phone? Press Enter to start (s = skip, q = quit)"
  read -r ans
  [ "$ans" = q ] && break
  [ "$ans" = s ] && continue
  $PY ear/tools/audio/doa_test.py --raw --true "$deg" --frames 10 --label "$dist" \
      --save ~/calib/"$name".wav --log ~/calib/calib.csv
done
echo; echo "Done. Results: ~/calib/calib.csv"
