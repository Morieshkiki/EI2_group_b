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
from zoneinfo import ZoneInfo
from matplotlib.dates import DateFormatter, HourLocator, AutoDateLocator
from collections import defaultdict

import os
import app.config as config
import matplotlib.pyplot as plt
import tempfile

from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# the sensor routes and database setup follow Demo 1 (building_router.py).
router = APIRouter(prefix="/sensors", tags=["sensors"])
templates = Jinja2Templates(directory= TEMPLATES_DIR)

# generated using AI: helpers that convert stored UTC timestamps to local time and
# group readings into time buckets (per second/minute/hour, or an auto-picked size)
# for the charts and the PDF report.
UTC = ZoneInfo("UTC")
LOCAL_TZ = ZoneInfo(os.getenv("REPORT_TZ", "Europe/Berlin"))


def _to_local_naive(dt):
    """Treat a naive UTC datetime as UTC and return naive local wall-clock time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ).replace(tzinfo=None)


# Live-chart resolutions: (bucket size in seconds, number of buckets to show)
GRANULARITIES = {
    "second":     (1,    60),
    "minute":     (60,   60),
    "ten_minute": (600,  48),
    "hour":       (3600, 48),
}

# PDF report ranges: window length in seconds
REPORT_RANGES = {
    "5m": 300, "10m": 600, "30m": 1800,
    "1h": 3600, "3h": 10800, "6h": 21600, "12h": 43200,
    "24h": 86400, "2d": 172800, "7d": 604800,
}

REPORT_RANGE_LABELS = {
    "5m": "Last 5 minutes", "10m": "Last 10 minutes", "30m": "Last 30 minutes",
    "1h": "Last hour", "3h": "Last 3 hours", "6h": "Last 6 hours",
    "12h": "Last 12 hours", "24h": "Last 24 hours", "2d": "Last 2 days",
    "7d": "Last 7 days",
}

# "Nice" bucket sizes (seconds) used to keep charts to a readable number of points
_NICE_BUCKETS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                 3600, 7200, 10800, 21600, 43200, 86400]


def _pick_bucket(span_seconds, target_points=80):
    """Pick a sensible bucket size so a chart spanning span_seconds has ~target_points."""
    raw = max(1.0, span_seconds / target_points)
    for b in _NICE_BUCKETS:
        if b >= raw:
            return b
    return _NICE_BUCKETS[-1]


def _humanize_seconds(s):
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h"
    return f"{s // 86400} d"


def _bucket_series(readings, bucket_seconds):
    """
    readings: dicts with a datetime 'timestamp' (UTC) and optional temperature/humidity.
    Returns a time-sorted list of (bucket_start_utc_aware, temp_avg|None, hum_avg|None).
    """
    buckets = {}
    for r in readings:
        ts = r.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        epoch = ts.replace(tzinfo=UTC).timestamp() if ts.tzinfo is None else ts.timestamp()
        key = int(epoch // bucket_seconds) * bucket_seconds
        b = buckets.setdefault(key, {"t": [], "h": []})
        if r.get("temperature") is not None:
            b["t"].append(r["temperature"])
        if r.get("humidity") is not None:
            b["h"].append(r["humidity"])
    out = []
    for key in sorted(buckets):
        b = buckets[key]
        t = round(sum(b["t"]) / len(b["t"]), 1) if b["t"] else None
        h = round(sum(b["h"]) / len(b["h"]), 1) if b["h"] else None
        out.append((datetime.fromtimestamp(key, UTC), t, h))
    return out


def _axis_time_format(span_seconds):
    """Pick an x-axis time format based on the ACTUAL data span (auto-adjusts)."""
    if span_seconds <= 1800:        # up to 30 minutes
        return "%H:%M:%S"
    if span_seconds <= 86400:       # up to 24 hours
        return "%H:%M"
    if span_seconds <= 172800:      # up to 2 days
        return "%a %H:%M"
    return "%d %b"                  # longer (7 days)


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


# generated using AI: gives the live chart its data, averaged to the chosen
# resolution (per second / minute / 10 minutes / hour).
@router.get("/readings/{sensor_id}/series")
async def get_sensor_series(sensor_id: str, granularity: str = "second"):
    """Aggregated reading series for the live chart, averaged by resolution
    (secondly / per-minute / per-10-minutes / hourly)."""
    bucket, points = GRANULARITIES.get(granularity, GRANULARITIES["second"])
    window = bucket * points
    since = datetime.now() - timedelta(seconds=window)  # container time is UTC

    db = mongo_db_connector.init_db("sensor_readings")
    readings = list(db.find({
        "sensor_id": sensor_id,
        "timestamp": {"$gte": since}
    }).sort("timestamp", 1))

    series = _bucket_series(readings, bucket)[-points:]
    return {
        "granularity": granularity,
        "bucket_seconds": bucket,
        "points": [
            {"timestamp": ts.isoformat(), "temperature": t, "humidity": h}
            for ts, t, h in series
        ],
    }


# AI helped build the PDF report: it collects the readings for the chosen time range,
# draws the temperature/humidity chart, and fills the report template.
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

    # ---- Resolve the requested time range (defaults to 24 h) ----
    range_key = request.query_params.get("range", "24h")
    window = REPORT_RANGES.get(range_key, REPORT_RANGES["24h"])

    now = datetime.now()  # container time is UTC; stored timestamps are naive UTC
    since = now - timedelta(seconds=window)
    rdb = mongo_db_connector.init_db("sensor_readings")
    readings = list(rdb.find({
        "sensor_id": sensor_id,
        "timestamp": {"$gte": since}
    }).sort("timestamp", 1))

    # Averages across the selected window
    temps = [r["temperature"] for r in readings if r.get("temperature") is not None]
    hums = [r["humidity"] for r in readings if r.get("humidity") is not None]
    avg_temp = round(sum(temps) / len(temps), 1) if temps else "N/A"
    avg_hum = round(sum(hums) / len(hums), 1) if hums else "N/A"

    # ---- Bucket size & x-axis format adapt to the ACTUAL data span (not just the request) ----
    if readings:
        actual_span = max(1, int((readings[-1]["timestamp"] - readings[0]["timestamp"]).total_seconds()))
    else:
        actual_span = window
    bucket_seconds = _pick_bucket(actual_span)
    time_fmt = _axis_time_format(actual_span)

    series = _bucket_series(readings, bucket_seconds)

    # Local-time naive datetimes for matplotlib + display rows
    timestamps, temp_plot, hum_plot, table_rows = [], [], [], []
    for ts_utc, t, h in series:
        local = _to_local_naive(ts_utc)
        timestamps.append(local)
        temp_plot.append(t if t is not None else float("nan"))
        hum_plot.append(h if h is not None else float("nan"))
        table_rows.append({
            "time": local.strftime("%Y-%m-%d %H:%M:%S"),
            "temperature": t if t is not None else "—",
            "humidity": h if h is not None else "—",
        })

    range_label = REPORT_RANGE_LABELS.get(range_key, range_key)
    bucket_label = _humanize_seconds(bucket_seconds)

    # ---- Drafting-studio chart: amber/steel, gradient fills, local time, mono labels ----
    AMBER, STEEL, INK, MUTED, GRID = "#c2570c", "#3f5765", "#15171c", "#6f6b60", "#e3ded3"

    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=130)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    if timestamps:
        ax.plot(timestamps, temp_plot, color=AMBER, linewidth=2, marker="o", markersize=3,
                markerfacecolor=AMBER, markeredgecolor="white", markeredgewidth=0.5, label="Temperature °C")
        ax.plot(timestamps, hum_plot, color=STEEL, linewidth=2, marker="o", markersize=3,
                markerfacecolor=STEEL, markeredgecolor="white", markeredgewidth=0.5, label="Humidity %")
        ax.fill_between(timestamps, temp_plot, color=AMBER, alpha=0.10)
        ax.fill_between(timestamps, hum_plot, color=STEEL, alpha=0.08)
        ax.xaxis.set_major_locator(AutoDateLocator())
        ax.xaxis.set_major_formatter(DateFormatter(time_fmt))
        fig.autofmt_xdate(rotation=0, ha="center")
        # Place the legend ABOVE the plot area, side by side (not over the data lines)
        leg = ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=2,
                        frameon=False, fontsize=9, handlelength=1.6,
                        columnspacing=3.0, borderaxespad=0.0)
        for txt in leg.get_texts():
            txt.set_color(INK)
            txt.set_fontfamily("monospace")
    else:
        ax.text(0.5, 0.5, "No readings in this range", ha="center", va="center",
                color=MUTED, fontfamily="monospace")
        ax.set_xticks([])
        ax.set_yticks([])

    ax.set_xlabel("Time (local)", color=MUTED, fontsize=9, fontfamily="monospace")
    ax.set_ylabel("Reading", color=MUTED, fontsize=9, fontfamily="monospace")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(INK)
    ax.spines["bottom"].set_color(INK)
    ax.tick_params(colors=MUTED, labelsize=8)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontfamily("monospace")
    plt.tight_layout()

    # Save chart to temporary image file
    img_path = os.path.join(tempfile.gettempdir(), f"chart_{uuid4().hex}.png")
    plt.savefig(img_path, facecolor="white", bbox_inches="tight")
    plt.close()

    generated_at = datetime.now(UTC).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    try:
        html = templates.get_template("pdf_sensor_report.html").render({
            "sensor": sensor,
            "building_name": building_name,
            "table_rows": table_rows,
            "reading_count": len(readings),
            "bucket_count": len(table_rows),
            "avg_temp": avg_temp,
            "avg_hum": avg_hum,
            "range_label": range_label,
            "bucket_label": bucket_label,
            "tz_name": LOCAL_TZ.key,
            "generated_at": generated_at,
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
