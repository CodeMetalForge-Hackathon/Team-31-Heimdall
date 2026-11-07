#!/usr/bin/env bash
# Flash the XVF3800 with Seeed's 6-channel 16 kHz USB firmware (raw mics on ch2-5). Run on the Pi:
#   bash ~/Team-31/ear/tools/audio/flash_xvf3800.sh
# The kit with the XIAO board ships with I2S firmware, which is NOT a USB device. To reach DFU from it:
# unplug the array, hold the mute button, plug it back in while holding: red LED blinking = Safe Mode.
set -euo pipefail
FW_NAME="respeaker_xvf3800_usb_dfu_firmware_v2.1.1_16k6ch.bin"
URL="https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY/raw/refs/heads/master/xmos_firmwares/usb/$FW_NAME"
FW="$HOME/xvf_fw/$FW_NAME"

mkdir -p "$(dirname "$FW")"
[ -s "$FW" ] || curl -sSfL -o "$FW" "$URL"
size=$(stat -c %s "$FW")
[ "$size" -gt 500000 ] || { echo "firmware file looks wrong ($size bytes): $FW"; exit 1; }
echo "firmware: $FW ($size bytes)"

command -v dfu-util >/dev/null || { echo ">>> installing dfu-util (asks for the Pi password)"; sudo apt-get install -y dfu-util; }

echo ">>> looking for the array in DFU (2886:001a)"
if ! sudo dfu-util -l 2>/dev/null | grep -i "2886:001a"; then
  echo "!!! not found. Unplug the array, HOLD the mute button, plug it in while holding,"
  echo "    wait for the red LED to blink, release, and run this script again."
  exit 1
fi

echo ">>> flashing (about 30 s; don't unplug)"
sudo dfu-util -R -e -a 1 -D "$FW"
echo ">>> done. Waiting for it to come back as a USB microphone..."
for _ in $(seq 1 20); do arecord -l 2>/dev/null | grep -qi "xvf\|respeaker" && break; sleep 1; done
arecord -l
echo "If it isn't listed: unplug and replug the array (no button), then: arecord -l"
