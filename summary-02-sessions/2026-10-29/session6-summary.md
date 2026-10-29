# Session 6：M5 寫自己的第一個控制節點實車演練（第 8 場）

- 日期：2026-10-29（11:20～13:05）
- 機器：家用機 DESKTOP-6LST1BR

## 完成事項

### 演練（skill `pi5-live-drill`，7 步全部完成）

- 上電檢查 1～9 ✅：Pi IP 10.169.179.1、33.4 °C、throttled 0x0、電池 81、/scan 12.5 Hz；時鐘差 3514 秒（本節點不看 header 時間戳，不影響）。
- 前半在 WSL Jazzy＋Gazebo：`ros2 pkg create` 建 `~/m5_ws/src/my_obstacle_stop` → 換入講義三檔 → `colcon build --symlink-install` → 模擬車在 `/odom` x = 1.146 停下（「前方 0.30 m 有障礙」）→ `param set stop_distance 0.2` 後 0.18 m 停、x = 1.266 → 關模擬後持續警告並送零。
- 後半實車：WSL `scp -P 8022 ... pi@127.0.0.1` → `docker cp` 進容器 cc8a72674c13（含 M4 限速閥）→ Humble 容器 build 約 3 秒 → remap `/cmd_vel:=/cmd_vel_raw` 經限速閥。架高：手在前停 5 次、手在後 18 秒不停、Ctrl+C 兩層送零；落地：紙箱前 0.29 m 停，拿開後「淨空 1.81 m」繼續。
- 電池 81 → 72。

### 收尾

- 影片：<https://youtu.be/oy_Q1QeHzf8>（私人，47 分 49 秒；原始 71 分鐘壓縮），播放清單第 11 支。
- `site/links.json` 加連結、重建並 `git subtree push` 部署，curl 確認線上有 oy_Q1QeHzf8。
- `lessons/M5.md` 寫回實測（兩段 info、除錯表 +2 列、setuptools 警告 Humble 也會印、MS200 0° 是車頭）。
- 路線圖第 8 場打勾；mermaid-viewer `books.json` 901 count 10 → 11（commit 1293ca9）。
- pitfalls.md 新增 8 列（wsl -e、tmux 新格送設定、開 WT、Gazebo 視窗與鏡頭、ros2 daemon 卡住、模擬變慢、pkill 自殺、半模擬半實車切換）。

## 重要決定

- **使用者訂下規則**：演練結束後不再問，一律做影片上傳＋登錄網站，現場全部關掉（ROS 2 容器與 agent 不動）。已寫進 skill `pi5-live-drill` SKILL.md Phase 2 與記憶 `drill-wrapup-no-ask.md`。
- 實車上自寫節點也走 M4 限速閥（remap，不改程式）。
- Gazebo 畫面在 WSLg 不可靠，改用 `/odom` 數字與節點 log 當證據。

## 關鍵技術筆記

- `wsl -- bash -c "..."` 會被 wsl.exe 再展開一次；含 `( | $` 的指令要 `wsl -e bash -c`＋base64。
- WSL ros2 daemon 卡住：`pkill -9 -f '^/usr/bin/python3 /opt/ros/jazzy/bin/_ros2_daemon'` 再 `ros2 daemon start`。
- `pkill -f 樣式` 與樣式同在一個 `bash -c` 會殺掉自己（整串無輸出）。
- WSL mirrored 網路可直接連 127.0.0.1:8022（手機轉接的 Pi SSH）。

## 產出檔案

| 檔案 | 說明 |
| --- | --- |
| `drill/live/20261029-m5-first-node/` | plan.md（步驟＋結果＋影片）、01～20 語音稿 txt/mp3、tts_log、shots/ 22 張、my_obstacle_stop/ 講義三檔、video_plan.json |
| `lessons/M5.md`、`site/M5.html`、`site/links.json`、`site/index.html` | 講義寫回、網站 |
| `drill/DRILL-ROADMAP.md` | 第 8 場打勾＋影片 |
| `~/.claude/skills/pi5-live-drill/SKILL.md`、`references/pitfalls.md` | 收尾規則、8 個新坑 |
| `~/Videos/pi5-drill/pi5-m5-first-node-drill.mp4`、`m5-title.png`、`w2-work/manifest.json` | 影片（不進 git） |

Commits：f2cce8a、55780be（專案）；1293ca9（mermaid-viewer）。

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] 下一場演練 M2「MediaPipe：手、臉、姿態」（車不動、使用者入鏡；相機畫面截圖只放 scratchpad，影片要打碼）。
- [ ] 開場照 `drill/POWER-ON-CHECK.md` 上電檢查；Pi IP 用 `ip neigh` 重查（本次 10.169.179.1）。
- [ ] 收尾照新規則：不問，直接影片、上傳、網站、books.json 901 count 11 → 12、路線圖、講義寫回、現場全關。

### 進行中（需接續）

- 無未完成工作。車上容器 cc8a72674c13 裡保留 `/root/my_ws`（重開容器就會消失）。
- M4 巡邏 patrol 第一段沒在 0.5 m 停的原因仍待查（見 M4 plan.md）。

### 注意事項

- 電池這場從 81 掉到 72（約 70 分鐘），下一場開場若 < 75 要先充電。
- WSL 版畫面：WT 用 PowerShell `Start-Process wt.exe --pos`，Gazebo 視窗 `-X -530 -W 500 -H 720`；Gazebo 鏡頭用程式控制無效。
- 雲台 S2 不可用指令動；S1 -30 才是正前方。
