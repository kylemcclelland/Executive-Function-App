# ruff: noqa: E501
"""Run the upstream Divinum Officium engine for one date and hour, locally and safely.

No network, no shell: a fixed argument list, a timeout, and an environment containing only what Perl needs. If the engine is not
configured or fails, ``EngineUnavailable`` carries the plain reason and the caller reports it: no text is ever invented.
"""

import subprocess
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

VERSION = "Rubrics 1960 - 1960"      # the 1960 rubrics with the 1960 (universal Roman) calendar; NOT "Rubrics 1960 - 2020 USA" / Newcalendar
UPSTREAM_URL = "https://github.com/DivinumOfficium/divinum-officium"
WRAPPER = Path(__file__).with_name("run_engine.pl")
HORAS = ("web", "cgi-bin", "horas")
TIMEOUT_SECONDS = 40
MIN_YEAR, MAX_YEAR = 1900, 2100


class EngineUnavailable(Exception):
    pass


@dataclass(frozen=True)
class EngineConfig:
    path: str | None
    perl: str = "perl"
    perl5lib: str | None = None


def horas_dir(config: EngineConfig) -> Path:
    if not config.path:
        raise EngineUnavailable("The Divinum Officium engine is not configured (set DIVINUM_OFFICIUM_PATH to a checkout).")
    directory = Path(config.path).joinpath(*HORAS)
    if not (directory / "officium.pl").is_file():
        raise EngineUnavailable("DIVINUM_OFFICIUM_PATH does not contain web/cgi-bin/horas/officium.pl.")
    return directory


@lru_cache(maxsize=4)
def upstream_commit(path: str) -> str | None:
    # The production image holds an extracted archive with no git: scripts/fetch_divinum_officium.py records the pinned commit beside it.
    try:
        recorded = Path(path, "UPSTREAM_COMMIT").read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        recorded = ""
    if len(recorded) == 40 and all(c in "0123456789abcdef" for c in recorded):
        return recorded
    try:
        done = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    commit = done.stdout.strip()
    return commit if done.returncode == 0 and len(commit) == 40 else None


def query_for(day: date, command: str) -> str:
    return f"date={day.month:02d}-{day.day:02d}-{day.year}&command={command}&version={VERSION}&lang1=Latin&lang2=English&content=1"


def run_engine(config: EngineConfig, day: date, command: str) -> str:
    if not (MIN_YEAR <= day.year <= MAX_YEAR):
        raise EngineUnavailable(f"The Office is available for the years {MIN_YEAR} to {MAX_YEAR}.")
    directory = horas_dir(config)
    env = {"PATH": _path_env()}
    if config.perl5lib:
        env["PERL5LIB"] = config.perl5lib
    try:
        done = subprocess.run(
            [config.perl, str(WRAPPER), str(directory), query_for(day, command)],
            capture_output=True, timeout=TIMEOUT_SECONDS, env=env, check=False,
        )
    except FileNotFoundError as exc:
        raise EngineUnavailable("Perl was not found; the Divinum Officium engine needs it.") from exc
    except subprocess.TimeoutExpired as exc:
        raise EngineUnavailable("The Divinum Officium engine did not answer in time.") from exc
    output = done.stdout.decode("utf-8", errors="replace")
    if done.returncode != 0 or "DO-META" not in output:
        detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()[:1]
        raise EngineUnavailable("The Divinum Officium engine failed" + (f": {detail[0][:160]}" if detail else "."))
    return output


def _path_env() -> str:
    import os
    return os.environ.get("PATH", "")
