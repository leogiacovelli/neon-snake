// Input handling: keyboard (Arrows/WASD), touch swipe, and a few action keys.
// The game core is the single source of truth — we only translate raw events into
// intent (turn / pause / primary action / resume-audio gesture).

const DIRS = {
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  w: [0, -1],
  s: [0, 1],
  a: [-1, 0],
  d: [1, 0],
  W: [0, -1],
  S: [0, 1],
  A: [-1, 0],
  D: [1, 0],
};

export class Input {
  constructor(target, game, handlers = {}) {
    this.target = target;
    this.game = game;
    this.onPause = handlers.onPause || (() => {});
    this.onPrimary = handlers.onPrimary || (() => {});
    this.onGesture = handlers.onGesture || (() => {});
    this._touch = null;
    this.bind();
  }

  bind() {
    window.addEventListener('keydown', (e) => this.onKey(e), { passive: false });

    const t = this.target;
    t.addEventListener('touchstart', (e) => this.touchStart(e), { passive: false });
    t.addEventListener('touchend', (e) => this.touchEnd(e), { passive: false });
    // First pointer/touch anywhere unlocks audio.
    const wake = () => this.onGesture();
    window.addEventListener('pointerdown', wake, { once: true });
    window.addEventListener('keydown', wake, { once: true });
  }

  onKey(e) {
    const dir = DIRS[e.key];
    if (dir) {
      e.preventDefault();
      this.game.turn(dir[0], dir[1]);
      return;
    }
    if (e.key === ' ' || e.key === 'p' || e.key === 'P' || e.key === 'Escape') {
      e.preventDefault();
      this.onPause();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      this.onPrimary();
    }
  }

  touchStart(e) {
    const t = e.changedTouches[0];
    this._touch = { x: t.clientX, y: t.clientY };
  }

  touchEnd(e) {
    if (!this._touch) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - this._touch.x;
    const dy = t.clientY - this._touch.y;
    this._touch = null;
    const adx = Math.abs(dx);
    const ady = Math.abs(dy);
    if (Math.max(adx, ady) < 24) return; // tap, not a swipe
    e.preventDefault();
    if (adx > ady) this.game.turn(Math.sign(dx), 0);
    else this.game.turn(0, Math.sign(dy));
  }
}
