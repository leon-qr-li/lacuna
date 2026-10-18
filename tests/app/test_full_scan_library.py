"""Library decoding edge cases found by the full scan of 2026-10-18."""
import shutil

import pytest

from lacuna_app.library import LibraryError, decode
from lacuna_core import media

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_a_file_ffmpeg_cannot_read_leaves_no_half_decoded_file(tmp_path):
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"not audio at all" * 100)
    with pytest.raises(LibraryError):
        decode(bad, tmp_path / "out" / "x.wav", 16000, "m")
    assert list((tmp_path / "out").iterdir()) == []


def test_without_ffmpeg_the_message_says_so(tmp_path, monkeypatch):
    """The soxr check ran ffmpeg first and raised FileNotFoundError before the friendly message."""
    src = tmp_path / "a.wav"
    src.write_bytes(b"RIFF")
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    media.ffmpeg_has_soxr.cache_clear()
    try:
        with pytest.raises(LibraryError, match="ffmpeg"):
            decode(src, tmp_path / "out" / "x.wav", 16000, "m")
    finally:
        monkeypatch.undo()
        media.ffmpeg_has_soxr.cache_clear()
