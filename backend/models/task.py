"""
Task model for managing file upload and processing tasks.
"""

from enum import Enum
from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict


class TaskStatus(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """Task model for tracking file upload and processing status."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique task identifier")
    filename: str = Field(..., description="Original filename")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="Progress percentage (0-100)")
    error_message: Optional[str] = Field(None, description="Error message if task failed")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Task creation timestamp")

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        },
        use_enum_values=True
    )

    @classmethod
    def create(cls, filename: str) -> "Task":
        """
        Create a new task with default values.

        Args:
            filename: The name of the uploaded file

        Returns:
            A new Task instance
        """
        return cls(
            filename=filename,
            status=TaskStatus.PENDING,
            progress=0.0
        )


class TaskUploadResponse(BaseModel):
    """Response model for file upload that includes task and file path."""

    id: str
    filename: str
    status: TaskStatus
    progress: float
    error_message: Optional[str] = None
    created_at: datetime
    file_path: str

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        },
        use_enum_values=True
    )
