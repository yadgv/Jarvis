// Jarvis bridge: lets Jarvis switch pins and read sensors over USB.
// Upload with the Arduino IDE (Tools > Board: your board), then close the
// Serial Monitor so Jarvis can use the port. One command per line, 115200 baud:
//   PING | ON pin | OFF pin | PWM pin 0-255 | SERVO pin 0-180 | TONE pin hz ms | READ pin (A0.. or 2..)
// Add your own commands in handle() below; Jarvis can send them with the
// arduino tool's "command" action.
#include <Servo.h>

const int MAX_SERVOS = 4;
Servo servos[MAX_SERVOS];
int servoPins[MAX_SERVOS] = {-1, -1, -1, -1};
String line;

int parsePin(String p) {
  p.trim();
  p.toUpperCase();
  if (p.startsWith("A")) return A0 + p.substring(1).toInt();
  return p.toInt();
}

Servo* servoFor(int pin) {
  for (int i = 0; i < MAX_SERVOS; i++) if (servoPins[i] == pin) return &servos[i];
  for (int i = 0; i < MAX_SERVOS; i++) {
    if (servoPins[i] == -1) { servoPins[i] = pin; servos[i].attach(pin); return &servos[i]; }
  }
  return NULL;
}

String argAt(String s, int n) {  // the nth space-separated word (0-based)
  s.trim();
  for (int i = 0; i < n; i++) {
    int sp = s.indexOf(' ');
    if (sp < 0) return "";
    s = s.substring(sp + 1);
    s.trim();
  }
  int sp = s.indexOf(' ');
  return sp < 0 ? s : s.substring(0, sp);
}

void handle(String cmd) {
  String op = argAt(cmd, 0);
  op.toUpperCase();
  int pin = parsePin(argAt(cmd, 1));
  if (op == "PING") { Serial.println("PONG jarvis-bridge 1"); }
  else if (op == "ON" || op == "OFF") {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, op == "ON" ? HIGH : LOW);
    Serial.println("OK");
  }
  else if (op == "PWM") { pinMode(pin, OUTPUT); analogWrite(pin, constrain(argAt(cmd, 2).toInt(), 0, 255)); Serial.println("OK"); }
  else if (op == "SERVO") {
    Servo* s = servoFor(pin);
    if (!s) { Serial.println("ERR too many servos"); return; }
    s->write(constrain(argAt(cmd, 2).toInt(), 0, 180));
    Serial.println("OK");
  }
  else if (op == "TONE") { tone(pin, argAt(cmd, 2).toInt(), argAt(cmd, 3).toInt()); Serial.println("OK"); }
  else if (op == "READ") {
    String p = argAt(cmd, 1);
    p.toUpperCase();
    if (p.startsWith("A")) Serial.println("OK " + String(analogRead(pin)));
    else { pinMode(pin, INPUT); Serial.println("OK " + String(digitalRead(pin))); }
  }
  // Add your own commands here, e.g.:
  // else if (op == "FAN") { ... Serial.println("OK"); }
  else { Serial.println("ERR unknown command " + op); }
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { line.trim(); if (line.length()) handle(line); line = ""; }
    else if (c != '\r' && line.length() < 64) line += c;
  }
}
