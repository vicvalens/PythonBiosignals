const int SENSOR_PIN = A0;
const int LED_PIN    = 13;

const unsigned long PERIOD_MS = 10; // ~100 Hz
unsigned long t0 = 0;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(115200); // debe coincidir con Python
  delay(200);
}

void loop() {
  unsigned long now = millis();

  // 1) enviar crudo de A0 a ~100 Hz
  if (now - t0 >= PERIOD_MS) {
    t0 = now;
    int v = analogRead(SENSOR_PIN);   // 0..1023
    Serial.println(v);
  }

  // 2) leer comando (1/0) desde Python
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '1') {
      digitalWrite(LED_PIN, HIGH);
    } else if (c == '0') {
      digitalWrite(LED_PIN, LOW);
    }
  }
}
