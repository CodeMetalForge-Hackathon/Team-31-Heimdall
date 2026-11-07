#!/usr/bin/env bash
# List USB serial, video, and audio devices on the station Pi.
set -u

echo "=== USB ==="
if command -v lsusb >/dev/null 2>&1; then
  lsusb
else
  echo "(lsusb not installed)"
fi

echo
echo "=== serial ==="
shopt -s nullglob
serials=(/dev/ttyACM* /dev/ttyUSB*)
if [ ${#serials[@]} -eq 0 ]; then
  echo "(none)"
else
  ls -l "${serials[@]}"
fi
if [ -d /dev/serial/by-id ]; then
  echo "-- by-id --"
  ls -l /dev/serial/by-id
fi

echo
echo "=== video ==="
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices || true
else
  videos=(/dev/video*)
  if [ ${#videos[@]} -eq 0 ]; then
    echo "(none)"
  else
    ls -l "${videos[@]}"
  fi
fi

echo
echo "=== audio ==="
if command -v arecord >/dev/null 2>&1; then
  arecord -l || true
else
  echo "(arecord not installed)"
fi
