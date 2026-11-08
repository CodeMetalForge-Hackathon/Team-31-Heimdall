#!/usr/bin/env python3
"""Talk to the Heimdall servo+knock Seeeduino (docs/SPEC.md section 4).
  python servo_cli.py            interactive: type P 30 10, R 0 90, ?, PING  (Ctrl-C quits)
  python servo_cli.py sweep      pan -60..60, tilt -20..40, then center
  python servo_cli.py listen     print everything the board says for 60 s (KNOCK lines)
"""
import sys, time, glob, threading
import serial  # pyserial

def find_port():
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/cu.usb*"))
    if not ports:
        sys.exit("No serial port found. Is the Seeeduino plugged in?")
    return ports[0]

def reader(s, stop):
    while not stop.is_set():
        line = s.readline().decode(errors="replace").strip()
        if line:
            print(f"[{time.strftime('%H:%M:%S')}] <- {line}")

def send(s, cmd):
    print(f"-> {cmd}")
    s.write((cmd + "\n").encode())

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "interactive"
    s = serial.Serial(find_port(), 115200, timeout=0.2)
    time.sleep(2.0)  # the board resets when the port opens
    stop = threading.Event()
    threading.Thread(target=reader, args=(s, stop), daemon=True).start()
    send(s, "PING"); time.sleep(0.3)
    try:
        if mode == "sweep":
            for p, t in [(0, 0), (-60, 0), (60, 0), (0, 0), (0, -20), (0, 40), (0, 0)]:
                send(s, f"P {p} {t}"); time.sleep(1.5)
        elif mode == "listen":
            time.sleep(60)
        else:
            while True:
                send(s, input().strip())
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set(); s.close()

if __name__ == "__main__":
    main()
