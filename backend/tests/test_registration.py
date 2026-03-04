"""
Tests for the georegistration module.

Tests the GeoRegistration class for control point management,
validation, RMS error calculation, and image transformation.
"""

import pytest
import numpy as np
import os
import tempfile
from core.registration import GeoRegistration, GDAL_AVAILABLE

# Skip decorator for GDAL-dependent tests
skip_if_no_gdal = pytest.mark.skipif(
    not GDAL_AVAILABLE,
    reason="GDAL is not installed - skipping GDAL-dependent tests"
)


class TestControlPoints:
    """Test control point management."""

    def test_add_control_points(self):
        """Test adding control points."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))
        reg.add_control_point((200, 200), (116.4, 40.0))
        reg.add_control_point((300, 300), (116.5, 40.1))

        assert reg.get_gcp_count() == 3

    def test_get_gcp_count_empty(self):
        """Test GCP count when no points added."""
        reg = GeoRegistration()
        assert reg.get_gcp_count() == 0

    def test_get_gcp_count_multiple(self):
        """Test GCP count with multiple points."""
        reg = GeoRegistration()
        for i in range(5):
            reg.add_control_point((i * 10, i * 10), (116.0 + i * 0.1, 39.0 + i * 0.1))
        assert reg.get_gcp_count() == 5


class TestValidation:
    """Test validation of control points."""

    def test_validate_sufficient_points(self):
        """Test validation with sufficient control points."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))
        reg.add_control_point((200, 200), (116.4, 40.0))
        reg.add_control_point((300, 300), (116.5, 40.1))

        valid, msg = reg.validate()
        assert valid is True
        assert "满足要求" in msg

    def test_insufficient_control_points(self):
        """Test validation with insufficient control points."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))

        valid, msg = reg.validate()
        assert valid is False
        assert "至少需要3个" in msg
        assert "当前有1个" in msg

    def test_insufficient_two_points(self):
        """Test validation with exactly two control points."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))
        reg.add_control_point((200, 200), (116.4, 40.0))

        valid, msg = reg.validate()
        assert valid is False
        assert "至少需要3个" in msg
        assert "当前有2个" in msg

    def test_validate_empty(self):
        """Test validation with no control points."""
        reg = GeoRegistration()

        valid, msg = reg.validate()
        assert valid is False
        assert "至少需要3个" in msg
        assert "当前有0个" in msg


class TestRMSError:
    """Test RMS error calculation."""

    def test_calculate_rms_error_with_sufficient_points(self):
        """Test RMS calculation with sufficient points."""
        reg = GeoRegistration()
        reg.add_control_point((0, 0), (0, 0))
        reg.add_control_point((100, 0), (1, 0))
        reg.add_control_point((0, 100), (0, 1))

        rms = reg.calculate_rms_error()
        assert isinstance(rms, float)
        # For well-aligned points, RMS should be reasonable
        assert rms >= 0

    def test_calculate_rms_error_perfect_alignment(self):
        """Test RMS with perfectly aligned points."""
        reg = GeoRegistration()
        # Points that align perfectly with a simple linear transform
        reg.add_control_point((0, 0), (100.0, 40.0))
        reg.add_control_point((100, 0), (101.0, 40.0))
        reg.add_control_point((0, 100), (100.0, 41.0))

        rms = reg.calculate_rms_error()
        # For perfect linear relationship, RMS should be very small
        assert rms < 1.0

    def test_calculate_rms_error_insufficient_points(self):
        """Test RMS calculation with insufficient points."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))

        rms = reg.calculate_rms_error()
        assert rms == 0.0

    def test_calculate_rms_error_no_points(self):
        """Test RMS calculation with no points."""
        reg = GeoRegistration()

        rms = reg.calculate_rms_error()
        assert rms == 0.0

    def test_calculate_rms_error_scattered_points(self):
        """Test RMS with scattered control points."""
        reg = GeoRegistration()
        # Add points with some scatter
        reg.add_control_point((100, 100), (116.3, 39.9))
        reg.add_control_point((200, 200), (116.4, 40.0))
        reg.add_control_point((300, 300), (116.5, 40.1))

        rms = reg.calculate_rms_error()
        assert isinstance(rms, float)
        assert rms > 0


class TestTransformImage:
    """Test image transformation."""

    @skip_if_no_gdal
    def test_transform_image_insufficient_gcps(self):
        """Test transformation fails with insufficient GCPs."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(b'fake png content')
            tmp_path = tmp.name

        try:
            with pytest.raises(ValueError, match="至少需要3个控制点"):
                reg.transform_image(tmp_path, "output.tiff")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @skip_if_no_gdal
    def test_transform_image_nonexistent_file(self):
        """Test transformation with nonexistent input file."""
        reg = GeoRegistration()
        reg.add_control_point((100, 100), (116.3, 39.9))
        reg.add_control_point((200, 200), (116.4, 40.0))
        reg.add_control_point((300, 300), (116.5, 40.1))

        with pytest.raises(ValueError, match="无法读取图像"):
            reg.transform_image("nonexistent.png", "output.tiff")


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_georegistration_workflow(self):
        """Test complete georegistration workflow."""
        reg = GeoRegistration()

        # Add control points
        points = [
            ((0, 0), (100.0, 40.0)),
            ((100, 0), (101.0, 40.0)),
            ((0, 100), (100.0, 41.0)),
            ((100, 100), (101.0, 41.0)),
        ]

        for pixel_pt, geo_pt in points:
            reg.add_control_point(pixel_pt, geo_pt)

        # Validate
        valid, msg = reg.validate()
        assert valid is True

        # Calculate RMS
        rms = reg.calculate_rms_error()
        assert isinstance(rms, float)

        # Check counts
        assert reg.get_gcp_count() == 4
