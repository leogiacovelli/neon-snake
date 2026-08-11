# audioviz — audio-reactive video renderer

Point it at an audio file, get a finished mp4 back. No GUI, no timeline, no
manual editing: the audio is analysed with librosa, frames are painted with
numpy, and ffmpeg muxes the result against the original track.

```bash
python3 render.py track.mp3
# -> track-tunnel.mp4
```

## Install

```bash
pip install -r requirements.txt
```

You also need **ffmpeg** on `PATH`. Any of these work:

```bash
apt install ffmpeg          # or: brew install ffmpeg
npm i -D ffmpeg-static      # picked up automatically from this repo
python3 render.py … --ffmpeg /path/to/ffmpeg
```

No audio file to hand? Synthesise one:

```bash
python3 make_demo_audio.py --out demo.mp3
python3 render.py demo.mp3 --style grid
```

## Usage

```bash
python3 render.py TRACK [options]

  -s, --style      grid | particles | glitch | fluid | tunnel | random | mix
  -p, --palette    neon | vapor | acid | ember | ice | sunset | mono | toxic
      --size       square (1080²) | story | reel | wide | hd | WxH
      --fps        frame rate (default 30)
      --start      skip N seconds of audio
  -d, --duration   render only N seconds
      --seed       same seed + same audio = byte-identical video
  -j, --workers    parallel processes (0 = auto)
      --crf        x264 quality; 21 default, 23 roughly halves the file
      --stills     write PNGs at "3,12.5" instead of a video
      --analyze-only   print the analysis summary and stop
      --list       show styles, palettes and sizes
```

```bash
# a vertical clip of the drop, one style throughout
python3 render.py track.mp3 --style glitch --size story --start 64 -d 30

# let it pick, but pin the result so you can reproduce it
python3 render.py track.mp3 --style random --seed 4242

# change look at every structural section of the track
python3 render.py track.mp3 --style mix

# preview three moments as PNGs before committing to a full render
python3 render.py track.mp3 --style fluid --stills 5,30,60
```

## Styles

| name | look | reacts to |
|---|---|---|
| `grid` | retrowave sun over an infinite perspective grid | bass sizes the sun, beats kick the grid forward, mids brighten the lines |
| `particles` | 22k-particle curl-noise swarm with motion trails | bass pulls the swarm in, air pushes it out, beats fire radial bursts |
| `glitch` | spectrum bars torn by slice displacement and RGB split | onsets drive the tearing, transients punch datamosh blocks |
| `fluid` | domain-warped plasma, marbled and liquid | low-mids drive the warp, brightness shifts the hue |
| `tunnel` | infinite ring corridor, spectrum wrapped around the angle | each angular slice tracks its own frequency band |

`random` picks one. `mix` gives each structural section of the track its own
style and palette, crossfading half a second at the boundaries.

## How it works

```
audio ──▶ ffmpeg decode ──▶ librosa analysis ──▶ Timeline (per video frame)
                                                     │
                                    style.render(Frame) ──▶ post ──▶ ffmpeg ──▶ mp4
```

**`avz/analysis.py`** decodes the track through ffmpeg (so any format works
without extra Python codecs) and extracts everything once, up front, resampled
onto the video's frame grid: loudness, five frequency bands, onset strength,
beat times and phase, spectral centroid, a 48-band mel spectrum, and structural
section boundaries. Each value is percentile-normalised and run through an
attack/release follower, so a style reads plain 0..1 numbers that already move
the way you'd want them to on screen.

**`avz/styles/`** paints frames. A style gets a `Frame` of those numbers and
returns a float image; it never touches librosa. Most render at half resolution
— their content is smooth enough that nothing is lost, and it is four times
faster.

**`avz/postfx.py`** does the grading that makes procedural output look
photographed rather than plotted: threshold bloom, chromatic aberration,
vignette, exponential highlight roll-off, grain.

**`avz/pipeline.py`** decides which style paints which frames, renders them
(in parallel where the style allows it) and streams raw RGB into ffmpeg.

### Notes

- **Determinism.** A seed plus an audio file fully determines the output.
  Stateless styles are rendered across worker processes; `particles` carries a
  simulation between frames, so it runs single-threaded.
- **Speed.** Roughly 8 frames/sec at 1080×1080 on 4 cores — about 2× realtime
  cost, so a 3-minute track takes ~10 minutes. `--size hd` or `--fps 24` cuts
  that considerably.
- **File size.** Film grain is expensive to encode. `--crf 23` roughly halves
  the output with little visible difference.

## Tests

```bash
python3 -m pytest tests -q
```

Tests needing ffmpeg skip themselves when it isn't installed.
