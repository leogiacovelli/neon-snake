import { MODES } from './config.js';
import { store } from './storage.js';

// DOM/UI layer. Owns the overlay screens, HUD, power-up pips and the menu
// controls. It reads persisted preferences from `store` and reports user intent
// back through the handlers passed in.

const $ = (sel) => document.querySelector(sel);

export class UI {
  constructor(handlers = {}) {
    this.h = handlers;

    this.overlay = $('#overlay');
    this.panels = [...document.querySelectorAll('.panel')];
    this.hud = $('#hud');
    this.pauseBtn = $('#pause-btn');
    this.powerups = $('#powerups');

    this.elScore = $('#hud-score');
    this.elBest = $('#hud-best');
    this.elLevel = $('#hud-level');
    this.elComboWrap = $('#hud-combo-wrap');
    this.elCombo = $('#hud-combo');

    this.mode = store.get('mode');
    this.speed = store.get('speed');
    this.soundOn = store.get('soundOn');

    this._pips = new Map();

    this.bind();
    this.syncMenu();
    this.elBest.textContent = store.get('best');
  }

  bind() {
    $('#play-btn').addEventListener('click', () => this.h.onPlay?.(this.mode, this.speed));
    $('#resume-btn').addEventListener('click', () => this.h.onResume?.());
    $('#quit-btn').addEventListener('click', () => this.h.onMenu?.());
    $('#retry-btn').addEventListener('click', () => this.h.onPlay?.(this.mode, this.speed));
    $('#menu-btn').addEventListener('click', () => this.h.onMenu?.());
    this.pauseBtn.addEventListener('click', () => this.h.onPause?.());

    // Segmented controls
    this.bindSeg('#mode-select', 'mode', (v) => {
      this.mode = v;
      store.set({ mode: v });
      $('#mode-hint').textContent = MODES[v].hint;
    });
    this.bindSeg('#speed-select', 'speed', (v) => {
      this.speed = v;
      store.set({ speed: v });
    });

    // Sound toggle
    $('#sound-toggle').addEventListener('click', () => {
      this.soundOn = !this.soundOn;
      store.set({ soundOn: this.soundOn });
      this.syncSound();
      this.h.onToggleSound?.(this.soundOn);
    });
  }

  bindSeg(sel, attr, cb) {
    const root = $(sel);
    root.addEventListener('click', (e) => {
      const btn = e.target.closest('.seg-btn');
      if (!btn) return;
      [...root.children].forEach((b) => b.classList.toggle('is-active', b === btn));
      cb(btn.dataset[attr]);
      this.h.onUi?.();
    });
  }

  syncMenu() {
    const setActive = (sel, attr, val) => {
      document.querySelectorAll(`${sel} .seg-btn`).forEach((b) => {
        b.classList.toggle('is-active', b.dataset[attr] === val);
      });
    };
    setActive('#mode-select', 'mode', this.mode);
    setActive('#speed-select', 'speed', this.speed);
    $('#mode-hint').textContent = MODES[this.mode]?.hint ?? '';
    this.syncSound();
  }

  syncSound() {
    const btn = $('#sound-toggle');
    btn.textContent = this.soundOn ? '🔊 Sound: On' : '🔇 Sound: Off';
    btn.setAttribute('aria-pressed', String(this.soundOn));
  }

  // ---- screen switching ------------------------------------------------------

  show(screen) {
    if (screen === 'playing') {
      this.overlay.classList.add('is-hidden');
    } else {
      this.overlay.classList.remove('is-hidden');
      this.panels.forEach((p) => (p.hidden = p.dataset.screen !== screen));
    }
    this.hud.hidden = screen === 'menu';
    this.pauseBtn.hidden = screen !== 'playing';
  }

  // ---- HUD -------------------------------------------------------------------

  setScore(n) {
    this.elScore.textContent = n;
  }
  setLevel(n) {
    this.elLevel.textContent = n;
  }
  setBest(n) {
    this.elBest.textContent = n;
  }
  setCombo(combo) {
    if (combo >= 2) {
      this.elComboWrap.hidden = false;
      this.elCombo.textContent = 'x' + combo;
      // retrigger pop
      this.elCombo.style.animation = 'none';
      void this.elCombo.offsetWidth;
      this.elCombo.style.animation = '';
    } else {
      this.elComboWrap.hidden = true;
    }
  }

  // ---- power-up pips ---------------------------------------------------------

  updatePips(effects) {
    const seen = new Set(effects.map((e) => e.type));
    // Remove stale
    for (const [type, rec] of this._pips) {
      if (!seen.has(type)) {
        rec.el.remove();
        this._pips.delete(type);
      }
    }
    // Add/update
    for (const e of effects) {
      let rec = this._pips.get(e.type);
      if (!rec) {
        const el = document.createElement('div');
        el.className = 'pip';
        el.style.setProperty('--c', e.color);
        el.innerHTML = `<span class="pip-icon">${e.icon}</span><div class="pip-bar"><div class="pip-fill"></div></div>`;
        this.powerups.appendChild(el);
        rec = { el, fill: el.querySelector('.pip-fill') };
        this._pips.set(e.type, rec);
      }
      rec.fill.style.width = Math.round(e.remaining * 100) + '%';
    }
  }

  // ---- game over -------------------------------------------------------------

  showGameOver({ score, length, best, isNewBest }) {
    $('#final-score').textContent = score;
    $('#final-best').textContent = best;
    $('#final-length').textContent = length;
    $('#new-best').hidden = !isNewBest;
  }
}
