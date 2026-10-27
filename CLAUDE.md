# CLAUDE.md

Yahboom MicroROS-Pi5（Raspberry Pi 5＋ESP32 micro-ROS 麥克納姆輪小車）的 ROS 2 自學專案，包含三部分：繁中自學教材（20 單元＋網站＋影片）、電腦模擬套件（Gazebo），以及實車工具。實車工具包括連車、儀表板，以及藍牙耳機語音指令。個人學習專案，所有說明一律用繁體中文。

## 目錄結構

| 路徑 | 內容 | 進 git |
| --- | --- | --- |
| `voice/` | **藍牙耳機語音指令**（STT＋Claude Haiku＋ROS 2）：程式、規格、部署手冊、測試報告 | ✅ |
| `drill/` | 實車連線工具（`ycar.py`、`monitor.py`）與演練交接文件 | ✅ |
| `lessons/` | 20 單元講義原稿（W 暖身／B 初級／M 中級／A 高級），格式見 `LESSON-FORMAT.md` | ✅ |
| `site/` | 互動教材網站（GitHub Pages），由 `tools/build_site.py` 產生 | ✅ |
| `sim/` | ROS 2 Jazzy＋Gazebo Harmonic 模擬套件 `microros_pi5_sim/`、`scripts/` | ✅ |
| `research/notes/` | 研究筆記（A～F 主題） | ✅ |
| `tools/` | 建網站、做影片的腳本 | ✅ |
| `official/`、`source-code/`、`research/pdf-text/`、`videos/*` | 官方文件、原始碼、逐字稿（版權屬 Yahboom） | ❌ 只留本機 |
| `logs/`、`videos-out/` | 演練紀錄、輸出影片 | ❌ |

## 實車架構

```
PC (Windows, Git Bash)
  └─ USB ─ 手機（adb 84bbb261，nc 轉接 8022→SSH、5900→VNC）
             └─ 手機熱點 ─ Pi 5（10.57.201.1，使用者 pi）
                  ├─ 主機：PipeWire＋藍牙耳機、~/voice（voice_agent.py, venv）
                  ├─ Docker：yahboomtechnology/ros-humble:4.1.2（ROS 2 Humble, DOMAIN 20）
                  ├─ Docker：microros/micro-ros-agent（不要把指令送進這個）
                  └─ ESP32 擴展板（馬達、IMU、蜂鳴器、雲台、光達）
```

主要話題：`/cmd_vel`（Twist）、`/beep`（UInt16 毫秒）、`/servo_s1`、`/servo_s2`（Int32 角度）、`/scan`（12 Hz，0° 是車頭）、`/imu`、`/battery`（電壓×10）、`/odom_raw`。

## 常用指令

```bash
# 連車檢查（需先開 adb nc 轉接，見 drill/NEW-PC-SETUP.md）
cd drill && YCAR_PASS=yahboom PYTHONUTF8=1 python ycar.py status
# 子指令：host（Pi 主機）／ros（容器內 ros2）／rospy <檔>（容器內跑 python）／kill <樣式>／gui

# 語音指令：本機自我測試
cd voice && PYTHONUTF8=1 python intent_proto.py --selftest && PYTHONUTF8=1 python ros_cmd_node.py --selftest

# 教材
PYTHONUTF8=1 python tools/build_site.py
PYTHONUTF8=1 python tools/make_lesson_videos.py
```

**上電檢查**（代號「拍五」＝這台車）：照 **`drill/POWER-ON-CHECK.md`** 1～10 步。網路架構、Wi-Fi 備援看門狗、與教材連法的差別見 **`drill/NETWORK.md`**。

語音指令的部署（PC → SFTP → 車上）、啟動與停止方式，見 **`voice/DEPLOY.md`**。

## 重要規則與踩坑

- **程式正本在 PC。** 車上 `~/voice` 是部署複本，沒有 git，不要在車上直接改。
- **機密**：`ANTHROPIC_API_KEY` 只放在 `voice/.env`（PC）與車上 `~/voice/.env`，權限 600。repo 是**公開**的，`.env` 已列入 gitignore。不設全域環境變數，也不要貼到對話裡。
- **雲台**：`/servo_s2` 只能 -45～0（大於 0 是抬頭）。實測水平 ±45 加低頭也會扯斷相機 USB 線，語音預設停用雲台。
- **停車**：只送零 `/cmd_vel`。不要用 `ycar.py stopcar`，它會把雲台送回 0 度。
- **速度上限**：線速 0.15 m/s、角速 0.8 rad/s。語音延遲約 4～11 秒，語音「停」不能當緊急煞車（用手把 R1 接管）。
- **選容器**要過濾映像檔（`--filter ancestor=yahboomtechnology/ros-humble:4.1.2`）。不過濾會挑到 micro-ros-agent。
- 在 Pi 主機上用 PipeWire 前，先 `export XDG_RUNTIME_DIR=/run/user/1000`。
- 在 Pi 上用 `pgrep`／`pkill -f` 時，樣式要用 `^` 錨定，否則會比對到自己；停背景程式用 SIGTERM（SIGINT 會被忽略）。
- 在容器內執行 `pkill -f '<樣式>'` 時，若樣式也出現在自己的指令列裡，會連自己一起殺掉。
- 傳檔用 paramiko SFTP。用 base64 經 `ycar.py host` 傳，大檔會被截斷。
- 低電量時，ESP32 的蜂鳴器會一直叫，即使 Pi 已經關機。充電前要先讓 Pi 正常關機，再關總開關。
- 演練視窗與錄影不放螢幕 1。
- **Wi-Fi 備援**：車上跑 `pi5-wifi-fallback` 服務。連不上 AnPing 2 分鐘後開 `Micro_ros` 熱點（10.42.0.1），熱點閒置 5 分鐘就關掉、回頭找 AnPing。`Micro_ros` 已改成不自動連線，不要改回去。

## 技術堆疊

- 車上：Raspberry Pi OS（Debian）、Python 3.11、ROS 2 Humble（Docker）、PipeWire 0.3.65、faster-whisper 1.2.1（base int8）、anthropic 2.3.0（`claude-haiku-5-5`）、edge-tts（`zh-TW-HsiaoChenNeural`）、ffmpeg
- PC：Windows、Git Bash、Python 3.14（paramiko、faster-whisper、anthropic）、adb、TigerVNC
- 模擬：WSL Ubuntu 24.04、ROS 2 Jazzy、Gazebo Harmonic

## 開發慣例

- commit message 用繁體中文（「新增／修復／調整＋說明」），commit 後直接 push。
- 本專案屬學習性質，語音功能用「快速 demo 模式」開發（只派 code-writer，不跑 QA／reviewer），但每次改完都要跑內建 `--selftest`。
- 不硬編碼使用者路徑：Python 用 `Path.home()`／`Path(__file__)`，文件用 `~`。
