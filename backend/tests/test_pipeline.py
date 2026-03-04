"""
Tests for the processing pipeline orchestration.

Tests the ProcessingPipeline class that coordinates the digitization workflow.
"""

import pytest
import numpy as np
from core.pipeline import ProcessingPipeline, GEOPANDAS_AVAILABLE, GDAL_AVAILABLE


class TestPipelineInitialization:
    """Test pipeline initialization."""

    def test_pipeline_initialization(self):
        """Test basic pipeline initialization."""
        pipeline = ProcessingPipeline("test_task_id")

        assert pipeline.task_id == "test_task_id"
        assert pipeline.enable_georeferencing is True

    def test_pipeline_without_georeferencing(self):
        """Test pipeline initialization with georeferencing disabled."""
        pipeline = ProcessingPipeline("test_task_id", enable_georeferencing=False)

        assert pipeline.task_id == "test_task_id"
        assert pipeline.enable_georeferencing is False

    def test_pipeline_has_processors(self):
        """Test that pipeline has all required processors."""
        pipeline = ProcessingPipeline("test_task_id")

        assert pipeline.preprocessor is not None
        assert pipeline.contour_extractor is not None
        assert pipeline.boundary_extractor is not None
        assert pipeline.stratigraphy_extractor is not None


class TestSendProgressMethods:
    """Test progress update methods."""

    @pytest.mark.asyncio
    async def test_send_progress(self):
        """Test sending progress updates."""
        pipeline = ProcessingPipeline("test_task_id")

        # Should not raise exception even if WebSocket not available
        await pipeline._send_progress(0.5, "Test message")

    @pytest.mark.asyncio
    async def test_send_complete(self):
        """Test sending completion message."""
        pipeline = ProcessingPipeline("test_task_id")

        result = {'test': 'data'}
        await pipeline._send_complete(result)

    @pytest.mark.asyncio
    async def test_send_error(self):
        """Test sending error message."""
        pipeline = ProcessingPipeline("test_task_id")

        await pipeline._send_error("Test error")


class TestProcess:
    """Test complete processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_with_nonexistent_file(self):
        """Test processing with nonexistent file."""
        pipeline = ProcessingPipeline("test_task_id")

        with pytest.raises(ValueError, match="Unable to read image"):
            await pipeline.process("nonexistent.png", "outputs")

    @pytest.mark.asyncio
    async def test_process_with_mock_image(self, tmp_path):
        """Test processing with mock image."""
        # Create a simple test image
        import cv2
        test_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        test_file = tmp_path / "test.png"
        cv2.imwrite(str(test_file), test_image)

        pipeline = ProcessingPipeline("test_task_id")
        output_dir = str(tmp_path / "outputs")

        result = await pipeline.process(str(test_file), output_dir)

        assert 'contours_count' in result
        assert 'boundaries_count' in result
        assert 'stratigraphy_layers' in result
        assert 'output_dir' in result
        assert isinstance(result['contours_count'], int)
        assert isinstance(result['boundaries_count'], int)
        assert isinstance(result['stratigraphy_layers'], int)


class TestOptionalImports:
    """Test optional import handling."""

    def test_geopandas_availability(self):
        """Test GEOPANDOS_AVAILABLE flag."""
        # Just check the flag exists
        assert isinstance(GEOPANDAS_AVAILABLE, bool)

    def test_gdal_availability(self):
        """Test GDAL_AVAILABLE flag."""
        # Just check the flag exists
        assert isinstance(GDAL_AVAILABLE, bool)


@pytest.mark.skipif(not GEOPANDAS_AVAILABLE, reason="geopandas not installed")
class TestProcessWithOutputs:
    """Test processing with output file generation."""

    @pytest.mark.asyncio
    async def test_process_creates_output_files(self, tmp_path):
        """Test that processing creates output files."""
        import cv2

        # Create test image with some features
        test_image = np.zeros((200, 200, 3), dtype=np.uint8)
        # Add some colored regions for stratigraphy
        test_image[50:100, 50:100] = [100, 50, 50]
        test_image[120:170, 120:170] = [50, 100, 50]
        # Add some lines for boundaries
        cv2.line(test_image, (10, 180), (190, 180), (200, 200, 200), 2)

        test_file = tmp_path / "test.png"
        cv2.imwrite(str(test_file), test_image)

        pipeline = ProcessingPipeline("test_task_id")
        output_dir = str(tmp_path / "outputs")

        result = await pipeline.process(str(test_file), output_dir)

        # Check that output directory exists
        from pathlib import Path
        output_path = Path(output_dir)
        assert output_path.exists()

        # Check that files were created (if any features detected)
        if result['files']:
            for file in result['files']:
                assert (output_path / file).exists()
