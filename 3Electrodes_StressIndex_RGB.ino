#include <arduinoFFT.h>
#include <Adafruit_NeoPixel.h>

// ================= FFT CONFIG =================
const uint16_t SAMPLES = 128;               // Potencia de 2
const double SAMPLING_FREQUENCY = 250.0;    // Hz aprox

double vReal[SAMPLES];
double vImag[SAMPLES];

ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal, vImag, SAMPLES, SAMPLING_FREQUENCY);

// ================= EEG CHANNELS =================
// 3 señales: por ejemplo 3 electrodos/sensores en A0, A1, A2
const uint8_t EEG_PINS[3] = {A0, A1, A2};

// ================= LED STRIP CONFIG =================
#define LED_PIN   6      // Pin de datos de la tira (DAT)
#define NUM_LEDS  30     // CAMBIA esto al número de LEDs reales

// Probado: tu tira funciona bien como NEO_GRB
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// Estados de la lámpara:
// 0 = estrés (naranja), 1 = neutro (verde claro), 2 = relajado (violeta)
int ledState = -1;

// Color actual y objetivo (para fade suave)
int currentR = 0, currentG = 0, currentB = 0;
int targetR  = 0, targetG  = 0, targetB  = 0;

// Paso de transición: más pequeño = cambio más lento
const int FADE_STEP = 5;   // prueba 1–3 para lámpara muy suave

// Umbrales del índice de relajación (ajustables)
// RI_avg = alpha / (theta + alpha + beta)
const double TH_STRESS  = 0.30;   // RI_avg < 0.45 → estrés
const double TH_RELAXED = 0.80;   // RI_avg > 0.70 → relajado

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

  strip.begin();
  // strip.setBrightness(150);  // opcional: bajar brillo global (0–255)
  strip.show(); // Apagar la tira al inicio

  setColorInstant(0, 0, 0);

  Serial.println("EEG demo 3 canales + tira LED (naranja / verde claro / violeta).");
}

// ================= LOOP =================
void loop() {
  // 1) Calcular índice de relajación para cada canal
  double ri1 = computeRelaxIndex(EEG_PINS[0]);
  double ri2 = computeRelaxIndex(EEG_PINS[1]);
  double ri3 = computeRelaxIndex(EEG_PINS[2]);

  // 2) Promedio de los 3
  double ri_avg = (ri1 + ri2 + ri3) / 3.0;

  // 3) Decidir estado global y color objetivo
  int newState;
  if (ri_avg < TH_STRESS) {
    // Estrés -> NARANJA
    newState = 0;
    setTargetColor(255, 40, 0);          // naranja
  } else if (ri_avg > TH_RELAXED) {
    // Relajado -> VIOLETA
    newState = 2;
    setTargetColor(220, 0, 100);         // violeta/magenta
  } else {
    // Neutro -> VERDE CLARO
    newState = 1;
    setTargetColor(120, 255, 120);       // verde pastel
  }

  // 4) Mensaje en Serial solo si cambió el estado
  if (newState != ledState) {
    ledState = newState;
    if (ledState == 0) {
      Serial.println("ESTADO GLOBAL: ESTRES (naranja)");
    } else if (ledState == 1) {
      Serial.println("ESTADO GLOBAL: NEUTRO (verde claro)");
    } else if (ledState == 2) {
      Serial.println("ESTADO GLOBAL: RELAJADO (violeta)");
    }
  }

  // 5) Actualizar tira LED con transición suave
  updateLedSmooth();

  // 6) Salida para Serial Plotter: índice de relajación promedio
  Serial.print("RI_avg:");
  Serial.println(ri_avg, 4);

  // Si quieres depurar por canal:
  /*
  Serial.print(" RI1:"); Serial.print(ri1, 4);
  Serial.print(" RI2:"); Serial.print(ri2, 4);
  Serial.print(" RI3:"); Serial.println(ri3, 4);
  */

  delay(60);   // Ajusta también esto para cambiar velocidad del fade
}

// ================= FUNCIONES EEG =================

// Calcula índice de relajación para un canal (un pin analógico)
double computeRelaxIndex(uint8_t eegPin) {
  acquireSamples(eegPin);
  processFFT();

  double thetaPower = bandPower(4.0, 7.0);
  double alphaPower = bandPower(8.0, 12.0);
  double betaPower  = bandPower(13.0, 30.0);

  double total = thetaPower + alphaPower + betaPower + 1e-9;
  double ri = alphaPower / total;

  return ri;
}

// Adquirir SAMPLES desde un pin analógico
void acquireSamples(uint8_t pin) {
  unsigned long sampling_period_us = (unsigned long)(1000000.0 / SAMPLING_FREQUENCY);
  unsigned long microseconds;

  // Calcular offset DC
  long sum = 0;
  const int DC_SAMPLES = 50;
  for (int i = 0; i < DC_SAMPLES; i++) {
    sum += analogRead(pin);
    delay(2);
  }
  double dcOffset = (double)sum / DC_SAMPLES;

  for (uint16_t i = 0; i < SAMPLES; i++) {
    microseconds = micros();

    int raw = analogRead(pin);
    vReal[i] = (double)raw - dcOffset;
    vImag[i] = 0.0;

    while ((micros() - microseconds) < sampling_period_us) {
      // espera ocupada para mantener frecuencia de muestreo
    }
  }
}

// FFT sobre vReal / vImag
void processFFT() {
  FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD);
  FFT.compute(FFT_FORWARD);
  FFT.complexToMagnitude();
}

// Potencia en [fLow, fHigh]
double bandPower(double fLow, double fHigh) {
  double power = 0;
  double binWidth = SAMPLING_FREQUENCY / SAMPLES;

  uint16_t iLow  = (uint16_t)round(fLow  / binWidth);
  uint16_t iHigh = (uint16_t)round(fHigh / binWidth);

  if (iHigh >= SAMPLES / 2) {
    iHigh = (SAMPLES / 2) - 1;
  }

  for (uint16_t i = iLow; i <= iHigh; i++) {
    double mag = vReal[i];
    power += mag * mag;
  }

  return power;
}

// ================= CONTROL TIRA LED =================

// Definir color objetivo (no instantáneo)
void setTargetColor(int r, int g, int b) {
  targetR = constrain(r, 0, 255);
  targetG = constrain(g, 0, 255);
  targetB = constrain(b, 0, 255);
}

// Actualizar color actual hacia el objetivo y mostrar en la tira
void updateLedSmooth() {
  // R
  if (currentR < targetR) {
    currentR += FADE_STEP;
    if (currentR > targetR) currentR = targetR;
  } else if (currentR > targetR) {
    currentR -= FADE_STEP;
    if (currentR < targetR) currentR = targetR;
  }

  // G
  if (currentG < targetG) {
    currentG += FADE_STEP;
    if (currentG > targetG) currentG = targetG;
  } else if (currentG > targetG) {
    currentG -= FADE_STEP;
    if (currentG < targetG) currentG = targetG;
  }

  // B
  if (currentB < targetB) {
    currentB += FADE_STEP;
    if (currentB > targetB) currentB = targetB;
  } else if (currentB > targetB) {
    currentB -= FADE_STEP;
    if (currentB < targetB) currentB = targetB;
  }

  // Aplicar el color a toda la tira
  uint32_t color = strip.Color(currentR, currentG, currentB);
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}

// Fijar color sin fade (solo al inicio)
void setColorInstant(uint8_t r, uint8_t g, uint8_t b) {
  currentR = r;
  currentG = g;
  currentB = b;
  targetR  = r;
  targetG  = g;
  targetB  = b;

  uint32_t color = strip.Color(r, g, b);
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, color);
  }
  strip.show();
}
