from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# the data models here follow Demo 1 (building_model.py) — these are the sensor versions.
class SensorModel(BaseModel):
    id: str
    name: str
    building_id: str
    type: str
    sensor_coord: Optional[List[float]] = Field(
        None, description="3D world coordinates [x, y, z]"
    )

class SensorReading(BaseModel):
    type: Optional[str] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    sensor_id: Optional[str] = None
    timestamp: Optional[datetime] = None
