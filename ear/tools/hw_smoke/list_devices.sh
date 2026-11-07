#!/usr/bin/env bash
echo "== lsusb"; lsusb
echo "== audio capture devices"; arecord -l
echo "== video devices"; v4l2-ctl --list-devices 2>/dev/null || ls /dev/video*
for d in /dev/video*; do echo "-- formats $d"; v4l2-ctl -d "$d" --list-formats-ext 2>/dev/null | head -20; done
echo "== serial ports"; ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
echo "== I2C bus 1"; i2cdetect -y 1 2>/dev/null
echo "== SPI"; ls /dev/spidev* 2>/dev/null || echo "SPI off (sudo raspi-config nonint do_spi 0)"
