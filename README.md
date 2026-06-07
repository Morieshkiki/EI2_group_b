# INF II — Smart City BIM

A FastAPI web app for managing buildings and sensors, with a 3D BIM viewer (xeokit),
IFC→XKT conversion, MongoDB storage, and ESP8266 (DHT11) sensors that send live readings.

Everything runs in Docker — you do **not** need to install Python, Node.js, or MongoDB
yourself. Docker builds them inside the containers from the `Dockerfile` and
`docker-compose.yml`.

## Run the app

1. Install [Docker Desktop](https://www.docker.com/get-started/) (and make sure it is running).
2. Clone this repository and open a terminal in the project folder.
3. Start everything with one command:
   ```
   docker compose up -d
   ```
   The first run takes a few minutes (it downloads images and builds the app +
   viewer). Later runs start in seconds.

That's it. The following services are then available:

| Service | URL | What it is |
|---|---|---|
| Web app | [http://127.0.0.1:8000](http://127.0.0.1:8000) | The main application |
| API docs | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Interactive Swagger UI |
| 3D viewer | [http://127.0.0.1:8080](http://127.0.0.1:8080) | xeokit BIM viewer |
| DB admin | [http://127.0.0.1:8081](http://127.0.0.1:8081) | Mongo Express (browse the database) |

## Stopping

```
docker compose down
```
This stops and removes the containers. Your database (buildings, sensors, readings)
is kept safe in the `mongo_data` volume, so it is still there next time you start.

> Do **not** add `-v` to `docker compose down` — that would delete the database volume.

## Using the 3D model viewer (IFC)

1. Create a building in the app.
2. Open the building's dashboard and **upload an IFC file**.
3. Click **convert** — the app converts the IFC to XKT (this runs inside the app
   container via Node.js) and displays the 3D model.

## Sensors (ESP8266 / DHT11)

The `arduino/` folder contains the ESP8266 sketches that read a DHT11 sensor and POST
readings to the app.

1. Place a sensor on a building in the app, then copy its **sensor ID** from the
   sensor dashboard.
2. Open `arduino/esp8266/esp8266.ino` and set your WiFi credentials, the sensor ID,
   and the IP of the machine running the app:
   ```cpp
   const char* sensorId = "<sensor-id-from-dashboard>";
   const String serverIp = "<your-server-ip>";   // e.g. 192.168.2.103
   const String ssid = "YOUR_WIFI_SSID";
   const String password = "YOUR_WIFI_PASSWORD";
   ```
3. Flash the sketch. The ESP8266 connects to WiFi on its own and starts sending
   readings to `http://<server-ip>:8000/sensors/data`.

The ESP8266 and the server must be on the **same network**. The app container already
listens on `0.0.0.0:8000`, so it is reachable from other devices on the LAN using your
machine's WiFi IP address.

> Tip: `arduino/esp8266_wifiscan` lists nearby WiFi networks and
> `arduino/esp8266_conntest` checks whether the board can reach the server — both are
> handy for debugging connection problems. The ESP8266 only supports 2.4 GHz WiFi
> (not 5 GHz) with WPA2.

## Rebuilding after code changes

If you change the app code or dependencies, rebuild the app image without touching the
database:
```
docker compose up -d --build app
```
