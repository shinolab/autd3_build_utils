import contextlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
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
    except subprocess.CalledProcessError:
        err(f"command failed: {' '.join(command)}")
        sys.exit(-1)


def fetch_submodule(*, recursive: bool = False) -> None:
    if shutil.which("git") is not None:
        command = ["git", "submodule", "update", "--init"]
        if recursive:
            command.append("--recursive")
        run_command(command)
    else:
        err("git is not installed. Skip fetching submodules.")


def _remove(path: Path) -> None:
    with contextlib.suppress(PermissionError):
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            for f in path.iterdir():
                _remove(f)
            path.rmdir()


def rremove(pattern: str, *, path: Path | str | None = None, exclude: str | None = None) -> None:
    path = path or Path.cwd()
    path = Path(path)

    if not path.exists():
        return

    if path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        paths = set(path.rglob(pattern))
        if exclude is not None:
            paths -= set(path.rglob(exclude))
        for f in paths:
            _remove(f)


def remove(path: Path | str) -> None:
    path = Path(path)
    rremove("*", path=path)
    if path.is_dir():
        path.rmdir()


def substitute_in_file(
    src_file: Path | str,
    mapping: list[tuple[str, str]],
    *,
    target_file: Path | str | None = None,
    flags: re.RegexFlag = re.NOFLAG,
) -> None:
    src_file = Path(src_file)
    target_file = Path(target_file) if target_file is not None else Path(src_file)
    content = src_file.read_text(encoding="utf-8")
    for key, value in mapping:
        content = re.sub(key, value, content, flags=flags)
    target_file.write_text(content, encoding="utf-8")


class BaseConfig:
    _platform: str
    arch: str
    release: bool

    def __init__(self: Self, args) -> None:  # noqa: ANN001
        self._platform = platform.system()
        if not self.is_windows() and not self.is_macos() and not self.is_linux():
            err(f'platform "{platform.system()}" is not supported.')
            sys.exit(-1)

        self.release = getattr(args, "release", False) or False

        arch: str = getattr(args, "arch", None)
        machine = platform.machine().lower()
        if arch is not None:
            machine = arch.lower()
        if machine in ["amd64", "x86_64"]:
            self.arch = "x64"
        elif machine in ["arm64", "aarch64"]:
            self.arch = "aarch64"
        elif machine in ["arm32", "armv7l"]:
            self.arch = "armv7l"
        else:
            err(f"Unsupported platform: {machine}")

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

    def download_and_extract(  # noqa: C901, PLR0912
        self: Self,
        repo: str,
        name: str,
        version: str,
        dest_dirs: list[str],
        *,
        ty: str = "shared",
    ) -> None:
        url: str
        base_url = f"https://github.com/shinolab/{repo}/releases/download/v{version}/{name}-v{version}"
        if self.is_windows():
            match self.arch:
                case "x64":
                    url = f"{base_url}-win-x64-{ty}.zip"
                case "aarch64":
                    url = f"{base_url}-win-aarch64-{ty}.zip"
                case _:
                    err(f"Unsupported platform: {platform.machine()}")
        elif self.is_macos():
            url = f"{base_url}-macos-aarch64-{ty}.tar.gz"
        elif self.is_linux():
            match self.arch:
                case "x64":
                    url = f"{base_url}-linux-x64-{ty}.tar.gz"
                case "aarch64":
                    url = f"{base_url}-linux-armv7-{ty}.tar.gz"
                case "armv7l":
                    url = f"{base_url}-linux-aarch64-{ty}.tar.gz"

        tmp_file = Path("tmp.zip" if url.endswith(".zip") else "tmp.tar.gz")
        urllib.request.urlretrieve(url, tmp_file)
        if tmp_file.suffix == ".zip":
            shutil.unpack_archive(tmp_file, ".")
        else:
            with tarfile.open(tmp_file, "r:gz") as tar:
                tar.extractall(filter="fully_trusted")
        tmp_file.unlink()

        for dest_dir in dest_dirs:
            Path(dest_dir).mkdir(parents=True, exist_ok=True)

        for dll in Path("bin").glob("*.dll"):
            for dest_dir in dest_dirs:
                shutil.copy(dll, dest_dir)
        for dylib in Path("bin").glob("*.dylib"):
            for dest_dir in dest_dirs:
                shutil.copy(dylib, dest_dir)
        for so in Path("bin").glob("*.so"):
            for dest_dir in dest_dirs:
                shutil.copy(so, dest_dir)
        for lib in Path("lib").glob("*.lib"):
            for dest_dir in dest_dirs:
                shutil.copy(lib, dest_dir)
        for a in Path("lib").glob("*.a"):
            for dest_dir in dest_dirs:
                shutil.copy(a, dest_dir)
        remove("bin")
        remove("lib")
