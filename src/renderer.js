import { COLORS, POWERUPS } from './config.js';
import { State } from './game.js';

// Canvas renderer. Works in CSS pixels (the context is pre-scaled by devicePixelRatio)
// and converts grid units to pixels via `cell`. All motion is interpolated between
// the snake's previous and current cells using game.moveProgress for buttery 60fps
// movement on top of the discrete logic grid.

const lerp = (a, b, t) => a + (b - a) * t;

export class Renderer {
  constructor(canvas, game) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.game = game;
    this.cell = 10;
    this.w = 0;
    this.h = 0;
    this.t = 0; // wall-clock seconds for ambient animation
    this.resize();
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const rect = this.canvas.getBoundingClientRect();
    const cssW = Math.max(1, rect.width);
    const cssH = Math.max(1, rect.height);
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round(cssH * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = cssW;
    this.h = cssH;
    this.cell = Math.min(cssW / this.game.cols, cssH / this.game.rows);
    // Centre the board if the canvas isn't a perfect square.
    this.offX = (cssW - this.cell * this.game.cols) / 2;
    this.offY = (cssH - this.cell * this.game.rows) / 2;
  }

  px(gx) {
    return this.offX + gx * this.cell;
  }
  py(gy) {
    return this.offY + gy * this.cell;
  }

  render(dt) {
    this.t += dt;
    const ctx = this.ctx;
    const g = this.game;

    ctx.save();
    ctx.clearRect(0, 0, this.w, this.h);

    // Screen shake
    if (g.shake > 0) {
      const m = g.shake * g.shake * 8;
      ctx.translate((Math.random() - 0.5) * m, (Math.random() - 0.5) * m);
    }

    this.drawGrid();
    this.drawObstacles();
    this.drawApple();
    this.drawSpecial();
    if (g.state !== State.MENU) this.drawSnake();
    this.drawParticles();

    ctx.restore();
  }

  // ---- layers ----------------------------------------------------------------

  drawGrid() {
    const ctx = this.ctx;
    const { cols, rows } = this.game;
    ctx.lineWidth = 1;
    ctx.strokeStyle = COLORS.grid;
    ctx.beginPath();
    for (let x = 0; x <= cols; x++) {
      ctx.moveTo(Math.round(this.px(x)) + 0.5, this.py(0));
      ctx.lineTo(Math.round(this.px(x)) + 0.5, this.py(rows));
    }
    for (let y = 0; y <= rows; y++) {
      ctx.moveTo(this.px(0), Math.round(this.py(y)) + 0.5);
      ctx.lineTo(this.px(cols), Math.round(this.py(y)) + 0.5);
    }
    ctx.stroke();
  }

  drawObstacles() {
    const ctx = this.ctx;
    const c = this.cell;
    for (const o of this.game.obstacles) {
      const x = this.px(o.x);
      const y = this.py(o.y);
      ctx.fillStyle = COLORS.obstacle;
      this.roundRect(x + 1, y + 1, c - 2, c - 2, c * 0.22);
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = COLORS.obstacleEdge;
      ctx.stroke();
    }
  }

  drawApple() {
    const a = this.game.apple;
    if (!a) return;
    const c = this.cell;
    const cx = this.px(a.x) + c / 2;
    const cy = this.py(a.y) + c / 2;
    const pulse = 0.5 + 0.5 * Math.sin(this.t * 5);
    const r = c * (0.3 + 0.04 * pulse);
    this.glowDot(cx, cy, r, COLORS.apple, 18 + pulse * 8);
  }

  drawSpecial() {
    const s = this.game.special;
    if (!s) return;
    const def = POWERUPS[s.type];
    const c = this.cell;
    const cx = this.px(s.x) + c / 2;
    const cy = this.py(s.y) + c / 2;

    // Blink faster as it's about to expire.
    const ageFrac = (this.game.time - s.born) / def.lifeMs;
    const blink = ageFrac > 0.65 ? (Math.sin(this.t * 22) > -0.2 ? 1 : 0.25) : 1;
    if (blink < 0.5) return;

    const pulse = 0.5 + 0.5 * Math.sin(this.t * 6);
    this.glowDot(cx, cy, c * (0.34 + 0.04 * pulse), def.color, 22);

    const ctx = this.ctx;
    ctx.save();
    ctx.font = `${Math.round(c * 0.62)}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(def.icon, cx, cy + c * 0.02);
    ctx.restore();
  }

  drawSnake() {
    const ctx = this.ctx;
    const g = this.game;
    const snake = g.snake;
    const c = this.cell;
    const prog = g.state === State.PLAYING ? g.moveProgress : 1;
    const ghost = g.hasEffect('ghost');

    // Build interpolated centre points (px). Snap segments that wrapped the edge.
    const pts = [];
    for (let i = 0; i < snake.segments.length; i++) {
      const cur = snake.segments[i];
      const prev = snake.prev[i] || cur;
      let gx = cur.x;
      let gy = cur.y;
      if (Math.abs(cur.x - prev.x) <= 1 && Math.abs(cur.y - prev.y) <= 1) {
        gx = lerp(prev.x, cur.x, prog);
        gy = lerp(prev.y, cur.y, prog);
      }
      pts.push({ x: this.px(gx) + c / 2, y: this.py(gy) + c / 2 });
    }

    // Split into sub-paths wherever the body crosses the wrap seam.
    const segs = [[pts[0]]];
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1];
      const b = pts[i];
      if (Math.hypot(b.x - a.x, b.y - a.y) > c * 1.6) segs.push([b]);
      else segs[segs.length - 1].push(b);
    }

    const grad = ctx.createLinearGradient(pts[0].x, pts[0].y, pts[pts.length - 1].x, pts[pts.length - 1].y);
    grad.addColorStop(0, ghost ? COLORS.snakeGhost : COLORS.snakeHead);
    grad.addColorStop(1, ghost ? '#7fb4ff' : COLORS.snakeTail);

    ctx.save();
    ctx.globalAlpha = ghost ? 0.55 : 1;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.shadowColor = ghost ? COLORS.snakeGhost : COLORS.snakeHead;
    ctx.shadowBlur = c * 0.7;

    for (const path of segs) {
      if (path.length === 1) {
        // Single dot (a lone wrapped head/tail piece)
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(path[0].x, path[0].y, c * 0.4, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      ctx.strokeStyle = grad;
      ctx.lineWidth = c * 0.82;
      ctx.beginPath();
      ctx.moveTo(path[0].x, path[0].y);
      for (let i = 1; i < path.length; i++) ctx.lineTo(path[i].x, path[i].y);
      ctx.stroke();
    }
    ctx.restore();

    this.drawHead(pts[0], pts[1], ghost);
  }

  drawHead(head, neck, ghost) {
    if (!head) return;
    const ctx = this.ctx;
    const c = this.cell;

    // Facing direction (fallback: rightwards)
    let dx = 1;
    let dy = 0;
    if (neck) {
      dx = head.x - neck.x;
      dy = head.y - neck.y;
      const len = Math.hypot(dx, dy) || 1;
      dx /= len;
      dy /= len;
    }
    // Perpendicular for eye placement
    const px = -dy;
    const py = dx;
    const eyeOff = c * 0.17;
    const fwd = c * 0.1;
    const r = c * 0.1;

    ctx.save();
    ctx.globalAlpha = ghost ? 0.7 : 1;
    for (const s of [1, -1]) {
      const ex = head.x + dx * fwd + px * eyeOff * s;
      const ey = head.y + dy * fwd + py * eyeOff * s;
      ctx.fillStyle = '#05101a';
      ctx.beginPath();
      ctx.arc(ex, ey, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#eaffff';
      ctx.beginPath();
      ctx.arc(ex + dx * r * 0.3, ey + dy * r * 0.3, r * 0.45, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  drawParticles() {
    const ctx = this.ctx;
    const c = this.cell;
    ctx.save();
    for (const p of this.game.particles.list) {
      const alpha = Math.max(0, p.life / p.maxLife);
      ctx.globalAlpha = alpha;
      ctx.fillStyle = p.color;
      const size = p.size * c;
      ctx.beginPath();
      ctx.arc(this.px(p.x), this.py(p.y), size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- primitives ------------------------------------------------------------

  glowDot(cx, cy, r, color, blur) {
    const ctx = this.ctx;
    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = blur;
    const grad = ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r);
    grad.addColorStop(0, '#ffffff');
    grad.addColorStop(0.35, color);
    grad.addColorStop(1, color);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  roundRect(x, y, w, h, r) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}
