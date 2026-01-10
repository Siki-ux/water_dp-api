from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DataSourceBase(BaseModel):
    name: str
    type: str = Field(..., description="POSTGRES, GEOSERVER, TIMEIO")
    connection_details: Dict[str, Any]


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    connection_details: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    sql: str


class DataSourceResponse(DataSourceBase):
    id: UUID
    project_id: UUID

    class Config:
        from_attributes = True

    @property
    def connection_details_safe(self) -> Dict[str, Any]:
        pass


class DataSourceResponseSafe(DataSourceResponse):
    pass
