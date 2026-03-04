"""
File download API routes for serving processed results.

Provides endpoints for downloading individual files and ZIP archives.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List
import os
import zipfile
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/download/{task_id}")
async def download_results(task_id: str) -> FileResponse:
    """
    Download processing results as a ZIP archive.

    Args:
        task_id: Unique task identifier

    Returns:
        ZIP file containing all results

    Raises:
        HTTPException: If results not found
    """
    output_dir = os.path.join("outputs", task_id)

    if not os.path.exists(output_dir):
        raise HTTPException(
            status_code=404,
            detail=f"Results not found for task {task_id}"
        )

    # Create ZIP file
    zip_path = os.path.join("outputs", f"{task_id}_results.zip")

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, arcname)

        logger.info(f"Created ZIP archive for task {task_id}")

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{task_id}_results.zip"
        )

    except Exception as e:
        logger.error(f"Error creating ZIP for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create download archive: {str(e)}"
        )


@router.get("/{task_id}/{filename}")
async def get_file(task_id: str, filename: str) -> FileResponse:
    """
    Get an individual result file.

    Args:
        task_id: Unique task identifier
        filename: Name of the file to download

    Returns:
        Requested file

    Raises:
        HTTPException: If file not found
    """
    # Security: Validate filename to prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )

    file_path = os.path.join("outputs", task_id, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {filename}"
        )

    # Determine media type
    if filename.endswith('.geojson'):
        media_type = "application/geo+json"
    elif filename.endswith('.shp'):
        media_type = "application/x-esri-shapefile"
    elif filename.endswith('.tiff') or filename.endswith('.tif'):
        media_type = "image/tiff"
    elif filename.endswith('.png'):
        media_type = "image/png"
    elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
        media_type = "image/jpeg"
    else:
        media_type = "application/octet-stream"

    logger.info(f"Serving file {filename} for task {task_id}")

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename
    )


@router.get("/list/{task_id}")
async def list_files(task_id: str) -> dict:
    """
    List all available result files for a task.

    Args:
        task_id: Unique task identifier

    Returns:
        Dictionary with list of files
    """
    output_dir = os.path.join("outputs", task_id)

    if not os.path.exists(output_dir):
        return {
            "task_id": task_id,
            "files": []
        }

    files = []
    for file in os.listdir(output_dir):
        file_path = os.path.join(output_dir, file)
        if os.path.isfile(file_path):
            files.append({
                "filename": file,
                "url": f"/api/files/{task_id}/{file}",
                "size": os.path.getsize(file_path)
            })

    return {
        "task_id": task_id,
        "files": files
    }
