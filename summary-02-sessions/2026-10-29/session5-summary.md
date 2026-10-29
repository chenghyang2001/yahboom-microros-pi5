# Session 5 摘要：M4 光達應用實車逐步演練（第 7 場）

- 日期：2026-10-29（09:00～10:40，DESKTOP-6LST1BR）
- 主題：路線圖第 7 場 M4 光達應用：警衛、避障、跟隨、巡邏
- 影片：<https://youtu.be/SCftI8V7Atw>（私人，約 48 分鐘，播放清單「Yahboom MicroROS-Pi5 逐步演練」第 10 支）

## 完成事項

### 開場準備

- 上電檢查 1～9 ✅：29.6 °C、throttled 0x0、磁碟 55%、電池 81、/scan 12.5 Hz、/imu 20.7 Hz。Pi 的 IP 是 10.169.179.1（跟 10/28 下午一樣，不是 10.57.201.1）。第 10 步時鐘差 38841 秒，使用者按 ESP32 Reset 後降到 1 秒，**這次手機 nc 轉接沒有斷**。
- 開始前讀車上程式碼，發現 4 個安全問題：避障預設 0.3 m/s、1.0 rad/s 且一啟動就跑；跟隨、警衛的 PID 沒有速度上限；巡邏預設 0.2／0.9，且讀 `/scan` 那行被註解掉（遇障不停）；手把開機不會自動啟動。
- 寫了 `cmd_vel_limiter.py` 限速閥（code-writer，快速模式）：官方程式用 `-r cmd_vel:=cmd_vel_raw -r /cmd_vel:=/cmd_vel_raw` 改名，限速閥夾成 ≤0.15 m/s、≤0.8 rad/s 再送 `/cmd_vel`；0.5 秒沒輸入就送零。上車前用上限 0 驗證過（車不動）。
- 寫了 `scan_peek.py`：用 `angle_min + angle_increment × i` 印出 8 個方向的距離。
- VNC 一開始連不上，原因是**前面開的好幾個 vncviewer 沒有關乾淨，一起搶同一條連線**（`readTLS -110`）。改用 `Stop-Process` 全部關掉，再用環境變數 `VNC_USERNAME`／`VNC_PASSWORD` 直接登入。
- tmux 四格：①光達程式、②限速閥、③檢查與調參數、④手把；格子標題改用 `@label`，這樣才不會被容器 shell 蓋掉。

### 七步演練結果

1. **/scan**：360 點、angle_min -180°、每格 1°、0° 是車頭（左正右負）。
2. **安全裝置**：限速閥加上 joy_node＋yahboom_joy（`xspeed_limit 0.30`、`angular_speed_limit 3.2`、雲台話題改名成 `servo_s1_off`）。
3. **警衛**：使用者確認車頭會轉向紙箱，靠到 30 cm 內蜂鳴器會響；官方 PID 要求 0.81～1.33 rad/s，被夾成 0.80。
4. **避障**（`linear 0.15`、`angular 0.8`）：約 610 次判斷，直走 430（70%）、左轉明顯比右轉多。
5. **調參數**：先用 `Switch:=true`（暫停）啟動，`ros2 param set ResponseDist 0.55→0.3`，再 `Switch false` 開跑。直走比例 70%→82%，「左有→右轉」從 13 次變 0 次。
6. **跟隨**：限速閥出手 52 次，官方要求最高 0.65 m/s、**7.5 rad/s**（上限的 4 倍、9 倍）。
7. **巡邏**：bringup 後 TF 在 (0,0,0)，patrol `Length 0.5`。**第一段沒有停，distance 一路印到 4.2 m**，使用者喊停，Ctrl+C 加上連送零速度 4 秒。停車後 TF 在 (-1.29, 3.15)，/odom 18 Hz 正常 → 不是里程計壞掉，懷疑 `advancing()` 的 `abs(error) < 0.05` 沒有觸發（原因待查）。

### 插曲：雲台

- 鏡頭偏右。S1 送 10、20 都不動，手也轉不動（舵機有出力）；`/beep` 有響，代表 ESP32 收得到指令。改依序送 0、-10、-20、-30，送完 -30 後使用者確認朝向正前方 → 先記為「**S1 = -30 是正前方**」。是哪一個數字讓它動的沒有確認。

### 蜂鳴器長叫

- patrol 的 `obstacles` 分支會送 `/beep data=1`，程式被關掉後沒有人送 0。補送 `/beep 0` 後使用者確認停了，**不是低電量**（當時 6.9 V）。

### 收尾與發布

- 電池 81 → 72 → 70 → 69（6.9 V）。避障時已到 7.0 V，使用者選擇硬撐做完。
- Pi 正常關機（`sudo shutdown -h now`），使用者關總開關充電。
- 影片：原始 63 分鐘，用 freezedetect 偵測「沒有語音、畫面靜止超過 60 秒」的空檔，壓縮 10 段 → 48 分鐘，加片頭卡和 12 個章節。「送 30 度」的報數其實沒送出，換成 0.1 秒靜音。
- 上傳（`yt_upload_drills.py`，manifest 在 `~/Videos/pi5-drill/w2-work/`），用 API 確認是 private。
- 網站 `site/links.json` 加連結 → build → `git subtree push`，curl 確認線上有新影片 id。
- 書目總表 mermaid-viewer `books.json` 901「逐步演練（語音＋實錄）」9→10（commit a8a7770），用 gh api 確認。
- 路線圖第 7 場打勾，另外加了三條規則：限速閥、S1=-30、巡邏待查。
- skill `pi5-live-drill` 的 `references/pitfalls.md` 補了 11 列新坑（VNC 環境變數登入、多個 viewer 搶連線、tmux @label、ffmpeg `-/filter_complex`、tmux 捲動緩衝 2000 行等）。

## 關鍵決定

- **官方光達／PID 程式一律經過限速閥**，並用 `Switch:=true` 暫停狀態啟動，等使用者準備好再 `param set Switch false` 開跑（patrol 相反：true 才走）。
- 電池到 7.0 V 時讓使用者選擇；這次選硬撐，6.9 V 收尾。
- 本場在 yahboom repo 寫 session summary（延續 session2～4），不寫在 hp1。

## 技術筆記

- `laser_Warning`、`laser_Avoidance`、`laser_Tracker` 的 Switch 在車上映像裡確定是「true＝暫停」，跟原始碼一致；patrol 是「true＝開始」。
- 巡邏節點名稱 `/YahboomCarPatrol`，參數 `Linear`、`Angular`、`Length`、`Switch`、`Command`（預設 Square）。
- `tf2_echo odom base_footprint` 可以直接確認 bringup 的 TF 有沒有出來。
- 新版 ffmpeg 已經移除 `-filter_complex_script`，要改用 `-/filter_complex <檔>`。
- Git Bash 呼叫 ffmpeg 一定要用 `cygpath -w` 轉路徑（這次又踩了一次）。

## 產出檔案

| 檔案 | 內容 |
| --- | --- |
| `drill/live/20261029-m4-lidar/plan.md` | 步驟、問題、結果、插話紀錄、影片連結 |
| `drill/live/20261029-m4-lidar/cmd_vel_limiter.py` | 限速閥節點（含 `--selftest`） |
| `drill/live/20261029-m4-lidar/scan_peek.py` | 印 8 個方向距離（含 `--selftest`） |
| `drill/live/20261029-m4-lidar/01～17-*.txt/.mp3`、`servo/` | 語音稿與 mp3 |
| `drill/live/20261029-m4-lidar/shots/` | 12 張截圖 |
| `drill/live/20261029-m4-lidar/video_plan.json`、`tts_log.tsv` | 剪輯計畫與語音時間表 |
| `drill/DRILL-ROADMAP.md` | 第 7 場打勾、加 3 條規則 |
| `site/links.json`、`site/index.html` | M4 影片連結 |
| `~/.claude/skills/pi5-live-drill/references/pitfalls.md` | 補 11 列 |
| mermaid-viewer `books.json` | 901 逐步演練 count 10 |
| `~/Videos/pi5-drill/pi5drill-m4-lidar-final.mp4`（不進 git） | 成品影片 |

Commits（yahboom repo）：M4 演練資料夾、`b83dd07`（影片連結＋網站＋路線圖）、`9f87672`（蜂鳴器原因）；gh-pages `553a9c1`；mermaid-viewer `a8a7770`。

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] 車子充飽電後，跑路線圖第 8 場：「拍五逐步演練：M5 寫自己的第一個控制節點」。把限速閥和「停車要關蜂鳴器」的教訓直接寫進自己的節點，先在 WSL 模擬再上實車。
- [ ] 查 M4 巡邏走過頭的原因：在 WSL 模擬車上跑 `patrol`（Square、Length 0.5），看 `advancing()` 的 `abs(error) < LineTolerance` 為什麼沒觸發；查清楚後補做實車 0.5 m 正方形（可以說「拍五逐步演練：M4 巡邏補做」）。
- [ ] 檢查雲台 S1：送 10、20 不動、手轉不動的原因（線、舵機、零點）。依 10/28 S2 事故的經驗，只用小角度。

### 進行中（需接續）

- M4 講義（`lessons/M4.md`）還沒依實車結果改寫：Switch 語意已實車確認、官方 PID 沒有上限要加警告、patrol 讀 /scan 確實被註解掉、巡邏走過頭待查。
- 路線圖已完成 7/14 場。

### 注意事項

- 每場開始前讀官方程式碼，確認速度上限和 Switch 語意；會動的官方程式一律走限速閥（`drill/live/20261029-m4-lidar/cmd_vel_limiter.py`，要先 SFTP 再 `docker cp` 進容器 `/root/`）。
- 雲台目前 S1 = -30 是正前方（需重測：S1 送 10、20 是否真的無效，用 ±5° 小步驟、搭配 `/beep` 確認指令有到）；手把節點一定要 `-r servo_s1:=servo_s1_off -r servo_s2:=servo_s2_off`。
- 一場約 1 小時，電池約掉 1.2 V（8.1→6.9）；第 4 場以後要充飽再開始。
- 開 VNC 前先 `Get-Process vncviewer | Stop-Process -Force`，再用環境變數登入。
