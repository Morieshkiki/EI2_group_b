from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.routers.building_router import router as building_router
from app.routers.sensor_router import router as sensor_router

# this part uses Demo 1 (main.py): it creates the FastAPI app, includes the routers,
# and redirects the home page ("/") to the buildings list.
app = FastAPI()

app.include_router(building_router)
app.include_router(sensor_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to your static folder (adjust if necessary)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_folder_path = os.path.join(BASE_DIR, "static")

# Serve static files from the 'static' folder
app.mount("/static", StaticFiles(directory=static_folder_path), name="static")


@app.get("/")
def read_root():
    return RedirectResponse("/buildings/management", status_code=303)
