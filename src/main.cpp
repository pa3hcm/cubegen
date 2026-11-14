/*
 * QubeRG v0.1b - simple RF signal generator
 * (c) 2026 PA3HCM
 *
 * Licensed under the Creative Commons Attribution-NonCommercial 4.0
 * International License (CC BY-NC 4.0). See the LICENSE file or
 * https://creativecommons.org/licenses/by-nc/4.0/
 *
 * Hardware:
 *   - ESP32 devboard (esp32dev)
 *   - Si5351 DDS board, 25 MHz crystal, I2C address 0x60, output on CLK0
 *   - GM009605v4 0.96" OLED (SSD1306, 128x64), I2C address 0x3C
 *   - 4 push buttons to GND (internal pull-ups used)
 *
 * Wiring (all 3.3 V):
 *   I2C SDA  -> GPIO21 (Si5351 SDA + OLED SDA)
 *   I2C SCL  -> GPIO22 (Si5351 SCL + OLED SCL)
 *   Button 1 -> GPIO32  increase selected digit
 *   Button 2 -> GPIO33  decrease selected digit
 *   Button 3 -> GPIO25  select next digit (wraps around)
 *   Button 4 -> GPIO26  select next mode (CW, CW-keyed, FSK470, FSK850, FSK1K, FSK10K, OFF)
 *   Button COM -> GND
 */

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <si5351.h>

// ---------------------------------------------------------------- pins
static const uint8_t PIN_SDA = 21;
static const uint8_t PIN_SCL = 22;

static const uint8_t NUM_BUTTONS = 4;
static const uint8_t BUTTON_PINS[NUM_BUTTONS] = {32, 33, 25, 26};

// ---------------------------------------------------------------- display
static const uint8_t SCREEN_WIDTH = 128;
static const uint8_t SCREEN_HEIGHT = 64;
static const uint8_t OLED_ADDR = 0x3C;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ---------------------------------------------------------------- Si5351
Si5351 si5351;                       // default I2C address 0x60
static const uint32_t XTAL_FREQ = 25000000UL;
static const int32_t XTAL_CORRECTION = 0;   // in parts per billion, calibrate later
bool si5351Present = false;

// ---------------------------------------------------------------- frequency
static const uint8_t NUM_DIGITS = 8;                 // "10.000.000" -> 8 digits
static const uint32_t FREQ_MIN = 8000UL;             // Si5351 lower limit ~8 kHz
static const uint32_t FREQ_MAX = 99999999UL;         // max that fits in 8 digits
static const uint32_t FREQ_START = 10000000UL;       // 10 MHz

uint32_t frequency = FREQ_START;
uint8_t selectedDigit = 0;     // 0 = left-most digit (10 MHz position)

// ---------------------------------------------------------------- modes
enum Mode : uint8_t {
  MODE_CW = 0,      // continuous carrier
  MODE_CW_KEYED,    // keyed carrier: -.-.-. ...
  MODE_FSK470,      // 500 ms on f, 500 ms on f + 470 Hz
  MODE_FSK850,      // 500 ms on f, 500 ms on f + 850 Hz
  MODE_FSK1K,       // 500 ms on f, 500 ms on f + 1000 Hz
  MODE_FSK10K,      // 500 ms on f, 500 ms on f + 10000 Hz
  MODE_OFF,         // no output
  NUM_MODES
};
const char *const MODE_NAMES[NUM_MODES] = {
  "CW", "CW-keyed", "FSK470", "FSK850", "FSK1K", "FSK10K", "OFF"
};
const uint32_t FSK_SHIFT[NUM_MODES] = {0, 0, 470, 850, 1000, 10000, 0};
static const uint32_t FSK_STEP_MS = 500;

// CW-keyed pattern "-." repeated (gives -.-.-.-.), 100 ms dot unit (12 WPM)
struct KeyStep {
  bool on;
  uint16_t ms;
};
static const uint16_t CW_UNIT_MS = 100;
const KeyStep KEY_PATTERN[] = {
  {true, 3 * CW_UNIT_MS},   // dash
  {false, CW_UNIT_MS},      // gap
  {true, CW_UNIT_MS},       // dot
  {false, CW_UNIT_MS},      // gap
};
static const uint8_t KEY_PATTERN_LEN = sizeof(KEY_PATTERN) / sizeof(KEY_PATTERN[0]);

Mode mode = MODE_OFF;              // default mode at power-up
uint8_t patternStep = 0;        // current step in keying / FSK pattern
uint32_t patternStepStart = 0;  // millis() at start of current step

// what the Si5351 is currently doing (to avoid needless I2C traffic)
uint32_t outFreq = 0;
bool outEnabled = false;

// ---------------------------------------------------------------- buttons
static const uint32_t DEBOUNCE_MS = 25;
static const uint32_t REPEAT_DELAY_MS = 500;   // hold time before auto-repeat
static const uint32_t REPEAT_RATE_MS = 120;    // auto-repeat interval

struct Button {
  uint8_t pin;
  bool stableState;      // true = pressed
  bool lastReading;
  uint32_t lastChange;
  uint32_t nextRepeat;
};
Button buttons[NUM_BUTTONS];

// ---------------------------------------------------------------- helpers

// Weight of digit 'd' (0 = left-most): 10^(NUM_DIGITS-1-d)
uint32_t digitWeight(uint8_t d) {
  uint32_t w = 1;
  for (uint8_t i = 0; i < NUM_DIGITS - 1 - d; i++) w *= 10;
  return w;
}

// Character column of digit 'd' in the string "XX.XXX.XXX"
uint8_t digitCharPos(uint8_t d) {
  return d + (d >= 2 ? 1 : 0) + (d >= 5 ? 1 : 0);
}

void formatFrequency(uint32_t f, char *buf) {
  // buf must hold at least 16 chars
  snprintf(buf, 16, "%02lu.%03lu.%03lu",
           (unsigned long)(f / 1000000UL),
           (unsigned long)((f / 1000UL) % 1000UL),
           (unsigned long)(f % 1000UL));
}

// Program the Si5351 CLK0 output; only talks I2C when something changes
void setOutput(bool enabled, uint32_t f) {
  if (!si5351Present) return;
  if (f != outFreq) {
    // set_freq takes the frequency in units of 0.01 Hz
    si5351.set_freq((uint64_t)f * 100ULL, SI5351_CLK0);
    outFreq = f;
    si5351.output_enable(SI5351_CLK0, enabled ? 1 : 0);
    outEnabled = enabled;
  } else if (enabled != outEnabled) {
    si5351.output_enable(SI5351_CLK0, enabled ? 1 : 0);
    outEnabled = enabled;
  }
}

// Set the output for the current mode and pattern step
void applyOutput() {
  switch (mode) {
    case MODE_CW:
      setOutput(true, frequency);
      break;
    case MODE_CW_KEYED:
      setOutput(KEY_PATTERN[patternStep].on, frequency);
      break;
    case MODE_FSK470:
    case MODE_FSK850:
    case MODE_FSK1K:
    case MODE_FSK10K:
      setOutput(true, frequency + (patternStep ? FSK_SHIFT[mode] : 0));
      break;
    default:  // MODE_OFF
      setOutput(false, frequency);
      break;
  }
}

// Duration of the current pattern step, 0 = static (no timing)
uint32_t patternStepDuration() {
  switch (mode) {
    case MODE_CW_KEYED: return KEY_PATTERN[patternStep].ms;
    case MODE_FSK470:
    case MODE_FSK850:
    case MODE_FSK1K:
    case MODE_FSK10K:   return FSK_STEP_MS;
    default:            return 0;
  }
}

void restartPattern() {
  patternStep = 0;
  patternStepStart = millis();
  applyOutput();
}

// Advance keying / FSK pattern; call often from loop()
void updatePattern() {
  uint32_t d = patternStepDuration();
  if (d == 0) return;
  uint32_t now = millis();
  if (now - patternStepStart >= d) {
    // keep a steady rhythm, but resync if we fell far behind
    patternStepStart = (now - patternStepStart >= 2 * d) ? now : patternStepStart + d;
    uint8_t len = (mode == MODE_CW_KEYED) ? KEY_PATTERN_LEN : 2;
    patternStep = (patternStep + 1) % len;
    applyOutput();
  }
}

void drawMainScreen() {
  char buf[16];
  formatFrequency(frequency, buf);

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);                 // 12 x 16 px per character

  const int16_t charW = 12;
  const int16_t textX = (SCREEN_WIDTH - 10 * charW) / 2;   // 10 characters
  const int16_t textY = 22;

  display.setCursor(textX, textY);
  display.print(buf);

  // cursor: a bar just below the selected digit
  int16_t cx = textX + digitCharPos(selectedDigit) * charW;
  display.fillRect(cx, textY + 18, charW - 2, 2, SSD1306_WHITE);

  display.setTextSize(1);
  display.setCursor(textX, 52);
  display.print("Mode: ");
  display.print(MODE_NAMES[mode]);

  if (!si5351Present) {
    display.setCursor(textX, 4);
    display.print("Si5351 not found!");
  }

  display.display();
}

void showSplash() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  const char *line1 = "QubeRG v0.1b";
  const char *line2 = "(c) 2026 PA3HCM";
  display.setCursor((SCREEN_WIDTH - strlen(line1) * 6) / 2, 20);
  display.print(line1);
  display.setCursor((SCREEN_WIDTH - strlen(line2) * 6) / 2, 36);
  display.print(line2);
  display.display();
}

// ---------------------------------------------------------------- actions

void increaseDigit() {
  uint32_t w = digitWeight(selectedDigit);
  // Adding the weight automatically carries into the next digit (19 -> 20)
  if (frequency <= FREQ_MAX - w) {
    frequency += w;
    applyOutput();
    drawMainScreen();
  }
}

void decreaseDigit() {
  uint32_t w = digitWeight(selectedDigit);
  // Subtracting the weight automatically borrows from the next digit (20 -> 19)
  if (frequency >= FREQ_MIN + w) {
    frequency -= w;
    applyOutput();
    drawMainScreen();
  }
}

void nextDigit() {
  selectedDigit = (selectedDigit + 1) % NUM_DIGITS;
  drawMainScreen();
}

void nextMode() {
  mode = (Mode)((mode + 1) % NUM_MODES);
  restartPattern();
  drawMainScreen();
}

void handleButton(uint8_t index) {
  switch (index) {
    case 0: increaseDigit(); break;
    case 1: decreaseDigit(); break;
    case 2: nextDigit(); break;
    case 3: nextMode(); break;
  }
}

void pollButtons() {
  uint32_t now = millis();
  for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
    Button &b = buttons[i];
    bool reading = (digitalRead(b.pin) == LOW);   // active low

    if (reading != b.lastReading) {
      b.lastReading = reading;
      b.lastChange = now;
    }

    if ((now - b.lastChange) >= DEBOUNCE_MS && reading != b.stableState) {
      b.stableState = reading;
      if (b.stableState) {               // just pressed
        handleButton(i);
        b.nextRepeat = now + REPEAT_DELAY_MS;
      }
    }

    // auto-repeat for up/down buttons while held
    if (b.stableState && i <= 1 && (int32_t)(now - b.nextRepeat) >= 0) {
      handleButton(i);
      b.nextRepeat = now + REPEAT_RATE_MS;
    }
  }
}

// ---------------------------------------------------------------- setup / loop

void setup() {
  Serial.begin(115200);

  for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    buttons[i] = {BUTTON_PINS[i], false, false, 0, 0};
  }

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("SSD1306 not found");
  }
  showSplash();

  si5351Present = si5351.init(SI5351_CRYSTAL_LOAD_8PF, XTAL_FREQ, XTAL_CORRECTION);
  if (si5351Present) {
    si5351.drive_strength(SI5351_CLK0, SI5351_DRIVE_8MA);
    si5351.output_enable(SI5351_CLK1, 0);
    si5351.output_enable(SI5351_CLK2, 0);
    restartPattern();
  } else {
    Serial.println("Si5351 not found");
  }

  delay(2000);
  drawMainScreen();
}

void loop() {
  pollButtons();
  updatePattern();
  delay(1);
}
