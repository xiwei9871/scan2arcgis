import React, { useState, useEffect, useRef } from 'react';
import { Stage, Layer, Circle, Image as KonvaImage } from 'react-konva';
import useImage from 'use-image';

interface Point {
  x: number;
  y: number;
}

interface RegistrationCanvasProps {
  imageUrl: string;
  onPointsChange: (points: Point[]) => void;
}

const URLImage = ({ image, x, y, scale }: { image: HTMLImageElement | null; x: number; y: number; scale: number }) => {
  if (!image) return null;
  return <KonvaImage image={image} x={x} y={y} scale={{ x: scale, y: scale }} />;
};

export const RegistrationCanvas: React.FC<RegistrationCanvasProps> = ({ imageUrl, onPointsChange }) => {
  const [image] = useImage(imageUrl);
  const [points, setPoints] = useState<Point[]>([]);
  const [scale, setScale] = useState(1);
  const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (image && containerRef.current) {
      const containerWidth = containerRef.current.offsetWidth - 40;
      const containerHeight = containerRef.current.offsetHeight - 40;

      const imageWidth = image.width;
      const imageHeight = image.height;

      const scaleX = containerWidth / imageWidth;
      const scaleY = containerHeight / imageHeight;
      const calculatedScale = Math.min(scaleX, scaleY, 1);

      setScale(calculatedScale);
      setStageSize({
        width: imageWidth * calculatedScale,
        height: imageHeight * calculatedScale,
      });
    }
  }, [image]);

  const handleStageClick = (e: any) => {
    const stage = e.target.getStage();
    if (!stage) return;

    const pointerPos = stage.getPointerPosition();
    if (!pointerPos) return;

    const clickedOnCircle = e.target instanceof Circle;

    if (clickedOnCircle) {
      const pointIndex = parseInt(e.target.index());
      const newPoints = points.filter((_, i) => i !== pointIndex);
      setPoints(newPoints);
      onPointsChange(newPoints);
    } else {
      const newPoint = {
        x: pointerPos.x / scale,
        y: pointerPos.y / scale,
      };
      const newPoints = [...points, newPoint];
      setPoints(newPoints);
      onPointsChange(newPoints);
    }
  };

  return (
    <div ref={containerRef} className="w-full h-full flex flex-col">
      <div className="mb-4 text-center">
        <p className="text-sm text-gray-600">
          已标记 {points.length} 个控制点（至少需要 3 个）
        </p>
        <p className="text-xs text-gray-500 mt-1">
          点击图像添加控制点，点击红色圆点删除
        </p>
      </div>
      <div className="flex-1 flex items-center justify-center border border-gray-300 rounded-lg overflow-hidden bg-gray-50">
        <Stage
          width={stageSize.width}
          height={stageSize.height}
          onClick={handleStageClick}
        >
          <Layer>
            {image && <URLImage image={image} x={0} y={0} scale={scale} />}
            {points.map((point, index) => (
              <Circle
                key={index}
                index={index}
                x={point.x * scale}
                y={point.y * scale}
                radius={8}
                fill="red"
                stroke="white"
                strokeWidth={2}
              />
            ))}
          </Layer>
        </Stage>
      </div>
    </div>
  );
};
