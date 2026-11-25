import type { MiniMapNodeProps } from "@xyflow/react";

/** Нода на мини-карте: простой прямоугольник с рамкой. */
export default function MiniMapNode({ x, y, width, height, color, selected, onClick, id }: MiniMapNodeProps) {
    return (
        <g onClick={(e) => onClick?.(e, id)} className="cursor-pointer">
            <rect
                x={x}
                y={y}
                width={width}
                height={height}
                rx={6}
                fill="#ffffff"
                stroke={color}
                strokeWidth={selected ? 10 : 7}
            />
        </g>
    );
}
