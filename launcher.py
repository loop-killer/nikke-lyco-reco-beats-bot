"""Interactive launcher for the LYCO RECO BEATS replay bot."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"

STAGES = {
    "2": ("第一关 ShootStage（Hard）", ROOT / "charts" / "ShootStage_HD.json"),
    "3": ("第二关 Training（Hard）", ROOT / "charts" / "TrainingHD.json"),
    "4": ("第三关 DessertStage（Hard）", ROOT / "charts" / "DessertStage_HD.json"),
}


def load_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"offset_ms": -45, "device": None, "game_dir": None}


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def run(cmd: list[str]) -> int:
    print("$", " ".join(str(c) for c in cmd))
    return subprocess.call([sys.executable, *map(str, cmd)], cwd=ROOT)


def extract(cfg: dict) -> None:
    args = ["tools/extract_charts.py"]
    if cfg.get("game_dir"):
        args += ["--game-dir", cfg["game_dir"]]
    if run(args) != 0:
        path = input("未找到游戏目录。请输入 NIKKE 安装目录（包含 nikke_Data 的那一层）: ").strip().strip('"')
        if not path:
            return
        cfg["game_dir"] = path
        save_config(cfg)
        if run(["tools/extract_charts.py", "--game-dir", path]) != 0:
            print("谱面提取失败，请检查路径")
            return
    run(["tools/extract_bgm.py"])
    run(["tools/extract_sfx.py"])
    print("资源提取完成。极少数调试关卡的 BGM 不在游戏里，跳过是正常的。")


def play(cfg: dict, chart: Path) -> None:
    if not chart.exists():
        print(f"缺少 {chart}，请先执行「提取游戏资源」")
        return
    args = ["tools/replay.py", "--chart", chart, "--offset-ms", str(cfg.get("offset_ms", -45))]
    if cfg.get("device"):
        args += ["--device", cfg["device"]]
    run(args)


def calibrate(cfg: dict) -> None:
    chart = ROOT / "charts" / "ShootStage_NM.json"
    if not chart.exists():
        print("缺少 Normal 谱面，请先执行「提取游戏资源」")
        return
    print(
        "\n校准会跑一次 Normal 第一关，用 -90/-70/-50/-30/-10 五个偏移轮换测试。\n"
        "请先进入 Normal 第一关，看到提示后按 F9 再开始。\n"
        "（校准不会替你点菜单：在游戏里手动进 Normal 第一关。）\n"
    )
    args = ["tools/calibrate.py", "--chart", chart]
    if cfg.get("device"):
        args += ["--device", cfg["device"]]
    run(args)


def main() -> None:
    cfg = load_config()
    while True:
        print("\n" + "=" * 52)
        print("  LYCO RECO BEATS 自动 Perfect 工具")
        print("=" * 52)
        print(f"  当前偏移: {cfg.get('offset_ms', -45):+} ms")
        print("  1) 提取游戏资源（首次使用 / 游戏更新后）")
        print("  2) 第一关 ShootStage（Hard，全 MOD）")
        print("  3) 第二关 Training（Hard，全 MOD）")
        print("  4) 第三关 DessertStage（Hard，全 MOD）")
        print("  5) 校准偏移")
        print("  0) 退出")
        choice = input("请选择: ").strip()
        if choice == "0":
            return
        if choice == "1":
            extract(cfg)
        elif choice in STAGES:
            name, chart = STAGES[choice]
            print(f"\n{name}\n请在游戏里选 Hard 并打开全部 MOD，然后按提示操作。")
            play(cfg, chart)
        elif choice == "5":
            calibrate(cfg)
        else:
            print("无效选择")


if __name__ == "__main__":
    main()
