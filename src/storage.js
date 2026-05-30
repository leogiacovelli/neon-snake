import { STORAGE_KEY } from './config.js';

// Thin, defensive wrapper over localStorage. Private/incognito modes and
// storage-disabled browsers throw on access, so every call is guarded — the
// game must never crash just because it can't persist a high score.

const DEFAULTS = {
  best: 0,
  bestLength: 3,
  games: 0,
  soundOn: true,
  mode: 'classic',
  speed: 'normal',
};

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULTS };
  }
}

function write(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* storage unavailable — silently ignore */
  }
}

export const store = {
  get all() {
    return read();
  },
  get(key) {
    return read()[key];
  },
  set(patch) {
    const next = { ...read(), ...patch };
    write(next);
    return next;
  },
};
