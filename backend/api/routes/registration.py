"""
Registration API routes for georeferencing geological maps.

Provides endpoints for submitting control points and executing
georeferencing transformations.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from core.registration import GeoRegistration
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/registration", tags=["registration"])


class ControlPoint(BaseModel):
    """A single ground control point with pixel and geographic coordinates."""
    pixel_x: float = Field(..., description="Pixel X coordinate")
    pixel_y: float = Field(..., description="Pixel Y coordinate")
    geo_x: float = Field(..., description="Geographic X coordinate (longitude)")
    geo_y: float = Field(..., description="Geographic Y coordinate (latitude)")

    @field_validator('pixel_x', 'pixel_y')
    @classmethod
    def validate_pixel_coords(cls, v: float) -> float:
        """Validate pixel coordinates are non-negative."""
        if v < 0:
            raise ValueError("Pixel coordinates must be non-negative")
        return v

    @field_validator('geo_x', 'geo_y')
    @classmethod
    def validate_geo_coords(cls, v: float) -> float:
        """Validate geographic coordinates are within reasonable bounds."""
        if not -180 <= v <= 180:
            raise ValueError("Geographic coordinates must be between -180 and 180")
        return v


class RegistrationRequest(BaseModel):
    """Request model for georegistration submission."""
    task_id: str = Field(..., description="Unique task identifier")
    control_points: List[ControlPoint] = Field(..., description="List of ground control points", min_length=3)
    target_crs: str = Field(default="EPSG:4326", description="Target coordinate reference system")

    @field_validator('control_points')
    @classmethod
    def validate_control_points_count(cls, v: List[ControlPoint]) -> List[ControlPoint]:
        """Validate minimum number of control points."""
        if len(v) < 3:
            raise ValueError("至少需要3个控制点")
        if len(v) > 20:
            raise ValueError("控制点数量不能超过20个")
        return v


class RegistrationResponse(BaseModel):
    """Response model for successful georegistration."""
    status: str = Field(..., description="Operation status")
    task_id: str = Field(..., description="Task identifier")
    output_path: str = Field(..., description="Path to georeferenced output file")
    rms_error: float = Field(..., description="Root Mean Square error in geographic units")
    gcp_count: int = Field(..., description="Number of ground control points used")


class ValidationError(BaseModel):
    """Response model for validation errors."""
    detail: str = Field(..., description="Error description")


@router.post(
    "/submit",
    response_model=RegistrationResponse,
    responses={
        400: {"model": ValidationError, "description": "Invalid request (insufficient control points)"},
        404: {"model": ValidationError, "description": "Task or file not found"},
        500: {"model": ValidationError, "description": "Processing error"}
    },
    summary="Submit georegistration control points",
    description="Submit ground control points and execute georeferencing transformation"
)
async def submit_registration(request: RegistrationRequest) -> RegistrationResponse:
    """
    Submit georegistration control points and execute transformation.

    Args:
        request: RegistrationRequest with task_id, control_points, and target_crs

    Returns:
        RegistrationResponse with output file path and accuracy metrics

    Raises:
        HTTPException: If validation fails or processing error occurs
    """
    # Validate control point count (redundant due to Pydantic validation)
    if len(request.control_points) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要3个控制点"
        )

    # Create georegistration object and add control points
    geo_reg = GeoRegistration()
    for cp in request.control_points:
        geo_reg.add_control_point(
            (cp.pixel_x, cp.pixel_y),
            (cp.geo_x, cp.geo_y)
        )

    # Validate control points
    valid, msg = geo_reg.validate()
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )

    # Calculate RMS error
    rms_error = geo_reg.calculate_rms_error()
    logger.info(f"Task {request.task_id}: RMS error = {rms_error:.6f}")

    # Determine file paths
    # Try to find the uploaded file
    uploads_dir = "uploads"
    outputs_dir = "outputs"

    # Ensure outputs directory exists
    os.makedirs(outputs_dir, exist_ok=True)

    # Try different possible file extensions
    input_path = None
    for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
        test_path = os.path.join(uploads_dir, f"{request.task_id}{ext}")
        if os.path.exists(test_path):
            input_path = test_path
            break

    # If not found by task_id, try to find any file starting with task_id
    if input_path is None and os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            if filename.startswith(request.task_id):
                input_path = os.path.join(uploads_dir, filename)
                break

    if input_path is None:
        logger.error(f"File not found for task {request.task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到任务 {request.task_id} 对应的上传文件"
        )

    logger.info(f"Using input file: {input_path}")

    # Create output path
    output_basename = f"{request.task_id}_georeferenced.tiff"
    output_path = os.path.join(outputs_dir, output_basename)

    try:
        # Execute georeferencing transformation
        result = geo_reg.transform_image(
            input_path,
            output_path,
            request.target_crs
        )

        return RegistrationResponse(
            status="success",
            task_id=request.task_id,
            output_path=result["output_path"],
            rms_error=result["rms_error"],
            gcp_count=result["gcp_count"]
        )

    except ValueError as e:
        logger.error(f"Validation error for task {request.task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Processing error for task {request.task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"地理配准处理失败: {str(e)}"
        )


@router.get(
    "/status/{task_id}",
    summary="Get registration status (placeholder)",
    description="Check if a task has been georeferenced"
)
async def get_registration_status(task_id: str):
    """
    Get registration status for a task.

    This is a placeholder endpoint for future enhancement.
    """
    # TODO: Implement proper status tracking with database
    outputs_dir = "outputs"
    expected_file = os.path.join(outputs_dir, f"{task_id}_georeferenced.tiff")

    exists = os.path.exists(expected_file)

    return {
        "task_id": task_id,
        "georeferenced": exists,
        "output_path": expected_file if exists else None
    }
