"""Caption helpers: build cues (from speech, a script, or an .srt), style them, write .srt/.ass."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from vedit.ffmpeg import FFmpegError


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Style:
    font: str = "Arial"
    size: int = 0              # 0 = auto (scaled to video height)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    highlight: str | None = None   # colour of the word being spoken (needs word timings)
    position: str = "bottom"       # bottom | middle | top
    bold: bool = True
    upper: bool = False
    outline: int = 3
    margin_v: int = 0          # 0 = auto
    max_words: int = 0         # 0 = keep original cue; N = show N words at a time


# ---------- time / colour helpers ----------

def parse_time(value) -> float:
    """Seconds (12.5) or [HH:]MM:SS[.ms] -> float seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def ass_color(hex_color: str) -> str:
    """'#RRGGBB' -> ASS '&H00BBGGRR'."""
    h = hex_color.lstrip("#")
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"colour must look like #FFFFFF, got {hex_color!r}")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


# ---------- reading / writing .srt ----------

def parse_srt(path) -> list[Cue]:
    text = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        a, b = (x.strip() for x in lines[idx].split("-->"))
        cues.append(Cue(_read_srt_time(a), _read_srt_time(b), " ".join(l.strip() for l in lines[idx + 1:])))
    return cues


def _read_srt_time(s: str) -> float:
    return parse_time(s.replace(",", ".").split()[0])


def write_srt(cues: list[Cue], path) -> None:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_srt_time(c.start)} --> {_srt_time(c.end)}\n{c.text}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")


# ---------- building cues ----------

def script_to_cues(script: str, total: float, start: float = 0.0) -> list[Cue]:
    """One cue per non-empty line; time is shared out in proportion to line length."""
    lines = [l.strip() for l in script.splitlines() if l.strip()]
    if not lines:
        raise ValueError("script is empty")
    weights = [max(len(l), 1) for l in lines]
    scale = total / sum(weights)
    cues, t = [], start
    for line, w in zip(lines, weights):
        end = t + w * scale
        cues.append(Cue(t, end, line, _spread_words(line, t, end)))
        t = end
    return cues


def _spread_words(text: str, start: float, end: float) -> list[Word]:
    words = text.split()
    if not words:
        return []
    weights = [max(len(w), 1) for w in words]
    scale = (end - start) / sum(weights)
    out, t = [], start
    for w, wt in zip(words, weights):
        out.append(Word(t, t + wt * scale, w))
        t += wt * scale
    return out


def transcribe(src, language: str | None = None, model: str = "small") -> list[Cue]:
    """Speech -> cues with word timings using faster-whisper (pip install faster-whisper)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise FFmpegError(
            "automatic captions need faster-whisper: pip install faster-whisper "
            "(or pass --script / an .srt instead)"
        ) from e
    wm = WhisperModel(model, compute_type="int8")
    segments, _ = wm.transcribe(str(src), language=language, word_timestamps=True, vad_filter=True)
    cues = []
    for seg in segments:
        words = [Word(w.start, w.end, w.word.strip()) for w in (seg.words or []) if w.word.strip()]
        cues.append(Cue(seg.start, seg.end, seg.text.strip(), words))
    return cues


def regroup(cues: list[Cue], max_words: int) -> list[Cue]:
    """Re-split cues so each shows at most max_words words (TikTok style)."""
    if max_words <= 0:
        return cues
    out = []
    for c in cues:
        words = c.words or _spread_words(c.text, c.start, c.end)
        for i in range(0, len(words), max_words):
            chunk = words[i:i + max_words]
            out.append(Cue(chunk[0].start, chunk[-1].end, " ".join(w.text for w in chunk), chunk))
    return out


# ---------- ASS (styled) output ----------

_ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def to_ass(cues: list[Cue], style: Style, width: int, height: int) -> str:
    if style.position not in _ALIGN:
        raise ValueError("position must be bottom, middle or top")
    size = style.size or max(int(height * 0.045), 12)
    margin_v = style.margin_v or int(height * (0.08 if style.position != "middle" else 0))
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{style.font},{size},{ass_color(style.color)},{ass_color(style.color)},"
        f"{ass_color(style.outline_color)},&H80000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,1,"
        f"{style.outline},0,{_ALIGN[style.position]},{int(width * 0.06)},{int(width * 0.06)},{margin_v},1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    cues = regroup(cues, style.max_words)
    fmt = (lambda s: s.upper()) if style.upper else (lambda s: s)
    lines = []
    for c in cues:
        if style.highlight and c.words:
            hl = ass_color(style.highlight)
            for i, w in enumerate(c.words):
                end = c.words[i + 1].start if i + 1 < len(c.words) else c.end
                text = " ".join(
                    f"{{\\c{hl}}}{fmt(x.text)}{{\\r}}" if j == i else fmt(x.text)
                    for j, x in enumerate(c.words)
                )
                lines.append(_dialogue(w.start, end, text))
        else:
            lines.append(_dialogue(c.start, c.end, fmt(c.text)))
    return head + "\n".join(lines) + "\n"


def _dialogue(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
