import random
import time
import requests
from datetime import datetime
from typing import Optional

# Define the backend URL
SENSOR_ID = "1779375809981" # Example sensor ID, in the webapp copy sensor ID from the sensors dashboard from a specific building
BASE_URL = f"http://127.0.0.1:8000/sensors/{SENSOR_ID}/value"

# Sensor data simulation
def get_sensor_data():
    # Generate synthetic temperature and humidity values
    temperature = random.uniform(15, 30)  # temperature range between 15 and 30 C
    humidity = random.uniform(30, 60)  # humidity range between 30% and 60%
    return temperature, humidity

def send_to_server(temperature, humidity):
    # Prepare the sensor reading data
    sensor_data = {
        "type": "DHT11-2",  # Example sensor type, adjust as needed
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "timestamp": datetime.now().isoformat()  # Get the current timestamp in ISO format
    }

    try:
        # Send a POST request to the server with the sensor data in JSON format
        response = requests.post(BASE_URL, json=sensor_data)
        print(sensor_data)

        # Print the response from the server
        print(f"HTTP Code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data: {e}")

def main():
    while True:
        # Get synthetic sensor data
        temperature, humidity = get_sensor_data()
        
        # Print the simulated data to console (just like the Serial.print in Arduino)
        print(f"Temperature: {temperature:.2f}°C, Humidity: {humidity:.2f}%")
        
        # Send the data to the server
        send_to_server(temperature, humidity)
        
        # Wait for 10 seconds before sending data again
        time.sleep(10)

if __name__ == "__main__":
    main()
