# 🐍 Neon Snake

### ▶️ [**Play it live**](https://leogiacovelli.github.io/neon-snake/) &nbsp;·&nbsp; no install, runs in your browser

A modern, juicy take on the classic Snake — built from scratch with **vanilla JavaScript + Canvas**, bundled with **Vite**. No game engine, no asset files, no runtime dependencies. The whole thing ships as **~9 KB of gzipped JS**.

[![Play now](https://img.shields.io/badge/▶_Play_now-leogiacovelli.github.io%2Fneon--snake-56ffc2?style=for-the-badge)](https://leogiacovelli.github.io/neon-snake/)

![mode: classic · wrap · maze](https://img.shields.io/badge/modes-classic%20·%20wrap%20·%20maze-56ffc2)
![deps: 0 runtime](https://img.shields.io/badge/runtime%20deps-0-38d9ff)

## Features

- **Smooth, interpolated movement** — the logic runs on a discrete grid, but the snake glides between cells at 60 fps.
- **Three modes** — *Classic* (deadly walls), *Wrap* (edges teleport), *Maze* (deadly walls + obstacles that grow each level).
- **Three speeds** — Chill, Normal, Insane. Speed also ramps up as you level.
- **5 power-ups** — ⭐ 2× Score, ⚡ Rush, 🌀 Slow-mo, 👻 Ghost (phase through yourself & walls), ✂️ Trim.
- **Combo system** — chain quick pickups to multiply your score (up to ×8).
- **Juice** — particle bursts, screen shake, neon glow, animated HUD.
- **Synthesized audio** — all SFX and a generative background track are built live with the Web Audio API. Zero audio files.
- **Persistent best score & stats** — saved to `localStorage`.
- **Plays everywhere** — keyboard (Arrows / WASD), touch swipe on mobile, responsive square board.

## Controls

| Action | Keys |
| --- | --- |
| Move | Arrow keys / `W` `A` `S` `D` |
| Steer (mobile) | Swipe in any direction |
| Pause / resume | `Space` · `P` · `Esc` · on-screen `II` |
| Confirm (menu / retry) | `Enter` |

## Getting started

```bash
npm install      # install the single dev dependency (Vite)
npm run dev      # local dev server with hot reload, opens the browser
npm test         # headless smoke tests for the game core
npm run build    # production bundle -> dist/
npm run preview  # serve the production build locally on :4173
```

Requires Node 18+.

## Deploy

The production build in `dist/` is a fully static site — host it anywhere.
`vite.config.js` sets `base: './'`, so it works from any sub-path (no config needed).

```bash
npm run build
```

- **Netlify** — drag `dist/` onto the dashboard, or set build command `npm run build` and publish dir `dist`.
- **Vercel** — framework preset *Vite*, output dir `dist`.
- **GitHub Pages** — push `dist/` to a `gh-pages` branch (e.g. with `npx gh-pages -d dist`).
- **Cloudflare Pages / S3 / any CDN** — upload the contents of `dist/`.
- **itch.io** — zip the contents of `dist/` and upload as an HTML5 game.

## Architecture

The code is deliberately split so the game logic stays **DOM-free and testable** —
everything in `src/game.js` and its dependencies runs headless under Node (that's
what `npm test` exercises).

```
src/
  config.js     all tunable numbers: grid, speeds, scoring, power-ups, colors
  events.js     tiny synchronous event emitter (core → presentation)
  storage.js    defensive localStorage wrapper (preferences + high score)
  snake.js      snake entity + previous-tick snapshot for interpolation
  food.js       free-cell finder + weighted power-up picker
  level.js      maze obstacle generator (scales with level, never traps)
  particles.js  grid-space particle system
  game.js       state machine, fixed-step tick, collisions, scoring   ← no DOM
  renderer.js   Canvas 2D: interpolation, gradients, glow, particles, shake
  audio.js      Web Audio SFX + generative music
  input.js      keyboard + touch → game intent
  ui.js         overlay screens, HUD, power-up pips, menu controls
  main.js       bootstrap: wires everything + the requestAnimationFrame loop
test/
  smoke.mjs     headless assertions on the core (growth, wrap, death, maze…)
```

### Key design decisions

- **Fixed-step logic, interpolated render.** The game advances on a fixed time
  accumulator (`Game.update`), independent of frame rate, while the renderer lerps
  between the snake's previous and current cells. This decouples *feel* (smooth)
  from *fairness* (deterministic), and the `dt` clamp prevents a backgrounded tab
  from fast-forwarding the simulation.
- **Free-cell collection instead of rejection sampling** for spawning food. On a
  nearly-full late-game board, retrying random cells can stall; collecting the
  free set once is O(cells) and can't loop forever.
- **Event-driven presentation.** The core only emits events; audio and UI subscribe
  in `main.js`. Swapping the renderer or muting audio touches nothing in the logic.

## License

MIT — do whatever you like.
