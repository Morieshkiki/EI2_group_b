from pydantic import BaseModel
from typing import Optional, List


# this part uses Demo 1 (building_model.py) for the building data model.
class BuildingModel(BaseModel):
    id: str
    name: str
    address: str
    floors: Optional[int] = 1
    inhabitants: Optional[int] = 0
    has_elevator: Optional[bool] = False
    has_parking: Optional[bool] = False
