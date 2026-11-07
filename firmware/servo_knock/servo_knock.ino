// Heimdall E1: Seeeduino Uno servo + SW-420 knock controller.
// Serial 115200, newline. Servos: D5 pan, D6 tilt. Knock SIG: D2.
// Servo power is external 5 V; share GND with the Seeeduino.

#include <Servo.h>

const int PIN_PAN = 5;
const int PIN_TILT = 6;
const int PIN_KNOCK = 2;

const int PAN_MIN_DEG = -90;
const int PAN_MAX_DEG = 90;
const int TILT_MIN_DEG = -30;
const int TILT_MAX_DEG = 60;

const unsigned long SLEW_MS = 12;
const unsigned long KNOCK_SEP_MS = 120;
const unsigned long KNOCK_GROUP_MS = 1500;

Servo panServo;
Servo tiltServo;

int panCenterRaw = 90;
int tiltLevelRaw = 90;
int panDeg = 0;
int tiltDeg = 0;
int panRaw = 90;
int tiltRaw = 90;
int targetPanRaw = 90;
int targetTiltRaw = 90;
unsigned long lastSlewMs = 0;

int knockCount = 0;
unsigned long lastKnockMs = 0;
int lastKnockLevel = LOW;

String lineBuf;

int clampi(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

int panToRaw(int deg) {
  return clampi(panCenterRaw + deg, 0, 180);
}

int tiltToRaw(int deg) {
  return clampi(tiltLevelRaw + deg, 0, 180);
}

void applyImmediate(int ch, int raw) {
  raw = clampi(raw, 0, 180);
  if (ch == 0) {
    panRaw = raw;
    targetPanRaw = raw;
    panDeg = panRaw - panCenterRaw;
    panServo.write(panRaw);
  } else {
    tiltRaw = raw;
    targetTiltRaw = raw;
    tiltDeg = tiltRaw - tiltLevelRaw;
    tiltServo.write(tiltRaw);
  }
}

void handleLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line == "PING") {
    Serial.println("PONG");
    return;
  }

  if (line == "?") {
    int idle = (panRaw == targetPanRaw && tiltRaw == targetTiltRaw) ? 1 : 0;
    Serial.print("STATE P ");
    Serial.print(panDeg);
    Serial.print(" T ");
    Serial.print(tiltDeg);
    Serial.print(" C ");
    Serial.print(panCenterRaw);
    Serial.print(" ");
    Serial.print(tiltLevelRaw);
    Serial.print(" IDLE ");
    Serial.println(idle);
    return;
  }

  int a = 0;
  int b = 0;
  if (sscanf(line.c_str(), "P %d %d", &a, &b) == 2) {
    panDeg = clampi(a, PAN_MIN_DEG, PAN_MAX_DEG);
    tiltDeg = clampi(b, TILT_MIN_DEG, TILT_MAX_DEG);
    targetPanRaw = panToRaw(panDeg);
    targetTiltRaw = tiltToRaw(tiltDeg);
    Serial.print("OK P ");
    Serial.print(panDeg);
    Serial.print(" T ");
    Serial.println(tiltDeg);
    return;
  }

  if (sscanf(line.c_str(), "R %d %d", &a, &b) == 2) {
    if (a != 0 && a != 1) {
      Serial.println("ERR R");
      return;
    }
    b = clampi(b, 0, 180);
    applyImmediate(a, b);
    Serial.print("OK R ");
    Serial.print(a);
    Serial.print(" ");
    Serial.println(b);
    return;
  }

  if (sscanf(line.c_str(), "C %d %d", &a, &b) == 2) {
    panCenterRaw = clampi(a, 0, 180);
    tiltLevelRaw = clampi(b, 0, 180);
    targetPanRaw = panToRaw(panDeg);
    targetTiltRaw = tiltToRaw(tiltDeg);
    Serial.print("OK C ");
    Serial.print(panCenterRaw);
    Serial.print(" ");
    Serial.println(tiltLevelRaw);
    return;
  }

  Serial.println("ERR");
}

void pollSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineBuf.length() > 0) {
        handleLine(lineBuf);
        lineBuf = "";
      }
    } else {
      lineBuf += c;
      if (lineBuf.length() > 64) {
        lineBuf = "";
      }
    }
  }
}

void slew() {
  unsigned long now = millis();
  if ((now - lastSlewMs) < SLEW_MS) return;
  lastSlewMs = now;
  if (panRaw < targetPanRaw) panRaw++;
  else if (panRaw > targetPanRaw) panRaw--;
  if (tiltRaw < targetTiltRaw) tiltRaw++;
  else if (tiltRaw > targetTiltRaw) tiltRaw--;
  panServo.write(panRaw);
  tiltServo.write(tiltRaw);
}

void pollKnock() {
  int level = digitalRead(PIN_KNOCK);
  unsigned long now = millis();
  if (level == HIGH && lastKnockLevel == LOW) {
    if (knockCount == 0 || (now - lastKnockMs) >= KNOCK_SEP_MS) {
      knockCount++;
      lastKnockMs = now;
    }
  }
  lastKnockLevel = level;
  if (knockCount > 0 && (now - lastKnockMs) >= KNOCK_GROUP_MS) {
    Serial.print("KNOCK ");
    Serial.println(knockCount);
    knockCount = 0;
  }
}

void setup() {
  pinMode(PIN_KNOCK, INPUT);
  panServo.attach(PIN_PAN);
  tiltServo.attach(PIN_TILT);
  panServo.write(panRaw);
  tiltServo.write(tiltRaw);
  Serial.begin(115200);
  while (!Serial) {
    ;
  }
  Serial.println("HELLO HEIMDALL-SERVO 1");
}

void loop() {
  pollSerial();
  slew();
  pollKnock();
}
