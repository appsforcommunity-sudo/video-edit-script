"""Command-line interface: `python -m vedit <command> ...` or `vedit <command> ...`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vedit import edits
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
    s.add_argument("--font-size", type=int, default=24)

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

    s = sub.add_parser("batch", help="run resize or compress on every video in a folder")
    s.add_argument("action", choices=["resize", "compress"])
    s.add_argument("folder"); s.add_argument("-o", "--outdir", default="output")
    s.add_argument("--preset", choices=PRESETS, default="vertical")
    s.add_argument("--mode", choices=["blur", "pad", "crop"], default="blur")
    s.add_argument("--crf", type=int, default=28)
    return p


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
            edits.subtitles(args.input, args.srt, args.output, args.font_size, dry_run=d)
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
    except FFmpegError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
