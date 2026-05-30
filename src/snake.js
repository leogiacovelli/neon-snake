// The snake entity. It owns its body cells and a snapshot of the previous tick,
// which the renderer uses to interpolate smooth motion between discrete grid
// steps. The Game decides collisions; the Snake only knows how to move itself.

export class Snake {
  constructor(cx, cy, dir = { x: 1, y: 0 }, startLength = 3) {
    this.dir = { ...dir };
    this.segments = [];
    for (let i = 0; i < startLength; i++) {
      this.segments.push({ x: cx - i * dir.x, y: cy - i * dir.y });
    }
    this.prev = this.segments.map((s) => ({ ...s }));
    this.queue = []; // buffered direction changes (max 2)
    this.growBy = 0;
  }

  get head() {
    return this.segments[0];
  }

  get length() {
    return this.segments.length;
  }

  // Queue a turn. Rejects 180° reversals relative to the last queued/active dir
  // and ignores no-ops. Buffering up to two turns makes fast inputs feel precise.
  turn(dx, dy) {
    const last = this.queue.length ? this.queue[this.queue.length - 1] : this.dir;
    if (dx === last.x && dy === last.y) return; // same direction
    if (dx === -last.x && dy === -last.y) return; // reversal
    if (this.queue.length < 2) this.queue.push({ x: dx, y: dy });
  }

  // Compute the next head cell from the queued direction, applying edge wrap.
  nextHead(cols, rows, wrap) {
    if (this.queue.length) this.dir = this.queue.shift();
    let nx = this.head.x + this.dir.x;
    let ny = this.head.y + this.dir.y;
    if (wrap) {
      nx = (nx + cols) % cols;
      ny = (ny + rows) % rows;
    }
    return { x: nx, y: ny };
  }

  // Commit movement: snapshot for interpolation, add the new head, drop the tail
  // unless we owe growth.
  advance(head) {
    this.prev = this.segments.map((s) => ({ ...s }));
    this.segments.unshift(head);
    if (this.growBy > 0) {
      this.growBy--;
      // Keep prev the same length as segments so interpolation has a partner
      // for the freshly added head (it appears to grow out of the neck).
      this.prev.unshift({ ...this.prev[0] });
    } else {
      this.segments.pop();
    }
  }

  grow(n = 1) {
    this.growBy += n;
  }

  shrink(n) {
    const min = 2;
    const target = Math.max(min, this.segments.length - n);
    this.segments.length = target;
    if (this.prev.length > target) this.prev.length = target;
  }

  occupies(x, y, fromIndex = 0) {
    for (let i = fromIndex; i < this.segments.length; i++) {
      if (this.segments[i].x === x && this.segments[i].y === y) return true;
    }
    return false;
  }
}
