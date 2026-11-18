#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>
#include <atomic>
#include <cstring>

Arduino_LED_Matrix matrix;
std::atomic<unsigned int> displayState(0);
std::atomic<unsigned long> lastUpdate(0);
std::atomic<bool> received(false);
std::atomic<bool> calendarFrame(false);
std::atomic<unsigned int> frameVersion(0);
std::atomic<unsigned int> frameParts[4];
uint8_t frame[104] = {0};
// Original 3x5 digits; one blank column separates each character.
const uint8_t DIGITS[10][5] = {
  {7,5,5,5,7}, {2,6,2,2,7}, {7,1,7,4,7}, {7,1,7,1,7}, {5,5,7,1,1},
  {7,4,7,1,7}, {7,4,7,5,7}, {7,1,1,1,1}, {7,5,7,5,7}, {7,5,7,1,7}
};
const uint8_t MINUTE[5] = {0,7,7,5,5};
const uint8_t SECOND[5] = {0,3,4,2,6};

bool focusDisplay(int mode, int seconds, int percent, bool alert) {
  if (mode < 0 || mode > 6 || seconds < 0 || seconds > 10800 || percent < 0 || percent > 100) return false;
  unsigned int packed = (unsigned int)mode | ((unsigned int)seconds << 3)
    | ((unsigned int)percent << 17) | (alert ? (1u << 24) : 0);
  displayState.store(packed);
  calendarFrame.store(false);
  lastUpdate.store(millis());
  received.store(true);
  return true;
}

bool showCalendarFrame(int a, int b, int c, int d) {
  int parts[4] = {a,b,c,d};
  for (int i=0; i<4; i++) if (parts[i] < 0 || parts[i] >= (1 << 26)) return false;
  frameVersion.fetch_add(1);
  for (int i=0; i<4; i++) frameParts[i].store((unsigned int)parts[i]);
  frameVersion.fetch_add(1);
  calendarFrame.store(true);
  lastUpdate.store(millis());
  received.store(true);
  return true;
}

void pixel(int row, int col) {
  if (row >= 0 && row < 8 && col >= 0 && col < 13) frame[row * 13 + col] = 1;
}

void glyph(const uint8_t *rows, int col) {
  for (int r = 0; r < 5; r++)
    for (int c = 0; c < 3; c++)
      if (rows[r] & (1u << (2 - c))) pixel(r + 1, col + c);
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(1);
  matrix.clear();
  Bridge.begin();
  Bridge.provide("focus_display_v2", focusDisplay);
  Bridge.provide("calendar_frame_v1", showCalendarFrame);
}

void loop() {
  static unsigned long lastDraw = 0;
  unsigned long now = millis();
  if (now - lastDraw < 100) return;
  lastDraw = now;
  memset(frame, 0, sizeof(frame));
  if (!received.load() || now - lastUpdate.load() > 5000) {
    for (int i = 0; i < 7; i++) { pixel(i, 3 + i); pixel(i, 9 - i); }
  } else if (calendarFrame.load()) {
    unsigned int version = frameVersion.load();
    unsigned int parts[4];
    for (int i=0; i<4; i++) parts[i] = frameParts[i].load();
    if ((version & 1u) || version != frameVersion.load()) return;
    for (int i=0; i<104; i++) frame[i] = (parts[i/26] >> (i%26)) & 1u;
  } else {
    unsigned int packed = displayState.load();
    int mode = packed & 7u;
    int seconds = (packed >> 3) & 16383u;
    int percent = (packed >> 17) & 127u;
    bool alert = (packed & (1u << 24)) != 0;
    if (mode == 6) {
      // Exclamation mark: time to prepare for the next calendar event.
      for (int r = 0; r < 5; r++) { pixel(r, 6); pixel(r, 7); }
      pixel(6, 6); pixel(6, 7);
    } else if (mode == 5) {
      pixel(4, 2); pixel(5, 3);
      for (int i = 0; i < 6; i++) pixel(6 - i, 4 + i);
    } else {
      int value = seconds >= 60 ? (seconds + 59) / 60 : seconds;
      if (value >= 100) {
        glyph(DIGITS[value / 100], 1);
        glyph(DIGITS[(value / 10) % 10], 5);
        glyph(DIGITS[value % 10], 9);
      } else {
        glyph(DIGITS[value / 10], 1);
        glyph(DIGITS[value % 10], 5);
        glyph(seconds >= 60 ? MINUTE : SECOND, 9);
      }
      if (mode == 2 || mode == 4) { pixel(0, 10); pixel(0, 11); pixel(0, 12); }
      else { pixel(0, 0); pixel(0, 1); pixel(0, 2); }
      if (mode == 3 || mode == 4) { pixel(0, 5); pixel(0, 7); }
      int lit = (percent * 13 + 99) / 100;
      for (int c = 0; c < lit; c++) pixel(7, c);
    }
    if (alert && (now / 250) % 2 == 0) {
      for (int i = 0; i < 104; i++) frame[i] = 1 - frame[i];
    }
  }
  matrix.draw(frame);
}
