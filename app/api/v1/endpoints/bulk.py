from fastapi import APIRouter, UploadFile, File, Depends
from app.tasks.import_tasks import import_geojson_task, import_timeseries_task
from celery.result import AsyncResult
from app.api.deps import get_current_active_superuser

router = APIRouter()

@router.post("/import/geojson", dependencies=[Depends(get_current_active_superuser)])
async def import_geojson(file: UploadFile = File(...)):
    content = await file.read()
    # Decode to string for celery serialization - valid geojson is text
    content_str = content.decode("utf-8") 
    task = import_geojson_task.delay(content_str)
    return {"task_id": task.id, "status": "submitted"}

@router.post("/import/timeseries", dependencies=[Depends(get_current_active_superuser)])
async def import_timeseries(file: UploadFile = File(...)):
    content = await file.read()
    content_str = content.decode("utf-8")
    task = import_timeseries_task.delay(content_str)
    return {"task_id": task.id, "status": "submitted"}

@router.get("/tasks/{task_id}")
def get_import_status(task_id: str):
    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }
