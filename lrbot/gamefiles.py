"""Locate the NIKKE installation and resolve Addressables bundles by name.

Bundle file names carry a 32-hex content hash that changes with every game update,
so nothing here is hard-coded: the Addressables catalog is parsed on demand and the
hash is used to find the corresponding file in the runtime cache.
"""
from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from pathlib import Path

CATALOG_REL = Path("nikke_Data/StreamingAssets/aa/catalog.json")
CACHE_REL = Path("nikke_Data/runtime_data/cache")
BUNDLE_RE = re.compile(r"([^\"\\/]+?)_([0-9a-f]{32})\.bundle")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


def _process_paths() -> list[Path]:
    """Executable paths of running nikke.exe processes."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    paths: list[Path] = []
    try:
        count = 4096
        pids = (wintypes.DWORD * count)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(needed)):
            return paths
        for index in range(needed.value // ctypes.sizeof(wintypes.DWORD)):
            pid = pids[index]
            if not pid:
                continue
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                continue
            try:
                size = wintypes.DWORD(2048)
                buf = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    path = Path(buf.value)
                    if path.name.lower() in ("nikke.exe", "nikke_launcher.exe"):
                        paths.append(path)
            finally:
                kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        pass
    return paths


def find_game_dir(explicit: str | None = None) -> Path:
    """Return the folder that contains nikke_Data."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("NIKKE_DIR")
    if env:
        candidates.append(Path(env))
    for exe in _process_paths():
        candidates.append(exe.parent)
        candidates.append(exe.parent.parent)
    for base in ("D:/NIKKE", "C:/NIKKE", "E:/NIKKE", "D:/Games/NIKKE", "C:/Games/NIKKE"):
        candidates.append(Path(base))
    for candidate in candidates:
        roots = [candidate]
        try:
            roots.extend(p for p in candidate.iterdir() if p.is_dir())
        except OSError:
            continue
        for root in roots:
            if (root / CATALOG_REL).exists():
                return root
    raise FileNotFoundError(
        "找不到 NIKKE 安装目录（需要包含 nikke_Data/StreamingAssets/aa/catalog.json）。\n"
        "请用 --game-dir 指定，或设置环境变量 NIKKE_DIR。"
    )


class GameFiles:
    def __init__(self, game_dir: str | None = None):
        self.root = find_game_dir(game_dir)
        self.catalog_path = self.root / CATALOG_REL
        self.cache = self.root / CACHE_REL
        self._catalog_text: str | None = None
        self._bundles: list[tuple[str, str]] | None = None

    def __repr__(self) -> str:
        return f"GameFiles({self.root})"

    @property
    def catalog_text(self) -> str:
        if self._catalog_text is None:
            self._catalog_text = self.catalog_path.read_text(encoding="utf-8", errors="ignore")
        return self._catalog_text

    def bundles(self) -> list[tuple[str, str]]:
        if self._bundles is None:
            text = self.catalog_text
            found: list[tuple[str, str]] = []
            # Scan hashes first (linear), then walk back to the preceding path separator.
            for match in re.finditer(r"([0-9a-f]{32})\.bundle", text):
                end = match.start() - 1
                if end <= 0 or text[end] != "_":
                    continue
                start = end
                while start > 0 and text[start - 1] not in '"\\/':
                    start -= 1
                name = text[start:end]
                if name:
                    found.append((name, match.group(1)))
            self._bundles = found
        return self._bundles

    def bundle_hash(self, pattern: str, suffix: bool = False) -> str:
        for name, hash_ in self.bundles():
            if (name.endswith(pattern) if suffix else pattern in name):
                return hash_
        raise LookupError(
            f"catalog 中找不到 bundle: {pattern}\n"
            "游戏更新后如果仍找不到，请先在游戏里进入一次该小游戏，让资源下载到本地。"
        )

    def bundle_data(self, pattern: str, suffix: bool = False) -> Path:
        hash_ = self.bundle_hash(pattern, suffix=suffix)
        for candidate in self.cache.glob(f"*/{hash_}/__data"):
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"资源未下载（bundle {pattern}, hash {hash_}）。\n"
            "请先在游戏里进入一次 LYCO RECO BEATS，让 Addressables 把资源缓存到本地。"
        )
