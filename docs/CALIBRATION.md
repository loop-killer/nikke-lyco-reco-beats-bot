# 偏移校准（进阶）

脚本的按键时刻 = 谱面时刻 + `offset_ms`。这个偏移吸收的是「游戏把声音放出来 → 回环把它录回来」
的固定延迟，所以它和声卡/耳机/输出设备有关，每台机器不一样。

## 自动校准（推荐）

`start.bat` → `5) 校准偏移`。

它会用 `-90 / -70 / -50 / -30 / -10` 五个偏移在 Normal 第一关轮换打一遍，
统计每个偏移的 Perfect 率，把最好的写进 `config.json`。

## 手动扫描

```bat
py -3.13 tools\replay.py --chart charts\ShootStage_NM.json --sweep=-80,-60,-40,-20,0 --dump-verdicts
```

跑完看 `runs/<时间>.log` 里的 `note ... <offset>ms <verdict>`，哪个偏移全 Perfect 就用哪个。

## 判定窗口

以 ShootStage 为例，实测（带难度 MOD）：

| 偏移 | Perfect |
|---|---|
| -80 ~ -50 | 全 Perfect |
| -30 | 全 Perfect |
| -20 | 偶尔 Great |
| -10 | 约一半 Great |
| 0 | 几乎全 Great |

窗口大约 60–70ms 宽，中心在 -40 左右。校准误差在 ±10ms 以内即可稳定 AP。

## 用游戏音效测延迟（高级）

`tools/record.py` 可以记录一次手动演奏的按键时刻；`tools/analyze_latency.py`
可以从 `--record-audio` 录下的回环音频里找到游戏播放的打击音效，直接算出声音链路延迟：

```bat
py -3.13 tools\replay.py --chart charts\ShootStage_NM.json --offset-ms 0 --max-notes 15 --record-audio
py -3.13 tools\analyze_latency.py --wav runs\audio_xxx.wav --meta runs\audio_xxx.json
```

输出里的 `implied --offset-ms` 就是建议值（取负）。
