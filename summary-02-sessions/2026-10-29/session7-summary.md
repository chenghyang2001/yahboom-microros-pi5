# Session 7：M3 視覺互動實車演練、A1 SLAM 第一次（低電量中斷）

- 日期：2026-10-29（約 14:20～17:10）
- 機器：家用機 DESKTOP-6LST1BR

## 完成事項

### 演練流程改變（使用者決定）

- **車子充電時先備料、備好才開車**：讀原始碼、寫 plan.md、寫安全程式、預先產生語音 mp3，全部做完才請使用者開機；用車部分結束就讓 Pi 關機。記成記憶 `drill-prep-before-power.md`。
- 查 Yahboom 官網〈5. About charging〉確認：**充電時必須關總開關，不可邊充邊用**（<https://www.yahboom.net/study/MicroROS-Pi5/10612>）。

### M3 視覺互動實車逐步演練（路線圖第 10 場，`drill/live/20261029-m3-visual/`）

- 讀原始碼發現四支官方程式（colorTracker、face_fllow、follow_line、HandCtrl）一啟動都送 S2（-50／-60／-75／-45）。新寫 **`servo_guard.py`**（code-writer 快速模式）：訂閱 `/servo_s*_raw`，S2 一律攔下，S1 = -30 ± 10、每筆最多 3 度。全場攔下 S2 指令 **276 次**，相機線無損。
- 顏色追蹤：框選紅色後遮罩整片白，因為**紅色橫跨 HSV 色環 0／180 接縫**，ROI 算出 H 0～184。改法：寫 `colorHSV.text` 成 `160, 90, 40, 180, 255, 255` 再按 `i`（改 ROS 參數無效）。另觀察到**控制器飽和**（要求到 ±90，實際只轉 ±10）。
- 人臉追蹤：9 張截圖 3 張有框（只認正臉）；S2 要求 +20 被攔。
- 巡線：⏸ 跳過、以後補做（沒有色膠帶；S2 不能低頭只看得到 30 cm 外地面）。
- 手勢控車：手勢都認得（食指 26、比二 15），但原地轉不動。原因：HandCtrl 每 0.7 秒才送一筆，限速閥看門狗 0.5 秒就送零。對照實驗 `turntest.py`：連續送平均 0.52 rad/s、斷續送 0.02。`cmd_vel_limiter.py` 新增參數 `watchdog_timeout`，用 1.0 後斷續送 0.27 rad/s，使用者確認左右轉 OK。
- 講義 `lessons/M3.md` 寫回 5 處實測結果；commit `ad3f870`。
- M3 影片剪輯：`build.py`（scratchpad，已遺失）做到 31 分鐘版本、相機視窗 5 段打碼；第一次輸出失敗、第二次 exit 0，**輸出檔 `~/Videos/pi5-drill/pi5-m3-visual-drill.mp4` 尚未驗證、尚未上傳**。

### A1 SLAM 建圖第一次（`drill/live/20261029-a1-slam/`）

- 開機後 6 分鐘熱點找不到 Pi，使用者關總開關重開後連上；時鐘差 986 秒 → 按 ESP32 Reset 後 0。
- 第 1～4 步完成：時鐘差 0、/scan 12.5 Hz、bringup、RViz、Gmapping 出圖（Global Status 轉 Ok、Scan Matching 341）。
- 第 5 步開手把後**電池掉到 68 觸發 ESP32 低電量蜂鳴**，同時手機 USB 斷線，請使用者直接關總開關。**地圖未存**。commit `8c02ee9`。

### 其他

- 書目總表 901 加入「逐步演練（精華版）」PLBB8VkgBCQ7M（10 支），mermaid-viewer commit `b53ca06`、`a6b8d5c`（第二筆修回 1 格縮排）。
- 把精華版播放清單網址寄到使用者 Gmail。

## 關鍵技術筆記

- `ycar.py ros '<heredoc>'` 不會建檔；要在車上跑 Python 用 `ycar.py rospy <本機檔>`。
- 在 Git Bash 給 Windows Python／edge-tts 的路徑要 `cygpath -w`，不然 `/c/...` 會 FileNotFoundError。
- `timeout N cmd | tail` 會把 tail 一起殺掉只剩 Terminated；hz 不要接 tail。
- books.json 是 1 格縮排，Edit 後格式化 hook 會改成 2 格整檔 diff，要 `json.dumps(indent=1)` 寫回。
- tmux kill-session 不會結束容器內的程序（servo_guard 留下孤兒），要 `docker exec ... pkill -TERM -f '^python3 servo_guard.py'`。
- edge-tts 偶爾連線逾時：tts_play 沒出聲，要刪掉 tts_log 那筆再重播。

## 產出檔案

| 檔案 | 說明 |
| --- | --- |
| `drill/live/20261029-m3-visual/servo_guard.py` | 雲台守門員（S2 攔下、S1 限幅） |
| `drill/live/20261029-m3-visual/cmd_vel_limiter.py` | 加 `watchdog_timeout` 參數 |
| `drill/live/20261029-m3-visual/turntest.py` | 連續 vs 斷續送轉彎對照實驗 |
| `drill/live/20261029-m3-visual/plan.md`、`01～15-*.txt/mp3`、`tts_log.tsv`、`video_plan.json` | M3 演練紀錄 |
| `drill/live/20261029-a1-slam/plan.md`、`01～12-*.txt/mp3` | A1 規劃、語音、第一次結果 |
| `lessons/M3.md` | 寫回實車結果 |
| `~/Videos/pi5-drill/pi5drill-m3-visual-20261029-151001.mp4`、`pi5drill-a1-slam-20261029-161337.mp4` | 原始錄影（不進 git） |
| `~/Videos/pi5-drill/pi5-m3-visual-drill.mp4` | M3 剪輯版（待驗證） |
| mermaid-viewer `books.json` | 901 加入精華版播放清單（b53ca06、a6b8d5c） |
| memory `drill-prep-before-power.md`、`drill-roadmap.md` | 新增／更新 |

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] **M3 完整版**：驗證 `pi5-m3-visual-drill.mp4`（ffprobe 長度約 1869 秒、抽格看打碼），加進 `~/Videos/pi5-drill/w2-work/manifest.json` 上傳私人播放清單 PLLyok0IrjeqE；網站 links.json、DRILL-ROADMAP 已完成表、books.json 901「逐步演練（語音＋實錄）」count 12→13。
- [ ] **補做精華版**：M5、M2、M3 還沒有精華版（播放清單 PLBB8VkgBCQ7M 目前 10 支：boot、W1～W4、B4、B5、B6、M1、M4）。照 `drill/live/*/digest/` 的既有做法做（M3 精華版要等完整版確認後才做），接在第 10 支後面，再更新網站 links.json 與 books.json 的精華版 count。
- [ ] **A1 重做**：電池充飽（開始時 ≥ 75）再從頭做，補第 5 步繞場、第 6 步存地圖＋`docker cp` 到主機 `~/maps`。

### 進行中（需接續）

- M3 影片：剪輯版已輸出（第二次 exit 0），未驗證、未上傳；YouTube 授權 hook 顯示 EXPIRED（原因是 getaddrinfo 失敗，可能只是當時網路），上傳前先 `--dry-run` 再正式跑確認。
- A1：plan.md、語音稿都可重用；第一次的錄影 `pi5drill-a1-slam-20261029-161337.mp4` 可留著或併入重做影片。
- M3 巡線：待準備色膠帶後補做；鏡頭不能低頭，線要從車頭 30 cm 外開始。

### 注意事項

- 演練要「先備料、再開車」；用車結束就讓 Pi `sudo shutdown -h now`，使用者再關總開關充電。
- A1 會開車繞場，電池 72 開始撐不到繞場；低於 70 ESP32 會一直叫，軟體關不掉，只能斷電。
- 官方視覺程式一律要經 `servo_guard.py`（雲台改名）＋`cmd_vel_limiter.py`（`/cmd_vel` 改名）；HandCtrl 這類斷續送的程式要 `-p watchdog_timeout:=1.0`。
- scratchpad（剪輯 build.py、vncmouse.ps1）已隨工作階段重連失效，需要時重寫。
