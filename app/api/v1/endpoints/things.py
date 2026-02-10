import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import get_db
from app.core.exceptions import (
    ResourceNotFoundException,
)
from app.models.user_context import Project
from app.schemas.frost.datastream import Datastream, Observation
from app.schemas.frost.thing import Thing
from app.schemas.sensor import (
    IngestionResponse,
    SensorCreate,
    SensorCreationResponse,
)

# Use async service for non-blocking FROST calls
from app.services.async_thing_service import AsyncThingService
from app.services.timeio.orchestrator import TimeIOOrchestrator

logger = logging.getLogger(__name__)


router = APIRouter()

orchestrator = TimeIOOrchestrator()


@router.get(
    "/{schema_name}/all",
    response_model=List[Thing],
    summary="List Sensors",
    description="Returns all sensors for a project.",
)
async def list_sensors(
    schema_name: str, expand: list[str] = ["Locations", "Datastreams"]
):
    """
    Fetch all sensors for a project (async).
    """
    things = await AsyncThingService.get_all_things(schema_name, expand)

    if things is None:
        return []
    return things


@router.get(
    "/{sensor_uuid}",
    response_model=Thing,
    summary="Get Sensor Details",
    description="Fetch Sensor details from via FROST.",
)
async def get_thing_details(
    sensor_uuid: str, expand: list[str] = ["Locations", "Datastreams"]
):
    """
    Get Sensor details from via FROST (async).
    """
    schema_name = await AsyncThingService.get_schema_from_uuid(sensor_uuid)
    if schema_name is None:
        raise ResourceNotFoundException("Schema not found")
    thing_service = AsyncThingService(schema_name)
    thing = await thing_service.get_thing(sensor_uuid, expand)
    if not thing:
        raise ResourceNotFoundException("Thing not found")
    return thing


@router.post(
    "/",
    response_model=SensorCreationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Sensor (Autonomous v3)",
    description="Registers a new sensor in ConfigDB and triggers TSM workers via MQTT. Bypasses legacy APIs.",
)
async def create_sensor(
    sensor: SensorCreate,
    database: Session = Depends(get_db),
    user: dict = Depends(deps.get_current_user),
):
    """
    Create a new sensor autonomously (v3).

    This bypasses the legacy thing-management-api and works directly with
    the TimeIO ConfigDB and MQTT bus.
    """
    try:
        location = None
        if sensor.latitude is not None and sensor.longitude is not None:
            location = {"latitude": sensor.latitude, "longitude": sensor.longitude}

        # Fetch project details for refined schema naming
        project = (
            database.query(Project).filter(Project.id == sensor.project_uuid).first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        result = orchestrator.create_sensor(
            project_group=project.authorization_provider_group_id or project.name,
            sensor_name=sensor.sensor_name,
            description=sensor.description,
            mqtt_device_type=sensor.device_type,
            geometry=location,
            properties=(
                [prop.dict() for prop in sensor.properties]
                if sensor.properties
                else None
            ),
            project_schema=project.schema_name,
        )

        # Automatic Link to Project
        from app.services.project_service import ProjectService

        try:
            # Check permissions implicitly via add_sensor (requires 'editor')
            # The result['uuid'] is the new Thing UUID
            ProjectService.add_sensor(
                database,
                project_id=sensor.project_uuid,
                sensor_id=result["uuid"],
                user=user,
            )
        except Exception as error:
            # We log but don't fail the whole request because the sensor IS created in TimeIO
            # The user might just need to link it manually if this failed (e.g. permissions/race condition)
            print(f"Failed to auto-link sensor to project: {error}")

        if location:
            result["latitude"] = location["latitude"]
            result["longitude"] = location["longitude"]

        return result
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sensor: {str(error)}",
        )


@router.get(
    "/{uuid}/datastreams",
    response_model=List[Datastream],
    summary="Get Sensor Datastreams (FROST)",
    description="Get datastreams for a sensor via FROST.",
)
async def get_sensor_datastreams(
    sensor_uuid: str,
):
    """
    Get datastreams for a sensor via FROST (async).
    """
    schema_name = await AsyncThingService.get_schema_from_uuid(sensor_uuid)
    if schema_name is None:
        raise ResourceNotFoundException("Schema not found")
    thing_service = AsyncThingService(schema_name)
    datastreams = await thing_service.get_sensor_datastreams(sensor_uuid)
    if not datastreams:
        return []
    return datastreams


@router.get(
    "/{sensor_uuid}/datastreams/{datastream_name:path}",
    response_model=Datastream,
    summary="Get Sensor Datastream (FROST)",
    description="Get datastream for a sensor via FROST.",
)
async def get_sensor_datastream(
    sensor_uuid: str,
    datastream_name: str,
):
    """
    Get datastream for a sensor via FROST (async).
    """
    schema_name = await AsyncThingService.get_schema_from_uuid(sensor_uuid)
    if schema_name is None:
        raise ResourceNotFoundException("Schema not found")
    thing_service = AsyncThingService(schema_name)
    datastream = await thing_service.get_sensor_datastream(sensor_uuid, datastream_name)
    if not datastream:
        raise ResourceNotFoundException("Datastream not found")
    return datastream


@router.get(
    "/{sensor_uuid}/datastream/{datastream_name:path}/observations",
    response_model=List[Observation],
    summary="Get Sensor Data (FROST)",
    description="Get generic time-series data for a sensor via FROST. Optionally filter by datastream name.",
)
async def get_sensor_observations(
    sensor_uuid: str,
    datastream_name: Optional[str] = None,
    limit: int = 100,
    start_time: str = None,
    end_time: str = None,
    order_by: str = "resultTime desc",
    select: str = "@iot.id,phenomenonTime,result,resultTime",
):
    """
    Get generic time-series data for a sensor via FROST (async).
    """
    schema_name = await AsyncThingService.get_schema_from_uuid(sensor_uuid)
    if schema_name is None:
        raise ResourceNotFoundException("Schema not found")
    thing_service = AsyncThingService(schema_name)
    observations = await thing_service.get_observations_by_name_from_sensor_uuid(
        sensor_uuid, datastream_name, start_time, end_time, limit, order_by, select
    )
    if not observations:
        return []
    return observations


@router.post(
    "/{uuid}/ingest/csv",
    response_model=IngestionResponse,
    summary="Ingest CSV Data",
    description="Upload a CSV file to the Thing's S3 bucket for ingestion.",
)
async def ingest_csv(
    uuid: str,
    file: UploadFile = File(...),
    database: Session = Depends(get_db),
    # user: dict = Depends(deps.get_current_user) # Optional auth check
):
    """
    Upload CSV for ingestion.
    """
    from app.services.ingestion_service import IngestionService

    return await IngestionService.upload_csv(uuid, file)
