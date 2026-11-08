// HEIMDALL-AC1 frame for the Tag (docs/SPEC.md section 1), at exactly 16000 samples/s.
// Header-only, no heap. Matches modem/heimdall_ac1.py sample for sample (tested against it).
//
//   hac1::Fields f;            // fill in, then:
//   uint8_t frame[6];  hac1::pack(f, frame);                 // 5 payload bytes + CRC-8
//   float s = hac1::sample(frame, band, i);                  // i = 0 .. hac1::N_SAMPLES-1, |s| <= 0.8
//   uint8_t duty = hac1::toPwm8(s);   int16_t pcm = hac1::toPcm16(s);
#pragma once
#include <stdint.h>
#include <math.h>

namespace hac1 {

const int FS = 16000;
const int N_PRE = 3200;                 // 200 ms preamble
const int N_GAP = 160;                  // 10 ms silence
const int N_SYM = 640;                  // 40 ms per symbol
const int N_SYMBOLS = 48;
const int DATA0 = N_PRE + N_GAP;        // 3360
const int N_SAMPLES = DATA0 + N_SYMBOLS * N_SYM;   // 34080 = 2.130 s
const float PRE_RAMP_S = 0.005f, SYM_RAMP_S = 0.002f, AMPLITUDE = 0.8f;
const float BANDS[4][2] = {{1500.f, 2500.f}, {2500.f, 3500.f}, {3500.f, 4500.f}, {5000.f, 6500.f}};

enum Status : uint8_t { NO_RESPONSE = 0, OK = 1, INJURED = 2, CRITICAL = 3 };

struct Fields {
  uint16_t id = 0x1A2B;     // shown as 4 hex digits
  bool floorKnown = false;  // false = "floor unknown"
  int floor = 0;            // -1 .. 29 when floorKnown
  int minutes = 0;          // since SOS; sent as minutes/2, capped at 126
  bool motion = false;      // moved in the last 20 s (demo) / 60 s
  uint8_t status = NO_RESPONSE;
  uint8_t people = 1;       // 0..7 (7 = 7+)
  uint8_t battery = 3;      // 0..3 quarters
  uint8_t hops = 0;         // Tags never relay: always 0
  bool knock = false;       // heard rescuer knocks in the last 2 min
};

inline int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

// CRC-8/SMBUS: poly 0x07, init 0, no reflection, no final XOR. crc8("123456789") == 0xF4.
inline uint8_t crc8(const uint8_t *d, int n) {
  uint8_t c = 0;
  for (int i = 0; i < n; i++) {
    c ^= d[i];
    for (int b = 0; b < 8; b++) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
  }
  return c;
}

inline void pack(const Fields &f, uint8_t out[6]) {
  uint64_t p = 0;
  uint32_t floorCode = f.floorKnown ? (uint32_t)clampi(f.floor + 2, 1, 31) : 0;
  p |= (uint64_t)f.id << 24;
  p |= (uint64_t)floorCode << 19;
  p |= (uint64_t)clampi(f.minutes / 2, 0, 63) << 13;
  p |= (uint64_t)(f.motion ? 1 : 0) << 12;
  p |= (uint64_t)(f.status & 3) << 10;
  p |= (uint64_t)clampi(f.people, 0, 7) << 7;
  p |= (uint64_t)clampi(f.battery, 0, 3) << 5;
  p |= (uint64_t)clampi(f.hops, 0, 3) << 3;
  p |= (uint64_t)(f.knock ? 1 : 0) << 2;
  for (int i = 0; i < 5; i++) out[i] = (uint8_t)(p >> (8 * (4 - i)));
  out[5] = crc8(out, 5);
}

// Bit k of the frame in air order: byte 0 first, MSB first.
inline int bitAt(const uint8_t frame[6], int k) { return (frame[k >> 3] >> (7 - (k & 7))) & 1; }

inline float ramp(float tau, float T, float r) {
  const float PI_F = 3.14159265358979f;
  if (tau < r) return 0.5f - 0.5f * cosf(PI_F * tau / r);
  if (tau > T - r) return 0.5f - 0.5f * cosf(PI_F * (T - tau) / r);
  return 1.0f;
}

// One linear chirp segment f0 -> f1 of length T; phase restarts at 0 for every segment (SPEC 1.2).
inline float chirp(float tau, float T, float f0, float f1, float r) {
  const float TWO_PI_F = 6.28318530717959f;
  float phi = TWO_PI_F * (f0 * tau + (f1 - f0) * tau * tau / (2.0f * T));
  return ramp(tau, T, r) * sinf(phi);
}

// Sample i (0 .. N_SAMPLES-1) of the frame on `band`, in -0.8 .. 0.8.
inline float sample(const uint8_t frame[6], int band, int i) {
  const float lo = BANDS[band][0], hi = BANDS[band][1];
  if (i < 0 || i >= N_SAMPLES) return 0.0f;
  if (i < N_PRE) return AMPLITUDE * chirp((float)i / FS, 0.200f, lo, hi, PRE_RAMP_S);
  int j = i - DATA0;
  if (j < 0) return 0.0f;                          // the 10 ms gap
  int k = j / N_SYM;
  float tau = (float)(j % N_SYM) / FS;
  return bitAt(frame, k) ? AMPLITUDE * chirp(tau, 0.040f, lo, hi, SYM_RAMP_S)     // 1 = up
                         : AMPLITUDE * chirp(tau, 0.040f, hi, lo, SYM_RAMP_S);    // 0 = down
}

inline uint8_t toPwm8(float s) { return (uint8_t)clampi((int)lroundf(128.0f + s * 127.0f), 0, 255); }
inline int16_t toPcm16(float s) { return (int16_t)clampi((int)lroundf(s * 32767.0f), -32767, 32767); }

// SPEC 1.5: band for transmission number k of this beacon.
inline int bandFor(uint32_t k, uint16_t id) { return (int)((k + id) % 4); }

}  // namespace hac1
