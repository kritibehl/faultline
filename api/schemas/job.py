from pydantic import BaseModel, Field
from typing import Any, Dict
import uuid

class JobCreate(BaseModel):
    type: str = Field(..., min_length=1)
    payload: Dict[str, Any]

class JobCreated(BaseModel):
    id: uuid.UUID
    state: str
