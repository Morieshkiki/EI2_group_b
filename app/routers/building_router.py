
# the following code is largely based on the building_router.py from Demo 1, but with additional endpoints
# the additional code was in part written using the https://docs.python.org/3/ as reference and Autocomplete and to fix bugs AI was used in a manner like: "Fix issue x" or "add feature y"


from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Body, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.building_model import BuildingModel as Building
from app.util import mongo_db_connector

from app.util.pdf_generator import html_to_pdf # this is the function we created in pdf_generator.py to convert HTML to PDF, it uses xhtml2pdf under the hood
from xhtml2pdf import pisa # library for converting HTML to PDF
from io import BytesIO# temporary in-memory file for PDF output
# Import necessary libraries FOR pessimistic locking
from datetime import datetime, timedelta
from fastapi import Body,HTTPException
from fastapi.responses import JSONResponse

import os
import subprocess
import tempfile

from pymongo import MongoClient
import gridfs
import app.config as config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# the building routes and database setup here are based on Demo 1 (building_router.py):
# listing, adding, editing and fetching buildings. The locking, IFC/XKT and report
# features were added on top.
router = APIRouter(prefix="/buildings", tags=["buildings"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 1. Endpoints for frontend tempaltes rendering


@router.get("/management")
async def building_management(request: Request):
    buildings = await get_buildings()
    return templates.TemplateResponse("buildings.html", {"request": request, "buildings": buildings})

# 2. Endpoints for general operations on ALL buildings


@router.get("/")
async def read_buildings():
    """Fetches all buildings from the database."""
    buildings = await get_buildings()
    return buildings


@router.post("/")
async def create_building(building_data: Building):
    """Creates a new building and stores it in the database."""
    buildings_collection = mongo_db_connector.init_db("buildings")
    buildings_collection.insert_one(building_data.model_dump())
    return {"message": "Building added successfully", "building": building_data}

# 3. Endpoints for operations on a specific building


@router.get("/{building_id}")
async def read_building(building_id: str):
    """Fetches specific building from the database by building_id."""
    buildings = await get_buildings(id=building_id)
    if not buildings:
        raise HTTPException(status_code=404, detail="Building not found")
    return buildings[0]


@router.put("/{building_id}")
async def update_building(building_id: str, building_data: Building):
    """Updates a specific building in the database."""
    buildings_collection = mongo_db_connector.init_db("buildings")
    buildings_collection.update_one({"id": building_id}, {
                                    "$set": building_data.model_dump()})
    return {"message": "Building updated successfully", "building": building_data}


@router.delete("/{building_id}")
async def delete_building(building_id: str):
    """Deletes a specific building from the database (and its IFC and XKT files if they exist)."""
    buildings_collection = mongo_db_connector.init_db("buildings")
    result = buildings_collection.delete_one({"id": building_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Building not found")
    
    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs_ifc = gridfs.GridFS(db, collection="ifc_files")
    fs_xkt = gridfs.GridFS(db, collection="xkt_files")

    # Delete IFC file from GridFS
    file_ifc = fs_ifc.find_one({"building_id": building_id})
    if file_ifc:
        fs_ifc.delete(file_ifc._id)

    # Delete XKT file from GridFS
    file_xkt = fs_xkt.find_one({"building_id": building_id})
    if file_xkt:
        fs_xkt.delete(file_xkt._id)

    # Also delete the XKT file from the static directory if it exists
    output_dir = os.path.join(BASE_DIR, "static", "xkt_models")
    xkt_filename = f"{building_id}.xkt"
    xkt_file_path = os.path.join(output_dir, xkt_filename)
    
    if os.path.exists(xkt_file_path):
        try:
            os.remove(xkt_file_path)
            print(f"Deleted XKT file from static directory: {xkt_file_path}")
        except Exception as e:
            print(f"Failed to delete XKT file from static directory: {xkt_file_path}, error: {e}")

    return {"message": "Building and associated files deleted successfully", "building_id": building_id}

@router.post("/{building_id}/edit")
async def edit_building(building_id: str, building_data: dict = Body(...)):
    """Updates a specific building using JSON (for use in modals)."""
    buildings_collection = mongo_db_connector.init_db("buildings")

    result = buildings_collection.update_one({"id": building_id}, {"$set": building_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Building not found")

    return {"message": "Building updated successfully"}

# 4. Endpoints for specific operations on buildings (IFC file upload, sensors, etc.)


@router.get("/{building_id}/sensors")
async def get_building_sensors(building_id: str):
    """Returns sensors for a specific building."""
    sensors_collection = mongo_db_connector.init_db("sensors")
    sensors = list(sensors_collection.find({"building_id": building_id}))
    for s in sensors:
        s.pop("_id", None)
    return sensors


@router.get("/{building_id}/dashboard-data")
async def building_dashboard_data(building_id: str):
    """Generates a dashboard (JSON format) for a specific building --> no. of sensors, sensor types, etc."""
    sensors_collection = mongo_db_connector.init_db("sensors")
    sensors = list(sensors_collection.find({"building_id": building_id}))
    for sensor in sensors:
        sensor.pop("_id", None)
    return {
        "building_id": building_id,
        "total_sensors": len(sensors),
        "sensors": sensors
    }

@router.post("/{building_id}/upload_ifc")
async def upload_ifc_file(building_id: str, file: UploadFile = File(...)):
    """Uploads an IFC file for a specific building using GridFS."""

    if not file.filename.endswith('.ifc'):
        raise HTTPException(status_code=400, detail="File must be an IFC file")

    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs = gridfs.GridFS(db, collection="ifc_files")

    content = await file.read()
    file_id = fs.put(
        content, filename=f"{building_id}.ifc", building_id=building_id)

    return {"message": "IFC file uploaded successfully", "file_id": str(file_id)}

@router.post("/{building_id}/convert_to_xkt")
async def convert_ifc_to_xkt(building_id: str):
    from subprocess import run
    from uuid import uuid4

    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs_ifc = gridfs.GridFS(db, collection="ifc_files")
    fs_xkt = gridfs.GridFS(db, collection="xkt_files")  # NEW

    file = fs_ifc.find_one({"building_id": building_id})
    if not file:
        raise HTTPException(status_code=404, detail="IFC file not found")

    # Save IFC to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as temp_ifc:
        temp_ifc.write(file.read())
        temp_ifc_path = temp_ifc.name

    # Define output path for XKT
    output_filename = f"{building_id}.xkt"
    output_dir = os.path.join(BASE_DIR, "static", "xkt_models")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    print(f"Output directory: {output_dir}")
    print(f"Output file path: {output_path}")


    # Run Node.js conversion script
    result = subprocess.run(
        ["node", "app/convert/convert.js", temp_ifc_path, output_path],
        capture_output=True, text=True
    )

    

    os.remove(temp_ifc_path)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {result.stderr}")

    # Save the generated .xkt to MongoDB (GridFS)
    with open(output_path, "rb") as xkt_file:
        fs_xkt.put(xkt_file.read(), filename=output_filename, building_id=building_id)

    return {
        "message": "IFC converted successfully",
        "xkt_path": f"/static/xkt_models/{output_filename}"
    }

@router.delete("/{building_id}/ifc_file")
async def delete_ifc_file(building_id: str):
    """Deletes IFC file from GridFS and its corresponding XKT file from GridFS and the static directory for a specific building."""
    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    
    fs_ifc = gridfs.GridFS(db, collection="ifc_files")
    fs_xkt = gridfs.GridFS(db, collection="xkt_files")

    # Delete IFC file from GridFS
    file_ifc = fs_ifc.find_one({"building_id": building_id})
    if not file_ifc:
        raise HTTPException(status_code=404, detail="IFC file not found")

    fs_ifc.delete(file_ifc._id)

    # Delete the associated XKT file from GridFS
    file_xkt = fs_xkt.find_one({"building_id": building_id})
    if file_xkt:
        fs_xkt.delete(file_xkt._id)

    # Also delete the XKT file from the static directory if it exists
    output_dir = os.path.join(BASE_DIR, "static", "xkt_models")
    xkt_filename = f"{building_id}.xkt"
    xkt_file_path = os.path.join(output_dir, xkt_filename)
    
    if os.path.exists(xkt_file_path):
        try:
            os.remove(xkt_file_path)
            print(f"Deleted XKT file from static directory: {xkt_file_path}")
        except Exception as e:
            print(f"Failed to delete XKT file from static directory: {xkt_file_path}, error: {e}")

    return {"message": "IFC and associated XKT files deleted successfully", "building_id": building_id}


@router.get("/{building_id}/model.ifc")
async def get_ifc_file(building_id: str):
    """Fetches IFC file for a specific building."""
    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs = gridfs.GridFS(db, collection="ifc_files")

    grid_out = fs.find_one({"building_id": building_id})
    if not grid_out:
        raise HTTPException(
            status_code=404, detail="IFC file not found for this building")

    return StreamingResponse(
        grid_out,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={grid_out.filename}"}
    )


@router.get("/{building_id}/dashboard")
async def building_dashboard(request: Request, building_id: str):
    """Renders a dashboard (visual) for a specific building."""
    buildings = await get_buildings(id=building_id)
    if not buildings:
        raise HTTPException(status_code=404, detail="Building not found")
    building = buildings[0]

    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs = gridfs.GridFS(db, collection="ifc_files")
    has_ifc = fs.find_one({"building_id": building_id}) is not None

    sensors_collection = mongo_db_connector.init_db("sensors")
    sensors = list(sensors_collection.find({"building_id": building_id}))
    for sensor in sensors:
        sensor.pop("_id", None)

    return templates.TemplateResponse("building_dashboard.html", {
        "request": request,
        "building": building,
        "sensors": sensors,
        "building_id": building_id,
        "has_ifc": has_ifc
    })

@router.get("/{building_id}/model.xkt")
async def get_xkt_file(building_id: str):
    """Fetches XKT file for a specific building from MongoDB."""
    client = MongoClient(config.MONGO_ADDRESS)
    db = client[config.MONGO_DB_NAME]
    fs = gridfs.GridFS(db, collection="xkt_files")

    file = fs.find_one({"building_id": building_id})
    if not file:
        raise HTTPException(status_code=404, detail="XKT file not found")

    return StreamingResponse(
        file,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file.filename}"}
    )


@router.get("/{building_id}/report")
async def generate_building_report(request: Request, building_id: str):
    buildings_db = mongo_db_connector.init_db("buildings")
    sensors_db = mongo_db_connector.init_db("sensors")
    readings_db = mongo_db_connector.init_db("sensor_readings")

    building = buildings_db.find_one({"id": building_id})
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    building.pop("_id", None)

    sensors = list(sensors_db.find({"building_id": building_id}))
    for s in sensors:
        s.pop("_id", None)
        readings = list(readings_db.find({"sensor_id": s["id"]}))
        temps = [r["temperature"] for r in readings if "temperature" in r]
        hums = [r["humidity"] for r in readings if "humidity" in r]
        s["avg_temp"] = round(sum(temps) / len(temps), 2) if temps else None
        s["avg_humidity"] = round(sum(hums) / len(hums), 2) if hums else None

    # Render HTML
    html = templates.get_template("pdf_building_report.html").render(
        {"request": request, "building": building, "sensors": sensors}
    )

    pdf = BytesIO()
    pisa.CreatePDF(src=html, dest=pdf)
    pdf.seek(0)
# AI-assisted implementation after asking how generated PDFs can be
# returned directly in FastAPI without saving temporary files
    return StreamingResponse(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename=building_{building_id}_report.pdf"
    })


async def get_buildings(name: str = None, project: str = None, location: str = None, id: str = None) -> list:
    """Fetches buildings from the database depending on received params."""
    buildings_collection = mongo_db_connector.init_db("buildings")
    query = {}
    if name:
        query["name"] = name
    if project:
        query["project"] = project
    if location:
        query["location"] = location
    if id:
        query["id"] = id
    buildings = buildings_collection.find(query)
    buildings_return = []
    for building in buildings:
        building.pop("_id", None)
        buildings_return.append(building)
    return buildings_return


# 5. Endpoints for the implementation of Pessimistic locking 

@router.post("/{building_id}/lock")
async def lock_building(building_id: str, lock_info: dict = Body(...)):
    """
    Lock a building unless already locked (admins can override).
    lock_info = {
        "user": "username",
        "is_admin": true or false
    }
    """
    user = lock_info.get("user")
    is_admin = lock_info.get("is_admin", False) # this is a simple way to indicate if the user is an admin, in a real application you would have proper authentication and role management

    buildings_collection = mongo_db_connector.init_db("buildings")
    building = buildings_collection.find_one({"id": building_id})
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    current_lock = building.get("lock")

    if current_lock:
        lock_time = datetime.fromisoformat(current_lock["timestamp"])
        if datetime.utcnow() - lock_time < timedelta(minutes=8) and not is_admin:
            return JSONResponse(status_code=423, content={
                "message": "Building is already locked",
                "lock": current_lock
            })

    new_lock = {
        "user": user,
        "timestamp": datetime.utcnow().isoformat()
    }

    buildings_collection.update_one(
        {"id": building_id},
        {"$set": {"lock": new_lock}}
    )

    return {"message": "Building locked", "lock": new_lock}

@router.post("/{building_id}/unlock")
async def unlock_building(building_id: str, unlock_info: dict = Body(...)):
    """
    Unlock a building — allowed if user owns lock or is admin.
    unlock_info = {
        "user": "username",
        "is_admin": true or false
    }
    """
    user = unlock_info.get("user")
    is_admin = unlock_info.get("is_admin", False) # this is a simple way to indicate if the user is an admin, in a real application you would have proper authentication and role management

    buildings_collection = mongo_db_connector.init_db("buildings")
    building = buildings_collection.find_one({"id": building_id})
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    current_lock = building.get("lock")
    if not current_lock:
        return {"message": "Building was not locked"}

    if current_lock["user"] != user and not is_admin:
        raise HTTPException(status_code=403, detail="You are not the lock owner or admin")

    buildings_collection.update_one(
        {"id": building_id},
        {"$unset": {"lock": ""}}
    )

    return {"message": "Building unlocked"}
