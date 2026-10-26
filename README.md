# video-edit-scripts

Small Python scripts that wrap **FFmpeg** to automate the edits you do over and over: trimming, joining clips, reformatting for Reels/TikTok/Shorts, compressing, adding music, burning subtitles, watermarking, and batch processing a whole folder.

No Python dependencies — just Python 3.9+ and FFmpeg.

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
vedit subs input/clip.mp4 input/captions.srt --font-size 28 -o output/captioned.mp4
vedit watermark input/clip.mp4 input/logo.png --position top-right -o output/branded.mp4
vedit speed input/clip.mp4 --factor 1.5 -o output/fast.mp4
vedit thumb input/clip.mp4 --at 00:00:03 -o output/thumb.jpg

# Batch: every video in input/ → output/
vedit batch resize input --preset vertical
vedit batch compress input --crf 26
```

Add `--dry-run` before any command to print the FFmpeg command without running it — handy for learning FFmpeg or tweaking it by hand.

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
