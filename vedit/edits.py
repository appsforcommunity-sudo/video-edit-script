"""Common video edits. Each function builds and runs one ffmpeg command."""
from __future__ import annotations

import tempfile
from pathlib import Path

from vedit.ffmpeg import has_audio, run

H264 = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"]
AAC = ["-c:a", "aac", "-b:a", "192k"]


def trim(src, dst, start, end=None, reencode=True, dry_run=False):
    """Cut a clip. Times accept seconds (12.5) or HH:MM:SS(.ms)."""
    args = ["-i", str(src), "-ss", str(start)]
    if end:
        args += ["-to", str(end)]
    args += [*H264, "-crf", "18", *AAC] if reencode else ["-c", "copy"]
    return run([*args, str(dst)], dry_run)


def concat(srcs, dst, dry_run=False):
    """Join clips end to end (fast, no re-encode; clips should share codec/size)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for s in srcs:
            f.write(f"file '{Path(s).resolve().as_posix()}'\n")
        listfile = f.name
    return run(["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", str(dst)], dry_run)


def resize(src, dst, width, height, mode="blur", dry_run=False):
    """Fit video into WxH. mode: 'blur' (blurred background), 'pad' (black bars), 'crop' (fill)."""
    w, h = width, height
    if mode == "crop":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
        args = ["-i", str(src), "-vf", vf]
    elif mode == "pad":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
        args = ["-i", str(src), "-vf", vf]
    elif mode == "blur":
        fc = (f"[0:v]split[a][b];"
              f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:2[bg];"
              f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
        args = ["-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
    else:
        raise ValueError("mode must be blur, pad, or crop")
    return run([*args, *H264, "-crf", "20", *AAC, str(dst)], dry_run)


def compress(src, dst, crf=28, max_height=None, dry_run=False):
    """Shrink file size. Higher crf = smaller file (23 good, 28 small, 32 tiny)."""
    args = ["-i", str(src)]
    if max_height:
        args += ["-vf", f"scale=-2:'min({max_height},ih)'"]
    return run([*args, *H264, "-crf", str(crf), "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(dst)], dry_run)


def extract_audio(src, dst, dry_run=False):
    """Pull the audio track out. Output format follows dst extension (.mp3, .wav, .m4a)."""
    return run(["-i", str(src), "-vn", str(dst)], dry_run)


def add_music(src, music, dst, music_volume=0.3, replace=False, dry_run=False):
    """Add background music, looped/cut to video length. Mixes with original audio unless replace."""
    args = ["-i", str(src), "-stream_loop", "-1", "-i", str(music)]
    if replace or (not dry_run and not has_audio(src)):
        fc = f"[1:a]volume={music_volume}[a]"
    else:
        fc = (f"[1:a]volume={music_volume}[m];"
              f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]")
    return run([*args, "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", *AAC, "-shortest", str(dst)], dry_run)


def subtitles(src, srt, dst, font_size=24, dry_run=False):
    """Burn an .srt file into the video."""
    path = Path(srt).resolve().as_posix().replace(":", r"\:")
    vf = f"subtitles='{path}':force_style='Fontsize={font_size},Outline=2'"
    return run(["-i", str(src), "-vf", vf, *H264, "-crf", "20", "-c:a", "copy", str(dst)], dry_run)


POSITIONS = {
    "top-left": "20:20",
    "top-right": "W-w-20:20",
    "bottom-left": "20:H-h-20",
    "bottom-right": "W-w-20:H-h-20",
    "center": "(W-w)/2:(H-h)/2",
}


def watermark(src, logo, dst, position="bottom-right", scale=0.15, opacity=0.8, dry_run=False):
    """Overlay a logo image. scale = logo width as a fraction of video width."""
    fc = (f"[1:v][0:v]scale2ref=w=iw*{scale}:h=ow/mdar[logo][base];"
          f"[logo]format=rgba,colorchannelmixer=aa={opacity}[l];"
          f"[base][l]overlay={POSITIONS[position]}[v]")
    return run(["-i", str(src), "-i", str(logo), "-filter_complex", fc,
                "-map", "[v]", "-map", "0:a?", *H264, "-crf", "20", "-c:a", "copy", str(dst)],
               dry_run)


def speed(src, dst, factor, dry_run=False):
    """Speed up (>1) or slow down (<1) video and audio."""
    atempo, f = [], factor
    while f > 2.0:
        atempo.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        atempo.append("atempo=0.5")
        f /= 0.5
    atempo.append(f"atempo={f}")
    fc = f"[0:v]setpts=PTS/{factor}[v]"
    maps = ["-map", "[v]"]
    if dry_run or has_audio(src):
        fc += f";[0:a]{','.join(atempo)}[a]"
        maps += ["-map", "[a]"]
    return run(["-i", str(src), "-filter_complex", fc, *maps, *H264, "-crf", "20", *AAC, str(dst)],
               dry_run)


def thumbnail(src, dst, at="1", dry_run=False):
    """Save a single frame as an image."""
    return run(["-ss", str(at), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)], dry_run)
