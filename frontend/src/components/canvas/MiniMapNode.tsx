import type { MiniMapNodeProps } from "@xyflow/react";

/** Нода на мини-карте: уменьшенная «карточка» — цветная шапка и строки текста, как на рабочем поле. */
export default function MiniMapNode({ x, y, width, height, color, selected, onClick, id }: MiniMapNodeProps) {
    const headerHeight = Math.min(height * 0.38, 44);
    const lineHeight = Math.max(height * 0.07, 4);
    return (
        <g onClick={(e) => onClick?.(e, id)} className="cursor-pointer">
            <rect x={x} y={y} width={width} height={height} rx={10} fill="#ffffff" stroke={color} strokeWidth={selected ? 6 : 3} />
            <rect x={x} y={y} width={width} height={headerHeight} rx={10} fill={color} opacity={0.85} />
            <rect x={x + 12} y={y + headerHeight + lineHeight * 1.2} width={width * 0.7} height={lineHeight} rx={lineHeight / 2} fill="#d1d5db" />
            <rect x={x + 12} y={y + headerHeight + lineHeight * 3} width={width * 0.45} height={lineHeight} rx={lineHeight / 2} fill="#e5e7eb" />
        </g>
    );
}
