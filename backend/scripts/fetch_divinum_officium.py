# ruff: noqa: E501
"""Fetch the pinned Divinum Officium engine into a directory, for the production image.

Downloads GitHub's archive of ONE commit, refuses it unless its SHA-256 matches, and extracts only
what the Office and the liturgical calendar read: the Perl engine (web/cgi-bin/horas and the
DivinumOfficium modules) and its data (web/www/horas texts, web/www/Tabulae tables). Records the
commit in UPSTREAM_COMMIT, because the image has no git to ask. Run by the Dockerfile at build time.

    python scripts/fetch_divinum_officium.py <commit> <sha256> <destination>
"""

import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ARCHIVE_URL = "https://codeload.github.com/DivinumOfficium/divinum-officium/tar.gz/{commit}"
KEEP = ("web/cgi-bin/horas", "web/cgi-bin/DivinumOfficium", "web/www/horas", "web/www/Tabulae")
COMMIT_FILE = "UPSTREAM_COMMIT"


def kept(name: str) -> str | None:
    """The member's path inside the checkout if it is one we keep (the archive's top folder dropped), else None."""
    parts = PurePosixPath(name).parts[1:]
    if not parts or ".." in parts:
        return None
    relative = "/".join(parts)
    return relative if any(relative == keep or relative.startswith(keep + "/") for keep in KEEP) else None


def verify(archive: Path, sha256: str) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != sha256.lower():
        raise SystemExit(f"Divinum Officium archive checksum mismatch: expected {sha256}, got {digest.hexdigest()}")


def extract(archive: Path, commit: str, destination: Path) -> int:
    count = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            relative = kept(member.name)
            if relative is None or not (member.isfile() or member.isdir()):
                continue                                   # links, devices and everything outside KEEP stay out
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            count += 1
    if not (destination / "web/cgi-bin/horas/officium.pl").is_file():
        raise SystemExit("The archive does not contain web/cgi-bin/horas/officium.pl")
    (destination / COMMIT_FILE).write_text(commit + "\n", encoding="ascii")
    return count


def main(commit: str, sha256: str, destination: str) -> None:
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise SystemExit("Pin a full 40-character commit, not a branch or tag")
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "divinum-officium.tar.gz"
        with urllib.request.urlopen(ARCHIVE_URL.format(commit=commit), timeout=300) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        verify(archive, sha256)
        count = extract(archive, commit, Path(destination))
    print(f"Divinum Officium {commit}: {count} files in {destination}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
