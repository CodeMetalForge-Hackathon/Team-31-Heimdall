#!/usr/bin/env python3
"""Find the Hti thermal camera and save what it sends.  python thermal_probe.py [video_index]"""
import sys, glob
import cv2
import numpy as np

def main():
    if len(sys.argv) > 1:
        idxs = [int(sys.argv[1])]
    else:
        idxs = sorted(int(p.replace("/dev/video", "")) for p in glob.glob("/dev/video*") if p[10:].isdigit())
    found = []
    for i in idxs:
        cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
        if not cap.isOpened():
            continue
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fcc = "".join(chr((fourcc >> 8 * k) & 0xFF) for k in range(4))
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok, frame = cap.read()
        print(f"/dev/video{i}: {w}x{h} fourcc={fcc!r} read={ok} shape={None if frame is None else frame.shape}")
        if ok:
            cv2.imwrite(f"video{i}_converted.png", frame)
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # raw mode: thermal cams often hide temperatures here
            ok2, raw = cap.read()
            if ok2:
                np.save(f"video{i}_raw.npy", raw)
                print(f"   raw shape={raw.shape} dtype={raw.dtype} min={raw.min()} max={raw.max()}")
            found.append(i)
        cap.release()
    if not found:
        print("No camera gave a frame. Run `v4l2-ctl --list-devices` and `dmesg | tail -30` and send the output.")
    else:
        print("Saved PNG + NPY files. Send them to Namig with this output.")

if __name__ == "__main__":
    main()
