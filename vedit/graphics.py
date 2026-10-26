"""Timed text graphics (titles, lower thirds, call-outs) rendered as ASS events."""
from __future__ import annotations

from dataclasses import dataclass

from vedit.captions import _ALIGN, _ass_time, ass_color, parse_time


@dataclass
class TextGraphic:
    text: str
    start: float
    end: float
    position: str = "middle"       # top | middle | bottom
    size: int = 0                  # 0 = auto
    color: str = "#FFFFFF"
    box: str | None = None         # background box colour, e.g. "#000000"
    font: str = "Arial"
    fade: float = 0.3
    bold: bool = True


def parse_at(at) -> tuple[float, float]:
    a, _, b = str(at).partition("-")
    if not b:
        raise ValueError(f"time range must look like START-END, got {at!r}")
    return parse_time(a), parse_time(b)


def to_ass(items: list[TextGraphic], width: int, height: int) -> str:
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,60,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    for g in items:
        if g.position not in _ALIGN:
            raise ValueError("position must be top, middle or bottom")
        size = g.size or int(height * 0.06)
        margin = int(height * 0.12) if g.position != "middle" else 0
        tags = (f"\\an{_ALIGN[g.position]}\\fn{g.font}\\fs{size}\\b{1 if g.bold else 0}"
                f"\\c{ass_color(g.color)}\\fad({int(g.fade * 1000)},{int(g.fade * 1000)})")
        if g.box:  # opaque box behind the text
            tags += f"\\bord{int(size * 0.3)}\\3c{ass_color(g.box)}"
        text = g.text.replace("\\n", "\\N")
        lines.append(f"Dialogue: 1,{_ass_time(g.start)},{_ass_time(g.end)},Default,,0,0,{margin},,{{{tags}}}{text}")
    return head + "\n".join(lines) + "\n"
