# 語音指令：部署與操作手冊

最後更新：2026-10-27｜對應 commit：c50cfcf 之後

藍牙耳機（K200 Pro）說中文 → 車上 Pi 5 辨識 → Claude Haiku 解析 → ROS 2 控制小車。本文件說明「程式放哪、怎麼改、怎麼傳上車、怎麼啟動與停止」。

## 1. 檔案放在哪裡

| 位置 | 角色 | 內容 | 版本控管 |
| --- | --- | --- | --- |
| PC `~/workspace/yahboom-microros-pi5/voice/` | **正本** | 程式、規格、本手冊、測試報告 | git |
| GitHub `chenghyang2001/yahboom-microros-pi5` | 遠端備份 | 同上（**公開 repo**） | git |
| Pi 5 `~/voice/` | **執行用複本** | 程式＋`.venv`＋`.env`（API Key）＋執行產物 | 無（從 PC 傳上去） |

**規則：只在 PC 改程式。** 車上沒有 git，在車上直接改的內容不會留下紀錄，下次部署也會被覆蓋。

### 程式檔

| 檔案 | 在哪裡執行 | 作用 |
| --- | --- | --- |
| `voice_agent.py` | Pi 主機（venv） | 主程式：耳機收音、斷句、呼叫辨識與解析、送指令、拍照、播提示音 |
| `intent_proto.py` | 被 `voice_agent.py` import | faster-whisper 語音辨識＋喚醒詞＋停車捷徑＋Claude 解析＋安全夾限 |
| `ros_cmd_node.py` | Docker 容器內（啟動時自動 `docker cp` 到 `/tmp/`） | 收 JSON 指令 → 發布 `/beep`、`/cmd_vel`、`/servo_s1/s2`；雷達防撞、看門狗 |

### 車上才有、不進 repo 的檔案

| 檔案 | 說明 |
| --- | --- |
| `~/voice/.env` | `ANTHROPIC_API_KEY=...`，權限 600。**不可進 git**（repo 是公開的）、不設全域環境變數 |
| `~/voice/.venv/` | Python 3.11 venv：faster-whisper 1.2.1、anthropic 2.3.0、edge-tts |
| `~/voice/agent.log` | 執行 log（每次啟動覆蓋） |
| `~/voice/photos/` | 語音拍的照片 `YYYYmmdd-HHMMSS.jpg` |
| `~/voice/tts_cache/` | 「準備好了」語音的 mp3 快取 |

## 2. 修改與部署流程

```
PC 改程式 → 本機自我測試 → commit + push → SFTP 傳到車上 → 車上自我測試 → 重啟語音程式
```

### 2-1. 本機自我測試（PC，Git Bash）

```bash
cd ~/workspace/yahboom-microros-pi5/voice
PYTHONUTF8=1 python intent_proto.py --selftest        # 規則與夾限，不需網路
PYTHONUTF8=1 python ros_cmd_node.py --selftest        # 雷達防撞判斷，不需 ROS
PYTHONUTF8=1 python intent_proto.py --selftest-llm    # 實打 Claude（需要 voice/.env）
PYTHONUTF8=1 python -m py_compile voice_agent.py
```

### 2-2. 提交

```bash
cd ~/workspace/yahboom-microros-pi5
git add voice/<改過的檔案>
git commit -m "動詞 + 簡短說明"
git push
```

### 2-3. 連上車子（前提）

手機開熱點、車子連上熱點（IP `10.57.201.1`），手機 USB 接 PC（adb 序號 `84bbb261`）。兩條轉接在背景執行：

```bash
adb -s 84bbb261 shell "nc -L -p 8022 nc 10.57.201.1 22"     # SSH，背景執行
adb -s 84bbb261 forward tcp:8022 tcp:8022
cd ~/workspace/yahboom-microros-pi5/drill
YCAR_PASS=yahboom PYTHONUTF8=1 python ycar.py status       # 確認連得到
```

轉接常會自己斷（exit 255）。`ycar.py` 報「連不上 127.0.0.1:8022」時，重開 `nc` 並重設 `adb forward`。詳見 `drill/NEW-PC-SETUP.md`。

### 2-4. 傳到車上（SFTP）

Windows 內建 ssh 不能帶密碼，一律用 Python paramiko：

```bash
cd ~/workspace/yahboom-microros-pi5/voice
PYTHONUTF8=1 python - <<'EOF'
import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("127.0.0.1", port=8022, username="pi", password="yahboom", timeout=15)
s = c.open_sftp()
for f in ["intent_proto.py", "ros_cmd_node.py", "voice_agent.py"]:
    s.put(f, "/home/pi/voice/" + f)
_, o, _ = c.exec_command("cd ~/voice && .venv/bin/python intent_proto.py --selftest | tail -1; "
                         "python3 ros_cmd_node.py --selftest | tail -1; "
                         "sha256sum intent_proto.py ros_cmd_node.py voice_agent.py")
print(o.read().decode()); c.close()
EOF
```

兩個 `PASS` 都出現，且 SHA256 與 PC 一致（`sha256sum voice/*.py`）才算部署成功。

> 不要用 base64 經 `ycar.py host` 傳檔，大檔會被截斷（實測 192 KB 只收到 49 KB）。

### 2-5. 啟動、停止、重啟（在車上執行）

| 動作 | 指令（在 Pi 的 `~/voice` 下） |
| --- | --- |
| 啟動 | `setsid nohup .venv/bin/python -u voice_agent.py > agent.log 2>&1 < /dev/null &` |
| 停止 | `pkill -TERM -f '^.venv/bin/python -u voice_agent'` |
| 確認是否在跑 | `pgrep -af '^.venv/bin/python -u voice_agent'` |
| 看 log | `tail -f ~/voice/agent.log` |

- 用 `setsid nohup` 在背景執行：手機轉接斷掉時，語音程式不會跟著停。
- 停止**一定用 SIGTERM**。背景程式會忽略 SIGINT（Ctrl+C），`pkill -INT` 停不掉。
- `pgrep`/`pkill` 的樣式要用 `^` 錨定。不錨定的話，比對指令會把自己那一行也算進去，誤判「已在執行」，或把自己殺掉。
- 停止時程式會依序：送停車 → 關閉節點 → 停止收音 → 把耳機切回 A2DP。
- 啟動約 10 秒後，耳機會播「小車已經準備好了，可以開始用語音下命令」。**啟動時請保持安靜約 3 秒**，程式要量背景噪音；量到時有人講話，門檻會被設太高（實測 1370→門檻 2192，正常約 450→720）。看 log 的「背景 RMS」，數值異常就重啟一次。

PC 端便利腳本（只在本機 scratchpad，不在 repo）：`run_agent.py` 會在車上沒有語音程式時啟動它，並把 `agent.log` 串流回本機；加 `--attach` 只看 log、不啟動。

### 2-6. 常用參數

| 參數 | 預設 | 說明 |
| --- | --- | --- |
| `--model` | `base` | faster-whisper 模型。`small` 較準但慢約 2.5 倍（Pi 5 約 12 秒） |
| `--allow-gimbal` | 關 | **雲台預設停用**（會扯斷相機線，見第 4 節） |
| `--no-ready-voice` | — | 不播「準備好了」語音 |
| `--dry-run` | — | 不啟動 ROS 節點，只印出要送的 JSON（拍照仍會真的拍） |
| `--wav <檔>` | — | 不收音，直接處理一個 wav 後結束（冒煙測試用） |
| `--threshold` | 500 | 收音門檻下限（實際門檻 = max(背景噪音 × 1.6, 這個值)） |

## 3. 語音指令

每句開頭都要說「**小車**」。從說完到動作約 4～11 秒，其中辨識約 4 秒、Claude 解析約 1～6.5 秒。

| 類別 | 說法範例 | 執行內容 |
| --- | --- | --- |
| 蜂鳴器 | 小車，蜂鳴器響五秒／蜂鳴器停止 | `/beep` 毫秒數，0～60000；送 0 可中斷正在響的蜂鳴器 |
| 短距離移動 | 小車，直線前進／後退／左轉／右轉 | 走 2 秒（最多 3 秒）後自動停 |
| 持續移動 | 小車，持續前進／一直前進／一直後退 | 一直走，直到說「停」、防撞觸發或滿 180 秒 |
| 速度 | 慢慢前進（0.05）、前進（0.1）、快一點前進（0.15 m/s） | 線速上限 ±0.15 m/s，角速上限 ±0.8 rad/s |
| 停止 | 小車，停 | 走捷徑、不經 Claude，約 4 秒生效；同時停掉蜂鳴器 |
| 拍照 | 小車，拍一張照片 | 存到 `~/voice/photos/`，相機不會轉動 |
| 雲台 | （停用） | 回兩聲低音，不動作 |

**不要說「前進不要停」**：句子裡有「停」字，會被當成停車。

### 耳機提示音

| 聲音 | 意思 |
| --- | --- |
| 一聲高音 | 指令已送出 |
| 兩聲短高音 | 拍照完成 |
| 兩聲低音（短） | 聽不懂、意思不清楚，或雲台被停用 |
| 兩聲低音（長） | 車子自己停了：防撞觸發、雷達沒資料，或滿 180 秒 |
| TTS 語音 | 啟動完成，或耳機重新連上 |

## 4. 安全設計與限制

| 項目 | 設定 | 為什麼 |
| --- | --- | --- |
| 喚醒詞 | 句子要有「小車」（含小鞋、小謝、曉車、小陳等誤辨字） | 平常講話不會誤觸發 |
| 停車捷徑 | 有「停」且沒有「蜂鳴」→ 直接停車 | 不等 Claude，快 1～6 秒 |
| 移動護欄 | Claude 回移動指令，但原文沒有前、後、走、轉等移動字 → 改成聽不懂 | 實測「鏡頭往左看」被聽成「進頭往」，Claude 卻猜成前進 |
| 雷達防撞 | `move`／`drive` 期間，前進方向 ±25° 內小於 0.30 m 就停；雷達超過 1 秒沒資料也停 | 語音停車有 4 秒延遲。雷達 0° 是車頭（2026-10-27 用手實測） |
| 持續移動上限 | 180 秒（`DRIVE_MAX_SEC`） | 保底，避免沒聽到「停」時一直走 |
| 看門狗 | 節點的 stdin 中斷（主程式掛掉）→ 送零速度 | 程式出錯時車子會停 |
| 雲台 | 預設停用；開啟時水平 ±90、垂直只用 -45～0 | 水平 ±45 加低頭 -45 也扯斷過相機 USB 線（`dmesg` 顯示 USB disconnect） |
| 停車方式 | 只送零 `/cmd_vel`，不用 `ycar.py stopcar` | `stopcar` 會把雲台送回 0 度 |

**語音「停」不能當緊急煞車。** 要立刻停，用手把按 R1 接管，或直接把車拿起來。

## 5. 常見問題

| 症狀 | 原因與處理 |
| --- | --- |
| 一直顯示「片段太短，丟棄」 | 收音門檻太高。看 log 的背景 RMS，太高就安靜後重啟 |
| 辨識出重複句子，例如「鏡頭往右看」×30 | Whisper 遇到雜音會重複提示詞。已加 VAD 過濾和 40 token 上限，最多約 7 秒；提示詞也已拿掉雲台句子 |
| 辨識一次花幾十秒 | 同時在車上拍照或跑其他吃 CPU 的程式。已設 `temperature=0`，不會反覆重試 |
| Claude 解析 6 秒以上 | 3 秒逾時後 SDK 自動重試一次。網路慢時會發生 |
| 指令送到錯的容器 | 車上有兩個容器。程式用 `--filter ancestor=yahboomtechnology/ros-humble:4.1.2` 指定 |
| 拍照失敗、`/dev/video0` 不見 | 相機 USB 線鬆了。重插後用 `v4l2-ctl -d /dev/video0 --info` 確認 |
| 停止語音程式後耳機還在通話模式 | 程式被強制結束、沒有正常收尾。執行 `pactl set-card-profile bluez_card.00_12_12_00_D9_C2 a2dp-sink-sbc` |
| 指令要在 Pi 主機上執行 | 先 `export XDG_RUNTIME_DIR=/run/user/1000`，否則找不到 PipeWire |

## 6. 相關文件

- `voice/SPEC.md`：最初的 MVP 規格
- `voice/reports/test-20261027.md`：2026-10-27 實車測試報告
- `drill/NEW-PC-SETUP.md`：換電腦接手（軟體、連車、API Key 重建）
- `drill/PART2-HANDOFF.md`：實車演練 Part 2 交接
- 根目錄 `CLAUDE.md`：給 Claude Code 的專案簡報
