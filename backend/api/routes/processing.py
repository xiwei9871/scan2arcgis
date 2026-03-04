"""
Processing API routes for task execution and result retrieval.

Provides endpoints for starting processing tasks and retrieving results.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from core.pipeline import ProcessingPipeline
from api.routes.upload import tasks
from api.websocket import manager
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/processing", tags=["processing"])


class ProcessingRequest(BaseModel):
    """Request model for starting a processing task."""
    task_id: str = Field(..., description="Unique task identifier")
    auto_process: bool = Field(
        default=False,
        description="Whether to auto-process (skip georeferencing and process immediately)"
    )
    enable_georeferencing: bool = Field(
        default=True,
        description="Whether to apply georeferencing if GCPs available"
    )


class ProcessingStatus(BaseModel):
    """Status model for processing tasks."""
    task_id: str
    status: str
    progress: float = 0.0
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None


async def run_processing_task(
    task_id: str,
    auto_process: bool = False,
    enable_georeferencing: bool = True
) -> None:
    """
    Background task to execute the processing pipeline.

    Args:
        task_id: Unique task identifier
        auto_process: Whether to skip georeferencing
        enable_georeferencing: Whether to enable georeferencing
    """
    try:
        # Get task from in-memory storage
        if task_id not in tasks:
            logger.error(f"Task {task_id} not found")
            await manager.send_error(task_id, "Task not found")
            return

        task = tasks[task_id]

        # Update task status to processing
        task.status = "processing"
        await manager.send_progress(task_id, 0.0, "Starting processing...")

        # Determine file path
        # Try different extensions
        file_path = None
        for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
            test_path = os.path.join("uploads", f"{task_id}{ext}")
            if os.path.exists(test_path):
                file_path = test_path
                break

        # If not found by task_id, try to find any file starting with task_id
        if file_path is None and os.path.exists("uploads"):
            for filename in os.listdir("uploads"):
                if filename.startswith(task_id):
                    file_path = os.path.join("uploads", filename)
                    break

        if file_path is None:
            raise FileNotFoundError(f"File not found for task {task_id}")

        logger.info(f"Processing file: {file_path}")

        # Create output directory
        output_dir = os.path.join("outputs", task_id)
        os.makedirs(output_dir, exist_ok=True)

        # Create processing pipeline
        pipeline = ProcessingPipeline(
            task_id=task_id,
            enable_georeferencing=enable_georeferencing
        )

        # Execute processing
        result = await pipeline.process(file_path, output_dir)

        # Update task status to completed
        task.status = "completed"
        task.progress = 1.0

        await manager.send_complete(task_id, result)
        logger.info(f"Processing complete for task {task_id}")

    except FileNotFoundError as e:
        logger.error(f"File not found for task {task_id}: {e}")
        if task_id in tasks:
            tasks[task_id].status = "failed"
            tasks[task_id].error_message = str(e)
        await manager.send_error(task_id, f"File not found: {e}")

    except Exception as e:
        logger.error(f"Processing error for task {task_id}: {e}")
        if task_id in tasks:
            tasks[task_id].status = "failed"
            tasks[task_id].error_message = str(e)
        await manager.send_error(task_id, f"Processing failed: {e}")


@router.post("/start", response_model=dict)
async def start_processing(
    request: ProcessingRequest,
    background_tasks: BackgroundTasks
) -> dict:
    """
    Start a processing task in the background.

    Args:
        request: Processing request with task_id and options
        background_tasks: FastAPI background tasks manager

    Returns:
        Confirmation message with task_id
    """
    if request.task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {request.task_id} not found. Please upload a file first."
        )

    task = tasks[request.task_id]

    if task.status == "processing":
        return {
            "message": "Task is already processing",
            "task_id": request.task_id,
            "status": "processing"
        }

    if task.status == "completed":
        return {
            "message": "Task is already completed",
            "task_id": request.task_id,
            "status": "completed"
        }

    # Add background task
    background_tasks.add_task(
        run_processing_task,
        request.task_id,
        request.auto_process,
        request.enable_georeferencing
    )

    logger.info(f"Started processing task {request.task_id}")

    return {
        "message": "Processing task started",
        "task_id": request.task_id,
        "status": "started"
    }


@router.get("/status/{task_id}", response_model=ProcessingStatus)
async def get_processing_status(task_id: str) -> ProcessingStatus:
    """
    Get the current status of a processing task.

    Args:
        task_id: Unique task identifier

    Returns:
        Processing status information
    """
    if task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    task = tasks[task_id]

    return ProcessingStatus(
        task_id=task_id,
        status=task.status,
        progress=task.progress,
        message="Task completed" if task.status == "completed" else "",
        error=task.error_message
    )


@router.get("/result/{task_id}")
async def get_result(task_id: str) -> dict:
    """
    Get processing result files for a task.

    Args:
        task_id: Unique task identifier

    Returns:
        Dictionary with task status and list of result files
    """
    if task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    task = tasks[task_id]

    output_dir = os.path.join("outputs", task_id)
    result_files = []

    if os.path.exists(output_dir):
        for file in os.listdir(output_dir):
            if file.endswith('.geojson') or file.endswith('.shp'):
                result_files.append(f"/api/files/{task_id}/{file}")

    return {
        "task_id": task_id,
        "status": task.status,
        "result_files": result_files,
        "error": task.error_message
    }


@router.post("/cancel/{task_id}")
async def cancel_processing(task_id: str) -> dict:
    """
    Cancel a processing task (placeholder for future enhancement).

    Args:
        task_id: Unique task identifier

    Returns:
        Confirmation message
    """
    if task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    task = tasks[task_id]

    # TODO: Implement proper task cancellation
    # For now, just return a message
    logger.info(f"Cancel requested for task {task_id}")

    return {
        "message": f"Cancel request received for task {task_id}",
        "note": "Task cancellation not yet implemented"
    }
