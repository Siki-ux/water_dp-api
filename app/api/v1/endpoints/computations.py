import os
import uuid
import shutil
from typing import List, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from celery.result import AsyncResult
from app.tasks.computation_tasks import run_computation_task
from app.api import deps
from app.core.database import get_db
from app.models.computations import ComputationScript
from app.services.project_service import ProjectService
from pydantic import BaseModel, UUID4

router = APIRouter()

class ComputationScriptRead(BaseModel):
    id: UUID4
    name: str
    description: str | None
    project_id: UUID4
    filename: str

    class ConfigDict:
        from_attributes = True

class ComputationRequest(BaseModel):
    params: dict = {}

COMPUTATIONS_DIR = "app/computations"

@router.post("/upload", response_model=ComputationScriptRead)
def upload_computation_script(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(None),
    project_id: UUID4 = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(deps.get_current_user),
):
    """
    Upload a new computation script and associate it with a project.
    Requires 'editor' access to the project.
    """
    # Check Project Access (Editor required)
    ProjectService._check_access(db, project_id, current_user, required_role="editor")

    if not os.path.exists(COMPUTATIONS_DIR):
        os.makedirs(COMPUTATIONS_DIR)

    # Secure filename - ensure valid python module name (no dashes)
    project_hex = project_id.hex if hasattr(project_id, "hex") else str(project_id).replace("-", "")
    safe_filename = f"{project_hex}_{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(COMPUTATIONS_DIR, safe_filename)

    # Save File
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save to DB
    db_script = ComputationScript(
        name=name,
        description=description,
        filename=safe_filename,
        project_id=project_id,
        uploaded_by=current_user.get("sub", "unknown")
    )
    db.add(db_script)
    db.commit()
    db.refresh(db_script)
    
    return db_script

@router.post("/run/{script_id}")
def run_computation(
    script_id: UUID4, 
    request: ComputationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(deps.get_current_user),
):
    """
    Run a computation script by ID.
    Requires 'viewer' access to the associated project.
    """
    script = db.query(ComputationScript).filter(ComputationScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Check Project Access (Viewer required)
    ProjectService._check_access(db, script.project_id, current_user, required_role="viewer")

    # Check file existence
    script_path = os.path.join(COMPUTATIONS_DIR, script.filename)
    if not os.path.exists(script_path):
         raise HTTPException(status_code=404, detail="Script file missing on server")

    # Pass the filename (module name logic will handle it in the task)
    # We strip .py extension for the module loader if needed, or handle it in task
    # Let's pass the filename and let the task resolve it.
    
    # NOTE: The task currently expects a module path like "app.computations.xyz".
    # Our filenames are now "project-uuid_xyz.py".
    # The module name would be "app.computations.project-uuid_xyz" (without .py)
    
    module_name = script.filename
    if module_name.endswith(".py"):
        module_name = module_name[:-3]

    task = run_computation_task.delay(module_name, request.params)
    return {"task_id": task.id, "status": "submitted"}

@router.get("/list/{project_id}", response_model=List[ComputationScriptRead])
def list_project_computations(
    project_id: UUID4,
    db: Session = Depends(get_db),
    current_user: dict = Depends(deps.get_current_user),
):
    """
    List scripts for a specific project.
    """
    ProjectService._check_access(db, project_id, current_user, required_role="viewer")
    
    scripts = db.query(ComputationScript).filter(ComputationScript.project_id == project_id).all()
    return scripts

@router.get("/tasks/{task_id}")
def get_computation_status(task_id: str):
    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }
