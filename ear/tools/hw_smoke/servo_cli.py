#!/usr/bin/env python3
"""Talk to the Heimdall servo+knock Seeeduino (docs/SPEC.md section 4).
  python servo_cli.py            interactive: type P 30 10, R 0 90, ?, PING  (Ctrl-C quits)
  python servo_cli.py sweep      pan -60..60, tilt -20..40, then center
  python servo_cli.py listen     print everything the board says for 60 s (KNOCK lines)
  python servo_cli.py --port /dev/ttyUSB0 sweep
"""
import sys, time, glob, threading
import serial  # pyserial

DEFAULT_PORT = "/dev/ttyUSB0"

def candidate_ports():
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                  + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*"))

def parse_argv():
    """Return (mode, port_or_None). mode defaults to interactive."""
    args = sys.argv[1:]
    port = None
    mode_args = []
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = args[i + 1]
            i += 2
            continue
        mode_args.append(args[i])
        i += 1
    mode = mode_args[0] if mode_args else "interactive"
    return mode, port

def find_port(explicit=None):
    """Use --port if given; else probe HELLO/PONG (prefer /dev/ttyUSB0); else first candidate."""
    if explicit:
        return explicit
    ports = candidate_ports()
    if not ports:
        sys.exit("No serial port found. Is the Seeeduino plugged in?")
    ordered = ([DEFAULT_PORT] if DEFAULT_PORT in ports else []) + [p for p in ports if p != DEFAULT_PORT]
    for p in ordered:
        try:
            s = serial.Serial(p, 115200, timeout=0.2)
        except (OSError, serial.SerialException) as e:
            print(f"skip {p}: {e}", file=sys.stderr)
            continue
        t0, pinged = time.time(), False
        while time.time() - t0 < 5.0:
            line = s.readline().decode(errors="replace").strip()
            if line.startswith("HELLO HEIMDALL-SERVO") or line == "PONG":
                s.close()
                print(f"servo board on {p} ({line})", file=sys.stderr)
                return p
            if not pinged and time.time() - t0 > 2.5:
                s.write(b"PING\n")
                pinged = True
        s.close()
        print(f"no servo board on {p}", file=sys.stderr)
    return DEFAULT_PORT if DEFAULT_PORT in ports else ports[0]

def reader(s, stop):
    while not stop.is_set():
        line = s.readline().decode(errors="replace").strip()
        if line:
            print(f"[{time.strftime('%H:%M:%S')}] <- {line}")

def send(s, cmd):
    print(f"-> {cmd}")
    s.write((cmd + "\n").encode())

def main():
    mode, port = parse_argv()
    s = serial.Serial(find_port(port), 115200, timeout=0.2)
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
