#!/usr/bin/env python3
"""Send SPEC serial commands to the Seeeduino servo+knock firmware."""
from __future__ import annotations

import argparse
import select
import sys
import time

try:
    import serial  # type: ignore
except ImportError:
    sys.stderr.write("missing pyserial; install with: pip3 install pyserial\n")
    sys.exit(1)


def read_until_reply(ser: serial.Serial, timeout_s: float = 3.0) -> list[str]:
    lines: list[str] = []
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            if lines:
                break
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        print(line)
        lines.append(line)
        if (
            line == "PONG"
            or line.startswith("OK ")
            or line.startswith("STATE ")
            or line.startswith("ERR")
        ):
            break
    return lines


def send(ser: serial.Serial, cmd: str) -> None:
    ser.write((cmd.strip() + "\n").encode("ascii"))
    ser.flush()
    read_until_reply(ser)


def drain_hello(ser: serial.Serial) -> None:
    # Uno resets on port open; wait for HELLO.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if line:
            print(line)
        if line.startswith("HELLO HEIMDALL-SERVO"):
            return


def main() -> int:
    ap = argparse.ArgumentParser(description="Heimdall servo/knock USB CLI")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "cmd",
        nargs="*",
        help="command, e.g. PING or P 30 0. Omit for interactive mode.",
    )
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.3)
    except OSError as exc:
        sys.stderr.write(f"open failed: {exc}\n")
        return 1

    time.sleep(2.0)
    ser.reset_input_buffer()
    drain_hello(ser)

    if args.cmd:
        send(ser, " ".join(args.cmd))
        ser.close()
        return 0

    print("interactive: type PING, P 30 0, P -30 0, P 0 20, P 0 0, ?, R 0 90, C 90 90")
    print("Ctrl-C to quit. Unsolicited KNOCK lines print as they arrive.")
    try:
        while True:
            if ser.in_waiting:
                raw = ser.readline()
                if raw:
                    print(raw.decode("utf-8", errors="replace").strip())
                continue
            if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    send(ser, line)
    except KeyboardInterrupt:
        print()
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
