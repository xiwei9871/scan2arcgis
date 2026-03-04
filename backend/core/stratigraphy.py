"""
Stratigraphy extraction module for geological map digitization.

This module provides the StratigraphyExtractor class for identifying
and extracting stratigraphic units (layers) from geological maps using
color-based segmentation and clustering.
"""

import cv2
import numpy as np
from typing import Dict, List, Any
from sklearn.cluster import KMeans
from shapely.geometry import Polygon
import logging

logger = logging.getLogger(__name__)

# Optional scikit-learn import
SKLEARN_AVAILABLE = True
try:
    from sklearn.cluster import KMeans
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not installed - stratigraphy extraction limited")


class StratigraphyExtractor:
    """
    Handles stratigraphic unit extraction from geological maps.

    Uses color-based clustering to identify different geological units
    and extracts their boundaries as polygons.
    """

    def __init__(self, n_clusters: int = 8, min_area: float = 100):
        """
        Initialize the StratigraphyExtractor.

        Args:
            n_clusters: Number of color clusters to identify
            min_area: Minimum polygon area in pixels
        """
        self.n_clusters = n_clusters
        self.min_area = min_area  # Minimum polygon area in pixels

        logger.debug(f"StratigraphyExtractor initialized with {n_clusters} clusters")

    def extract_colors(self, image: np.ndarray) -> np.ndarray:
        """
        Extract dominant colors from the image using K-means clustering.

        Args:
            image: Input BGR image

        Returns:
            Array of dominant colors (BGR format)

        Raises:
            ValueError: If image is invalid or scikit-learn not available
        """
        if not SKLEARN_AVAILABLE:
            raise ValueError("scikit-learn is required for color extraction")

        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Resize image for faster processing
        small_image = cv2.resize(image, (100, 100))
        pixels = small_image.reshape(-1, 3)

        # Perform K-means clustering
        kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        kmeans.fit(pixels)

        # Get cluster centers as dominant colors
        colors = kmeans.cluster_centers_.astype(np.uint8)

        logger.debug(f"Extracted {len(colors)} dominant colors")
        return colors

    def create_color_masks(
        self,
        image: np.ndarray,
        colors: np.ndarray,
        tolerance: int = 50
    ) -> Dict[int, np.ndarray]:
        """
        Create color masks for each dominant color.

        Args:
            image: Input BGR image
            colors: Array of dominant colors (BGR)
            tolerance: Color tolerance threshold (0-255)

        Returns:
            Dictionary mapping color index to binary mask

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        masks = {}

        for i, color in enumerate(colors):
            # Convert color to HSV - ensure it's uint8
            color_uint8 = color.astype(np.uint8)
            color_bgr = color_uint8.reshape(1, 1, 3)
            color_hsv = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2HSV)[0][0]

            # Define color range with tolerance
            lower = np.array([
                max(0, int(color_hsv[0]) - 10),
                max(0, int(color_hsv[1]) - tolerance),
                max(0, int(color_hsv[2]) - tolerance)
            ], dtype=np.uint8)
            upper = np.array([
                min(180, int(color_hsv[0]) + 10),
                min(255, int(color_hsv[1]) + tolerance),
                min(255, int(color_hsv[2]) + tolerance)
            ], dtype=np.uint8)

            # Create mask
            mask = cv2.inRange(hsv, lower, upper)
            masks[i] = mask

        logger.debug(f"Created {len(masks)} color masks")
        return masks

    def find_contours(self, mask: np.ndarray) -> List[np.ndarray]:
        """
        Find contours in a binary mask.

        Args:
            mask: Binary mask

        Returns:
            List of contours
        """
        contours_tuple, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        # cv2.findContours returns (contours, hierarchy) tuple
        return list(contours_tuple) if contours_tuple is not None else []

    def contours_to_polygons(
        self,
        contours: List[np.ndarray],
        min_area: float = None
    ) -> List[Polygon]:
        """
        Convert contours to Shapely Polygon objects.

        Args:
            contours: List of OpenCV contours
            min_area: Minimum area threshold (uses self.min_area if None)

        Returns:
            List of Polygon geometries
        """
        if min_area is None:
            min_area = self.min_area

        polygons = []

        for contour in contours:
            # Filter by area
            if cv2.contourArea(contour) < min_area:
                continue

            # Simplify contour
            epsilon = 0.01 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Convert to point coordinates
            points = approx.reshape(-1, 2).tolist()

            # Need at least 3 points for a polygon
            if len(points) >= 3:
                polygons.append(Polygon(points))

        logger.debug(f"Converted {len(contours)} contours to {len(polygons)} polygons")
        return polygons

    def extract(
        self,
        image: np.ndarray,
        min_area: float = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        Complete stratigraphy extraction pipeline.

        Args:
            image: Input preprocessed BGR image
            min_area: Minimum polygon area (uses self.min_area if None)

        Returns:
            Dictionary mapping color index to:
                - 'color': BGR color as list
                - 'polygons': List of Polygon geometries

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        logger.info(f"Starting stratigraphy extraction for image: {image.shape}")

        # Step 1: Extract dominant colors
        if SKLEARN_AVAILABLE:
            colors = self.extract_colors(image)
            logger.debug("Step 1/3: Color extraction complete")
        else:
            # Fallback: use predefined colors
            colors = np.array([
                [100, 50, 50],   # Brown
                [50, 100, 50],   # Green
                [50, 50, 100],   # Blue
                [100, 100, 50],  # Yellow
                [100, 50, 100],  # Purple
                [50, 100, 100],  # Cyan
                [150, 100, 50],  # Orange
                [50, 50, 50]     # Gray
            ], dtype=np.uint8)
            logger.warning("Using predefined colors (scikit-learn not available)")

        # Step 2: Create color masks
        masks = self.create_color_masks(image, colors)
        logger.debug("Step 2/3: Mask creation complete")

        # Step 3: Extract polygons
        result = {}
        for color_idx, mask in masks.items():
            contours = self.find_contours(mask)
            polygons = self.contours_to_polygons(contours, min_area)

            if polygons:
                result[color_idx] = {
                    'color': colors[color_idx].tolist(),
                    'polygons': polygons
                }

        logger.info(f"Stratigraphy extraction complete: {len(result)} layers found")
        return result

    def set_n_clusters(self, n_clusters: int) -> None:
        """
        Update the number of color clusters.

        Args:
            n_clusters: New number of clusters
        """
        self.n_clusters = n_clusters
        logger.debug(f"Updated n_clusters to {n_clusters}")

    def set_min_area(self, min_area: float) -> None:
        """
        Update the minimum polygon area threshold.

        Args:
            min_area: New minimum area in pixels
        """
        self.min_area = min_area
        logger.debug(f"Updated min_area to {min_area}")
