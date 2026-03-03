"""
File upload API routes for the geological map digitizer.
"""

import os
import uuid
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from models.task import Task, TaskStatus, TaskUploadResponse


# Configure upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory task storage (in production, use a database)
tasks: Dict[str, Task] = {}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
ALLOWED_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/pdf": ".pdf"
}


router = APIRouter(prefix="/api/upload", tags=["upload"])


def validate_file(file: UploadFile) -> None:
    """
    Validate uploaded file type and extension.

    Args:
        file: The uploaded file to validate

    Raises:
        HTTPException: If file type is not allowed
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_MIME_TYPES.keys())}"
        )

    # Check file extension
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
        )


@router.post("/image", response_model=TaskUploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image file for processing.

    Args:
        file: The uploaded file (PNG, JPEG, or PDF)

    Returns:
        Task object with task_id, filename, status, and file_path

    Raises:
        HTTPException: If file validation fails
    """
    # Validate file type
    validate_file(file)

    # Generate unique file ID
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    unique_filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename

    # Save file to disk
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        await file.close()

    # Create task
    task = Task.create(filename=file.filename or "unknown")
    tasks[task.id] = task

    return {
        "id": task.id,
        "filename": task.filename,
        "status": task.status,
        "progress": task.progress,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "file_path": str(file_path)
    }


@router.get("/task/{task_id}", response_model=Task)
async def get_task_status(task_id: str):
    """
    Get the status of a processing task.

    Args:
        task_id: The unique task identifier

    Returns:
        Task object with current status

    Raises:
        HTTPException: If task is not found
    """
    if task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task not found: {task_id}"
        )

    task = tasks[task_id]
    return {
        "id": task.id,
        "filename": task.filename,
        "status": task.status,
        "progress": task.progress,
        "error_message": task.error_message,
        "created_at": task.created_at
    }
