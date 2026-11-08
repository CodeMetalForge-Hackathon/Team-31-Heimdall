// Heimdall Tag A (M2): HEIMDALL-AC1 SOS beacon, docs/SPEC.md v1.2.
// Board: Seeed XIAO ESP32S3 Plus, Espressif Arduino core 3.3.x, FQBN esp32:esp32:XIAO_ESP32S3_Plus.
// Library: Adafruit LSM6DS (Adafruit_ISM330DHCX), the same one tag_smoke uses.
//
// What it does: from power-on (AUTOSTART_SOS) it plays one 2.13 s frame every 8 s +- 1 s, band (k + id) % 4.
//   The frame carries id A001, status (starts "injured"), minutes since SOS, and "moved in the last 20 s"
//   from the IMU. SOS button = beacon on/off. Touch pad = next status (the motor buzzes 1/2/3 times).
// Not in this version (cut at 02:00 Sunday): fall detection, knock-back, barometer floor, battery level.
//
// Audio out, pick one with AUDIO_OUT below:
//   AUDIO_PWM (Plan A, default): Grove Speaker SIG on D0. 8-bit LEDC PWM at 156.25 kHz, a 16 kHz timer ISR
//     writes the samples (the method tag_smoke measured: 16000 samples in 1.0005 s).
//   AUDIO_I2S (Plan B): Adafruit Speaker Bonnet (MAX98357A), I2S at 16 kHz on D8/D9/D10, see M2 Part E.
//
// Serial 115200: s = SOS on/off, t = one frame now, b = burst mode (3 s, band 1, for direction tests),
//   0..3 = status (0 no_response, 1 ok, 2 injured, 3 critical), m = motion readout, h = help.
// Log lines (SPEC 5): "TX id=A001 band=1 k=12 bytes=...", "BTN SOS on", "BTN STATUS injured", "MOVE", "STILL 20s".

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_ISM330DHCX.h>
#include "heimdall_ac1.h"

#define AUDIO_PWM 1
#define AUDIO_I2S 2
#ifndef AUDIO_OUT
#define AUDIO_OUT AUDIO_PWM          // <- Plan B: change AUDIO_PWM to AUDIO_I2S
#endif

#if AUDIO_OUT == AUDIO_I2S
#include <ESP_I2S.h>
#endif

// ---------------- settings ----------------
static const uint16_t TAG_ID = 0xA001;           // shown as "A001"; the relay demo ignores this id's direct frames
static const bool AUTOSTART_SOS = true;          // beacon from power-on (the demo plugs the power bank in at setup)
static const uint8_t START_STATUS = hac1::INJURED;
static const uint32_t PERIOD_MS = 8000;          // SPEC 1.5 demo mode
static const uint32_t JITTER_MS = 1000;          // +- 1 s
static const uint32_t BURST_PERIOD_MS = 3000;    // SPEC 1.5 burst mode, always band 1
static const uint32_t MOTION_WINDOW_MS = 20000;  // SPEC 1.3 demo mode: "moved in the last 20 s"
static const float MOVE_G = 0.08f;               // | |a| - rest | > 0.08 g (0.8 m/s2, the phones' rule)
static const float MOVE_DPS = 20.0f;             // or turning faster than 20 deg/s
static const uint32_t QUIET_AFTER_MS = 300;      // ignore the IMU this long after our own sound or buzz

// ---------------- pins (same wiring as tag_smoke) ----------------
static const uint8_t PIN_SPK = D0;     // Grove Speaker SIG (Plan A)
static const uint8_t PIN_BTN = D1;     // Grove Button SIG: SOS on/off
static const uint8_t PIN_TOUCH = D2;   // Grove Touch SIG: next status
static const uint8_t PIN_VIB = D3;     // Grove Vibration Motor SIG
static const uint8_t PIN_SDA = D4, PIN_SCL = D5;
static const uint8_t PIN_BCLK = D8, PIN_LRCLK = D9, PIN_DIN = D10;   // Plan B: Speaker Bonnet pins 12, 35, 40

// ---------------- state ----------------
Adafruit_ISM330DHCX imu;
static bool imuOk = false;
static float restG = 1.0f;                 // |a| at rest, measured at boot
static bool sos = false, burst = false;
static uint8_t tagStatus = START_STATUS;
static uint32_t sosStartMs = 0, nextTxMs = 0, txCount = 0;
static uint32_t lastMoveMs = 0;            // 0 = never moved since boot
static bool movingReported = false;
static uint32_t quietUntilMs = 0;          // IMU ignored until then (speaker / motor)
static uint8_t frameBytes[6];
struct Debounced { uint8_t pin; bool stable, lastRaw; uint32_t tChange; };
static Debounced sosBtn = {PIN_BTN, false, false, 0}, touchBtn = {PIN_TOUCH, false, false, 0};

static const char *statusName(uint8_t s) {
  static const char *names[] = {"no_response", "ok", "injured", "critical"};
  return names[s & 3];
}

// ---------------- audio: Plan A, PWM + 16 kHz timer ISR ----------------
#if AUDIO_OUT == AUDIO_PWM
static uint8_t txBuf[hac1::N_SAMPLES];     // 34080 duty values = 2.13 s
static hw_timer_t *audioTimer = nullptr;
static volatile uint32_t playIdx = hac1::N_SAMPLES;
static volatile bool playing = false;

static void IRAM_ATTR onAudioTimer() {
  uint32_t i = playIdx;
  if (i < (uint32_t)hac1::N_SAMPLES) {
    ledcWrite(PIN_SPK, txBuf[i]);
    playIdx = i + 1;
  } else if (playing) {
    ledcWrite(PIN_SPK, 128);               // back to silence (50 % duty)
    playing = false;
  }
}

static bool audioBegin() {
  // On this board LEDC runs from 40 MHz: 8-bit tops out at 156.25 kHz (tag_smoke, M1).
  bool ok = ledcAttachChannel(PIN_SPK, 156250, 8, 0) || ledcAttachChannel(PIN_SPK, 78125, 8, 0);
  if (!ok) return false;
  ledcWrite(PIN_SPK, 128);
  audioTimer = timerBegin(hac1::FS);       // 16 kHz tick, exact (APB 80 MHz / 5000)
  timerAttachInterrupt(audioTimer, &onAudioTimer);
  timerAlarm(audioTimer, 1, true, 0);      // fire every tick, forever; idle ticks do nothing
  return true;
}

static void audioPlay(const uint8_t frame[6], int band) {
  for (int i = 0; i < hac1::N_SAMPLES; i++) txBuf[i] = hac1::toPwm8(hac1::sample(frame, band, i));
  playIdx = 0;                             // the ISR starts on its next tick...
  playing = true;                          // ...and only the end of the frame clears this (index first: no race)
}

static bool audioBusy() { return playing; }
#endif

// ---------------- audio: Plan B, I2S to the MAX98357A ----------------
#if AUDIO_OUT == AUDIO_I2S
static int16_t txBuf[hac1::N_SAMPLES];
static I2SClass i2s;
static TaskHandle_t txTask = nullptr;
static volatile bool playing = false;

static void txTaskFn(void *) {
  static int16_t chunk[2 * 256];           // stereo: the same sample on left and right
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    for (int i = 0; i < hac1::N_SAMPLES; i += 256) {
      int n = min(256, hac1::N_SAMPLES - i);
      for (int j = 0; j < n; j++) chunk[2 * j] = chunk[2 * j + 1] = txBuf[i + j];
      i2s.write((uint8_t *)chunk, n * 4);  // blocks while the DMA plays: the clock is the I2S clock
    }
    memset(chunk, 0, sizeof(chunk));
    for (int k = 0; k < 8; k++) i2s.write((uint8_t *)chunk, sizeof(chunk));   // flush with silence
    playing = false;
  }
}

static bool audioBegin() {
  i2s.setPins(PIN_BCLK, PIN_LRCLK, PIN_DIN);
  if (!i2s.begin(I2S_MODE_STD, hac1::FS, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) return false;
  xTaskCreatePinnedToCore(txTaskFn, "tx", 4096, nullptr, 2, &txTask, 0);
  return true;
}

static void audioPlay(const uint8_t frame[6], int band) {
  for (int i = 0; i < hac1::N_SAMPLES; i++) txBuf[i] = hac1::toPcm16(hac1::sample(frame, band, i));
  playing = true;
  xTaskNotifyGive(txTask);
}

static bool audioBusy() { return playing; }
#endif

// ---------------- motor: non-blocking buzz patterns ----------------
static uint8_t buzzLeft = 0;
static uint16_t buzzOnMs = 0, buzzOffMs = 0;
static uint32_t buzzNextMs = 0;
static bool buzzOn = false;

static void buzz(uint8_t times, uint16_t onMs, uint16_t offMs = 150) {
  buzzLeft = times; buzzOnMs = onMs; buzzOffMs = offMs; buzzOn = false; buzzNextMs = millis();
}

static void buzzTick(uint32_t now) {
  if (!buzzOn && buzzLeft == 0) return;
  quietUntilMs = now + QUIET_AFTER_MS;     // the motor shakes the IMU
  if ((int32_t)(now - buzzNextMs) < 0) return;
  if (buzzOn) { digitalWrite(PIN_VIB, LOW); buzzOn = false; buzzNextMs = now + buzzOffMs; }
  else if (buzzLeft) { digitalWrite(PIN_VIB, HIGH); buzzOn = true; buzzLeft--; buzzNextMs = now + buzzOnMs; }
}

// ---------------- buttons (debounced rising edge) ----------------
// (struct Debounced and the two buttons are defined in the state section above: Arduino's
//  auto-generated prototype for pressed() lands before the first function and needs the type.)

static bool pressed(Debounced &d, uint32_t now) {
  bool raw = digitalRead(d.pin);
  if (raw != d.lastRaw) { d.lastRaw = raw; d.tChange = now; }
  if (now - d.tChange >= 30 && raw != d.stable) { d.stable = raw; return raw; }
  return false;
}

// ---------------- IMU motion ----------------
static void imuBegin() {
  imuOk = imu.begin_I2C(0x6B, &Wire);
  if (!imuOk) { Serial.println("IMU ISM330DHCX @0x6B NOT FOUND: motion stays 0. Check D4/D5 wiring."); return; }
  imu.setAccelRange(LSM6DS_ACCEL_RANGE_4_G);
  imu.setAccelDataRate(LSM6DS_RATE_104_HZ);
  imu.setGyroRange(LSM6DS_GYRO_RANGE_500_DPS);
  imu.setGyroDataRate(LSM6DS_RATE_104_HZ);
  delay(100);
  float sum = 0;
  for (int i = 0; i < 50; i++) {
    sensors_event_t a, g, t;
    imu.getEvent(&a, &g, &t);
    sum += sqrtf(a.acceleration.x * a.acceleration.x + a.acceleration.y * a.acceleration.y +
                 a.acceleration.z * a.acceleration.z) / SENSORS_GRAVITY_STANDARD;
    delay(10);
  }
  restG = constrain(sum / 50.0f, 0.9f, 1.1f);
  Serial.printf("IMU OK, |a| at rest %.3f g\n", restG);
}

static float lastAG = 0, lastDps = 0;

static void imuTick(uint32_t now) {
  static uint32_t tLast = 0;
  if (!imuOk || now - tLast < 20) return;  // 50 Hz is plenty for "moved in the last 20 s"
  tLast = now;
  sensors_event_t a, g, t;
  imu.getEvent(&a, &g, &t);
  lastAG = sqrtf(a.acceleration.x * a.acceleration.x + a.acceleration.y * a.acceleration.y +
                 a.acceleration.z * a.acceleration.z) / SENSORS_GRAVITY_STANDARD;
  lastDps = sqrtf(g.gyro.x * g.gyro.x + g.gyro.y * g.gyro.y + g.gyro.z * g.gyro.z) * 57.2958f;
  if (audioBusy() || (int32_t)(now - quietUntilMs) < 0) return;   // our own sound / motor, not the victim
  if (fabsf(lastAG - restG) > MOVE_G || lastDps > MOVE_DPS) lastMoveMs = now ? now : 1;
}

static bool movedRecently(uint32_t now) { return lastMoveMs != 0 && now - lastMoveMs <= MOTION_WINDOW_MS; }

// ---------------- beacon ----------------
static void setSos(bool on, uint32_t now) {
  sos = on;
  if (on) { sosStartMs = now; nextTxMs = now + 500; buzz(1, 400); }
  else buzz(2, 120);
  Serial.printf("BTN SOS %s\n", on ? "on" : "off");
}

static void transmit(uint32_t now) {
  hac1::Fields f;
  f.id = TAG_ID;
  f.floorKnown = false;
  f.minutes = sos ? (int)((now - sosStartMs) / 60000UL) : 0;
  f.motion = movedRecently(now);
  f.status = tagStatus;
  f.people = 1;
  f.battery = 3;
  f.hops = 0;
  f.knock = false;
  hac1::pack(f, frameBytes);
  int band = burst ? 1 : hac1::bandFor(txCount, TAG_ID);
  digitalWrite(LED_BUILTIN, LOW);            // user LED on (active low) while we play
  audioPlay(frameBytes, band);
  Serial.printf("TX id=%04X band=%d k=%lu bytes=%02X%02X%02X%02X%02X%02X min=%d motion=%d %s\n", TAG_ID, band,
                (unsigned long)txCount, frameBytes[0], frameBytes[1], frameBytes[2], frameBytes[3], frameBytes[4],
                frameBytes[5], f.minutes, f.motion ? 1 : 0, statusName(tagStatus));
  txCount++;
}

static void help() {
  Serial.println("s = SOS on/off, t = one frame now, b = burst mode on/off, 0..3 = status, m = motion, h = help");
  Serial.printf("SOS %s, burst %s, status %s, id %04X\n", sos ? "on" : "off", burst ? "on" : "off",
                statusName(tagStatus), TAG_ID);
}

// ---------------- setup / loop ----------------
void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2000) delay(10);   // USB serial: don't wait forever on a power bank
  pinMode(PIN_VIB, OUTPUT); digitalWrite(PIN_VIB, LOW);
  pinMode(PIN_BTN, INPUT_PULLDOWN);
  pinMode(PIN_TOUCH, INPUT_PULLDOWN);
  pinMode(LED_BUILTIN, OUTPUT); digitalWrite(LED_BUILTIN, HIGH);
  Serial.printf("\nHeimdall Tag A (M2), id %04X, audio %s\n", TAG_ID, AUDIO_OUT == AUDIO_PWM ? "PWM D0" : "I2S D8-D10");
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  imuBegin();
  if (!audioBegin()) Serial.println("AUDIO INIT FAILED");
  if (AUTOSTART_SOS) setSos(true, millis());
  help();
}

void loop() {
  uint32_t now = millis();
  imuTick(now);
  buzzTick(now);

  bool moving = movedRecently(now);
  if (moving != movingReported) {
    movingReported = moving;
    if (moving) Serial.println("MOVE");
    else Serial.printf("STILL %lus\n", (unsigned long)(MOTION_WINDOW_MS / 1000));
  }

  if (pressed(sosBtn, now)) setSos(!sos, now);
  // Ignore the touch pad while our own frame plays and QUIET_AFTER_MS after it: on Tag A the speaker
  // drive made the TTP223 fire once per frame (status cycled by itself). Found on hardware, M2.
  if (pressed(touchBtn, now) && !audioBusy() && (int32_t)(now - quietUntilMs) >= 0) {
    tagStatus = (tagStatus + 1) & 3;     // ok -> injured -> critical -> no_response -> ok
    buzz(tagStatus == hac1::NO_RESPONSE ? 1 : tagStatus, tagStatus == hac1::NO_RESPONSE ? 600 : 150);
    Serial.printf("BTN STATUS %s\n", statusName(tagStatus));
  }

  if (!audioBusy()) {
    digitalWrite(LED_BUILTIN, HIGH);
    if (sos && (int32_t)(now - nextTxMs) >= 0) {
      transmit(now);
      quietUntilMs = now + 2130 + QUIET_AFTER_MS;
      uint32_t period = burst ? BURST_PERIOD_MS : PERIOD_MS;
      int32_t jitter = burst ? 0 : (int32_t)random(-(long)JITTER_MS, (long)JITTER_MS + 1);
      nextTxMs = now + period + jitter;
    }
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == 's') setSos(!sos, now);
    else if (c == 't' && !audioBusy()) { transmit(now); quietUntilMs = now + 2130 + QUIET_AFTER_MS; }
    else if (c == 'b') { burst = !burst; Serial.printf("burst %s\n", burst ? "on (3 s, band 1)" : "off"); }
    else if (c >= '0' && c <= '3') { tagStatus = c - '0'; Serial.printf("BTN STATUS %s\n", statusName(tagStatus)); }
    else if (c == 'm') Serial.printf("|a| %.3f g (rest %.3f), %.1f deg/s, moved %s\n", lastAG, restG, lastDps,
                                     movedRecently(now) ? "yes" : "no");
    else if (c == 'h') help();
  }
}
