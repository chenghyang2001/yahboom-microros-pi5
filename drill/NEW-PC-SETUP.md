# 換電腦交接手冊：Yahboom MicroROS-Pi5 實車演練＋語音指令

最後更新：2026-10-27（原機：DESKTOP-6LST1BR，Windows 11）

這份給「在另一台 Windows PC 接手」用：要裝什麼、要搬什麼、怎麼連上車、怎麼確認一切正常。
接續 Part 2 的演練內容看 `drill/PART2-HANDOFF.md`；語音指令規格看 `voice/SPEC.md`。

---

## 0. 全貌

```
新 PC（Windows）
  ├─ USB 線 ── 手機 OPPO Reno13 F（adb 序號 84bbb261，開「個人熱點」AnPing）
  │              └─ Wi-Fi 熱點 ── 小車 Pi 5（10.57.201.1，帳號 pi）
  │                                   ├─ Docker 容器 ros-humble（ROS 2，DOMAIN_ID=20）
  │                                   ├─ ESP32 擴展板（micro-ROS：馬達、IMU、蜂鳴器、雲台、光達）
  │                                   └─ 藍牙：K200 Pro 耳機（已配對、信任）
  └─ 透過 adb 轉接：SSH（127.0.0.1:8022）、VNC（127.0.0.1:5900）
```

新 PC 不需要連上手機熱點；全部經 USB 線＋adb 轉接。

---

## 1. 要安裝的軟體（新 PC）

| 軟體 | 原機版本 | 安裝指令（PowerShell 或 Git Bash） | 用途 |
| --- | --- | --- | --- |
| Git for Windows | 2.55 | `winget install Git.Git` | Git Bash、拉 repo |
| GitHub CLI | 2.100 | `winget install GitHub.cli` 然後 `gh auth login` | 私人 repo、push |
| Python | 3.14 | `winget install Python.Python.3.14` | ycar.py、語音原型 |
| Android platform-tools（adb） | 1.0.41 | `winget install Google.PlatformTools` | 手機轉接 |
| TigerVNC Viewer | 1.16.2 | `winget install TigerVNC.TigerVNC` | 看 Pi 桌面 |
| ffmpeg | 9.0 | `winget install Gyan.FFmpeg` | 錄影、截圖、音檔 |
| Windows Terminal | 內建 | — | 教練／車況視窗 |
| Node.js | 24 | `winget install OpenJS.NodeJS.LTS` | Claude Code |
| Claude Code | 2.1.x | `npm install -g @anthropic-ai/claude-code` | 教練 |

Python 套件：

```bash
python -m pip install paramiko faster-whisper anthropic
```

| 套件 | 原機版本 | 用途 |
| --- | --- | --- |
| paramiko | 5.1.0 | SSH 帶密碼連車（Windows 內建 ssh 不能帶密碼） |
| faster-whisper | 1.2.1 | 語音轉文字（第一次跑會下載 small 模型約 480 MB） |
| anthropic | 2.3.0 | Claude Haiku 理解指令 |

> 執行 Python 一律加 `PYTHONUTF8=1`（系統預設 cp950 會讓中文亂碼）。

---

## 2. 要搬過去的東西

| 項目 | 怎麼拿 | 備註 |
| --- | --- | --- |
| 教材＋工具 repo | `git clone https://github.com/chenghyang2001/yahboom-microros-pi5 ~/workspace/yahboom-microros-pi5` | drill/、voice/、lessons/ 都在裡面 |
| 主工作 repo | `git clone https://github.com/chenghyang2001/hp1 ~/workspace/hp1` | Claude Code 在這裡開 |
| Claude 全域設定與記憶 | `git clone https://github.com/chenghyang2001/.claude ~/.claude`（已有就 `git pull`） | 記憶在 `~/.claude/projects/C--Users-<使用者名稱>-workspace-hp1/memory/`；**新 PC 使用者名稱不同時，資料夾名也不同**，要把原機的 `C--Users-USER-workspace-hp1/memory/` 複製到新名稱底下 |
| `voice/.env`（API Key） | **不在 git 裡**。照第 5 節重建 | 不要用 email／聊天傳 Key |
| 錄影工具 `~/workspace/ros2-turtle-cli-demo/` | **本機資料夾，沒有 git**。需要錄精華影片才搬（`say.sh`、`highlights/`、`tts_log_*.tsv`） | 只做語音指令可不搬 |
| 原始錄影 | 原機 `~/Videos/kindle-drill/yb-real-20261027-0445-*.mp4` | 選搬 |

---

## 3. 手機（只第一次要做）

1. 手機開「開發人員選項 → USB 偵錯」（原機已開）。
2. USB 線接新 PC，手機會跳「允許 USB 偵錯嗎？」→ 勾「一律允許」→ 允許。
3. 確認：

   ```bash
   adb devices -l      # 要看到 84bbb261  device
   ```

4. 個人熱點：名稱 `AnPing`（實驗用，密碼見記憶 `phone-hotspot-original`）。全部演練結束要改回原始設定 `Reno13F`（跟 Claude 說「恢復熱點」）。

---

## 4. 連上車（每次開機都要做）

前提：車子總開關開、Pi 開機約 30 秒、手機熱點開、USB 線接好。

```bash
# 4-1 找車子 IP（MAC 2c:cf:67 開頭是 Pi；一直是 10.57.201.1，可能會變）
adb -s 84bbb261 shell ip neigh

# 4-2 手機轉接（兩個都要背景常駐；USB 一拔就斷，要重開）
adb -s 84bbb261 shell "nc -L -p 8022 nc 10.57.201.1 22"   &
adb -s 84bbb261 shell "nc -L -p 5900 nc 10.57.201.1 5900" &
adb -s 84bbb261 forward tcp:8022 tcp:8022
adb -s 84bbb261 forward tcp:5900 tcp:5900

# 4-3 健康檢查（應看到 /YB_Car_Node、/battery、/scan 約 12 Hz）
cd ~/workspace/yahboom-microros-pi5/drill
YCAR_PASS=yahboom PYTHONUTF8=1 python ycar.py status
```

- 車子帳密：`pi` / `yahboom`（Yahboom 出廠預設）。密碼只放環境變數 `YCAR_PASS`。
- `/battery` 數值 = 電壓 × 10。**低於 70 要充電**；66～67 時蜂鳴器會連續嗶嗶並不聽指令。

### 車況視窗（Windows Terminal「YB 車況」）

建一個 `yb-monitor.cmd`（放暫存資料夾即可）：

```bat
@echo off
set YCAR_PASS=yahboom
set PYTHONUTF8=1
cd /d "%USERPROFILE%\workspace\yahboom-microros-pi5\drill"
python ycar.py rospy monitor.py --timeout 7200
pause
```

```bash
wt.exe -w new --title "YB 車況" --suppressApplicationTitle cmd /k "<yb-monitor.cmd 的 Windows 路徑>"
```

- 本機視窗關掉後，車上的 monitor 可能還在跑：`python ycar.py host 'docker exec $(docker ps -q|head -1) ps -eo pid,args | grep ycar_job'` 找到後用 `python ycar.py kill <ycar_job_...>` 收掉。

### VNC 看 Pi 桌面

```bash
"C:\Program Files\TigerVNC\vncviewer.exe" 127.0.0.1::5900
```

帳密用剪貼簿貼（注音輸入法會打亂字）。

### 視窗座標（每台 PC 不同，先量再擺）

- 原機（DESKTOP-6LST1BR）DPI-aware 座標：螢幕 2 = x 1920～3840；教練 `1920,0,960,1040`、車況 `2880,0,960,1040`。
- 舊筆電 hp1 是 x 2880～4800。新 PC 請先列出視窗座標再擺。
- **中文 PowerShell 腳本要存成 UTF-8 with BOM**，否則標題比對失敗。
- 演練視窗與錄影**不放螢幕 1**。

---

## 5. 語音指令（目前進度）

### 已完成

| 項目 | 狀態 |
| --- | --- |
| K200 Pro 耳機與 Pi 5 藍牙配對、信任 | ✅（耳機開著就自動連車） |
| 耳機聽蜂鳴器（A2DP 模擬嗶聲） | ✅ `drill/beep-bridge.txt` |
| 耳機麥克風 → 車子收音（HFP mSBC） | ✅ 辨識出「前進、後退、左轉、右轉、停止」 |
| 筆電原型：文字 → Claude Haiku → 指令 JSON | ✅ 6 句全對，每句約 1～1.6 秒 |

### 新 PC 重建 API Key

```bash
cd ~/workspace/yahboom-microros-pi5/voice
cp .env.example .env
# 用記事本打開 .env，填入 ANTHROPIC_API_KEY=sk-ant-...（Key 在 Gmail 主旨「anthropic key」那封）
git check-ignore .env   # 要印出 .env，代表不會進 git
```

- **不要**把 `ANTHROPIC_API_KEY` 設成 Windows 全域環境變數（會讓所有 `claude` 改扣 API 費用）。

### 測試原型

```bash
PYTHONUTF8=1 python intent_proto.py --selftest                       # 不需網路，印 PASS
PYTHONUTF8=1 python intent_proto.py --text "小車 蜂鳴器響三十秒"      # 預期 beep 30000
PYTHONUTF8=1 python intent_proto.py --no-llm 錄音.wav                 # 只測語音轉文字
```

### 藍牙耳機兩種模式（同時只能一種）

| 模式 | 指令（在車上，`XDG_RUNTIME_DIR=/run/user/1000`） | 能做什麼 |
| --- | --- | --- |
| A2DP（聽） | `pactl set-card-profile bluez_card.00_12_12_00_D9_C2 a2dp-sink-sbc` | 音質好，麥克風不能用 |
| HFP（講＋聽） | `pactl set-card-profile bluez_card.00_12_12_00_D9_C2 headset-head-unit-msbc` | 麥克風可用，聽的音質較差 |

麥克風來源：`bluez_input.00_12_12_00_D9_C2.0`；輸出：`bluez_output.00_12_12_00_D9_C2.1`（音量 50%）。

### 下一步（充飽電後）

1. 車上 `free -h` 看記憶體；在 Pi 主機建 venv 裝 faster-whisper、anthropic，量辨識速度
2. 容器內發指令節點 `voice/ros_cmd_node.py`（讀 stdin JSON → `/beep`、`/cmd_vel`，含逾時自動停）
3. 主機收音迴圈 `voice/voice_agent.py`（HFP 收音 → 斷句 → STT → 喚醒詞「小車」→ 停車捷徑／LLM → 安全夾限 → 送節點）
4. 架空測試 → 放地上 → 擴充到雲台（`/servo_s1` ±90、`/servo_s2` **只用 -45～0**）、相機、轉速

---

## 6. 安全與教訓（新 PC 也一樣）

1. **充電**：先讓 Pi 正常關機 → 關擴展板總開關 → 再插充電器（紅燈充電、綠燈拔）。不可邊充邊用、不可過夜。2000mAh，約 1.5～3 小時。
2. **Pi 關機 ≠ 全車斷電**：蜂鳴器在 ESP32 擴展板，Pi 關機後低電量警報仍會叫，要關總開關。
3. **雲台別抬頭**（`/servo_s2` > 0 會扯掉相機 USB，出現 error -71）；相機線先用束線帶固定。
4. **停車**：只送零 `/cmd_vel`；不要用 `ycar.py stopcar`（會把雲台送回 0 度）。
5. **手把**：先按 R1 才會發速度；Y／A 會轉雲台上下，沒有角度限制。
6. `ros2 topic pub` 一定要寫話題名，漏了只會報 `message type invalid`。
7. 在車上用 `pkill -f '<字串>'` 時，自己這條指令也含那段字串，會把自己殺掉；改用 `ycar.py kill <唯一 marker>`。
8. 語音延遲約 3～6 秒，**不能當緊急煞車**，車旁要有人、手把在身邊。

---

## 7. 新 PC 驗收清單

- [ ] `adb devices` 看到 `84bbb261`
- [ ] `ycar.py status` 看到 `/YB_Car_Node`、電池 ≥ 70、`/scan` 約 12 Hz
- [ ] 「YB 車況」視窗每 0.5 秒更新
- [ ] VNC 看得到 Pi 桌面
- [ ] `ros2 topic pub --once /beep std_msgs/msg/UInt16 '{data: 300}'` 蜂鳴器短嗶
- [ ] 耳機戴上，`beep-bridge` 跑著時送 `/beep` 耳機有嗶聲
- [ ] `intent_proto.py --selftest` 印 PASS、`--text` 測試回傳正確 JSON
