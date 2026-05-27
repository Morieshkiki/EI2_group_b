// generated using AI for checking whether the ESP8266 board can reach the server.
// It is a diagnostic helper, separate from the main sensor sketch.
//
// Connectivity test for ESP8266 -> FastAPI server.
// Connects to WiFi, then repeatedly does a plain HTTP GET to the server.
// Watch Serial Monitor @ 115200. HTTP 200 = reachable. -1 = blocked/unreachable.

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

const String serverIp = "10.36.214.122";   // PC's WiFi IP (running uvicorn)
const int    serverPort = 8000;
const String testURL  = "http://" + serverIp + ":" + serverPort + "/docs";  // returns 200

WiFiClient wifiClient;
HTTPClient http;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n===== ESP8266 connectivity test =====");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 60) { delay(500); Serial.print("."); tries++; }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK. ESP IP: ");   Serial.println(WiFi.localIP());
    Serial.print("Gateway: ");           Serial.println(WiFi.gatewayIP());
    Serial.print("RSSI: ");              Serial.println(WiFi.RSSI());
  } else {
    Serial.println("WiFi FAILED - wrong SSID/password or out of range.");
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi down - reconnecting...");
    WiFi.reconnect();
    delay(2000);
    return;
  }

  // 1) Raw TCP reachability check (isolates firewall / AP-isolation from HTTP issues)
  Serial.print("TCP connect to "); Serial.print(serverIp); Serial.print(":"); Serial.print(serverPort);
  if (wifiClient.connect(serverIp.c_str(), serverPort)) {
    Serial.println(" -> TCP OK");
    wifiClient.stop();
  } else {
    Serial.println(" -> TCP FAILED (firewall on PC, or hotspot AP-isolation)");
  }

  // 2) Full HTTP GET
  http.begin(wifiClient, testURL);
  http.setReuse(false);
  int code = http.GET();
  Serial.print("HTTP GET "); Serial.print(testURL); Serial.print(" -> "); Serial.println(code);
  if (code <= 0) { Serial.print("  err: "); Serial.println(http.errorToString(code)); }
  http.end();

  Serial.println("------");
  delay(4000);
}
