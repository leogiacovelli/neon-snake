// Headless smoke test for the DOM-free game core. Not a full unit suite — it
// exercises the high-risk paths (growth, wrap, wall death, self-collision, maze
// integrity, long random play) and fails loudly. Run: `npm test`.

import { Game, State } from '../src/game.js';

let failures = 0;
const assert = (cond, msg) => {
  if (cond) {
    console.log('  ✓', msg);
  } else {
    console.error('  ✗', msg);
    failures++;
  }
};

function freshHead(game, x, y, dir = { x: 1, y: 0 }) {
  // Rebuild a clean 3-cell body ending at (x,y) facing `dir`, queue empty.
  game.snake.dir = { ...dir };
  game.snake.queue = [];
  game.snake.growBy = 0;
  game.snake.segments = [
    { x, y },
    { x: x - dir.x, y: y - dir.y },
    { x: x - 2 * dir.x, y: y - 2 * dir.y },
  ];
  game.snake.prev = game.snake.segments.map((s) => ({ ...s }));
}

console.log('eating & growth');
{
  const g = new Game();
  g.start('classic', 'normal');
  freshHead(g, 11, 11);
  g.apple = { x: 12, y: 11 };
  g.special = null;
  const len0 = g.snake.length;
  g.tick();
  assert(g.snake.length === len0 + 1, 'snake grows by 1 after eating');
  assert(g.score > 0, 'score increases after eating');
  assert(g.snake.head.x === 12 && g.snake.head.y === 11, 'head moves onto apple');
  assert(g.state === State.PLAYING, 'still playing after eating');
}

console.log('wrap mode wraps edges');
{
  const g = new Game();
  g.start('wrap', 'normal');
  freshHead(g, g.cols - 1, 11);
  g.apple = { x: 1, y: 1 };
  g.tick();
  assert(g.state === State.PLAYING, 'no death at edge in wrap mode');
  assert(g.snake.head.x === 0, 'head wraps to opposite edge');
}

console.log('classic mode wall is deadly');
{
  const g = new Game();
  g.start('classic', 'normal');
  freshHead(g, g.cols - 1, 11);
  g.apple = { x: 1, y: 1 };
  g.tick();
  assert(g.state === State.GAMEOVER, 'hitting the wall ends the game');
}

console.log('self collision ends the game');
{
  const g = new Game();
  g.start('classic', 'normal');
  // Coiled body: moving the head one more step right lands on segment[7],
  // a body cell that will NOT vacate this tick (the tail is segment[8]).
  g.snake.dir = { x: 1, y: 0 };
  g.snake.queue = [];
  g.snake.growBy = 0;
  g.snake.segments = [
    { x: 13, y: 11 }, // head, facing right
    { x: 12, y: 11 },
    { x: 11, y: 11 },
    { x: 11, y: 10 },
    { x: 12, y: 10 },
    { x: 13, y: 10 },
    { x: 14, y: 10 },
    { x: 14, y: 11 }, // head will move here -> self-bite
    { x: 14, y: 12 }, // tail (vacates, so excluded from the check)
  ];
  g.snake.prev = g.snake.segments.map((s) => ({ ...s }));
  g.apple = { x: 1, y: 1 };
  g.tick();
  assert(g.state === State.GAMEOVER, 'biting own body ends the game');
}

console.log('maze obstacles are valid');
{
  const g = new Game();
  g.start('maze', 'normal');
  assert(g.obstacles.length > 0, 'maze mode spawns obstacles');
  const onSnake = g.obstacles.some((o) => g.snake.occupies(o.x, o.y));
  assert(!onSnake, 'no obstacle overlaps the snake');
  const inBounds = g.obstacles.every(
    (o) => o.x >= 0 && o.y >= 0 && o.x < g.cols && o.y < g.rows
  );
  assert(inBounds, 'all obstacles are inside the board');
}

console.log('long random play never throws and terminates');
{
  const g = new Game();
  g.start('classic', 'insane');
  let threw = null;
  let i = 0;
  try {
    for (; i < 5000 && g.state === State.PLAYING; i++) {
      if (Math.random() < 0.15) {
        const d = [
          [1, 0],
          [-1, 0],
          [0, 1],
          [0, -1],
        ][(Math.random() * 4) | 0];
        g.turn(d[0], d[1]);
      }
      g.update(0.05);
    }
  } catch (e) {
    threw = e;
  }
  assert(!threw, 'no exception during 5000-frame random play' + (threw ? `: ${threw.message}` : ''));
  assert(g.state === State.GAMEOVER, 'random play eventually ends');
}

console.log('');
if (failures) {
  console.error(`✗ ${failures} assertion(s) failed`);
  process.exit(1);
} else {
  console.log('✓ all smoke tests passed');
}
