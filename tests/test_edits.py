"""Integration tests: generate tiny synthetic clips with ffmpeg, run each edit, check output."""
import shutil
import subprocess

import pytest

from vedit import edits
from vedit.cli import main
from vedit.ffmpeg import duration, has_audio, probe

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    clip = d / "clip.mp4"
    _ff("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip))
    music = d / "music.mp3"
    _ff("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(music))
    logo = d / "logo.png"
    _ff("-f", "lavfi", "-i", "color=c=red:size=200x100", "-frames:v", "1", str(logo))
    srt = d / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n")
    return {"clip": clip, "music": music, "logo": logo, "srt": srt}


def _size(path):
    v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"]


def test_trim(media, tmp_path):
    out = tmp_path / "t.mp4"
    edits.trim(media["clip"], out, "1", "3")
    assert abs(duration(out) - 2) < 0.2


def test_concat(media, tmp_path):
    out = tmp_path / "c.mp4"
    edits.concat([media["clip"], media["clip"]], out)
    assert abs(duration(out) - 8) < 0.3


@pytest.mark.parametrize("mode", ["blur", "pad", "crop"])
def test_resize_vertical(media, tmp_path, mode):
    out = tmp_path / f"r_{mode}.mp4"
    edits.resize(media["clip"], out, 1080, 1920, mode=mode)
    assert _size(out) == (1080, 1920)


def test_compress_downscale(media, tmp_path):
    out = tmp_path / "s.mp4"
    edits.compress(media["clip"], out, max_height=240)
    assert _size(out)[1] == 240


def test_extract_audio(media, tmp_path):
    out = tmp_path / "a.mp3"
    edits.extract_audio(media["clip"], out)
    assert has_audio(out)


def test_add_music(media, tmp_path):
    out = tmp_path / "m.mp4"
    edits.add_music(media["clip"], media["music"], out)
    assert has_audio(out) and abs(duration(out) - 4) < 0.3


def test_subtitles(media, tmp_path):
    out = tmp_path / "sub.mp4"
    edits.subtitles(media["clip"], media["srt"], out)
    assert out.exists()


def test_watermark(media, tmp_path):
    out = tmp_path / "w.mp4"
    edits.watermark(media["clip"], media["logo"], out)
    assert _size(out) == (640, 360)


def test_speed(media, tmp_path):
    out = tmp_path / "f.mp4"
    edits.speed(media["clip"], out, 2.0)
    assert abs(duration(out) - 2) < 0.3


def test_thumbnail(media, tmp_path):
    out = tmp_path / "thumb.jpg"
    edits.thumbnail(media["clip"], out)
    assert out.stat().st_size > 0


def test_cli_dry_run(media, capsys):
    assert main(["--dry-run", "resize", str(media["clip"]), "-o", "x.mp4"]) == 0
    assert "ffmpeg" in capsys.readouterr().out


def test_cut_keep(media, tmp_path):
    out = tmp_path / "k.mp4"
    edits.cut_segments(media["clip"], out, keep=[("0", "1"), ("2", "3.5")])
    assert abs(duration(out) - 2.5) < 0.3 and has_audio(out)


def test_cut_remove(media, tmp_path):
    out = tmp_path / "rm.mp4"
    edits.cut_segments(media["clip"], out, remove=[("1", "2")])
    assert abs(duration(out) - 3) < 0.3


def test_volume(media, tmp_path):
    out = tmp_path / "v.mp4"
    edits.volume(media["clip"], out, gain=0.5)
    edits.volume(media["clip"], tmp_path / "n.mp4", normalize=True)
    assert has_audio(out) and (tmp_path / "n.mp4").exists()


def test_script_to_srt_roundtrip(tmp_path):
    from vedit import captions
    cues = captions.script_to_cues("Hello there\nSecond line is longer", 6)
    assert cues[0].start == 0 and abs(cues[-1].end - 6) < 1e-6
    captions.write_srt(cues, tmp_path / "s.srt")
    back = captions.parse_srt(tmp_path / "s.srt")
    assert [c.text for c in back] == ["Hello there", "Second line is longer"]


def test_styled_captions_with_highlight(media, tmp_path):
    from vedit import captions
    cues = captions.script_to_cues("Join our team today\nGrow with us", 4)
    style = captions.Style(color="#FFFF00", highlight="#FF0000", position="middle",
                           upper=True, max_words=2, size=40)
    out = tmp_path / "cap.mp4"
    edits.burn_captions(media["clip"], cues, out, style)
    assert _size(out) == (640, 360)
    assert "&H0000FFFF" in captions.to_ass(cues, style, 640, 360)


def test_cli_captions_from_script(media, tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("First caption\nSecond caption\n")
    out, srt = tmp_path / "c.mp4", tmp_path / "c.srt"
    rc = main(["captions", str(media["clip"]), "--script", str(script), "-o", str(out),
               "--srt-out", str(srt), "--position", "top", "--color", "#00FF00"])
    assert rc == 0 and out.exists() and srt.exists()


def test_bad_colour_is_clean_error(media, tmp_path):
    assert main(["subs", str(media["clip"]), str(media["srt"]), "-o", str(tmp_path / "x.mp4"),
                 "--color", "red"]) == 1


def _frame(path, t, out):
    _ff("-ss", str(t), "-i", str(path), "-frames:v", "1", str(out))
    return out.read_bytes()


@pytest.mark.parametrize("kind", ["in", "out", "punch"])
def test_zoom_keeps_size_and_changes_picture(media, tmp_path, kind):
    out = tmp_path / f"z_{kind}.mp4"
    edits.zoom(media["clip"], out, [(1, 3, kind, 1.5)])
    assert _size(out) == (640, 360) and abs(duration(out) - 4) < 0.3
    # mid-zoom frame differs from the original; a frame outside the range is untouched
    mid = 2.0 if kind == "punch" else 2.9 if kind == "in" else 1.1
    assert _frame(out, mid, tmp_path / "a.png") != _frame(media["clip"], mid, tmp_path / "b.png")


def test_zoom_rejects_bad_type(media, tmp_path):
    assert main(["zoom", str(media["clip"]), "-o", str(tmp_path / "x.mp4"), "--at", "1-2:spin:1.2"]) == 1


def test_graphics_image_and_text(media, tmp_path):
    from vedit import graphics
    out = tmp_path / "g.mp4"
    edits.add_graphics(
        media["clip"], out,
        images=[{"image": media["logo"], "at": "1-3", "position": "top-right", "scale": 0.3}],
        texts=[graphics.TextGraphic("Join us", 1, 3, box="#000000")])
    assert _size(out) == (640, 360) and abs(duration(out) - 4) < 0.3
    assert _frame(out, 2, tmp_path / "a.png") != _frame(media["clip"], 2, tmp_path / "b.png")


def test_mix_audio_bgm_and_sfx(media, tmp_path):
    out = tmp_path / "mix.mp4"
    edits.mix_audio(media["clip"], out, bgm=media["music"], sfx=[("builtin:whoosh", 1, 0.8),
                                                                 (media["music"], 2.5, 0.5)])
    assert has_audio(out) and abs(duration(out) - 4) < 0.3


def test_mix_audio_sfx_only_and_unknown_builtin(media, tmp_path):
    edits.mix_audio(media["clip"], tmp_path / "s.mp4", sfx=[("builtin:ding", 0.5, 1.0)])
    with pytest.raises(ValueError):
        edits.mix_audio(media["clip"], tmp_path / "x.mp4", sfx=[("builtin:nope", 0, 1)])


def test_make_full_spec(media, tmp_path):
    import json
    spec = {
        "input": str(media["clip"]), "output": str(tmp_path / "out" / "final.mp4"),
        "cuts": {"remove": [["3", "3.5"]]},
        "zooms": [{"at": "1-2", "type": "punch", "amount": 1.4}],
        "audio": {"bgm": str(media["music"]), "sfx": [{"file": "builtin:pop", "at": 1}]},
        "graphics": [{"image": str(media["logo"]), "at": "0.5-2", "position": "top-left"},
                     {"text": "Hello", "at": "1-2"}],
        "captions": {"srt": str(media["srt"]), "position": "bottom", "color": "#FFFF00"},
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    assert main(["make", str(p)]) == 0
    out = tmp_path / "out" / "final.mp4"
    assert _size(out) == (640, 360) and has_audio(out) and abs(duration(out) - 3.5) < 0.3


def test_make_empty_spec_is_clean_error(media, tmp_path):
    import json
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"input": str(media["clip"]), "output": str(tmp_path / "o.mp4")}))
    assert main(["make", str(p)]) == 1
