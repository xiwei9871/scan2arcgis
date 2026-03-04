"""
Processing pipeline orchestration for geological map digitization.

This module provides the ProcessingPipeline class that orchestrates
the complete digitization workflow from preprocessing to output generation.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import cv2
import asyncio
import logging

from .preprocessing import ImagePreprocessor
from .contour import ContourExtractor
from .boundary import BoundaryExtractor
from .stratigraphy import StratigraphyExtractor
from .registration import GeoRegistration, GDAL_AVAILABLE

logger = logging.getLogger(__name__)

# Optional imports
GEOPANDAS_AVAILABLE = True
try:
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon, mapping
except ImportError:
    GEOPANDAS_AVAILABLE = False
    logger.warning("geopandas not installed - output to Shapefile disabled")


class ProcessingPipeline:
    """
    Orchestrates the complete geological map digitization pipeline.

    This class coordinates all processing steps including preprocessing,
    feature extraction, and output generation with real-time progress
    updates via WebSocket.
    """

    def __init__(self, task_id: str, enable_georeferencing: bool = True):
        """
        Initialize the processing pipeline.

        Args:
            task_id: Unique task identifier for progress tracking
            enable_georeferencing: Whether to apply georeferencing
        """
        self.task_id = task_id
        self.enable_georeferencing = enable_georeferencing

        # Initialize processors
        self.preprocessor = ImagePreprocessor()
        self.contour_extractor = ContourExtractor()
        self.boundary_extractor = BoundaryExtractor()
        self.stratigraphy_extractor = StratigraphyExtractor()

        # WebSocket progress manager (imported to avoid circular dependency)
        try:
            from api.websocket import manager
            self.ws_manager = manager
        except ImportError:
            self.ws_manager = None
            logger.warning("WebSocket manager not available - progress updates disabled")

        logger.info(f"ProcessingPipeline initialized for task {task_id}")

    async def _send_progress(self, progress: float, message: str) -> None:
        """
        Send progress update via WebSocket.

        Args:
            progress: Progress value (0.0 to 1.0)
            message: Progress message
        """
        if self.ws_manager:
            await self.ws_manager.send_progress(self.task_id, progress, message)

    async def _send_complete(self, result: Dict) -> None:
        """
        Send completion message via WebSocket.

        Args:
            result: Processing result dictionary
        """
        if self.ws_manager:
            await self.ws_manager.send_complete(self.task_id, result)

    async def _send_error(self, error: str) -> None:
        """
        Send error message via WebSocket.

        Args:
            error: Error message
        """
        if self.ws_manager:
            await self.ws_manager.send_error(self.task_id, error)

    async def process(
        self,
        image_path: str,
        output_dir: str,
        geo_registration: Optional[GeoRegistration] = None
    ) -> Dict[str, Any]:
        """
        Execute the complete processing pipeline.

        Args:
            image_path: Path to input image file
            output_dir: Directory for output files
            geo_registration: Optional GeoRegistration object for georeferencing

        Returns:
            Dictionary containing processing results

        Raises:
            ValueError: If image cannot be read or processing fails
        """
        await self._send_progress(0.0, "Starting processing...")

        # Step 1: Read image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Unable to read image: {image_path}")

        logger.info(f"Processing image: {image.shape}")

        # Step 2: Preprocess
        await self._send_progress(0.1, "Preprocessing image...")
        processed = self.preprocessor.preprocess(image)
        logger.info("Preprocessing complete")

        # Step 3: Extract contours
        await self._send_progress(0.3, "Extracting contour lines...")
        contours, _ = self.contour_extractor.extract(processed)
        logger.info(f"Extracted {len(contours)} contour lines")

        # Step 4: Extract boundaries
        await self._send_progress(0.5, "Extracting geological boundaries...")
        boundaries, _ = self.boundary_extractor.extract(processed)
        logger.info(f"Extracted {len(boundaries)} geological boundaries")

        # Step 5: Extract stratigraphy
        await self._send_progress(0.7, "Identifying stratigraphic units...")
        stratigraphy = self.stratigraphy_extractor.extract(processed)
        logger.info(f"Identified {len(stratigraphy)} stratigraphic layers")

        # Step 6: Generate outputs
        await self._send_progress(0.9, "Generating output files...")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = {
            'contours_count': len(contours),
            'boundaries_count': len(boundaries),
            'stratigraphy_layers': len(stratigraphy),
            'output_dir': str(output_path),
            'files': []
        }

        if GEOPANDAS_AVAILABLE:
            # Save contours
            if contours:
                contours_gdf = gpd.GeoDataFrame(
                    {'geometry': contours, 'type': 'contour'},
                    crs='EPSG:4326'
                )
                contours_file = output_path / "contours.geojson"
                contours_gdf.to_file(contours_file, driver='GeoJSON')
                results['files'].append('contours.geojson')
                logger.info(f"Saved contours to {contours_file}")

            # Save boundaries
            if boundaries:
                boundaries_gdf = gpd.GeoDataFrame(
                    {'geometry': boundaries, 'type': 'boundary'},
                    crs='EPSG:4326'
                )
                boundaries_file = output_path / "boundaries.geojson"
                boundaries_gdf.to_file(boundaries_file, driver='GeoJSON')
                results['files'].append('boundaries.geojson')
                logger.info(f"Saved boundaries to {boundaries_file}")

            # Save stratigraphy
            if stratigraphy:
                for color_idx, data in stratigraphy.items():
                    if data['polygons']:
                        strata_gdf = gpd.GeoDataFrame(
                            {
                                'color': [str(data['color'])] * len(data['polygons']),
                                'layer_id': [color_idx] * len(data['polygons']),
                                'geometry': data['polygons']
                            },
                            crs='EPSG:4326'
                        )
                        strata_file = output_path / f"stratigraphy_{color_idx}.geojson"
                        strata_gdf.to_file(strata_file, driver='GeoJSON')
                        results['files'].append(f"stratigraphy_{color_idx}.geojson")
                        logger.info(f"Saved stratigraphy layer {color_idx} to {strata_file}")
        else:
            logger.warning("geopandas not available - skipping file output")

        # Complete
        await self._send_progress(1.0, "Processing complete")
        await self._send_complete(results)

        logger.info(f"Processing complete for task {self.task_id}")
        return results

    async def process_with_georeferencing(
        self,
        image_path: str,
        output_dir: str,
        geo_registration: GeoRegistration
    ) -> Dict[str, Any]:
        """
        Process with georeferencing transformation.

        Args:
            image_path: Path to input image file
            output_dir: Directory for output files
            geo_registration: GeoRegistration object with GCPs

        Returns:
            Dictionary containing processing results
        """
        if not GDAL_AVAILABLE:
            logger.warning("GDAL not available - skipping georeferencing")
            return await self.process(image_path, output_dir, None)

        await self._send_progress(0.0, "Starting georeferenced processing...")

        # First do georeferencing
        await self._send_progress(0.05, "Applying georeferencing...")
        georef_output = geo_registration.transform_image(
            image_path,
            str(Path(output_dir) / "georeferenced.tiff")
        )

        # Then process the georeferenced image
        result = await self.process(
            str(Path(output_dir) / "georeferenced.tiff"),
            output_dir,
            geo_registration
        )

        result['georeferencing'] = {
            'rms_error': georef_output['rms_error'],
            'gcp_count': georef_output['gcp_count']
        }

        return result
