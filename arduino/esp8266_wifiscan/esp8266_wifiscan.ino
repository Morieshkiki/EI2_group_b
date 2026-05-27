// generated using AI for listing the WiFi networks the ESP8266 can see, to help
// diagnose connection problems. It is a diagnostic helper, separate from the main sketch.
//
// WiFi scanner for ESP8266. Upload, open Serial Monitor @ 115200.
// It lists every 2.4 GHz network the ESP can actually see, with signal,
// channel, and security type. This tells us WHY it can't join your WiFi network.
//
// What to look for:
//  - Is your network (SSID) in the list at all?
//      NO  -> hotspot is 5 GHz-only, hidden, off, or out of range (ESP8266 is 2.4 GHz only).
//      YES -> check the next two:
//  - Enc column: must be WPA2 (or WPA/WPA2). If it shows WPA3/AUTO, the ESP can't connect -> set phone to "WPA2-Personal".
//  - RSSI: closer to 0 is stronger. Worse than about -85 dBm = too weak/unreliable.
//  - SSID: confirm the EXACT name (case, spaces). It must match the sketch char-for-char.

#include <ESP8266WiFi.h>

String encStr(uint8_t e) {
  switch (e) {
    case ENC_TYPE_NONE: return "OPEN";
    case ENC_TYPE_WEP:  return "WEP";
    case ENC_TYPE_TKIP: return "WPA";
    case ENC_TYPE_CCMP: return "WPA2";
    case ENC_TYPE_AUTO: return "WPA/WPA2-AUTO";
    default:            return "UNKNOWN(" + String(e) + ")";
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n===== ESP8266 WiFi scan =====");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
}

void loop() {
  Serial.println("Scanning...");
  int n = WiFi.scanNetworks(false, true);   // async=false, show hidden=true
  if (n == 0) {
    Serial.println("No networks found (no 2.4 GHz APs visible).");
  } else {
    Serial.print(n); Serial.println(" networks:");
    Serial.println("  # | RSSI | Ch |  Enc           | SSID");
    for (int i = 0; i < n; i++) {
      Serial.printf("  %d | %4d | %2d | %-14s | \"%s\"%s\n",
        i + 1,
        WiFi.RSSI(i),
        WiFi.channel(i),
        encStr(WiFi.encryptionType(i)).c_str(),
        WiFi.SSID(i).c_str(),
        (WiFi.SSID(i).length() == 0 ? " <hidden>" : ""));
    }
  }
  WiFi.scanDelete();
  Serial.println("------");
  delay(6000);
}
