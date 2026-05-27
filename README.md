# INF II Demo(s) 

# Database Setup 
You can setup a mongo db instance as a standalone server on your own physical machine, or use a container for that.

## Setup for running the demo with containers 

1. Install [Docker Desktop](https://www.docker.com/get-started/) 
2. Install [python](https://www.python.org/)
    1. generate virtual environment in this folder via ```python -m venv .venv``` also ```Remove-Item -Recurse -Force .venv``` for reinstalls
    1. install dependencies in the new venv (using a new terminal window) ```pip install -r requirements.txt```
3. Initialize mongodb, mongo express and the xeokit viewer using ```docker compose up -d```
4. run fastapi app via uvicorn using ```uvicorn app.main:app --reload```
    1. This may also be necessary to ensure the Arduinos can access ```uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload```
5. Service is available on [http://127.0.0.1:8000](http://127.0.0.1:8000) 
6. API Documentation is available under [/docs](http://127.0.0.1:8000/docs)
7. Once a sensor is placed in a building, copy the sensor ID from the sensor dashboard and paste it into the file testDataSend_sensor.py in SENSOR_ID.
8. Initialize the artifical sensor readings by opening a terminal window, navigating to the project directory and running testDataSend_sensor.py (python testDataSend_sensor.py)

## Running the tests

The test suite lives in `tests/` and uses pytest with an in-process ASGI client that talks to MongoDB. Make sure the containers are running (`docker compose up -d`) and the dependencies are installed, then run from the project root:

```
pytest
```

## Arduino firmware (ESP8266 sensor)

The `arduino/` folder contains the ESP8266 sketches that read a DHT11 sensor and POST readings to the app. Before flashing, open the sketch and set your own WiFi credentials and the IP of the machine running the app:

```
const String ssid = "YOUR_WIFI_SSID";
const String password = "YOUR_WIFI_PASSWORD";
const String serverIp = "<your-server-ip>";
```

The ESP8266 must be on the same network as the server, which should be started with `--host 0.0.0.0` (see step 4 above).  
