// Obstacle (maze) generation. Obstacles are short straight walls scattered around
// the board, deliberately kept away from the centre spawn zone and never long
// enough to fence off a region. The set grows with each level in maze mode.

const key = (x, y) => `${x},${y}`;

export function buildObstacles(level, cols, rows) {
  const cells = [];
  const taken = new Set();
  const cx = Math.floor(cols / 2);
  const cy = Math.floor(rows / 2);

  // Number of wall pieces scales with level, capped so the board stays playable.
  const pieces = Math.min(3 + level * 2, Math.floor((cols * rows) / 28));
  let guard = 0;

  while (cells.length < pieces && guard++ < 500) {
    const horizontal = Math.random() < 0.5;
    const len = 2 + Math.floor(Math.random() * 3); // 2..4
    const x0 = 2 + Math.floor(Math.random() * (cols - 4));
    const y0 = 2 + Math.floor(Math.random() * (rows - 4));

    const piece = [];
    let ok = true;
    for (let i = 0; i < len; i++) {
      const x = horizontal ? x0 + i : x0;
      const y = horizontal ? y0 : y0 + i;
      // Bounds + keep a clear 5x5 around centre spawn + avoid overlaps/adjacency.
      if (x < 1 || x >= cols - 1 || y < 1 || y >= rows - 1) ok = false;
      if (Math.abs(x - cx) <= 2 && Math.abs(y - cy) <= 2) ok = false;
      if (taken.has(key(x, y))) ok = false;
      piece.push({ x, y });
    }
    if (!ok) continue;

    for (const c of piece) {
      taken.add(key(c.x, c.y));
      cells.push(c);
    }
  }
  return cells;
}
