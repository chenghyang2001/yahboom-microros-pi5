# 拍五逐步演練：開機流程（2026-10-28）

第一次用 skill `pi5-live-drill` 實測。開始時電池 67（6.7 V，偏低）；使用者選擇直接開始，掉到 65 以下要停下來提醒。

格子（tmux session `drill`）：① agent 終端　② ROS 2 容器終端　③ 主機檢查用

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 準備 | — | 關掉上次的演練視窗與兩個容器，開三格終端，開始錄影 | 三格都是空的提示字元 |
| 1 | ③→① | ③ `docker ps`；① `sh ~/start_agent_rpi5.sh` | ③ 沒有容器；① agent `running...` 等小腦 |
| 2 | ①（使用者按 Reset） | 按 ESP32 Reset | ① `session established` 加一串 `created`；燈號每 3 秒快閃 2 次 |
| 3 | ③→②→③ | ③ `cat -n ~/ros2_humble.sh`；② `sh ~/ros2_humble.sh`；③ `docker ps` | ② 變成 `root@`；有 2 個容器 |
| 4 | ② | `ros2 node list`、`ros2 topic list`、`ros2 topic echo --once /battery` | `/YB_Car_Node`、10 個話題、電池數值 |

## 進度（2026-10-28 07:02 暫停）

- ✅ 準備：三格終端（tmux session `drill`）、開場語音 `01-intro`
- ✅ 第一步：③ `docker ps`（空）→ ③ `cat -n start_agent_rpi5.sh` → ① 翻譯官 `running...`（語音 `02-step1`、`03-step1-result`，截圖 `shots/02-step1.png`）
- ⏸ **暫停**：使用者的手機沒電要充電，預計 2～3 小時後繼續
- ⬜ 第二步：按 ESP32 Reset（接著寫 `04-step2.txt`）
- ⬜ 第三步、第四步

錄影第 1 段：`~/Videos/pi5-drill/pi5drill-boot-sequence-20261028-065224.mp4`（596 秒，06:52:25 開始）。
繼續時要開第 2 段錄影，合成影片時兩段要接起來；`tts_log.tsv` 用的是絕對時間，兩段各自對齊。
暫停時電池 67（6.7 V），之後要先看電量。

### 07:05 補充：接續方式

- 手機已從 PC 拔掉，遠端關機的指令沒有送出去。使用者會自己把車子關機、充電，手機也一起充。
- **車子會重開機**，所以繼續時從「準備」重來：
  1. 上電檢查
  2. 開三格終端
  3. 開第 2 段錄影
  4. 重做第一步
  5. 第二步：按 ESP32 Reset
  6. 第三步、第四步
- 使用者的接續口令：「繼續開機流程演練」。

## 11:17 接續（第 2 段）

- 上電檢查 1～9 ✅：33.4 °C、0x0、磁碟 55%、電池 81、/scan 12.5 Hz、/imu 21.1 Hz；第 10 步時鐘差 15083 秒（本場不跑 SLAM，第二步 Reset 會重新對時）
- **Pi 的 IP 變成 `10.169.179.1`**（手機熱點換網段），nc 轉接改用新 IP
- 準備：VNC 開到螢幕 3；`pkill -x lxterminal` 關掉自動開的兩個終端，ROS 2 容器跟著停，**agent 容器沒停**，另外 `docker stop`；tmux `drill` 三格
- 第 2 段錄影開始 11:17:16；接續開場語音 `04-resume`
