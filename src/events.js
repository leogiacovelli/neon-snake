// Minimal synchronous event emitter used to decouple the game core from
// presentation concerns (audio, UI, particles). The core only emits; main.js
// wires the listeners.

export class Emitter {
  #map = new Map();

  on(type, fn) {
    if (!this.#map.has(type)) this.#map.set(type, new Set());
    this.#map.get(type).add(fn);
    return () => this.off(type, fn);
  }

  off(type, fn) {
    this.#map.get(type)?.delete(fn);
  }

  emit(type, payload) {
    const set = this.#map.get(type);
    if (!set) return;
    for (const fn of set) fn(payload);
  }
}
