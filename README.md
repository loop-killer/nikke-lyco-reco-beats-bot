# LYCO RECO BEATS 自动 Perfect

[English](README.en.md) | 中文

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

> NIKKE (CN) × Lycoris Recoil collab minigame **LYCO RECO BEATS** auto-perfect bot — chart replay driven by local asset extraction + WASAPI loopback sync.

给《胜利女神：新的希望》（NIKKE 国服）×《莉可丽丝》联动小游戏 **LYCO RECO BEATS** 用的谱面回放工具。

Hard 三关 + 全 MOD 实测：

| 关卡 | 判定 |
|---|---|
| ShootStage（第一关） | **Perfect 76 / 76** |
| Training（第二关） | **Perfect 78 / 78** |
| DessertStage（第三关，含长按） | **Perfect 50 / 50** |

> 不需要看屏幕、不需要听声音判断、不需要识别“枪的种类”，也不改游戏文件。

---

## 原理

这游戏不是“看反应”，而是**背谱**：每个判定点的时刻都写在客户端资源里。

1. **提谱**：从游戏本地的 Addressables 缓存里读出 `LycorisLevelData`（每轨的 SubBeats）和
   `LycorisPresetData`（每个动作的判定偏移），拼出每个判定点的精确时刻：
   `t = (SubBeat + JudgeOffset) × 60 / (BPM × 24)`
2. **对时**：用 WASAPI 回环抓取游戏输出的 BGM，和从游戏里导出的参考音频做互相关，
   锁定“当前播放到第几秒”。
3. **回放**：用 `SendInput` 在正确时刻发送空格；Hold 段保持按住，Up 判定点松开。

因为时间是从谱面算出来的，误差只取决于调度（实测约 1ms）和声音链路延迟（校准后固定），
不需要每帧截图做识别——Hard 模式没有目押条、画面还是半黑的，视觉方案本来也做不了。

---

## 环境要求

- Windows 10/11
- 国服 PC 客户端（`nikke.exe`）
- Python 3.10+（推荐 3.13）
- 游戏内进入过一次 **LYCO RECO BEATS**（让资源下载到本地缓存）

## 安装

```bat
py -3.13 -m pip install -r requirements.txt
```

或者直接双击 `start.bat`，首次运行会让你先装依赖。

## 使用

双击 **`start.bat`**（会自动请求管理员权限），菜单里：

1. **提取游戏资源**：首次使用或游戏更新后跑一次，生成 `charts/`（谱面）、`audio/`（参考音频）、
   `audio/sfx/`（判定音效）。只读游戏目录，不会修改任何文件。
2. **校准偏移**：跑一次 Normal 第一关，用 5 个偏移轮换测试，自动选 Perfect 率最高的写进
   `config.json`。换耳机/换输出设备后建议重新校准。
3. **选关卡游玩**：进游戏选 Hard、打开全部 MOD，按脚本提示 **F9** 后开始。

脚本运行中：

- **F9** 开始（武装）
- **F10** 退出
- 游戏窗口必须保持前台；切走会中止
- 结算/暂停/死亡会自动停，不会在结算界面乱按

## 偏移（offset）

`config.json` 里的 `offset_ms` 是全局补偿：**正数 = 按晚，负数 = 按早**。

不同声卡/耳机的输出延迟不同，所以每台机器需要校准一次。默认 `-45` 是在
NVIDIA HDMI 输出 + 国服客户端上测出来的值。判定窗口大约有 60ms 宽，所以
校准到 ±10ms 以内就很稳。

## 支持范围

- 目前只做了 **Hard 三关**（ShootStage / Training / DessertStage）的全 MOD 谱面回放。
- MOD（HR/DT/HD/FL/SD/PF）不改变这三关的谱面，只改变判定窗口和规则；脚本只需要正确的偏移。
- 游戏更新后，bundle 的哈希会变，但 `extract_charts.py` 会重新读 `catalog.json` 解析，
  一般不需要改代码；如果游戏改了谱面结构则需要适配。

## 常见问题

**提示 “资源未下载”**
先在游戏里进一次 LYCO RECO BEATS（不用打完），让 Addressables 把资源缓存下来。

**提示 “timed out waiting for the stage BGM”**
输出设备选错了。运行 `py -3.13 tools/replay.py --list-devices` 看设备列表，
在 `config.json` 里填 `"device": "设备名的一部分"`。

**锁到了但判定全是 Great**
偏移不对。重新校准，或者手动把 `offset_ms` 往更负/更正调 10–20ms 试。

**没有判定（日志里 judgements 为空）**
说明空格没进游戏。确认是用管理员运行的（`start.bat` 会自动提权）、游戏在前台。

**会不会封号**
脚本只做外部输入模拟（`SendInput`）和只读本地资源，不注入进程、不改游戏文件、不碰 ACE。
但自动化本身违反游戏 ToS，风险自担。

## 目录结构

```
lrbot/                 核心库
  audio_sync.py        回环抓音 + 互相关锁定播放位置
  win_input.py         SendInput / 窗口 / 热键
  chart.py             谱面 -> 按下/松开事件
  gamefiles.py         定位游戏目录、按名字解析 bundle
tools/
  extract_charts.py    从游戏资源提取谱面
  extract_bgm.py       导出参考 BGM
  extract_sfx.py       导出判定音效（校准/分析用）
  replay.py            回放器
  calibrate.py         自动校准
  record.py            记录手动演奏（高级校准）
  analyze_latency.py   分析录音里的音效延迟
  dev/                 开发期用过的扫描/测试脚本（可选）
docs/
  CALIBRATION.md       偏移校准细节
charts/                生成的谱面（不入库）
audio/                 生成的参考音频（不入库）
runs/                  每次运行的日志（不入库）
```

## 技术细节

- 每拍 24 个 subbeat，`t = (SubBeat + JudgeOffset) × 60 / (BPM × 24)` 秒。
- `Down` / `Up` / `Hold` 三种判定：Hold 段只要保持按下就自动 Perfect，Up 段看松手时刻。
- MOD：`HR` 难度+1（收紧判定）、`DT` 伤害倍率、`HD` 追加 6/7 轨、`FL` 手电筒演出（画面变暗）、
  `SD` 一次 Miss 直接结束、`PF` Great/Good 直接判 Miss。
- 三关 Hard 的 HD/FL 轨为空，所以加不加这两个 MOD 谱面相同。

## 免责声明

本项目仅供学习交流，与 SHIFT UP / Level Infinite / 腾讯无关。
使用本工具可能违反游戏服务条款并导致账号处罚，一切后果由使用者自行承担。
请勿将提取出的游戏资源（谱面、音频）用于再分发。




