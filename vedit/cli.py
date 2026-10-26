"""Command-line interface: `python -m vedit <command> ...` or `vedit <command> ...`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vedit import captions, edits
from vedit.ffmpeg import FFmpegError, duration, probe

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
PRESETS = {"vertical": (1080, 1920), "square": (1080, 1080), "landscape": (1920, 1080)}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vedit", description="Automate common video edits with FFmpeg.")
    p.add_argument("--dry-run", action="store_true", help="print ffmpeg commands without running")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="show duration, resolution, codecs")
    s.add_argument("input")

    s = sub.add_parser("trim", help="cut a clip")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--start", default="0"); s.add_argument("--end")
    s.add_argument("--fast", action="store_true", help="stream copy (instant, cuts on keyframes)")

    s = sub.add_parser("concat", help="join clips in order")
    s.add_argument("inputs", nargs="+"); s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("resize", help="reformat for vertical/square/landscape")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--preset", choices=PRESETS, default="vertical")
    s.add_argument("--size", help="custom WxH, e.g. 1280x720 (overrides preset)")
    s.add_argument("--mode", choices=["blur", "pad", "crop"], default="blur")

    s = sub.add_parser("compress", help="shrink file size")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--crf", type=int, default=28)
    s.add_argument("--max-height", type=int, help="e.g. 720 to downscale")

    s = sub.add_parser("audio", help="extract audio")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("music", help="add background music")
    s.add_argument("input"); s.add_argument("music"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--volume", type=float, default=0.3)
    s.add_argument("--replace", action="store_true", help="drop original audio")

    s = sub.add_parser("subs", help="burn in .srt subtitles")
    s.add_argument("input"); s.add_argument("srt"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--font-size", type=int, default=0, help="0 = auto")
    _style_args(s, size=False)

    s = sub.add_parser("watermark", help="overlay a logo")
    s.add_argument("input"); s.add_argument("logo"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--position", choices=edits.POSITIONS, default="bottom-right")
    s.add_argument("--scale", type=float, default=0.15)
    s.add_argument("--opacity", type=float, default=0.8)

    s = sub.add_parser("speed", help="change playback speed")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--factor", type=float, required=True, help="2 = twice as fast, 0.5 = half")

    s = sub.add_parser("thumb", help="grab a frame as an image")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--at", default="1", help="timestamp (seconds or HH:MM:SS)")

    s = sub.add_parser("cut", help="keep several ranges and join them, or remove ranges")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--keep", nargs="+", metavar="START-END", help="e.g. 0-5 12-20")
    s.add_argument("--remove", nargs="+", metavar="START-END", help="e.g. 3-4.5 10-12")

    s = sub.add_parser("volume", help="louder/quieter, or normalize loudness")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--gain", type=float, default=1.0, help="1.5 = 50%% louder")
    s.add_argument("--normalize", action="store_true", help="even out loudness (-16 LUFS)")

    s = sub.add_parser("transcribe", help="speech -> .srt (needs faster-whisper)")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--lang", help="e.g. en, ms, zh (default: auto-detect)")
    s.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3")
    s.add_argument("--max-words", type=int, default=0)

    s = sub.add_parser("script2srt", help="turn a script (one caption per line) into .srt")
    s.add_argument("script"); s.add_argument("video"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--start", default="0", help="when the first line starts")

    s = sub.add_parser("captions", help="auto-caption a video (speech, --script, or --srt) and burn in")
    s.add_argument("input"); s.add_argument("-o", "--output", required=True)
    s.add_argument("--script", help="text file, one caption per line (timed across the video)")
    s.add_argument("--srt", help="use an existing .srt instead of transcribing")
    s.add_argument("--srt-out", help="also save the captions as .srt")
    s.add_argument("--lang"); s.add_argument("--model", default="small")
    _style_args(s)

    s = sub.add_parser("batch", help="run resize or compress on every video in a folder")
    s.add_argument("action", choices=["resize", "compress"])
    s.add_argument("folder"); s.add_argument("-o", "--outdir", default="output")
    s.add_argument("--preset", choices=PRESETS, default="vertical")
    s.add_argument("--mode", choices=["blur", "pad", "crop"], default="blur")
    s.add_argument("--crf", type=int, default=28)
    return p


def _style_args(s, size=True):
    if size:
        s.add_argument("--font-size", type=int, default=0, help="0 = auto (scales with video height)")
    s.add_argument("--font", default="Arial")
    s.add_argument("--color", default="#FFFFFF", help="text colour, e.g. #FFFF00")
    s.add_argument("--outline-color", default="#000000")
    s.add_argument("--highlight", help="colour of the spoken word, e.g. #FFD400 (speech/script only)")
    s.add_argument("--position", choices=["bottom", "middle", "top"], default="bottom")
    s.add_argument("--max-words", type=int, default=0, help="show N words at a time (0 = whole line)")
    s.add_argument("--upper", action="store_true", help="UPPERCASE text")
    s.add_argument("--no-bold", action="store_true")
    s.add_argument("--margin", type=int, default=0, help="distance from edge in px (0 = auto)")


def _style(args):
    return captions.Style(font=args.font, size=args.font_size, color=args.color,
                          outline_color=args.outline_color, highlight=args.highlight,
                          position=args.position, bold=not args.no_bold, upper=args.upper,
                          margin_v=args.margin, max_words=args.max_words)


def _ranges(items):
    out = []
    for item in items:
        a, _, b = item.partition("-")
        if not b:
            raise ValueError(f"range must look like START-END, got {item!r}")
        out.append((a, b))
    return out


def _size(args):
    if getattr(args, "size", None):
        w, h = args.size.lower().split("x")
        return int(w), int(h)
    return PRESETS[args.preset]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    d = args.dry_run
    try:
        if args.cmd == "info":
            info = probe(args.input)
            print(f"duration: {duration(args.input):.2f}s")
            for st in info["streams"]:
                if st["codec_type"] == "video":
                    print(f"video: {st['codec_name']} {st['width']}x{st['height']} @ {st.get('r_frame_rate')}")
                elif st["codec_type"] == "audio":
                    print(f"audio: {st['codec_name']} {st.get('sample_rate')}Hz {st.get('channels')}ch")
            return 0
        if args.cmd == "trim":
            edits.trim(args.input, args.output, args.start, args.end, reencode=not args.fast, dry_run=d)
        elif args.cmd == "concat":
            edits.concat(args.inputs, args.output, dry_run=d)
        elif args.cmd == "resize":
            edits.resize(args.input, args.output, *_size(args), mode=args.mode, dry_run=d)
        elif args.cmd == "compress":
            edits.compress(args.input, args.output, args.crf, args.max_height, dry_run=d)
        elif args.cmd == "audio":
            edits.extract_audio(args.input, args.output, dry_run=d)
        elif args.cmd == "music":
            edits.add_music(args.input, args.music, args.output, args.volume, args.replace, dry_run=d)
        elif args.cmd == "subs":
            edits.burn_captions(args.input, captions.parse_srt(args.srt), args.output,
                                _style(args), dry_run=d)
        elif args.cmd == "cut":
            edits.cut_segments(args.input, args.output,
                               keep=_ranges(args.keep) if args.keep else None,
                               remove=_ranges(args.remove) if args.remove else None, dry_run=d)
        elif args.cmd == "volume":
            edits.volume(args.input, args.output, args.gain, args.normalize, dry_run=d)
        elif args.cmd == "transcribe":
            cues = captions.regroup(captions.transcribe(args.input, args.lang, args.model), args.max_words)
            captions.write_srt(cues, args.output)
        elif args.cmd == "script2srt":
            start = captions.parse_time(args.start)
            cues = captions.script_to_cues(Path(args.script).read_text(encoding="utf-8"),
                                           duration(args.video) - start, start)
            captions.write_srt(cues, args.output)
        elif args.cmd == "captions":
            if args.srt:
                cues = captions.parse_srt(args.srt)
            elif args.script:
                cues = captions.script_to_cues(Path(args.script).read_text(encoding="utf-8"),
                                               duration(args.input))
            else:
                cues = captions.transcribe(args.input, args.lang, args.model)
            if args.srt_out:
                captions.write_srt(captions.regroup(cues, args.max_words), args.srt_out)
            edits.burn_captions(args.input, cues, args.output, _style(args), dry_run=d)
        elif args.cmd == "watermark":
            edits.watermark(args.input, args.logo, args.output, args.position, args.scale,
                            args.opacity, dry_run=d)
        elif args.cmd == "speed":
            edits.speed(args.input, args.output, args.factor, dry_run=d)
        elif args.cmd == "thumb":
            edits.thumbnail(args.input, args.output, args.at, dry_run=d)
        elif args.cmd == "batch":
            out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
            files = sorted(f for f in Path(args.folder).iterdir() if f.suffix.lower() in VIDEO_EXTS)
            if not files:
                print(f"no videos found in {args.folder}"); return 1
            for i, f in enumerate(files, 1):
                dst = out / f"{f.stem}_{args.action}.mp4"
                print(f"[{i}/{len(files)}] {f.name} -> {dst}")
                if args.action == "resize":
                    edits.resize(f, dst, *PRESETS[args.preset], mode=args.mode, dry_run=d)
                else:
                    edits.compress(f, dst, args.crf, dry_run=d)
        if not d and args.cmd != "batch":
            print(f"done -> {args.output}")
        return 0
    except (FFmpegError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
