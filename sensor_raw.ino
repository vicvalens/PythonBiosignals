const int SENSOR_PIN = A0;
const unsigned long PERIOD_MS = 10;
unsigned long t0 = 0;

void setup() {
  Serial.begin(115200);
}

void loop() {
  unsigned long t = millis();
  if (t - t0 >= PERIOD_MS) {
    t0 = t;
    int v = analogRead(SENSOR_PIN);
    Serial.println(v);
  }
}
