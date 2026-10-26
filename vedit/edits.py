"""Common video edits. Each function builds and runs one ffmpeg command."""
from __future__ import annotations

import tempfile
from pathlib import Path

from vedit import captions, graphics
from vedit.ffmpeg import duration, has_audio, run, video_size

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


def cut_segments(src, dst, keep=None, remove=None, dry_run=False):
    """Keep several (start, end) ranges and join them, or drop ranges and keep the rest.

    Give exactly one of keep / remove, each a list of (start, end) pairs (seconds or HH:MM:SS).
    """
    if bool(keep) == bool(remove):
        raise ValueError("give exactly one of keep or remove")
    if remove:
        total, t, keep = duration(src), 0.0, []
        for a, b in sorted((captions.parse_time(a), captions.parse_time(b)) for a, b in remove):
            if a > t:
                keep.append((t, a))
            t = max(t, b)
        if t < total:
            keep.append((t, total))
        if not keep:
            raise ValueError("nothing left after removing those ranges")
    segs = [(captions.parse_time(a), captions.parse_time(b)) for a, b in keep]
    audio = dry_run or has_audio(src)
    parts = []
    for i, (a, b) in enumerate(segs):
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        if audio:
            parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
    n = len(segs)
    inputs = "".join(f"[v{i}][a{i}]" if audio else f"[v{i}]" for i in range(n))
    parts.append(f"{inputs}concat=n={n}:v=1:a={1 if audio else 0}" + ("[v][a]" if audio else "[v]"))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if audio else [])
    return run(["-i", str(src), "-filter_complex", ";".join(parts), *maps,
                *H264, "-crf", "18", *AAC, str(dst)], dry_run)


def volume(src, dst, gain=1.0, normalize=False, dry_run=False):
    """Change loudness. gain: 1.5 = 50% louder, 0.5 = half. normalize: even out to -16 LUFS (speech/social)."""
    af = "loudnorm=I=-16:TP=-1.5:LRA=11" if normalize else f"volume={gain}"
    return run(["-i", str(src), "-af", af, "-c:v", "copy", *AAC, str(dst)], dry_run)


def burn_captions(src, cues, dst, style=None, dry_run=False):
    """Burn styled captions (a list of captions.Cue) into the video."""
    style = style or captions.Style()
    try:
        w, h = video_size(src)
    except Exception:
        if not dry_run:
            raise
        w, h = 1080, 1920
    with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
        f.write(captions.to_ass(cues, style, w, h))
        ass = f.name
    path = Path(ass).as_posix().replace(":", r"\:")
    return run(["-i", str(src), "-vf", f"ass='{path}'", *H264, "-crf", "20", "-c:a", "copy", str(dst)],
               dry_run)


BUILTIN_SFX = {
    "whoosh": "anoisesrc=d=0.7:c=pink:a=0.6,highpass=f=400,afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.4",
    "pop": "sine=f=520:d=0.15,afade=t=out:d=0.15",
    "ding": "sine=f=1320:d=0.6,afade=t=out:st=0.05:d=0.55",
    "boom": "sine=f=55:d=0.9,afade=t=out:st=0.1:d=0.8,volume=3",
}


def _zoom_expr(zooms):
    """Build the zoom factor z(t) from (start, end, kind, amount) tuples.

    kind: 'in' (1 -> amount across the range, then snaps back), 'out' (amount -> 1),
    'punch' (quick ease in, hold, quick ease out).
    """
    terms = []
    for s, e, kind, amt in zooms:
        if e <= s:
            raise ValueError("zoom end must be after start")
        d, a = e - s, amt - 1
        p = f"clip((t-{s})/{d},0,1)"
        if kind == "in":
            f = p
        elif kind == "out":
            f = f"(1-{p})"
        elif kind == "punch":
            r = min(0.35, d / 3)
            f = f"clip(min((t-{s})/{r},({e}-t)/{r}),0,1)"
        else:
            raise ValueError("zoom type must be in, out or punch")
        terms.append(f"between(t,{s},{e})*{a}*{f}")
    return "1+" + "+".join(terms)


def zoom(src, dst, zooms, focus=(0.5, 0.5), dry_run=False):
    """Animated zoom in/out. zooms: [(start, end, 'in'|'out'|'punch', amount)], e.g. (2, 4, 'punch', 1.3).

    focus: (x, y) as 0-1 fractions of the frame the zoom aims at (0.5, 0.5 = centre).
    """
    zooms = [(captions.parse_time(a), captions.parse_time(b), k, float(m)) for a, b, k, m in zooms]
    if not zooms:
        raise ValueError("no zooms given")
    z = _zoom_expr(zooms)
    w, h = video_size(src) if not dry_run else (1080, 1920)
    fx, fy = focus
    vf = (f"scale=w='trunc(iw*({z})/2)*2':h='trunc(ih*({z})/2)*2':eval=frame,"
          f"crop={w}:{h}:x='clip({fx}*iw-{w}/2,0,iw-{w})':y='clip({fy}*ih-{h}/2,0,ih-{h})',setsar=1")
    return run(["-i", str(src), "-vf", vf, "-map", "0:v", "-map", "0:a?", *H264, "-crf", "18",
                "-c:a", "copy", str(dst)], dry_run)


def add_graphics(src, dst, images=(), texts=(), dry_run=False):
    """Overlay timed images (logos, stickers, lower thirds) and text graphics.

    images: dicts with image, at ('2-5'), position, scale (fraction of video width), fade (sec), opacity
    texts:  graphics.TextGraphic items
    """
    w, h = video_size(src) if not dry_run else (1080, 1920)
    args, chains, last = ["-i", str(src)], [], "[0:v]"
    for i, g in enumerate(images, 1):
        s, e = graphics.parse_at(g["at"])
        fade = min(float(g.get("fade", 0.3)), (e - s) / 2)
        pos = POSITIONS[g.get("position", "bottom-right")]
        args += ["-loop", "1", "-t", str(e - s), "-i", str(g["image"])]
        chains.append(
            f"[{i}:v]format=rgba,scale={int(w * float(g.get('scale', 0.25)))}:-2,"
            f"colorchannelmixer=aa={g.get('opacity', 1.0)},"
            f"fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={e - s - fade}:d={fade}:alpha=1,"
            f"setpts=PTS+{s}/TB[g{i}]")
        chains.append(f"{last}[g{i}]overlay={pos}:eof_action=pass[o{i}]")
        last = f"[o{i}]"
    if texts:
        with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
            f.write(graphics.to_ass(list(texts), w, h))
        path = Path(f.name).as_posix().replace(":", r"\:")
        chains.append(f"{last}ass='{path}'[vout]")
        last = "[vout]"
    if not chains:
        raise ValueError("no graphics given")
    if last != "[vout]":
        chains[-1] = chains[-1].rsplit("[", 1)[0] + "[vout]"
    return run([*args, "-filter_complex", ";".join(chains), "-map", "[vout]", "-map", "0:a?",
                *H264, "-crf", "18", "-c:a", "copy", "-shortest", str(dst)], dry_run)


def mix_audio(src, dst, bgm=None, bgm_volume=0.25, duck=True, fade=1.5, bgm_start=0.0,
              sfx=(), voice_volume=1.0, dry_run=False):
    """Add background music (looped, faded, optionally ducked under speech) and timed sound effects.

    sfx: [(file_or_'builtin:whoosh', at_seconds, volume)]. Builtins: whoosh, pop, ding, boom.
    """
    if not bgm and not sfx:
        raise ValueError("give a bgm file and/or sfx")
    total = 1.0 if dry_run else duration(src)
    voice = dry_run or has_audio(src)
    args, parts, mix = ["-i", str(src)], [], []
    n = 1
    if voice:
        parts.append(f"[0:a]volume={voice_volume},asplit=2[v1][v2]" if (bgm and duck) else
                     f"[0:a]volume={voice_volume}[v1]")
        mix.append("[v1]")
    if bgm:
        args += ["-stream_loop", "-1", "-i", str(bgm)]
        f = min(fade, total / 2)
        chain = (f"[{n}:a]atrim=start={bgm_start},asetpts=PTS-STARTPTS,atrim=end={total},"
                 f"volume={bgm_volume},afade=t=in:d={f},afade=t=out:st={max(total - f, 0)}:d={f}")
        parts.append(chain + "[bgm]")
        if voice and duck:
            parts.append("[bgm][v2]sidechaincompress=threshold=0.03:ratio=10:attack=20:release=400[bgmd]")
            mix.append("[bgmd]")
        else:
            mix.append("[bgm]")
        n += 1
    for k, (file, at, vol) in enumerate(sfx):
        if str(file).startswith("builtin:"):
            name = str(file).split(":", 1)[1]
            if name not in BUILTIN_SFX:
                raise ValueError(f"unknown builtin sfx {name!r}; choose from {', '.join(BUILTIN_SFX)}")
            args += ["-f", "lavfi", "-i", BUILTIN_SFX[name]]
        else:
            args += ["-i", str(file)]
        ms = int(captions.parse_time(at) * 1000)
        parts.append(f"[{n}:a]volume={vol},adelay={ms}:all=1[s{k}]")
        mix.append(f"[s{k}]")
        n += 1
    parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0,"
                 f"atrim=end={total}[a]")
    return run([*args, "-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", *AAC, str(dst)], dry_run)
