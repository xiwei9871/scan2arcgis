from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from typing import Dict
import json
import logging

router = APIRouter()

# Configure logging for WebSocket operations
logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time progress updates.

    This class handles the lifecycle of WebSocket connections, allowing
    the backend to send progress updates, completion messages, and errors
    to connected clients during long-running processing tasks.

    Attributes:
        active_connections: Dictionary mapping task_id to WebSocket connections
    """

    def __init__(self):
        """Initialize the connection manager with an empty connection pool."""
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        """
        Accept and register a WebSocket connection for a specific task.

        Args:
            task_id: Unique identifier for the processing task
            websocket: The WebSocket connection object

        Logs:
            Info message when connection is established
        """
        await websocket.accept()
        self.active_connections[task_id] = websocket
        logger.info(f"WebSocket connected for task: {task_id}")

    def disconnect(self, task_id: str):
        """
        Remove a WebSocket connection from the active connections pool.

        Args:
            task_id: Unique identifier for the task to disconnect

        Logs:
            Info message when disconnection occurs
        """
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            logger.info(f"WebSocket disconnected for task: {task_id}")

    async def send_progress(self, task_id: str, progress: float, message: str):
        """
        Send a progress update to the client.

        Args:
            task_id: Unique identifier for the task
            progress: Progress value between 0.0 and 1.0
            message: Human-readable progress message

        Raises:
            ValueError: If progress is not between 0.0 and 1.0

        Logs:
            Warning if connection fails or is not found
        """
        # Validate progress is within valid range
        if not 0.0 <= progress <= 1.0:
            raise ValueError(f"Progress must be between 0.0 and 1.0, got {progress}")

        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json({
                    "type": "progress",
                    "progress": progress,
                    "message": message
                })
                logger.debug(f"Progress sent for task {task_id}: {progress*100:.1f}% - {message}")
            except Exception as e:
                logger.error(f"Failed to send progress to task {task_id}: {e}")
                # Clean up the broken connection
                self.disconnect(task_id)

    async def send_complete(self, task_id: str, result: dict):
        """
        Send a completion message with results to the client.

        Args:
            task_id: Unique identifier for the task
            result: Dictionary containing processing results

        Logs:
            Info message on successful completion
            Warning if connection fails or is not found
        """
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json({
                    "type": "complete",
                    "result": result
                })
                logger.info(f"Completion message sent for task: {task_id}")
            except Exception as e:
                logger.error(f"Failed to send completion to task {task_id}: {e}")
                # Clean up the broken connection
                self.disconnect(task_id)

    async def send_error(self, task_id: str, error: str):
        """
        Send an error message to the client.

        Args:
            task_id: Unique identifier for the task
            error: Error message string

        Logs:
            Error message when sending error to client
            Warning if connection fails or is not found
        """
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json({
                    "type": "error",
                    "error": error
                })
                logger.error(f"Error message sent for task {task_id}: {error}")
            except Exception as e:
                logger.error(f"Failed to send error to task {task_id}: {e}")
                # Clean up the broken connection
                self.disconnect(task_id)


manager = ConnectionManager()


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time progress updates.

    This endpoint maintains a persistent connection with the client,
    allowing the server to push progress updates during processing.
    The connection stays alive until the client disconnects.

    Args:
        websocket: The WebSocket connection object
        task_id: Unique identifier for the task to monitor

    Note:
        The receive loop below is used for keep-alive purposes.
        It waits for messages from the client (which can be empty/ping)
        to maintain the connection. If the client disconnects,
        WebSocketDisconnect is raised and cleanup occurs.
    """
    await manager.connect(task_id, websocket)
    try:
        while True:
            # Keep connection alive and wait for messages
            # This loop is primarily for keep-alive - the server pushes
            # updates via the ConnectionManager, this just prevents
            # the connection from timing out
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)
        logger.info(f"WebSocket endpoint closed for task: {task_id}")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket endpoint for task {task_id}: {e}")
        manager.disconnect(task_id)
