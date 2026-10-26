/*
  Trigger TTL controlado por Python - Arduino UNO

  Salidas:
    D12 -> Trigger 1
    D10 -> Trigger 2
    D13 -> Buzzer

  Protocolo serial: 9600 baud, comandos terminados en \n

    PING
      Respuesta: PONG

    PULSE,<duracion_D12_us>,<duracion_D10_us>,<buzzer_0_1>,<duracion_buzzer_us>
      Ejemplo: PULSE,10000,5000,1,5000
      Inicia D12 y D10 en el MISMO instante cuando ambos estan habilitados.
      Una duracion de 0 deshabilita ese canal para ese disparo.

    OUT,<pin>,<estado>
      Ejemplo: OUT,12,1
      Control manual para D10 o D12.

    BEEP,<duracion_us>
      Ejemplo: BEEP,100000

    RESET
      Apaga D12, D10 y D13 y cancela pulsos pendientes.

    STATUS
      Devuelve los estados actuales.

  Notas:
  - La salida TTL del Arduino UNO es aproximadamente 0/5 V.
  - La amplitud NO es ajustable por software en un pin digital.
  - micros() tiene resolucion de unos pocos microsegundos en el UNO.
  - Para pulsos extremadamente cortos/precisos se recomienda usar timers de hardware.
*/

#include <Arduino.h>
#include <string.h>
#include <stdlib.h>

const uint8_t PIN_TRIGGER_12 = 12; // PB4
const uint8_t PIN_TRIGGER_10 = 10; // PB2
const uint8_t PIN_BUZZER     = 13; // PB5

bool pulse12Active = false;
bool pulse10Active = false;
bool beepActive = false;
bool beepWhenPulseEnds = false;

uint32_t pulse12EndUs = 0;
uint32_t pulse10EndUs = 0;
uint32_t beepEndUs = 0;
uint32_t pendingBeepDurationUs = 5000;

static inline bool timeReached(uint32_t now, uint32_t target) {
  return (int32_t)(now - target) >= 0;
}

void allOutputsOff() {
  digitalWrite(PIN_TRIGGER_12, LOW);
  digitalWrite(PIN_TRIGGER_10, LOW);
  digitalWrite(PIN_BUZZER, LOW);
  pulse12Active = false;
  pulse10Active = false;
  beepActive = false;
  beepWhenPulseEnds = false;
}

void startBeep(uint32_t durationUs) {
  if (durationUs == 0) return;
  digitalWrite(PIN_BUZZER, HIGH);
  beepActive = true;
  beepEndUs = micros() + durationUs;
}

void startPulse(uint32_t duration12Us,
                uint32_t duration10Us,
                bool enableBuzzer,
                uint32_t buzzerDurationUs) {

  // Cancela cualquier disparo anterior y deja nivel inactivo LOW.
  digitalWrite(PIN_TRIGGER_12, LOW);
  digitalWrite(PIN_TRIGGER_10, LOW);
  pulse12Active = false;
  pulse10Active = false;

  uint32_t now = micros();

  // D10 = PB2 y D12 = PB4. Si ambos van a arrancar, se levantan
  // en una unica operacion sobre PORTB para minimizar el skew.
  uint8_t setMask = 0;
  if (duration12Us > 0) setMask |= _BV(PB4);
  if (duration10Us > 0) setMask |= _BV(PB2);
  PORTB |= setMask;

  if (duration12Us > 0) {
    pulse12Active = true;
    pulse12EndUs = now + duration12Us;
  }

  if (duration10Us > 0) {
    pulse10Active = true;
    pulse10EndUs = now + duration10Us;
  }

  beepWhenPulseEnds = enableBuzzer && (duration12Us > 0 || duration10Us > 0);
  pendingBeepDurationUs = buzzerDurationUs;
}

void sendStatus() {
  Serial.print(F("STATUS,D12="));
  Serial.print(digitalRead(PIN_TRIGGER_12));
  Serial.print(F(",D10="));
  Serial.print(digitalRead(PIN_TRIGGER_10));
  Serial.print(F(",BUZZER="));
  Serial.print(digitalRead(PIN_BUZZER));
  Serial.print(F(",P12_ACTIVE="));
  Serial.print(pulse12Active ? 1 : 0);
  Serial.print(F(",P10_ACTIVE="));
  Serial.println(pulse10Active ? 1 : 0);
}

void processCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line == "PING") {
    Serial.println(F("PONG"));
    return;
  }

  if (line == "RESET") {
    allOutputsOff();
    Serial.println(F("OK,RESET"));
    return;
  }

  if (line == "STATUS") {
    sendStatus();
    return;
  }

  char buffer[96];
  line.toCharArray(buffer, sizeof(buffer));

  char *cmd = strtok(buffer, ",");
  if (!cmd) {
    Serial.println(F("ERR,CMD"));
    return;
  }

  if (strcmp(cmd, "PULSE") == 0) {
    char *s12 = strtok(NULL, ",");
    char *s10 = strtok(NULL, ",");
    char *sbz = strtok(NULL, ",");
    char *sbd = strtok(NULL, ",");

    if (!s12 || !s10 || !sbz || !sbd) {
      Serial.println(F("ERR,PULSE_ARGS"));
      return;
    }

    uint32_t d12 = strtoul(s12, NULL, 10);
    uint32_t d10 = strtoul(s10, NULL, 10);
    bool buzzer = atoi(sbz) != 0;
    uint32_t buzzerUs = strtoul(sbd, NULL, 10);

    startPulse(d12, d10, buzzer, buzzerUs);
    Serial.println(F("OK,PULSE"));
    return;
  }

  if (strcmp(cmd, "OUT") == 0) {
    char *spin = strtok(NULL, ",");
    char *sstate = strtok(NULL, ",");

    if (!spin || !sstate) {
      Serial.println(F("ERR,OUT_ARGS"));
      return;
    }

    int pin = atoi(spin);
    int state = atoi(sstate) ? HIGH : LOW;

    if (pin != PIN_TRIGGER_12 && pin != PIN_TRIGGER_10) {
      Serial.println(F("ERR,OUT_PIN"));
      return;
    }

    digitalWrite(pin, state);
    if (pin == PIN_TRIGGER_12) pulse12Active = false;
    if (pin == PIN_TRIGGER_10) pulse10Active = false;
    Serial.println(F("OK,OUT"));
    return;
  }

  if (strcmp(cmd, "BEEP") == 0) {
    char *sdur = strtok(NULL, ",");
    if (!sdur) {
      Serial.println(F("ERR,BEEP_ARGS"));
      return;
    }

    uint32_t durationUs = strtoul(sdur, NULL, 10);
    startBeep(durationUs);
    Serial.println(F("OK,BEEP"));
    return;
  }

  Serial.println(F("ERR,UNKNOWN_CMD"));
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);

  pinMode(PIN_TRIGGER_12, OUTPUT);
  pinMode(PIN_TRIGGER_10, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  allOutputsOff();

  // Aviso corto de arranque similar al comportamiento original.
  digitalWrite(PIN_BUZZER, HIGH);
  delay(100);
  digitalWrite(PIN_BUZZER, LOW);

  Serial.println(F("READY,TRIGGER_TTL_V1"));
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    processCommand(line);
  }

  uint32_t now = micros();

  // Si ambos terminan en el mismo instante, limpiarlos juntos en PORTB.
  if (pulse12Active && pulse10Active && pulse12EndUs == pulse10EndUs &&
      timeReached(now, pulse12EndUs)) {
    PORTB &= ~(_BV(PB4) | _BV(PB2));
    pulse12Active = false;
    pulse10Active = false;
  } else {
    if (pulse12Active && timeReached(now, pulse12EndUs)) {
      digitalWrite(PIN_TRIGGER_12, LOW);
      pulse12Active = false;
    }
    if (pulse10Active && timeReached(now, pulse10EndUs)) {
      digitalWrite(PIN_TRIGGER_10, LOW);
      pulse10Active = false;
    }
  }

  if (beepActive && timeReached(now, beepEndUs)) {
    digitalWrite(PIN_BUZZER, LOW);
    beepActive = false;
  }

  if (beepWhenPulseEnds && !pulse12Active && !pulse10Active) {
    beepWhenPulseEnds = false;
    startBeep(pendingBeepDurationUs);
    Serial.println(F("DONE,PULSE"));
  }
}
