import contextlib
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Self


def err(msg: str) -> None:
    print("\033[91mERR \033[0m: " + msg)


def warn(msg: str) -> None:
    print("\033[93mWARN\033[0m: " + msg)


def info(msg: str) -> None:
    print("\033[92mINFO\033[0m: " + msg)


@contextlib.contextmanager
def working_dir(path: Path) -> Generator:
    cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def with_env(**kwargs: str) -> Generator:
    env = os.environ.copy()
    for key, value in kwargs.items():
        os.environ[key] = value
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(env)


def run_command(command: list[str]) -> None:
    try:
        subprocess.run(command, check=False).check_returncode()
    except subprocess.CalledProcessError as e:
        err(f"command failed: {e.cmd}")
        sys.exit(-1)


def fetch_submodule(*, recursive: bool = False) -> None:
    if shutil.which("git") is not None:
        command = ["git", "submodule", "update", "--init"]
        if recursive:
            command.append("--recursive")
        run_command(command)
    else:
        err("git is not installed. Skip fetching submodules.")


def rm_glob_f(pattern: str, *, path: Path | None = None, exclude: str | None = None) -> None:
    path = path or Path.cwd()
    paths = set(path.rglob(pattern))
    if exclude is not None:
        paths -= set(path.rglob(exclude))
    for f in paths:
        f.unlink(missing_ok=True)


class BaseConfig:
    _platform: str

    def __init__(self: Self) -> None:
        self._platform = platform.system()
        if not self.is_windows() and not self.is_macos() and not self.is_linux():
            err(f'platform "{platform.system()}" is not supported.')
            sys.exit(-1)

    def is_windows(self: Self) -> bool:
        return self._platform == "Windows"

    def is_macos(self: Self) -> bool:
        return self._platform == "Darwin"

    def is_linux(self: Self) -> bool:
        return self._platform == "Linux"

    def exe_ext(self: Self) -> str:
        return ".exe" if self.is_windows() else ""

    def is_pcap_available(self: Self) -> bool:
        if not self.is_windows():
            return True

        wpcap_exists = Path("C:\\Windows\\System32\\wpcap.dll").is_file() and Path("C:\\Windows\\System32\\Npcap\\wpcap.dll").is_file()
        packet_exists = Path("C:\\Windows\\System32\\Packet.dll").is_file() and Path("C:\\Windows\\System32\\Npcap\\Packet.dll").is_file()

        return wpcap_exists and packet_exists
