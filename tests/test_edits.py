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
