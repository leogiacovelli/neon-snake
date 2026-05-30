// All sound is synthesized at runtime with the Web Audio API — zero asset files,
// instant load, tiny bundle. Includes SFX plus an optional generative background
// loop (a wandering pentatonic arpeggio with a soft bass pulse).

const PENTA = [0, 3, 5, 7, 10]; // minor pentatonic scale degrees
const noteHz = (semi) => 220 * Math.pow(2, semi / 12);

export class Audio {
  constructor(enabled = true) {
    this.enabled = enabled;
    this.ctx = null;
    this.master = null;
    this.musicGain = null;
    this.musicOn = false;
    this._timer = null;
    this._step = 0;
    this._nextNoteTime = 0;
  }

  // Must be called from a user gesture so the AudioContext is allowed to start.
  ensure() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = this.enabled ? 0.9 : 0;
    this.master.connect(this.ctx.destination);

    this.musicGain = this.ctx.createGain();
    this.musicGain.gain.value = 0.0;
    this.musicGain.connect(this.master);
  }

  setEnabled(on) {
    this.enabled = on;
    if (this.master) {
      this.master.gain.setTargetAtTime(on ? 0.9 : 0, this.ctx.currentTime, 0.02);
    }
  }

  // ---- low-level voices ------------------------------------------------------

  tone(freq, { dur = 0.12, type = 'sine', gain = 0.25, glide = null, when = 0 } = {}) {
    if (!this.ctx || !this.enabled) return;
    const t = this.ctx.currentTime + when;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (glide) osc.frequency.exponentialRampToValueAtTime(glide, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(this.master);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  }

  noise({ dur = 0.3, gain = 0.4, type = 'lowpass', freq = 900 } = {}) {
    if (!this.ctx || !this.enabled) return;
    const t = this.ctx.currentTime;
    const len = Math.floor(this.ctx.sampleRate * dur);
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const filt = this.ctx.createBiquadFilter();
    filt.type = type;
    filt.frequency.value = freq;
    const g = this.ctx.createGain();
    g.gain.value = gain;
    src.connect(filt).connect(g).connect(this.master);
    src.start(t);
  }

  // ---- SFX -------------------------------------------------------------------

  eat(combo = 1) {
    // Pitch climbs with the combo for a rewarding ladder.
    const base = 520 + Math.min(combo, 8) * 70;
    this.tone(base, { dur: 0.1, type: 'triangle', gain: 0.28, glide: base * 1.5 });
  }

  powerup() {
    [0, 4, 7, 12].forEach((s, i) =>
      this.tone(noteHz(12 + s), { dur: 0.16, type: 'square', gain: 0.16, when: i * 0.05 })
    );
  }

  special() {
    this.tone(880, { dur: 0.08, type: 'sine', gain: 0.18, glide: 1320 });
  }

  levelup() {
    [0, 5, 7, 12, 16].forEach((s, i) =>
      this.tone(noteHz(s), { dur: 0.22, type: 'triangle', gain: 0.2, when: i * 0.06 })
    );
  }

  death() {
    this.tone(320, { dur: 0.5, type: 'sawtooth', gain: 0.3, glide: 60 });
    this.noise({ dur: 0.5, gain: 0.35, freq: 1200 });
  }

  uiClick() {
    this.tone(660, { dur: 0.05, type: 'square', gain: 0.12 });
  }

  // ---- generative music ------------------------------------------------------

  startMusic() {
    if (!this.ctx || this.musicOn) return;
    this.musicOn = true;
    this.musicGain.gain.setTargetAtTime(0.5, this.ctx.currentTime, 1.5);
    this._step = 0;
    this._nextNoteTime = this.ctx.currentTime + 0.1;
    const tick = () => {
      if (!this.musicOn) return;
      this._schedule();
      this._timer = setTimeout(tick, 25);
    };
    tick();
  }

  stopMusic() {
    this.musicOn = false;
    if (this._timer) clearTimeout(this._timer);
    if (this.musicGain) this.musicGain.gain.setTargetAtTime(0, this.ctx.currentTime, 0.4);
  }

  _schedule() {
    const spb = 0.26; // seconds per step (~ 230 BPM in 1/16 feel)
    while (this._nextNoteTime < this.ctx.currentTime + 0.12) {
      const t = this._nextNoteTime;
      const step = this._step;

      // Bass pulse every 4 steps
      if (step % 4 === 0) {
        this._voiceTo(noteHz(-12), t, 0.5, 'sine', 0.5);
      }
      // Wandering arpeggio
      if (step % 2 === 0) {
        const deg = PENTA[(Math.random() * PENTA.length) | 0];
        const oct = 12 * (1 + ((Math.random() * 2) | 0));
        this._voiceTo(noteHz(deg + oct), t, 0.32, 'triangle', 0.28);
      }
      this._nextNoteTime += spb;
      this._step = (step + 1) % 16;
    }
  }

  _voiceTo(freq, t, dur, type, gain) {
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(this.musicGain);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  }
}
