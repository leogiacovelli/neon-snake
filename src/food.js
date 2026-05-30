import { POWERUPS } from './config.js';

// Spawn helpers shared by the game core. `isBlocked(x, y)` reports cells that are
// unavailable (snake body, obstacles, existing pickups).

export function randomFreeCell(cols, rows, isBlocked) {
  // Reservoir-free approach: collect all free cells once, pick one. With a 23x23
  // board this is trivially cheap and avoids the infinite-loop risk of rejection
  // sampling when the board is nearly full (late game).
  const free = [];
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (!isBlocked(x, y)) free.push({ x, y });
    }
  }
  if (!free.length) return null; // board full — player basically won
  return free[(Math.random() * free.length) | 0];
}

const WEIGHTED = Object.values(POWERUPS);
const TOTAL_WEIGHT = WEIGHTED.reduce((s, p) => s + p.weight, 0);

export function pickSpecialType() {
  let r = Math.random() * TOTAL_WEIGHT;
  for (const p of WEIGHTED) {
    if ((r -= p.weight) <= 0) return p.key;
  }
  return WEIGHTED[0].key;
}
