"""Run a whole edit from one JSON spec: cuts -> zooms -> audio -> graphics -> captions."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from vedit import captions, edits, graphics


def _style(d: dict) -> captions.Style:
    keys = {"font", "size", "color", "outline_color", "highlight", "position", "bold", "upper",
            "outline", "margin_v", "max_words"}
    bad = set(d) - keys - {"script", "srt", "speech", "lang", "model", "srt_out"}
    if bad:
        raise ValueError(f"unknown caption keys: {', '.join(sorted(bad))}")
    return captions.Style(**{k: v for k, v in d.items() if k in keys})


def run_spec(spec: dict, dry_run: bool = False) -> str:
    src, out = spec["input"], spec["output"]
    with tempfile.TemporaryDirectory() as tmp:
        cur, n = src, 0

        def nxt() -> str:
            nonlocal n
            n += 1
            return str(Path(tmp) / f"step{n}.mp4")

        if "cuts" in spec:
            c = spec["cuts"]
            dst = nxt()
            edits.cut_segments(cur, dst, keep=c.get("keep"), remove=c.get("remove"), dry_run=dry_run)
            cur = dst
        if spec.get("zooms"):
            dst = nxt()
            edits.zoom(cur, dst, [(z["at"].split("-")[0], z["at"].split("-")[1], z.get("type", "punch"),
                                   z.get("amount", 1.3)) for z in spec["zooms"]],
                       focus=tuple(spec.get("zoom_focus", (0.5, 0.5))), dry_run=dry_run)
            cur = dst
        a = spec.get("audio")
        if a and (a.get("bgm") or a.get("sfx")):
            dst = nxt()
            edits.mix_audio(
                cur, dst, bgm=a.get("bgm"), bgm_volume=a.get("bgm_volume", 0.25), duck=a.get("duck", True),
                fade=a.get("fade", 1.5), bgm_start=a.get("bgm_start", 0),
                sfx=[(s["file"], s["at"], s.get("volume", 0.8)) for s in a.get("sfx", [])],
                voice_volume=a.get("voice_volume", 1.0), dry_run=dry_run)
            cur = dst
        g = spec.get("graphics")
        if g:
            dst = nxt()
            texts = []
            for t in g:
                if "text" in t:
                    s, e = graphics.parse_at(t["at"])
                    texts.append(graphics.TextGraphic(
                        t["text"], s, e, **{k: v for k, v in t.items() if k not in ("text", "at")}))
            edits.add_graphics(cur, dst, images=[t for t in g if "image" in t], texts=texts, dry_run=dry_run)
            cur = dst
        c = spec.get("captions")
        if c:
            dst = nxt()
            if c.get("srt"):
                cues = captions.parse_srt(c["srt"])
            elif c.get("script"):
                cues = captions.script_to_cues(Path(c["script"]).read_text(encoding="utf-8"),
                                               0 if dry_run else edits.duration(cur))
            else:
                cues = [] if dry_run else captions.transcribe(cur, c.get("lang"), c.get("model", "small"))
            if c.get("srt_out") and not dry_run:
                captions.write_srt(captions.regroup(cues, c.get("max_words", 0)), c["srt_out"])
            edits.burn_captions(cur, cues, dst, _style(c), dry_run=dry_run)
            cur = dst
        if cur == src:
            raise ValueError("spec has nothing to do (add cuts, zooms, audio, graphics or captions)")
        if not dry_run:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cur, out)
    return out
