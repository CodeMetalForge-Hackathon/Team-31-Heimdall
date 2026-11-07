// Heimdall station: pan-tilt servos + knock sensor.  Protocol: docs/SPEC.md section 4.
// Pi -> board:  PING | P <pan> <tilt> | R <ch> <raw> | C <panCenterRaw> <tiltLevelRaw> | ?
// board -> Pi:  HELLO HEIMDALL-SERVO 1 | PONG | OK ... | STATE ... | KNOCK <count> | ERR <line>
#include <Servo.h>

const uint8_t PAN_PIN = 5;
const uint8_t TILT_PIN = 6;
const uint8_t KNOCK_PIN = 2;

// Calibration: raw servo angle (0..180) where pan points at the front arrow and tilt is level.
// Find them with the R command, then edit these two numbers and re-upload.
int panCenter = 35;
int tiltLevel = 90;
// Flip to -1 if a positive command turns the wrong way (pan + = RIGHT, tilt + = UP).
const int PAN_DIR = 1;
const int TILT_DIR = 1;

const int PAN_MIN = -90, PAN_MAX = 90;
const int TILT_MIN = -30, TILT_MAX = 60;
const unsigned long STEP_MS = 15;   // smooth motion: update every 15 ms
const float STEP_DEG = 2.0;         // max 2 degrees per update (~130 deg/s)

const unsigned long KNOCK_LOCKOUT_MS = 120;  // hits closer than this count as one
const unsigned long KNOCK_GROUP_MS = 1500;   // group ends after 1.5 s of quiet

Servo panServo, tiltServo;
float panCur = 0, tiltCur = 0;
int panTgt = 0, tiltTgt = 0;
bool rawMode = false;
unsigned long lastStep = 0;

int idleLevel = HIGH;
unsigned long lastHit = 0;
int hitCount = 0;

char buf[40];
uint8_t bufLen = 0;

int rawPan(float d)  { return constrain(panCenter + PAN_DIR * (int)lround(d), 0, 180); }
int rawTilt(float d) { return constrain(tiltLevel + TILT_DIR * (int)lround(d), 0, 180); }

float approach(float cur, float tgt) {
  float d = tgt - cur;
  if (d > STEP_DEG) d = STEP_DEG;
  if (d < -STEP_DEG) d = -STEP_DEG;
  return cur + d;
}

void handleLine(char *s) {
  while (*s == ' ') s++;
  if (*s == 0) return;
  int a, b;
  if (strcmp(s, "PING") == 0) { Serial.println(F("PONG")); return; }
  if (s[0] == '?') {
    Serial.print(F("STATE P ")); Serial.print((int)lround(panCur));
    Serial.print(F(" T ")); Serial.print((int)lround(tiltCur));
    Serial.print(F(" C ")); Serial.print(panCenter); Serial.print(' '); Serial.print(tiltLevel);
    Serial.print(F(" IDLE ")); Serial.println(idleLevel == HIGH ? 1 : 0);
    return;
  }
  if (s[0] == 'P' && sscanf(s + 1, "%d %d", &a, &b) == 2) {
    rawMode = false;
    panTgt = constrain(a, PAN_MIN, PAN_MAX);
    tiltTgt = constrain(b, TILT_MIN, TILT_MAX);
    Serial.print(F("OK P ")); Serial.print(panTgt); Serial.print(F(" T ")); Serial.println(tiltTgt);
    return;
  }
  if (s[0] == 'R' && sscanf(s + 1, "%d %d", &a, &b) == 2) {
    rawMode = true;
    b = constrain(b, 0, 180);
    if (a == 0) panServo.write(b); else tiltServo.write(b);
    Serial.print(F("OK R ")); Serial.print(a); Serial.print(' '); Serial.println(b);
    return;
  }
  if (s[0] == 'C' && sscanf(s + 1, "%d %d", &a, &b) == 2) {
    panCenter = constrain(a, 0, 180);
    tiltLevel = constrain(b, 0, 180);
    Serial.print(F("OK C ")); Serial.print(panCenter); Serial.print(' '); Serial.println(tiltLevel);
    return;
  }
  Serial.print(F("ERR ")); Serial.println(s);
}

void setup() {
  Serial.begin(115200);
  pinMode(KNOCK_PIN, INPUT);
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  panServo.write(rawPan(0));
  tiltServo.write(rawTilt(0));
  // Learn the knock sensor's resting level (some SW-420 boards rest HIGH, some LOW).
  // Keep the sensor still for the first 0.3 s after power-up.
  int highs = 0;
  for (int i = 0; i < 300; i++) { highs += digitalRead(KNOCK_PIN); delay(1); }
  idleLevel = (highs > 150) ? HIGH : LOW;
  Serial.println(F("HELLO HEIMDALL-SERVO 1"));
}

void loop() {
  // 1. read command lines
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { buf[bufLen] = 0; handleLine(buf); bufLen = 0; }
    else if (bufLen < sizeof(buf) - 1) buf[bufLen++] = c;
  }
  unsigned long now = millis();
  // 2. smooth servo motion toward the target
  if (!rawMode && now - lastStep >= STEP_MS) {
    lastStep = now;
    panCur = approach(panCur, panTgt);
    tiltCur = approach(tiltCur, tiltTgt);
    panServo.write(rawPan(panCur));
    tiltServo.write(rawTilt(tiltCur));
  }
  // 3. knock detection: count separate hits, report the group when it ends
  if (digitalRead(KNOCK_PIN) != idleLevel && now - lastHit > KNOCK_LOCKOUT_MS) {
    lastHit = now;
    hitCount++;
  }
  if (hitCount > 0 && now - lastHit > KNOCK_GROUP_MS) {
    Serial.print(F("KNOCK ")); Serial.println(hitCount);
    hitCount = 0;
  }
}
