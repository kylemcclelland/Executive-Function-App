# ruff: noqa: E501
"""The production image's Divinum Officium engine: a pinned, checksum-verified archive, trimmed to what the engine reads."""

import hashlib
import io
import re
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_divinum_officium as fetch  # noqa: E402

from app.divine_office import engine  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
COMMIT = "e3e0894e00318a6fc5daae309c845ec5f300837a"
TOP = f"divinum-officium-{COMMIT}"


def archive(tmp_path: Path, extra=()) -> Path:
    path = tmp_path / "do.tar.gz"
    files = {
        "web/cgi-bin/horas/officium.pl": b"# engine",
        "web/cgi-bin/DivinumOfficium/Main.pm": b"1;",
        "web/www/horas/Latin/Sancti/11-10.txt": b"[Officium]",
        "web/www/Tabulae/Kalendaria/1960.txt": b"table",
        "web/www/missa/Latin/Ordo.txt": b"not needed",
        "web/cgi-bin/missa/missa.pl": b"not needed",
        "README.md": b"not needed",
    }
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{TOP}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra:
            tar.addfile(info)
    return path


def test_only_the_engine_and_its_data_are_extracted_and_the_commit_is_recorded(tmp_path):
    link = tarfile.TarInfo(f"{TOP}/web/cgi-bin/horas/escape")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    target = tmp_path / "out"
    assert fetch.extract(archive(tmp_path, [link]), COMMIT, target) == 4
    files = sorted(str(p.relative_to(target)).replace("\\", "/") for p in target.rglob("*") if p.is_file())
    assert files == ["UPSTREAM_COMMIT", "web/cgi-bin/DivinumOfficium/Main.pm", "web/cgi-bin/horas/officium.pl",
                     "web/www/Tabulae/Kalendaria/1960.txt", "web/www/horas/Latin/Sancti/11-10.txt"]
    assert engine.horas_dir(engine.EngineConfig(str(target))) == target / "web" / "cgi-bin" / "horas"


def test_paths_outside_the_checkout_are_never_kept():
    assert fetch.kept(f"{TOP}/web/cgi-bin/horas/../../../../etc/passwd") is None
    assert fetch.kept(f"{TOP}/web/www/horasX/file") is None
    assert fetch.kept(TOP) is None


def test_a_wrong_checksum_is_refused(tmp_path):
    path = archive(tmp_path)
    with pytest.raises(SystemExit, match="checksum mismatch"):
        fetch.verify(path, "0" * 64)
    fetch.verify(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_an_archive_without_the_engine_is_refused(tmp_path):
    path = tmp_path / "empty.tar.gz"
    with tarfile.open(path, "w:gz"):
        pass
    with pytest.raises(SystemExit, match=r"officium\.pl"):
        fetch.extract(path, COMMIT, tmp_path / "out")


def test_only_a_full_commit_can_be_pinned():
    with pytest.raises(SystemExit, match="40-character"):
        fetch.main("master", "0" * 64, "unused")


def test_the_recorded_commit_is_reported_without_git(tmp_path):
    (tmp_path / "UPSTREAM_COMMIT").write_text(COMMIT + "\n", encoding="ascii")
    engine.upstream_commit.cache_clear()
    assert engine.upstream_commit(str(tmp_path)) == COMMIT
    engine.upstream_commit.cache_clear()


def test_the_image_pins_the_documented_commit_and_points_the_api_at_it():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    pinned = re.search(r"ARG DIVINUM_OFFICIUM_COMMIT=([0-9a-f]+)", dockerfile).group(1)
    assert pinned == COMMIT and re.search(r"ARG DIVINUM_OFFICIUM_SHA256=[0-9a-f]{64}\n", dockerfile)
    assert COMMIT in (BACKEND.parent / "docs" / "divine-office.md").read_text(encoding="utf-8")
    assert "ENV DIVINUM_OFFICIUM_PATH=/opt/divinum-officium" in dockerfile and "libcgi-pm-perl" in dockerfile
    assert "scripts" not in (BACKEND / ".dockerignore").read_text(encoding="utf-8").split()
