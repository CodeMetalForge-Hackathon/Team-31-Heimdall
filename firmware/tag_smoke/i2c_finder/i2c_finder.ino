// I2C pin finder: reports pin levels and tries every SDA/SCL pin pair
#include <Wire.h>
const int pins[] = {D0, D1, D2, D3, D4, D5, D8, D9, D10};
const char *names[] = {"D0", "D1", "D2", "D3", "D4", "D5", "D8", "D9", "D10"};
const int N = 9;
const uint8_t addrs[] = {0x30, 0x6B, 0x77};

void setup() {
  Serial.begin(115200);
  delay(2000);
}

void loop() {
  Serial.println("\n--- pin levels (1 = pulled up by a sensor board) ---");
  for (int i = 0; i < N; i++) {
    pinMode(pins[i], INPUT_PULLDOWN);
    delay(2);
    Serial.printf("%s=%d  ", names[i], digitalRead(pins[i]));
  }
  Serial.println("\n--- trying every SDA/SCL pair ---");
  int hits = 0;
  for (int a = 0; a < N; a++) {
    for (int b = 0; b < N; b++) {
      if (a == b) continue;
      if (!Wire.begin(pins[a], pins[b], 100000)) continue;
      Wire.setTimeOut(5);
      for (uint8_t ad : addrs) {
        Wire.beginTransmission(ad);
        if (Wire.endTransmission() == 0) {
          Serial.printf("FOUND 0x%02X with SDA=%s SCL=%s\n", ad, names[a], names[b]);
          hits++;
        }
      }
      Wire.end();
    }
  }
  Serial.printf("--- done, %d hit(s). Repeating in 5 s ---\n", hits);
  delay(5000);
}
