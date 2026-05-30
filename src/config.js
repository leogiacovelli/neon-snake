// Central, tunable game configuration. Keeping every magic number here makes the
// game easy to balance without hunting through logic code.

export const GRID = {
  cols: 23,
  rows: 23,
};

// Logic tick interval (ms per cell move) by difficulty. Lower = faster.
// The interval shrinks as you level up, clamped at `min`.
export const SPEED = {
  chill: { start: 165, min: 95, step: 5 },
  normal: { start: 130, min: 70, step: 6 },
  insane: { start: 95, min: 48, step: 6 },
};

export const SCORE = {
  apple: 10, // base points per apple
  perLevel: 60, // points needed to advance one level
  comboWindowMs: 2600, // eat within this window to keep the combo alive
  comboMax: 8, // combo multiplier cap
};

// Game modes. `wall` is what happens at the board edge; `obstacles` toggles the maze.
export const MODES = {
  classic: {
    label: 'Classic',
    wall: 'die',
    obstacles: false,
    hint: 'Walls are deadly. Pure & ruthless.',
  },
  wrap: {
    label: 'Wrap',
    wall: 'wrap',
    obstacles: false,
    hint: 'Edges teleport you to the other side.',
  },
  maze: {
    label: 'Maze',
    wall: 'die',
    obstacles: true,
    hint: 'Deadly walls + obstacles that grow each level.',
  },
};

// Power-up definitions. `weight` drives spawn probability for special pickups.
// Every special pickup has a limited on-board lifetime before it vanishes.
export const POWERUPS = {
  golden: {
    key: 'golden',
    label: '2x Score',
    icon: '⭐',
    color: '#ffd24d',
    weight: 26,
    lifeMs: 7000,
    durationMs: 8000,
    points: 30,
  },
  speed: {
    key: 'speed',
    label: 'Rush',
    icon: '⚡',
    color: '#38d9ff',
    weight: 22,
    lifeMs: 7000,
    durationMs: 5000,
    points: 15,
    speedFactor: 0.62, // multiplies tick interval -> faster
  },
  slow: {
    key: 'slow',
    label: 'Slow-mo',
    icon: '🌀',
    color: '#9b8cff',
    weight: 16,
    lifeMs: 7000,
    durationMs: 5500,
    points: 15,
    speedFactor: 1.5, // slower
  },
  ghost: {
    key: 'ghost',
    label: 'Ghost',
    icon: '👻',
    color: '#cfe6ff',
    weight: 14,
    lifeMs: 6500,
    durationMs: 5000,
    points: 20,
  },
  shrink: {
    key: 'shrink',
    label: 'Trim',
    icon: '✂️',
    color: '#7cffb0',
    weight: 14,
    lifeMs: 6500,
    durationMs: 0,
    points: 20,
    shrinkBy: 4,
  },
};

// Chance that, after eating an apple, a special pickup spawns on the board.
export const SPECIAL_SPAWN_CHANCE = 0.34;

export const COLORS = {
  bg: '#070b15',
  grid: 'rgba(120,150,220,0.07)',
  snakeHead: '#b8ff5c',
  snakeTail: '#16d6ff',
  snakeGhost: '#cfe6ff',
  apple: '#ff3b6b',
  obstacle: '#243056',
  obstacleEdge: '#3b58a8',
};

export const STORAGE_KEY = 'neon-snake.save.v1';
