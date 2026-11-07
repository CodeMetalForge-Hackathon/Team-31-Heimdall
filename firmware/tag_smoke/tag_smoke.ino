// Heimdall Tag A - smoke test (M1)
// Board: Seeed XIAO ESP32S3 Plus, Espressif Arduino core 3.x
//
// Wiring (see M1 task):  D0 speaker SIG | D1 button | D2 touch | D3 vib motor
//                        D4 SDA, D5 SCL (IMU 0x6B, MAG 0x30, BME280 0x77)
//                        D6/D7 unused. D8 = I2S PDM clock (method 4 only, leave unconnected).
//
// Serial 115200 commands:
//   a = speaker test A (square tones)
//   b = speaker test B (sampled 1500->6500 Hz sweep)
//   r = record mode (test B x5, 1 s gaps)
//   1..4 = audio method for test B:
//          1 LEDC ledcWrite() in timer ISR (default)
//          2 IDF ledc_set_duty()+ledc_update_duty() in timer ISR
//          3 sigma-delta (sigmaDeltaWrite) in timer ISR
//          4 I2S PDM TX on D0 (DMA, no ISR)
//   s = rescan I2C, h = help

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <Adafruit_ISM330DHCX.h>
#include <Adafruit_BME280.h>
#include <driver/ledc.h>
#include <ESP_I2S.h>

// ---------------- pins ----------------
static const uint8_t PIN_SPK   = D0;
static const uint8_t PIN_BTN   = D1;
static const uint8_t PIN_TOUCH = D2;
static const uint8_t PIN_VIB   = D3;
static const uint8_t PIN_PDM_CLK = D8;   // only used by audio method 4, not connected

// ---------------- chirp ----------------
static const uint32_t FS        = 16000;    // samples/s
static const uint32_t N_SAMPLES = 16000;    // 1.0 s
static const float    F0 = 1500.0f, F1 = 6500.0f;
static const float    AMP = 0.8f;
static const float    FADE_S = 0.005f;      // 5 ms fade in/out
static uint8_t chirp[N_SAMPLES];            // 8-bit unsigned, 128 = silence

static const uint8_t LEDC_CH = 0;           // fixed channel so IDF calls know it
static uint32_t pwmFreq = 0;                // actual PWM carrier used for test B

// ---------------- playback state ----------------
enum AudioMethod : uint8_t { M_LEDC = 1, M_IDF = 2, M_SDM = 3, M_PDM = 4 };
static AudioMethod audioMethod = M_LEDC;
static hw_timer_t *audioTimer = nullptr;
static volatile uint32_t playIdx = 0;
static volatile bool playDone = true;
static volatile uint8_t isrMethod = M_LEDC;

// ---------------- sensors ----------------
Adafruit_ISM330DHCX imu;
Adafruit_BME280 bme;
static bool imuOk = false, bmeOk = false;
static const float SEA_LEVEL_HPA = 1013.25f;
static const float SHOCK_G = 2.5f;

// ---------------- buttons ----------------
struct Debounced {
  uint8_t pin;
  bool stable;      // debounced level
  bool lastRaw;
  uint32_t tChange;
};
static Debounced btn   = {PIN_BTN, false, false, 0};
static Debounced touch = {PIN_TOUCH, false, false, 0};
static const uint32_t DEBOUNCE_MS = 30;

// returns true on a debounced rising edge (press)
static bool pressed(Debounced &d) {
  bool raw = digitalRead(d.pin);
  uint32_t now = millis();
  if (raw != d.lastRaw) { d.lastRaw = raw; d.tChange = now; }
  if ((now - d.tChange) >= DEBOUNCE_MS && raw != d.stable) {
    d.stable = raw;
    return raw;   // HIGH = pressed
  }
  return false;
}

// ---------------- helpers ----------------
static void buzz(uint32_t ms) {
  digitalWrite(PIN_VIB, HIGH);
  delay(ms);
  digitalWrite(PIN_VIB, LOW);
}

static void i2cScan() {
  Serial.println("I2C scan (SDA=D4, SCL=D5):");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  found 0x%02X%s\n", a,
                    a == 0x30 ? " (MMC5983MA mag)" :
                    a == 0x6B ? " (ISM330DHCX IMU)" :
                    a == 0x77 ? " (BME280)" : "");
      n++;
    }
  }
  Serial.printf("  %d device(s). Expected 0x30, 0x6B, 0x77\n", n);
}

static void buildChirp() {
  const float T = (float)N_SAMPLES / FS;
  const float k = (F1 - F0) / T;              // Hz per second
  const uint32_t fadeN = (uint32_t)(FADE_S * FS);
  for (uint32_t i = 0; i < N_SAMPLES; i++) {
    float t = (float)i / FS;
    float phase = 2.0f * (float)M_PI * (F0 * t + 0.5f * k * t * t);
    float env = 1.0f;
    if (i < fadeN) env = (float)i / fadeN;
    else if (i >= N_SAMPLES - fadeN) env = (float)(N_SAMPLES - 1 - i) / fadeN;
    float s = AMP * env * sinf(phase);        // -0.8..0.8
    int v = (int)lroundf(127.5f + 127.5f * s);
    chirp[i] = (uint8_t)constrain(v, 0, 255);
  }
}

// ---------------- speaker test A: square tones ----------------
static void squareTone(uint32_t freq, uint32_t ms) {
  if (!ledcAttach(PIN_SPK, freq, 8)) { Serial.println("ledcAttach failed"); return; }
  ledcWrite(PIN_SPK, 128);                    // 50 % duty
  delay(ms);
  ledcWrite(PIN_SPK, 0);
  ledcDetach(PIN_SPK);
  pinMode(PIN_SPK, OUTPUT);
  digitalWrite(PIN_SPK, LOW);
}

static void speakerTestA() {
  Serial.println("Speaker test A: 2000/3000/4000/6000 Hz, 0.5 s each");
  const uint32_t f[] = {2000, 3000, 4000, 6000};
  for (uint32_t x : f) squareTone(x, 500);
}

// ---------------- speaker test B: sampled chirp ----------------
static void IRAM_ATTR onAudioTimer() {
  uint32_t i = playIdx;
  if (i >= N_SAMPLES) { playDone = true; return; }
  uint8_t s = chirp[i];
  switch (isrMethod) {
    case M_LEDC: ledcWrite(PIN_SPK, s); break;
    case M_IDF:
      ledc_set_duty(LEDC_LOW_SPEED_MODE, (ledc_channel_t)LEDC_CH, s);
      ledc_update_duty(LEDC_LOW_SPEED_MODE, (ledc_channel_t)LEDC_CH);
      break;
    case M_SDM: sigmaDeltaWrite(PIN_SPK, s); break;
  }
  playIdx = i + 1;
}

static bool attachHighPwm() {
  // On the XIAO ESP32S3 (core 3.3.x) LEDC runs from the 40 MHz clock, so the
  // highest 8-bit carrier is 40 MHz / 256 = 156.25 kHz (312.5/250 kHz fail).
  const uint32_t tries[] = {156250, 78125};
  for (uint32_t f : tries) {
    if (ledcAttachChannel(PIN_SPK, f, 8, LEDC_CH)) { pwmFreq = f; return true; }
  }
  return false;
}

static void playChirpTimer(AudioMethod m) {
  if (m == M_SDM) {
    if (!sigmaDeltaAttach(PIN_SPK, 1000000)) { Serial.println("sigmaDeltaAttach failed"); return; }
    sigmaDeltaWrite(PIN_SPK, 128);
  } else {
    if (!attachHighPwm()) { Serial.println("LEDC high-freq attach failed"); return; }
    ledcWrite(PIN_SPK, 128);
  }
  isrMethod = m;
  playIdx = 0;
  playDone = false;

  audioTimer = timerBegin(FS);                     // timer ticks at 16 kHz
  timerAttachInterrupt(audioTimer, &onAudioTimer);
  uint32_t t0 = micros();
  timerAlarm(audioTimer, 1, true, 0);              // fire every tick, forever

  while (!playDone && (micros() - t0) < 2000000UL) delay(1);
  uint32_t dt = micros() - t0;
  timerEnd(audioTimer);
  audioTimer = nullptr;

  if (m == M_SDM) { sigmaDeltaWrite(PIN_SPK, 128); sigmaDeltaDetach(PIN_SPK); }
  else { ledcWrite(PIN_SPK, 0); ledcDetach(PIN_SPK); }
  pinMode(PIN_SPK, OUTPUT);
  digitalWrite(PIN_SPK, LOW);

  Serial.printf("  played %lu/%lu samples in %lu us (expect ~1000000)%s\n",
                (unsigned long)playIdx, (unsigned long)N_SAMPLES, (unsigned long)dt,
                playDone ? "" : "  <-- TIMEOUT");
  if (m != M_SDM) Serial.printf("  PWM carrier %lu Hz\n", (unsigned long)pwmFreq);
}

static void playChirpPdm() {
  I2SClass i2s;
  i2s.setPinsPdmTx(PIN_PDM_CLK, PIN_SPK);
  if (!i2s.begin(I2S_MODE_PDM_TX, FS, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S PDM begin failed");
    return;
  }
  uint32_t t0 = micros();
  int16_t buf[256];
  for (uint32_t i = 0; i < N_SAMPLES; i += 256) {
    uint32_t n = min<uint32_t>(256, N_SAMPLES - i);
    for (uint32_t j = 0; j < n; j++) buf[j] = ((int16_t)chirp[i + j] - 128) << 8;
    i2s.write((uint8_t *)buf, n * sizeof(int16_t));
  }
  memset(buf, 0, sizeof(buf));                       // flush DMA with silence
  for (int k = 0; k < 8; k++) i2s.write((uint8_t *)buf, sizeof(buf));
  uint32_t dt = micros() - t0;
  i2s.end();
  pinMode(PIN_SPK, OUTPUT);
  digitalWrite(PIN_SPK, LOW);
  Serial.printf("  I2S PDM wrote %lu samples in %lu us (incl. ~128 ms silence)\n",
                (unsigned long)N_SAMPLES, (unsigned long)dt);
}

static const char *methodName(AudioMethod m) {
  switch (m) {
    case M_LEDC: return "LEDC+ISR (ledcWrite)";
    case M_IDF:  return "IDF LEDC (ledc_set_duty/update) in ISR";
    case M_SDM:  return "sigma-delta in ISR";
    case M_PDM:  return "I2S PDM TX";
  }
  return "?";
}

static void speakerTestB() {
  Serial.printf("Speaker test B: 1.0 s sweep %.0f->%.0f Hz @ %lu sps, method %d = %s\n",
                F0, F1, (unsigned long)FS, audioMethod, methodName(audioMethod));
  if (audioMethod == M_PDM) playChirpPdm();
  else playChirpTimer(audioMethod);
}

static void recordMode() {
  Serial.println("RECORD MODE: test B x5, 1 s gaps. Start recording now.");
  delay(1000);
  for (int i = 0; i < 5; i++) {
    Serial.printf(" chirp %d/5\n", i + 1);
    speakerTestB();
    delay(1000);
  }
  Serial.println("RECORD MODE done.");
}

static void help() {
  Serial.println("Commands: a=test A, b=test B, r=record x5, 1..4=audio method, s=I2C scan, h=help");
  Serial.printf("Current audio method: %d = %s\n", audioMethod, methodName(audioMethod));
}

// ---------------- setup ----------------
void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);   // wait for USB CDC, max 3 s

  pinMode(PIN_SPK, OUTPUT);   digitalWrite(PIN_SPK, LOW);
  pinMode(PIN_VIB, OUTPUT);   digitalWrite(PIN_VIB, LOW);
  pinMode(PIN_BTN, INPUT_PULLDOWN);
  pinMode(PIN_TOUCH, INPUT_PULLDOWN);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);                     // XIAO user LED is active-low: off

  Serial.println();
  Serial.println("==========================================");
  Serial.println(" Heimdall Tag A - smoke test (M1)");
  Serial.printf(" Core %d.%d.%d, chip %s rev %d, %lu MHz\n",
                ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
                ESP.getChipModel(), ESP.getChipRevision(), (unsigned long)ESP.getCpuFreqMHz());
  Serial.println("==========================================");

  // 1. I2C scan
  Wire.begin();               // XIAO default SDA=D4, SCL=D5
  Wire.setClock(400000);
  i2cScan();

  // 2. IMU
  imuOk = imu.begin_I2C(0x6B, &Wire);
  if (imuOk) {
    imu.setAccelRange(LSM6DS_ACCEL_RANGE_16_G);
    imu.setAccelDataRate(LSM6DS_RATE_416_HZ);
    Serial.println("IMU ISM330DHCX @0x6B OK (+-16 g, 416 Hz)");
  } else {
    Serial.println("IMU ISM330DHCX @0x6B NOT FOUND");
  }

  // 3. BME280
  bmeOk = bme.begin(0x77, &Wire);
  if (bmeOk) {
    bme.setSampling(Adafruit_BME280::MODE_NORMAL,
                    Adafruit_BME280::SAMPLING_X2,    // temp
                    Adafruit_BME280::SAMPLING_X16,   // pressure
                    Adafruit_BME280::SAMPLING_X1,    // humidity
                    Adafruit_BME280::FILTER_X16,
                    Adafruit_BME280::STANDBY_MS_0_5);
    delay(100);
    Serial.printf("BME280 @0x77 OK: %.2f hPa, alt %.2f m\n",
                  bme.readPressure() / 100.0f, bme.readAltitude(SEA_LEVEL_HPA));
  } else {
    Serial.println("BME280 @0x77 NOT FOUND");
  }

  // precompute chirp
  buildChirp();

  // 4. speaker test A
  speakerTestA();
  delay(300);

  // 5. speaker test B
  speakerTestB();

  // 6. LED + motor
  digitalWrite(LED_BUILTIN, LOW);
  buzz(200);
  digitalWrite(LED_BUILTIN, HIGH);

  help();
  Serial.println("Loop: ax ay az (g) | |a| (g) | hPa | alt m | btn touch");
}

// ---------------- loop ----------------
static uint32_t tPrint = 0, tShock = 0, tImu = 0;
static float ax = 0, ay = 0, az = 0, amag = 0, amagPeak = 0;

void loop() {
  uint32_t now = millis();

  // IMU at ~200 Hz so short taps are not missed between 200 ms prints
  if (imuOk && now - tImu >= 5) {
    tImu = now;
    sensors_event_t a, g, t;
    imu.getEvent(&a, &g, &t);
    ax = a.acceleration.x / SENSORS_GRAVITY_STANDARD;
    ay = a.acceleration.y / SENSORS_GRAVITY_STANDARD;
    az = a.acceleration.z / SENSORS_GRAVITY_STANDARD;
    amag = sqrtf(ax * ax + ay * ay + az * az);
    if (amag > amagPeak) amagPeak = amag;
    if (amag > SHOCK_G && now - tShock >= 1000) {
      tShock = now;
      Serial.printf("SHOCK %.2f g\n", amag);
    }
  }

  // buttons
  if (pressed(btn)) {
    Serial.println("BTN SOS");
    speakerTestB();
    buzz(200);
  }
  if (pressed(touch)) {
    Serial.println("BTN STATUS");
    squareTone(3000, 300);
  }

  // status line
  if (now - tPrint >= 200) {
    tPrint = now;
    float hpa = NAN, alt = NAN;
    if (bmeOk) { hpa = bme.readPressure() / 100.0f; alt = bme.readAltitude(SEA_LEVEL_HPA); }
    Serial.printf("%+6.2f %+6.2f %+6.2f | %5.2f (pk %5.2f) | %7.2f | %7.2f | %d %d\n",
                  ax, ay, az, amag, amagPeak, hpa, alt,
                  digitalRead(PIN_BTN), digitalRead(PIN_TOUCH));
    amagPeak = 0;
  }

  // serial commands
  while (Serial.available()) {
    char c = Serial.read();
    switch (c) {
      case 'a': speakerTestA(); break;
      case 'b': speakerTestB(); break;
      case 'r': recordMode(); break;
      case 's': i2cScan(); break;
      case 'h': help(); break;
      case '1': case '2': case '3': case '4':
        audioMethod = (AudioMethod)(c - '0');
        Serial.printf("Audio method -> %d = %s\n", audioMethod, methodName(audioMethod));
        break;
      default: break;
    }
  }
}
