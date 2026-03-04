"""
Georegistration module for transforming images using ground control points.

This module provides the GeoRegistration class for performing georeferencing
of scanned geological maps using Ground Control Points (GCPs).
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Optional GDAL import - GDAL is required for image transformation
# but the rest of the module works without it
gdal = None
osr = None
GDAL_AVAILABLE = False

try:
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
    logger.info("GDAL is available - georeferencing transformation enabled")
except ImportError:
    logger.warning(
        "GDAL is not installed. Image transformation will not be available. "
        "Install GDAL to enable georeferencing functionality."
    )


class GeoRegistration:
    """
    Handles georegistration of images using ground control points.

    Uses GDAL to create georeferenced GeoTIFF files from scanned images
    based on pixel-to-geography coordinate mappings.
    """

    def __init__(self):
        """Initialize the GeoRegistration object."""
        self.gcp_pairs: List[Tuple[float, float, float, float]] = []  # (pixel_x, pixel_y, geo_x, geo_y)

    def add_control_point(self, pixel_xy: Tuple[float, float], geo_xy: Tuple[float, float]) -> None:
        """
        Add a ground control point.

        Args:
            pixel_xy: Tuple of (x, y) pixel coordinates
            geo_xy: Tuple of (x, y) geographic coordinates (typically longitude, latitude)
        """
        self.gcp_pairs.append((*pixel_xy, *geo_xy))
        logger.debug(f"Added GCP: pixel={pixel_xy}, geo={geo_xy}")

    def get_gcp_count(self) -> int:
        """
        Get the number of ground control points.

        Returns:
            Number of GCPs currently registered
        """
        return len(self.gcp_pairs)

    def validate(self) -> Tuple[bool, str]:
        """
        Validate that sufficient control points exist.

        Returns:
            Tuple of (is_valid, message)
        """
        count = self.get_gcp_count()
        if count < 3:
            return False, f"至少需要3个控制点，当前有{count}个"
        return True, "控制点数量满足要求"

    def calculate_rms_error(self) -> float:
        """
        Calculate Root Mean Square (RMS) error for the control points.

        Uses least squares regression to fit a transformation and calculates
        the residuals to estimate transformation accuracy.

        Returns:
            RMS error value (lower is better)
        """
        if self.get_gcp_count() < 3:
            return 0.0

        try:
            # Extract pixel and geo coordinates
            pixel_coords = np.array([[p[0], p[1], 1] for p in self.gcp_pairs])
            geo_x = np.array([p[2] for p in self.gcp_pairs])
            geo_y = np.array([p[3] for p in self.gcp_pairs])

            # Solve for transformation parameters using least squares
            params_x, _, _, _ = np.linalg.lstsq(pixel_coords, geo_x, rcond=None)
            params_y, _, _, _ = np.linalg.lstsq(pixel_coords, geo_y, rcond=None)

            # Calculate predicted coordinates
            predicted_x = pixel_coords @ params_x
            predicted_y = pixel_coords @ params_y

            # Calculate residuals
            residuals_x = geo_x - predicted_x
            residuals_y = geo_y - predicted_y

            # Calculate RMS
            rms = np.sqrt(np.mean(residuals_x**2 + residuals_y**2))
            return float(rms)
        except Exception as e:
            logger.error(f"Error calculating RMS: {e}")
            return 0.0

    def transform_image(self, input_path: str, output_path: str, target_crs: str = "EPSG:4326") -> dict:
        """
        Execute georeferencing transformation on the input image.

        Creates a GeoTIFF file with embedded GCPs and projection information.

        Args:
            input_path: Path to input image file
            output_path: Path for output GeoTIFF file
            target_crs: Target coordinate reference system (default: EPSG:4326/WGS84)

        Returns:
            Dictionary with output_path, rms_error, and gcp_count

        Raises:
            ValueError: If insufficient GCPs or image cannot be read
            RuntimeError: If GDAL is not available
        """
        if not GDAL_AVAILABLE:
            raise RuntimeError(
                "GDAL is not installed. Please install GDAL to use georeferencing functionality. "
                "See: https://gdal.org/download.html"
            )

        valid, msg = self.validate()
        if not valid:
            raise ValueError(msg)

        # Read the input image
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f"无法读取图像: {input_path}")

        height, width = img.shape[:2]
        logger.info(f"Processing image: {width}x{height}")

        # Create GDAL dataset for output
        driver = gdal.GetDriverByName("GTiff")
        if driver is None:
            raise RuntimeError("GDAL GTiff driver not available")

        ds = driver.Create(output_path, width, height, 3, gdal.GDT_Byte)
        if ds is None:
            raise RuntimeError(f"Failed to create output file: {output_path}")

        try:
            # Write image data (convert BGR to RGB)
            ds.WriteArray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

            # Set coordinate reference system
            srs = osr.SpatialReference()
            if target_crs.startswith("EPSG:"):
                epsg_code = int(target_crs.split(":")[1])
                srs.ImportFromEPSG(epsg_code)
            else:
                # Assume WGS84 if not specified
                srs.ImportFromEPSG(4326)
            ds.SetProjection(srs.ExportToWkt())

            # Create and set GCPs
            gcps = []
            for px, py, gx, gy in self.gcp_pairs:
                gcp = gdal.GCP(gx, gy, 0, px, py)
                gcps.append(gcp)

            ds.SetGCPs(gcps, srs.ExportToWkt())
            ds.FlushCache()

            rms_error = self.calculate_rms_error()
            logger.info(f"Georeferencing complete: RMS={rms_error:.4f}, GCPs={len(gcps)}")

            return {
                "output_path": output_path,
                "rms_error": rms_error,
                "gcp_count": len(gcps)
            }
        except Exception as e:
            # Clean up on error
            ds = None
            raise
        finally:
            # Ensure dataset is closed
            ds = None
