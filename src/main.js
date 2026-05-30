import './style.css';
import { Game, State } from './game.js';
import { Renderer } from './renderer.js';
import { Input } from './input.js';
import { Audio } from './audio.js';
import { UI } from './ui.js';
import { store } from './storage.js';

const canvas = document.getElementById('game');
const stage = document.querySelector('.stage');

const game = new Game();
const audio = new Audio(store.get('soundOn'));

// --- intent handlers shared by UI + keyboard --------------------------------

function play(mode, speed) {
  audio.ensure();
  game.start(mode, speed);
  ui.show('playing');
  ui.setScore(0);
  ui.setLevel(1);
  ui.setCombo(0);
  ui.updatePips([]);
  if (store.get('soundOn')) audio.startMusic();
  maybeTouchHint();
}

function toMenu() {
  game.toMenu();
  ui.show('menu');
  audio.stopMusic();
}

function togglePause() {
  if (game.state === State.PLAYING) {
    game.pause();
    ui.show('paused');
  } else if (game.state === State.PAUSED) {
    game.resume();
    ui.show('playing');
  }
}

function primary() {
  // Enter key context-sensitive action.
  if (game.state === State.MENU || game.state === State.GAMEOVER) play(ui.mode, ui.speed);
  else if (game.state === State.PAUSED) togglePause();
}

const ui = new UI({
  onPlay: play,
  onResume: togglePause,
  onMenu: toMenu,
  onPause: togglePause,
  onToggleSound: (on) => {
    audio.ensure();
    audio.setEnabled(on);
    if (on && game.state !== State.MENU && game.state !== State.GAMEOVER) audio.startMusic();
    if (!on) audio.stopMusic();
  },
  onUi: () => {
    audio.ensure();
    audio.uiClick();
  },
});

const renderer = new Renderer(canvas, game);

new Input(stage, game, {
  onPause: togglePause,
  onPrimary: primary,
  onGesture: () => audio.ensure(),
});

// --- wire game events to audio + UI -----------------------------------------

game.events.on('score', ({ score }) => ui.setScore(score));
game.events.on('eat', ({ combo }) => audio.eat(combo));
game.events.on('combo', ({ combo }) => ui.setCombo(combo));
game.events.on('levelup', ({ level }) => {
  ui.setLevel(level);
  audio.levelup();
});
game.events.on('powerup', () => audio.powerup());
game.events.on('special', () => audio.special());
game.events.on('gameover', ({ score, length }) => {
  const prevBest = store.get('best');
  const isNewBest = score > prevBest;
  const best = Math.max(prevBest, score);
  store.set({
    best,
    games: store.get('games') + 1,
    bestLength: Math.max(store.get('bestLength'), length),
  });
  ui.setBest(best);
  ui.showGameOver({ score, length, best, isNewBest });
  ui.show('gameover');
  audio.death();
  audio.stopMusic();
});

// --- main loop ---------------------------------------------------------------

let last = performance.now();
function frame(now) {
  const dt = (now - last) / 1000;
  last = now;
  game.update(dt);
  ui.updatePips(game.getEffects());
  renderer.render(Math.min(dt, 0.05));
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// --- environment glue --------------------------------------------------------

let resizeRaf = 0;
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(() => renderer.resize());
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden && game.state === State.PLAYING) togglePause();
});

function maybeTouchHint() {
  if (!('ontouchstart' in window)) return;
  const hint = document.getElementById('touch-hint');
  if (!hint || hint.dataset.shown) return;
  hint.dataset.shown = '1';
  hint.hidden = false;
  setTimeout(() => (hint.hidden = true), 2600);
}

// Boot into the menu.
ui.show('menu');
