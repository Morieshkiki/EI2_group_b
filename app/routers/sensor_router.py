from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader

from app.models.sensor_model import SensorModel as Sensor
from app.models.sensor_model import SensorReading
from app.util import mongo_db_connector

from xhtml2pdf import pisa
from io import BytesIO
from uuid import uuid4
from datetime import datetime, timedelta
from matplotlib.dates import DateFormatter, HourLocator, AutoDateLocator
from collections import defaultdict

import os
import app.config as config
import matplotlib.pyplot as plt
import tempfile

from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

router = APIRouter(prefix="/sensors", tags=["sensors"])
templates = Jinja2Templates(directory= TEMPLATES_DIR)


@router.get("/management")
async def sensor_management(request: Request):
    """ Render the sensor management page. """
    db = mongo_db_connector.init_db("sensors")
    sensors = list(db.find({}))
    for s in sensors:
        s.pop("_id", None)
    return templates.TemplateResponse("sensors.html", {"request": request, "sensors": sensors})


@router.get("/")
async def get_dashboard(request: Request, building_id: str = None):
    """Render sensor dashboard with data from MongoDB."""
    db = mongo_db_connector.init_db("sensors")
    query = {"building_id": building_id} if building_id else {}
    sensors = list(db.find(query))
    
    for s in sensors:
        s["id"] = s.pop("id", "N/A") 
        s["name"] = s.get("name", "Unknown")
        s["building_id"] = s.get("building_id", "Unknown")
        # Get sensor_coord or default
        coord = s.get("sensor_coord", [0, 0, 0])
        
        # Fallback in case of incorrect format
        if not isinstance(coord, (list, tuple)) or len(coord) != 3:
            coord = [0, 0, 0]
        
        # Store raw and display coords
        s["sensor_coord"] = coord
        s["sensor_coord_display"] = [round(float(x), 2) for x in coord]

        s.pop("_id", None)

    # Get building name from building collection
    building_name = "All Buildings"
    if building_id:
        buildings_collection = mongo_db_connector.init_db("buildings")
        building = buildings_collection.find_one({"id": building_id})
        if building:
            building_name = building.get("name", "Unnamed")

    return templates.TemplateResponse("sensors_dashboard.html", {
        "request": request,
        "sensors": sensors,
        "building_name": building_name
    })


@router.post("/")
async def create_sensor(sensor: Sensor):
    """ Create a new sensor and store it in the database. """
    db = mongo_db_connector.init_db("sensors")
    db.insert_one(sensor.model_dump())
    return {"message": "Sensor created successfully", "sensor_id": sensor.id}


@router.get("/create")
async def create_sensor_form(request: Request):
    """ Render form (HTML) to create a new sensor. """
    return templates.TemplateResponse("create_sensor.html", {"request": request})

@router.get("/json")
async def get_sensors_json(building_id: str = None):
    """Return sensor data as JSON (for frontend API use)."""
    db = mongo_db_connector.init_db("sensors")
    query = {"building_id": building_id} if building_id else {}
    sensors = list(db.find(query))
    for s in sensors:
        s.pop("_id", None)
    return sensors


@router.get("/{sensor_id}")
async def sensor_detail(request: Request, sensor_id: str):
    """ Render sensor detail page with data from MongoDB. """
    db = mongo_db_connector.init_db("sensors")
    sensor = db.find_one({"id": sensor_id})
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    sensor.pop("_id", None)

    building_name = "Unknown Building"
    building_id= sensor.get("building_id")
    if building_id:
        buildings_collection = mongo_db_connector.init_db("buildings")
        building = buildings_collection.find_one({"id": building_id})
        if building:
            building_name = building.get("name", "Unnamed")

    return templates.TemplateResponse("sensor_detail.html", {
        "request": request, 
        "sensor": sensor,
        "building_name": building_name
        })

@router.put("/{sensor_id}")
async def update_sensor(sensor_id: str, sensor: Sensor):
    """ Update an existing sensor's data. """
    db = mongo_db_connector.init_db("sensors")
    result = db.update_one({"id": sensor_id}, {"$set": sensor.model_dump()})
    if result.modified_count == 0:
        raise HTTPException(
            status_code=404, detail="Sensor not found or no changes made")
    return {"message": "Sensor updated successfully", "sensor_id": sensor_id}


@router.delete("/{sensor_id}")
async def delete_sensor(sensor_id: str):
    """ Delete a sensor from database by its ID. """
    db = mongo_db_connector.init_db("sensors")
    result = db.delete_one({"id": sensor_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"message": "Sensor deleted successfully", "sensor_id": sensor_id}


@router.get("/type/{type}")
async def get_sensors_by_type(type: str):
    """ Returns sensors of a specific type. """
    db = mongo_db_connector.init_db("sensors")
    sensors = list(db.find({"type": type}))
    for s in sensors:
        s.pop("_id", None)
    return sensors


@router.post("/{sensor_id}/value")
async def update_sensor_value(sensor_id: str, reading: SensorReading):
    """ Create a new sensor reading and store it in the database. """
    db = mongo_db_connector.init_db("sensor_readings")
    reading_data = reading.model_dump()
    reading_data["sensor_id"] = sensor_id
    reading_data["timestamp"] = datetime.now()
    db.insert_one(reading_data)
    return {"message": "Sensor reading created successfully", "reading_id": reading_data.get("id")}


@router.get("/readings/{sensor_id}")
async def get_sensor_readings(sensor_id: str):
    """ Get all readings for a specific sensor. """
    db = mongo_db_connector.init_db("sensor_readings")
    readings = list(db.find({"sensor_id": sensor_id}))

    if not readings:
        raise HTTPException(
            status_code=404, detail="No readings found for this sensor")

    for reading in readings:
        reading.pop("_id", None)
        if "timestamp" in reading and reading["timestamp"]:
            reading["timestamp"] = reading["timestamp"].isoformat()

    return readings

@router.post("/data")
async def receive_sensor_data(reading: SensorReading):
    db = mongo_db_connector.init_db("sensor_readings")
    reading_data = reading.model_dump()

    # Remove this line:
    # reading_data["sensor_id"] = reading_data.get("type", "unknown")

    if not reading_data.get("timestamp"):
        reading_data["timestamp"] = datetime.now()

    result = db.insert_one(reading_data)

    reading_data["_id"] = str(result.inserted_id)

    if isinstance(reading_data["timestamp"], datetime):
        reading_data["timestamp"] = reading_data["timestamp"].isoformat()

    return {"message": "Sensor data received", "data": reading_data}


@router.get("/data")
async def get_all_sensor_data():
    """ Return all sensor readings (raw view). """
    db = mongo_db_connector.init_db("sensor_readings")
    readings = list(db.find({}))

    for reading in readings:
        reading["_id"] = str(reading["_id"])
        if "timestamp" in reading and isinstance(reading["timestamp"], datetime):
            reading["timestamp"] = reading["timestamp"].isoformat()

    return {"data": readings}

@router.get("/readings/{sensor_id}/json")
async def get_sensor_readings_json(sensor_id: str, limit: int = 20):
    """Returns the last N readings (JSON) for a specific sensor."""
    db = mongo_db_connector.init_db("sensor_readings")
    readings = list(db.find({"sensor_id": sensor_id}).sort("timestamp", -1).limit(limit))

    for reading in readings:
        reading["_id"] = str(reading["_id"])
        if "timestamp" in reading:
            reading["timestamp"] = reading["timestamp"].isoformat()

    # Return readings in chronological order
    return {"readings": list(reversed(readings))}


@router.get("/{sensor_id}/report")
async def generate_sensor_report(request: Request, sensor_id: str):
    db = mongo_db_connector.init_db("sensors")
    sensor = db.find_one({"id": sensor_id})
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    sensor.pop("_id", None)
    sensor["sensor_coord_display"] = [round(float(x), 2) for x in sensor.get("sensor_coord", [0, 0, 0])]

    # Get building name
    building_name = "Unknown"
    if sensor.get("building_id"):
        bdb = mongo_db_connector.init_db("buildings")
        b = bdb.find_one({"id": sensor["building_id"]})
        if b:
            building_name = b.get("name", "Unnamed")

    # Get readings
    now = datetime.now()
    past_24h = now - timedelta(hours=24)
    rdb = mongo_db_connector.init_db("sensor_readings")
    readings = list(rdb.find({
        "sensor_id": sensor_id,
        "timestamp": {"$gte": past_24h}
    }).sort("timestamp", -1))
    for r in readings:
        r.pop("_id", None)
        if "timestamp" in r and isinstance(r["timestamp"], datetime):
            r["timestamp"] = r["timestamp"].isoformat()

    # Calculate averages
    temps = [r["temperature"] for r in readings if "temperature" in r]
    hums = [r["humidity"] for r in readings if "humidity" in r]
    avg_temp = round(sum(temps)/len(temps), 2) if temps else "N/A"
    avg_hum = round(sum(hums)/len(hums), 2) if hums else "N/A"

    # Generate chart for all readings from the last 24 hours
    chart_readings = list(reversed(readings))
    
    if chart_readings:
        time_range_start = datetime.fromisoformat(chart_readings[0]["timestamp"]).strftime("%Y-%m-%d %H:%M")
        time_range_end = datetime.fromisoformat(chart_readings[-1]["timestamp"]).strftime("%Y-%m-%d %H:%M")
        chart_title = f"Readings from the Last 24 Hours (Average Values in 15-Minute Slots)\n{time_range_start} to {time_range_end}"
    else:
        chart_title = "Sensor Readings"

    # Group readings into 15-minute buckets
    buckets = defaultdict(lambda: {"temperature": [], "humidity": []})

    for r in chart_readings:
        ts = datetime.fromisoformat(r["timestamp"])
        interval = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        if "temperature" in r:
            buckets[interval]["temperature"].append(r["temperature"])
        if "humidity" in r:
            buckets[interval]["humidity"].append(r["humidity"])

    # Calculate average values for each bucket
    timestamps = []
    temp_data = []
    hum_data = []

    for interval in sorted(buckets.keys()):
        timestamps.append(interval)
        temps = buckets[interval]["temperature"]
        hums = buckets[interval]["humidity"]
        temp_data.append(round(sum(temps) / len(temps), 2) if temps else None)
        hum_data.append(round(sum(hums) / len(hums), 2) if hums else None)


    fig, ax = plt.subplots()
    ax.plot(timestamps, temp_data, label="Temperature (°C)", color="red")
    ax.plot(timestamps, hum_data, label="Humidity (%)", color="blue")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Value")
    ax.set_title(chart_title)
    if len(timestamps) < 1000:
        ax.set_xticks(timestamps)
    ax.xaxis.set_major_locator(AutoDateLocator())
    ax.xaxis.set_major_formatter(DateFormatter('%H')) 
    fig.autofmt_xdate()
    plt.tight_layout()
    ax.legend()
    

    # Save chart to temporary image file
    img_path = os.path.join(tempfile.gettempdir(), f"chart_{uuid4().hex}.png")
    plt.savefig(img_path)
    print("Saved chart image to:", img_path)
    print("File exists:", os.path.exists(img_path))
    plt.close()

    try:
        html = templates.get_template("pdf_sensor_report.html").render({
            "sensor": sensor,
            "building_name": building_name,
            "readings": readings,
            "avg_temp": avg_temp,
            "avg_hum": avg_hum,
            "image_path": img_path.replace("\\", "/")
        })

        pdf = BytesIO()
        pisa.CreatePDF(src=html, dest=pdf)
        pdf.seek(0)
        return StreamingResponse(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f"inline; filename=sensor_{sensor_id}_report.pdf"
        })

    finally:
        if os.path.exists(img_path):
            os.remove(img_path)

@router.get("/latest_reading/{sensor_id}")
async def get_latest_reading(sensor_id: str):
    db = mongo_db_connector.init_db("sensor_readings")
    reading = db.find_one({"sensor_id": sensor_id}, sort=[("timestamp", -1)])
    if reading:
        reading.pop("_id", None)
        if "timestamp" in reading:
            reading["timestamp"] = reading["timestamp"].isoformat()
    return reading or {}
