// Lightweight particle system. Positions are in grid units (not pixels) so the
// renderer can scale them with the board. Particles are pooled implicitly via a
// flat array that's compacted each frame.

export class Particles {
  constructor() {
    this.list = [];
  }

  burst(x, y, color, count = 14, opts = {}) {
    const speed = opts.speed ?? 6;
    const life = opts.life ?? 0.5;
    const size = opts.size ?? 0.16;
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.35 + Math.random() * 0.65);
      this.list.push({
        x,
        y,
        vx: Math.cos(a) * v,
        vy: Math.sin(a) * v,
        life,
        maxLife: life,
        color,
        size: size * (0.6 + Math.random() * 0.8),
        gravity: opts.gravity ?? 0,
      });
    }
  }

  update(dt) {
    const drag = Math.pow(0.0008, dt); // strong velocity damping
    let w = 0;
    for (let i = 0; i < this.list.length; i++) {
      const p = this.list[i];
      p.life -= dt;
      if (p.life <= 0) continue;
      p.vx *= drag;
      p.vy = p.vy * drag + p.gravity * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      this.list[w++] = p;
    }
    this.list.length = w;
  }

  clear() {
    this.list.length = 0;
  }
}
