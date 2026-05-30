import {
  GRID,
  SPEED,
  SCORE,
  MODES,
  POWERUPS,
  SPECIAL_SPAWN_CHANCE,
} from './config.js';
import { Snake } from './snake.js';
import { randomFreeCell, pickSpecialType } from './food.js';
import { buildObstacles } from './level.js';
import { Particles } from './particles.js';
import { Emitter } from './events.js';

// Game states
export const State = {
  MENU: 'menu',
  PLAYING: 'playing',
  PAUSED: 'paused',
  GAMEOVER: 'gameover',
};

export class Game {
  constructor() {
    this.cols = GRID.cols;
    this.rows = GRID.rows;
    this.events = new Emitter();
    this.particles = new Particles();
    this.state = State.MENU;

    this.modeKey = 'classic';
    this.speedKey = 'normal';

    this.reset();
  }

  // ---- lifecycle -------------------------------------------------------------

  reset() {
    const cx = Math.floor(this.cols / 2);
    const cy = Math.floor(this.rows / 2);
    this.snake = new Snake(cx, cy, { x: 1, y: 0 }, 3);
    this.obstacles = [];
    this.apple = null;
    this.special = null;
    this.effects = new Map();
    this.particles.clear();

    this.score = 0;
    this.level = 1;
    this.combo = 0;
    this.lastEatTime = -Infinity;

    this.time = 0; // ms game clock (frozen while paused)
    this.acc = 0; // tick accumulator (ms)
    this.moveProgress = 0; // 0..1 interpolation between cells
    this.shake = 0;
  }

  start(modeKey = this.modeKey, speedKey = this.speedKey) {
    this.modeKey = modeKey in MODES ? modeKey : 'classic';
    this.speedKey = speedKey in SPEED ? speedKey : 'normal';
    this.reset();

    if (MODES[this.modeKey].obstacles) {
      this.obstacles = buildObstacles(1, this.cols, this.rows).filter(
        (c) => !this.snake.occupies(c.x, c.y)
      );
    }
    this.apple = this.spawnCell();
    this.state = State.PLAYING;
    this.events.emit('start', { mode: this.modeKey });
    this.events.emit('score', { score: 0 });
  }

  pause() {
    if (this.state === State.PLAYING) {
      this.state = State.PAUSED;
      this.events.emit('pause');
    }
  }

  resume() {
    if (this.state === State.PAUSED) {
      this.state = State.PLAYING;
      this.events.emit('resume');
    }
  }

  toMenu() {
    this.state = State.MENU;
    this.reset();
  }

  // ---- input ----------------------------------------------------------------

  turn(dx, dy) {
    if (this.state === State.PLAYING) this.snake.turn(dx, dy);
  }

  // ---- main update -----------------------------------------------------------

  update(dtSec) {
    // Clamp dt so a tab regaining focus (or a long pause) can't fast-forward
    // dozens of ticks in one frame.
    const dt = Math.min(dtSec, 0.05);

    this.particles.update(dt);
    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 2.4);

    if (this.state !== State.PLAYING) return;

    this.time += dt * 1000;
    this.expireEffects();
    this.expireSpecial();
    if (this.combo > 0 && this.time - this.lastEatTime > SCORE.comboWindowMs) {
      this.combo = 0;
      this.events.emit('combo', { combo: 0 });
    }

    const interval = this.tickInterval();
    this.acc += dt * 1000;
    let ticks = 0;
    while (this.acc >= interval && ticks++ < 4) {
      this.acc -= interval;
      this.tick();
      if (this.state !== State.PLAYING) {
        this.acc = 0;
        break;
      }
    }
    this.moveProgress = Math.min(1, this.acc / interval);
  }

  tickInterval() {
    const s = SPEED[this.speedKey];
    let ms = Math.max(s.min, s.start - (this.level - 1) * s.step);
    const speedFx = this.effects.get('speed');
    const slowFx = this.effects.get('slow');
    if (speedFx) ms *= speedFx.factor;
    if (slowFx) ms *= slowFx.factor;
    return Math.max(36, ms);
  }

  // ---- one logic step --------------------------------------------------------

  tick() {
    const wrap = MODES[this.modeKey].wall === 'wrap';
    const head = this.snake.nextHead(this.cols, this.rows, wrap);
    const ghost = this.effects.has('ghost');

    // Wall collision (only when not wrapping)
    if (!wrap && (head.x < 0 || head.y < 0 || head.x >= this.cols || head.y >= this.rows)) {
      return this.die(head);
    }

    // Obstacle collision (ghost phases through)
    if (!ghost && this.isObstacle(head.x, head.y)) {
      return this.die(head);
    }

    const willEatApple = this.apple && head.x === this.apple.x && head.y === this.apple.y;

    // Self collision. The tail cell is vacated this tick unless we're growing,
    // so exclude it from the check when not eating.
    if (!ghost) {
      const last = this.snake.length - 1;
      for (let i = 0; i < this.snake.length; i++) {
        if (i === last && !willEatApple) continue;
        const s = this.snake.segments[i];
        if (s.x === head.x && s.y === head.y) return this.die(head);
      }
    }

    if (willEatApple) this.snake.grow(1);
    this.snake.advance(head);

    if (willEatApple) this.onApple(head);
    if (this.special && head.x === this.special.x && head.y === this.special.y) {
      this.onSpecial(head);
    }
  }

  // ---- eating ----------------------------------------------------------------

  onApple(at) {
    // Combo: increment if we ate within the window, else restart at 1.
    this.combo =
      this.time - this.lastEatTime <= SCORE.comboWindowMs
        ? Math.min(this.combo + 1, SCORE.comboMax)
        : 1;
    this.lastEatTime = this.time;

    const comboMult = Math.max(1, this.combo);
    const goldenMult = this.effects.has('golden') ? 2 : 1;
    const points = SCORE.apple * comboMult * goldenMult;
    this.addScore(points);

    this.particles.burst(at.x + 0.5, at.y + 0.5, '#ff6b8f', 16, { speed: 7 });
    this.events.emit('eat', { ...at, points, combo: this.combo });
    if (this.combo >= 2) this.events.emit('combo', { combo: this.combo });

    // Respawn apple, maybe spawn a special pickup.
    this.apple = this.spawnCell();
    if (!this.apple) return this.win();
    if (!this.special && Math.random() < SPECIAL_SPAWN_CHANCE) {
      this.spawnSpecial();
    }
  }

  onSpecial(at) {
    const def = POWERUPS[this.special.type];
    this.special = null;
    this.addScore(def.points);
    this.particles.burst(at.x + 0.5, at.y + 0.5, def.color, 22, { speed: 8 });
    this.shake = Math.max(this.shake, 0.35);
    this.events.emit('powerup', {
      type: def.key,
      label: def.label,
      icon: def.icon,
      color: def.color,
      duration: def.durationMs,
    });

    switch (def.key) {
      case 'golden':
        this.effects.set('golden', { until: this.time + def.durationMs });
        break;
      case 'speed':
        this.effects.delete('slow');
        this.effects.set('speed', { until: this.time + def.durationMs, factor: def.speedFactor });
        break;
      case 'slow':
        this.effects.delete('speed');
        this.effects.set('slow', { until: this.time + def.durationMs, factor: def.speedFactor });
        break;
      case 'ghost':
        this.effects.set('ghost', { until: this.time + def.durationMs });
        break;
      case 'shrink': {
        const before = this.snake.length;
        this.snake.shrink(def.shrinkBy);
        const removed = before - this.snake.length;
        if (removed > 0) this.addScore(0); // no extra; trim is its own reward
        break;
      }
    }
  }

  addScore(points) {
    this.score += points;
    this.events.emit('score', { score: this.score, gained: points });

    const newLevel = 1 + Math.floor(this.score / SCORE.perLevel);
    if (newLevel > this.level) this.levelUp(newLevel);
  }

  levelUp(level) {
    this.level = level;
    this.shake = Math.max(this.shake, 0.25);
    this.events.emit('levelup', { level });

    if (MODES[this.modeKey].obstacles) {
      const next = buildObstacles(level, this.cols, this.rows).filter(
        (c) => !this.snake.occupies(c.x, c.y)
      );
      this.obstacles = next;
      // Don't let new walls swallow the food.
      if (this.apple && this.isObstacle(this.apple.x, this.apple.y)) this.apple = this.spawnCell();
      if (this.special && this.isObstacle(this.special.x, this.special.y)) this.special = null;
    }
  }

  // ---- effects & special lifetime -------------------------------------------

  expireEffects() {
    for (const [k, v] of this.effects) {
      if (this.time >= v.until) {
        this.effects.delete(k);
        this.events.emit('effectend', { type: k });
      }
    }
  }

  expireSpecial() {
    if (!this.special) return;
    const def = POWERUPS[this.special.type];
    if (this.time - this.special.born > def.lifeMs) {
      this.particles.burst(this.special.x + 0.5, this.special.y + 0.5, def.color, 8, {
        speed: 3,
      });
      this.special = null;
    }
  }

  // Effects snapshot for the HUD pips. Returns active, timed effects with 0..1
  // remaining fraction.
  getEffects() {
    const out = [];
    for (const [k, v] of this.effects) {
      const def = POWERUPS[k];
      if (!def || !def.durationMs) continue;
      out.push({
        type: k,
        icon: def.icon,
        label: def.label,
        color: def.color,
        remaining: Math.max(0, (v.until - this.time) / def.durationMs),
      });
    }
    return out;
  }

  hasEffect(type) {
    return this.effects.has(type);
  }

  // ---- spawning --------------------------------------------------------------

  spawnCell() {
    return randomFreeCell(this.cols, this.rows, (x, y) => this.isBlocked(x, y));
  }

  spawnSpecial() {
    const cell = randomFreeCell(this.cols, this.rows, (x, y) => this.isBlocked(x, y));
    if (!cell) return;
    this.special = { x: cell.x, y: cell.y, type: pickSpecialType(), born: this.time };
    const def = POWERUPS[this.special.type];
    this.events.emit('special', { type: def.key, color: def.color });
  }

  isBlocked(x, y) {
    if (this.snake.occupies(x, y)) return true;
    if (this.isObstacle(x, y)) return true;
    if (this.apple && this.apple.x === x && this.apple.y === y) return true;
    if (this.special && this.special.x === x && this.special.y === y) return true;
    return false;
  }

  isObstacle(x, y) {
    for (const o of this.obstacles) if (o.x === x && o.y === y) return true;
    return false;
  }

  // ---- terminal states -------------------------------------------------------

  die(at) {
    this.shake = 1;
    // Explode along the whole body for a satisfying death.
    for (let i = 0; i < this.snake.length; i += 1) {
      const s = this.snake.segments[i];
      const t = i / this.snake.length;
      this.particles.burst(s.x + 0.5, s.y + 0.5, t < 0.5 ? '#b8ff5c' : '#16d6ff', 6, {
        speed: 9,
        life: 0.7,
      });
    }
    if (at) this.particles.burst(at.x + 0.5, at.y + 0.5, '#ff3b6b', 26, { speed: 11, life: 0.8 });

    this.state = State.GAMEOVER;
    this.events.emit('gameover', {
      score: this.score,
      length: this.snake.length,
      level: this.level,
    });
  }

  win() {
    // Board completely filled — extraordinarily rare, but handle it gracefully.
    this.state = State.GAMEOVER;
    this.events.emit('gameover', {
      score: this.score,
      length: this.snake.length,
      level: this.level,
      won: true,
    });
  }
}
