// based on Demo 1 (arduino/esp8266.ino), with help from AI.
// Purpose: reads the DHT11 temperature/humidity sensor on the ESP8266 and sends the
// values to the web app over WiFi every couple of seconds.
#include "DHT.h"
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

#define DHTPIN 13
#define DHTTYPE DHT11

const char* sensorId = "1779871634840";

const String serverIp = "10.36.214.122";
const int serverPort = 8000;
const String serverURL =  "http://" + serverIp + ":" + serverPort + "/sensors/data";

const String ssid = "YOUR_WIFI_SSID";
const String password = "YOUR_WIFI_PASSWORD";

DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifiClient;
HTTPClient http;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("===== ESP8266 sensor start =====");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  dht.begin();

  Serial.print("Connecting to WiFi");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 60) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi failed — will retry in loop().");
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi down — reconnecting...");
    WiFi.reconnect();
    delay(1000);
    return;
  }

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("DHT read failed (nan) — check wiring on GPIO 13.");
    delay(5000);
    return;
  }

  temperature = round(temperature * 10) / 10.0;
  humidity    = round(humidity    * 10) / 10.0;

  send_to_server(temperature, humidity);
  delay(2000);   // <-- DATA INTERVAL: change THIS to collect faster (2000ms = DHT11 minimum)
}

void send_to_server(float t, float h) {
  // Build JSON by hand — avoids ArduinoJson v6/v7 API differences.
  // FastAPI fills `timestamp` with datetime.now() when omitted.
  String jsonString = "{\"type\":\"DHT11-1\",\"temperature\":";
  jsonString += String(t, 1);
  jsonString += ",\"humidity\":";
  jsonString += String(h, 1);
  jsonString += ",\"sensor_id\":\"";
  jsonString += sensorId;
  jsonString += "\"}";

  http.begin(wifiClient, serverURL);
  http.addHeader("Content-Type", "application/json");
  http.setReuse(false);

  int httpCode = http.POST(jsonString);
  Serial.print("HTTP ");
  Serial.print(httpCode);
  Serial.print("  ");
  Serial.println(jsonString);

  if (httpCode <= 0) {
    Serial.print("  err: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}
