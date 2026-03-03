"""
Tests for WebSocket error handling and validation.
"""

import pytest
import asyncio
from api.websocket import ConnectionManager
from fastapi import WebSocket


@pytest.mark.asyncio
async def test_send_progress_validates_range():
    """Test that send_progress validates progress is between 0.0 and 1.0."""
    manager = ConnectionManager()

    # Test invalid progress values
    with pytest.raises(ValueError, match="Progress must be between 0.0 and 1.0"):
        await manager.send_progress("task_1", 1.5, "Too high")

    with pytest.raises(ValueError, match="Progress must be between 0.0 and 1.0"):
        await manager.send_progress("task_1", -0.1, "Too low")

    with pytest.raises(ValueError, match="Progress must be between 0.0 and 1.0"):
        await manager.send_progress("task_1", 2.0, "Way too high")

    # Test boundary values (should not raise)
    try:
        await manager.send_progress("task_1", 0.0, "Start")
        await manager.send_progress("task_1", 1.0, "Complete")
        await manager.send_progress("task_1", 0.5, "Halfway")
    except ValueError:
        pytest.fail("Valid progress values should not raise ValueError")

    print("✓ Progress validation works correctly")


@pytest.mark.asyncio
async def test_send_progress_handles_missing_connection():
    """Test that send_progress handles missing connections gracefully."""
    manager = ConnectionManager()

    # Should not raise an error for non-existent task
    await manager.send_progress("non_existent_task", 0.5, "Test")

    print("✓ send_progress handles missing connections gracefully")


@pytest.mark.asyncio
async def test_send_complete_handles_missing_connection():
    """Test that send_complete handles missing connections gracefully."""
    manager = ConnectionManager()

    # Should not raise an error for non-existent task
    await manager.send_complete("non_existent_task", {"status": "test"})

    print("✓ send_complete handles missing connections gracefully")


@pytest.mark.asyncio
async def test_send_error_handles_missing_connection():
    """Test that send_error handles missing connections gracefully."""
    manager = ConnectionManager()

    # Should not raise an error for non-existent task
    await manager.send_error("non_existent_task", "Test error")

    print("✓ send_error handles missing connections gracefully")


def test_connection_manager_has_logging():
    """Test that ConnectionManager has logging configured."""
    from api.websocket import logger
    import logging

    # Verify logger is configured
    assert logger is not None
    assert isinstance(logger, logging.Logger)
    assert logger.name == "api.websocket"

    print("✓ Logging is properly configured")


def test_connection_manager_docstring():
    """Test that ConnectionManager has proper documentation."""
    manager = ConnectionManager()

    # Check class docstring
    assert manager.__class__.__doc__ is not None
    assert "WebSocket" in manager.__class__.__doc__
    assert "progress" in manager.__class__.__doc__

    # Check method docstrings
    assert manager.connect.__doc__ is not None
    assert manager.disconnect.__doc__ is not None
    assert manager.send_progress.__doc__ is not None
    assert manager.send_complete.__doc__ is not None
    assert manager.send_error.__doc__ is not None

    # Check that send_progress documents the validation
    assert "ValueError" in manager.send_progress.__doc__
    assert "0.0 and 1.0" in manager.send_progress.__doc__

    print("✓ Documentation is complete and accurate")


def test_websocket_endpoint_docstring():
    """Test that websocket_endpoint has proper documentation."""
    from api.websocket import websocket_endpoint

    # Check endpoint docstring
    assert websocket_endpoint.__doc__ is not None
    assert "WebSocket" in websocket_endpoint.__doc__
    assert "keep-alive" in websocket_endpoint.__doc__

    print("✓ WebSocket endpoint has proper documentation")


@pytest.mark.asyncio
async def test_exception_handling_in_send_methods():
    """
    Test that send methods properly handle exceptions and clean up connections.

    This test verifies the try/except blocks in send methods work correctly.
    """
    from unittest.mock import AsyncMock, MagicMock
    from api.websocket import ConnectionManager

    manager = ConnectionManager()

    # Create a mock WebSocket that raises an exception on send_json
    mock_websocket = MagicMock()
    mock_websocket.send_json = AsyncMock(side_effect=Exception("Connection broken"))

    # Add the mock connection
    task_id = "test_task_error"
    manager.active_connections[task_id] = mock_websocket

    # Verify connection exists
    assert task_id in manager.active_connections

    # Try to send progress - should handle exception and disconnect
    await manager.send_progress(task_id, 0.5, "Test")

    # Verify connection was cleaned up after exception
    assert task_id not in manager.active_connections

    print("✓ Exception handling and cleanup works correctly")


if __name__ == "__main__":
    print("Running WebSocket error handling tests...\n")

    asyncio.run(test_send_progress_validates_range())
    print()

    asyncio.run(test_send_progress_handles_missing_connection())
    asyncio.run(test_send_complete_handles_missing_connection())
    asyncio.run(test_send_error_handles_missing_connection())
    print()

    test_connection_manager_has_logging()
    test_connection_manager_docstring()
    test_websocket_endpoint_docstring()
    print()

    asyncio.run(test_exception_handling_in_send_methods())

    print("\n✓ All error handling tests passed!")
