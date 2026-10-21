import { FACE_COLOURS } from "./Cube3D";

// Unfolded net so all six faces are visible (the 3D view shows only three).
//        U
//     L  F  R  B
//        D
const LAYOUT: Record<string, [number, number]> = { U: [1, 0], L: [0, 1], F: [1, 1], R: [2, 1], B: [3, 1], D: [1, 2] };
const ORDER = "URFDLB";

export default function CubeNet({ state, size = 7 }: { state: string; size?: number }) {
  const cells = [];
  for (let f = 0; f < 6; f++) {
    const [fx, fy] = LAYOUT[ORDER[f]];
    for (let i = 0; i < 9; i++) {
      const x = fx * 3 + (i % 3);
      const y = fy * 3 + Math.floor(i / 3);
      cells.push(
        <rect
          key={f * 9 + i}
          x={x * size + 0.5}
          y={y * size + 0.5}
          width={size - 1}
          height={size - 1}
          rx={1.2}
          fill={FACE_COLOURS[state[f * 9 + i]] ?? "#999"}
        />,
      );
    }
  }
  return (
    <svg className="cube-net" width={12 * size} height={9 * size} role="img" aria-label="Cube net showing all six faces">
      {cells}
    </svg>
  );
}
