# video-edit-scripts

Small Python scripts that wrap **FFmpeg** to automate the edits you do over and over: trimming, joining clips, reformatting for Reels/TikTok/Shorts, compressing, adding music, burning subtitles, watermarking, and batch processing a whole folder.

No Python dependencies — just Python 3.9+ and FFmpeg. (Automatic speech captions optionally use `faster-whisper`: `pip install -e .[captions]`.)

## Setup

**On iPad / in the browser:** open the repo on GitHub → **Code → Codespaces → Create codespace**. FFmpeg and `vedit` install automatically (or run `./setup.sh`). Upload videos to `input/`, run commands in the terminal, then right-click files in `output/` → Download.

**On a computer:**


1. Install FFmpeg
   - macOS: `brew install ffmpeg`
   - Windows: `winget install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
2. Clone and (optionally) install the `vedit` command:
   ```bash
   git clone https://github.com/<you>/video-edit-scripts.git
   cd video-edit-scripts
   pip install -e .          # optional: gives you the `vedit` command
   ```
   Without installing, use `python -m vedit` instead of `vedit`.

## Usage

```bash
vedit info input/clip.mp4                                   # duration, resolution, codecs
vedit trim input/clip.mp4 --start 00:00:05 --end 00:00:15 -o output/cut.mp4
vedit trim input/clip.mp4 --start 5 --end 15 --fast -o output/cut.mp4   # instant, no re-encode
vedit concat input/a.mp4 input/b.mp4 input/c.mp4 -o output/joined.mp4
vedit resize input/clip.mp4 --preset vertical -o output/reel.mp4        # 1080x1920, blurred bg
vedit resize input/clip.mp4 --preset square --mode crop -o output/sq.mp4
vedit resize input/clip.mp4 --size 1280x720 --mode pad -o output/720.mp4
vedit compress input/clip.mp4 --crf 28 --max-height 720 -o output/small.mp4
vedit audio input/clip.mp4 -o output/voice.mp3
vedit music input/clip.mp4 input/song.mp3 --volume 0.25 -o output/with_music.mp4
vedit subs input/clip.mp4 input/captions.srt --color "#FFFF00" --position middle -o output/captioned.mp4
vedit cut input/clip.mp4 --keep 0-5 12-20 -o output/highlights.mp4     # keep + join ranges
vedit cut input/clip.mp4 --remove 3-4.5 10-12 -o output/clean.mp4      # drop ranges
vedit volume input/clip.mp4 --normalize -o output/loud.mp4              # or --gain 1.5
vedit transcribe input/clip.mp4 --lang ms -o output/clip.srt            # speech -> .srt
vedit script2srt input/script.txt input/clip.mp4 -o output/clip.srt     # your script -> .srt
vedit zoom input/clip.mp4 --at 1-3:punch:1.3 6-9:in:1.5 12-14:out:1.4 -o output/zoomed.mp4
vedit graphics input/clip.mp4 --image input/logo.png@0-10 --text "JOIN US@1-3" --text-box "#E50914" -o output/gfx.mp4
vedit bgm input/clip.mp4 --music input/song.mp3 --volume 0.2 --sfx builtin:whoosh@1 --sfx hit.wav@6:0.6 -o output/audio.mp4
vedit make examples/spec.json                                           # everything in one go
# one step: caption + style + burn in (speech, --script file, or --srt file)
vedit captions input/clip.mp4 -o output/final.mp4 --lang en --max-words 3 --upper \
      --highlight "#FFD400" --position middle
vedit captions input/clip.mp4 -o output/final.mp4 --script input/script.txt --srt-out output/final.srt
vedit watermark input/clip.mp4 input/logo.png --position top-right -o output/branded.mp4
vedit speed input/clip.mp4 --factor 1.5 -o output/fast.mp4
vedit thumb input/clip.mp4 --at 00:00:03 -o output/thumb.jpg

# Batch: every video in input/ → output/
vedit batch resize input --preset vertical
vedit batch compress input --crf 26
```

Add `--dry-run` before any command to print the FFmpeg command without running it — handy for learning FFmpeg or tweaking it by hand.

## Zoom, graphics, BGM and SFX

- **Zoom** (`--at START-END:TYPE:AMOUNT`, times in seconds): `punch` eases in, holds, eases out;
  `in` zooms gradually across the range then cuts back; `out` starts zoomed and pulls back.
  `--focus 0.5,0.3` aims the zoom at a point (x,y as fractions of the frame; default centre).
- **Graphics**: images (logo, sticker, lower-third PNG) and text with fade in/out. Text can have a
  coloured box (`--text-box`).
- **BGM**: looped, faded in/out, and automatically lowered while someone speaks (`--no-duck` to
  turn off). **SFX** are placed at exact seconds; use your own files or `builtin:whoosh`,
  `builtin:pop`, `builtin:ding`, `builtin:boom`.
- **`vedit make spec.json`** runs cuts, zooms, audio, graphics, then captions in that order (see
  `examples/spec.json`). Captions go last so they are never zoomed or covered.

## Caption options

Used by `captions` and `subs`: `--font`, `--font-size` (0 = auto), `--color`, `--outline-color`,
`--highlight` (colour of the word being spoken), `--position bottom|middle|top`, `--max-words N`
(a few words at a time, TikTok style), `--upper`, `--no-bold`, `--margin`. Colours are `#RRGGBB`.

`--script` takes a text file with one caption per line; time is shared across the video by line
length, so it is approximate. Transcribed captions use real word timings.

## Resize modes

| mode  | result |
|-------|--------|
| `blur` | whole video fits, empty space filled with a blurred copy (default) |
| `pad`  | whole video fits, black bars |
| `crop` | fills the frame, edges cut off |

## Using it from Python

```python
from vedit import edits

edits.trim("input/raw.mp4", "output/cut.mp4", start="00:01:00", end="00:01:30")
edits.resize("output/cut.mp4", "output/reel.mp4", 1080, 1920, mode="blur")
edits.add_music("output/reel.mp4", "input/song.mp3", "output/final.mp4", music_volume=0.2)
```

## Project layout

```
vedit/
  ffmpeg.py   # run/probe helpers
  edits.py    # one function per edit
  captions.py # cues, styling, speech/script -> captions
  graphics.py # timed text graphics
  project.py  # `vedit make` JSON spec runner
  cli.py      # `vedit` command
tests/        # generates tiny test clips and checks every edit
input/        # put source media here (ignored by git)
output/       # results go here (ignored by git)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Media files are ignored by `.gitignore` so your repo stays small.
