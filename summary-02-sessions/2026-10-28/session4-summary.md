# Session 4 摘要（2026-10-28 14:30～16:50）

路線圖第 3～5 場實車演練：B5 讀懂車的話題、B4 遙控、B6 狀態估測與校準。三場都上傳影片、更新網站／播放清單／書目總表、依實車結果修正講義。期間發生雲台 S2 扯斷相機線事故，並確立雲台與小場地的安全規則。最後 Pi 正常關機充電。

## 完成事項

### 演練與影片（YouTube 私人，播放清單「Yahboom MicroROS-Pi5 逐步演練」PLLyok0IrjeqE，累計 8 支）

| 場次 | 演練 | 影片 | 長度 | 資料夾 |
| --- | --- | --- | --- | --- |
| 第 3 場 | B5 讀懂車的話題 | <https://youtu.be/b-A144Ayd7o> | 30:14 | `drill/live/20261028-b5-car-topics/` |
| 第 4 場 | B4 遙控：鍵盤、手把、App | <https://youtu.be/kSFRabO9FCE> | 25:37 | `drill/live/20261028-b4-remote-control/` |
| 第 5 場 | B6 狀態估測與校準 | <https://youtu.be/2VVCQaLF4ME> | 23:51 | `drill/live/20261028-b6-calibration/` |

每場都：`site/links.json` 加連結 → `build_site.py` → `git subtree push --prefix site origin gh-pages` → curl 驗證；mermaid-viewer `books.json` 901「逐步演練（語音＋實錄）」count 6→7→8；`drill/DRILL-ROADMAP.md` 打勾（已完成 5/14）。

### 依實車結果修正講義

- `lessons/B5.md`：停送 `/cmd_vel` 後車子**不會自己停**（Ctrl-C 後 3 秒 z 仍約 0.5 rad/s，送零才停）；`/beep data:100` 短嗶自停；S2 雲台事故警告；光達 0.12～8 m、360 點；/scan 12.5 Hz、/imu 20.2 Hz。
- `lessons/B4.md`：開機不會自動啟動手把；`yahboom_joy` 啟動送 S2=-60 → 用 remap 改名；手把速度＝搖桿×上限×檔位（預設 1/3、1/4），上限 0.1 推不動；App 只開 rosbridge 即可連線，輪盤無限速（實測 0.73 m/s）。
- `lessons/B6.md`：IMU 濾波是 complementary（非 madgwick）；線速度校準車子**倒退**、捲尺 70 cm／TF 70.4 cm，係數應約 1.05（原廠 1.5）；角速度實轉約 370°，係數應約 0.77（原廠 0.75）。

## 關鍵決定與規則

- **雲台 S2 禁止用指令動**：使用者先要求「小角度各動一次」，送 S2 -10 仍大幅上仰扯斷相機線（dmesg `usb 1-1: USB disconnect`）、送 0 不回；依使用者指示送 S2 -45，使用者插回線後 lsusb／`/dev/video0` 恢復。之後只動 S1 ±10。已寫入記憶 `gimbal-small-angle.md` 與路線圖安全規則。
- **場地限制要納入速度與時間**：使用者場地只有 1×1 公尺 → 鍵盤降到 0.106 m/s、手把實際約 0.10 m/s、App 只輕點；每步以原地轉為主。
- **速度不是越小越安全**：手把上限 0.1 × 檔位 1/3 = 0.033 m/s 馬達推不動，改 0.30／3.2 才正常。
- **看門狗**：手把（>0.11 m/s 或 >0.85 rad/s）與 App（>0.25 m/s 或 >1.5 rad/s）都在背景每秒檢查，超速就關節點並送零；App 那次確實觸發（0.73 m/s）。使用者接受結果、不再測。
- **校準程式**：不開 rqt_reconfigure，用 `--ros-args -p speed:=...` 降速、`ros2 param set /calibrate_* start_test true` 啟動；加 20／25 秒逾時強制停。
- **手機操作**：使用者要求用 adb 幫忙填 App 的 IP、選 ROS2、按連接；手機鎖定時不代解鎖，請使用者解鎖。
- **私密影像不進 repo**：B5 確認相機時抓的畫面拍到室內與人，移到 session 專屬 scratchpad（session 結束即隨暫存目錄清除），Pi 上的 `/tmp/camtest.jpg` 已刪，未 commit（repo 公開）。

## 關鍵技術筆記

- 上電：Pi IP 維持 `10.169.179.1`；重開 VNC 出現「Unknown encoding」是手機上新舊 nc 轉接重複，清掉重開即可。清理時誤對 7896 轉接送 kill（未生效、無影響）→ 以後只動 8022／5900。
- tmux 送指令改用 base64 傳輸的 `psend.sh`（避免引號跳脫）；容器格用 `docker exec` 進開機自動開的容器。
- B5：手推 10 cm → `/odom_raw` x=0.087；轉圈 Ctrl-C 後多轉約 5 秒，總約 605°。
- B4：鍵盤 x×6、c×3 → 0.106／0.729；遠端送鍵每方向約 2.3 秒；`ros2 topic echo` 的畫面歷史會被零速洗掉，App 那次改用 `tee /tmp/appcmd.log` 存檔分析。
- B6：`calibrate_linear` 用 `copysign(speed, distance−1.0)` → 起點倒退；`calibrate_angular` 程式自己累加 478°×0.75=358.5° 判定完成，但實轉約 370°、TF 約 385°（說明稿預測「多轉 120°」是錯的，結果稿更正）。
- 電池：14:30 開機 8.1 V → 16:45 6.8 V（三場約 2 小時）。

## 產出檔案

本 session 共 37 個 commit（`49da167..44f9a9a`），關鍵：`97e72e7` B5 講義、`9b4cabe` B5 影片、`14e8e2c` B4 1×1 調整、`055412f` B4 講義、`b15be06` B4 影片、`a64f9b1` B6 講義、`44f9a9a` B6 影片；mermaid-viewer `e05baaa`／`551894a`／`e49ccdc`。

| 檔案 | 說明 |
| --- | --- |
| `drill/live/20261028-b5-car-topics/` | 語音稿 01～13、shots/、plan、video_plan、chapters |
| `drill/live/20261028-b4-remote-control/` | 01～09、shots/、plan（含 1×1 調整與結果） |
| `drill/live/20261028-b6-calibration/` | 01～09、shots/、plan |
| `lessons/B5.md`、`B4.md`、`B6.md` | 實車驗證結果 |
| `drill/DRILL-ROADMAP.md` | 第 3～5 場打勾、雲台安全規則改為 S2 禁動 |
| `site/links.json`、`site/index.html` | 新增 3 筆影片 |
| `~/.claude/projects/C--Users-USER-workspace-yahboom-microros-pi5/memory/gimbal-small-angle.md` | 雲台規則（新） |
| `chenghyang2001/mermaid-viewer` 的 `books.json`（本機暫存 clone 在 session scratchpad） | 901 count 8 |
| `~/Videos/pi5-drill/pi5-b5/b4/b6-*.mp4`（不進 git） | 成品影片 |

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] **路線圖第 6 場 M1「OpenCV 與影像話題」**：車子充飽電後說「拍五逐步演練：M1」。先跑上電檢查（第 2 步看 `ip neigh` 實際 IP）；準備一張 QR code（手機螢幕也可）。車子不動，但會用相機——**不要動雲台 S2**。
- [ ] 每場收尾照固定流程：剪片 → manifest 上傳 → links.json＋subtree push → books.json 901 count+1 → roadmap 打勾 → 講義寫回實車結果。

### 進行中（需接續）

- 路線圖 14 場已完成 5 場（W1、W3＋B2、B5、B4、B6）；剩 M1、M4、M5、M2、M3、A1、A2、A5、A4。
- 雲台 S2 的數值與實際角度對應不明，尚未研究（研究前要先拆相機線、使用者在場）。
- `drill/NETWORK.md` 與專案 `CLAUDE.md` 的實車架構圖仍寫舊 IP 10.57.201.1（實測已是 10.169.179.1，應改成「以 `ip neigh` 實測為準」）；Pi 上 14 個停止的舊容器、`ros-humble:4.1.0` 舊映像未清（要先問使用者）。

### 注意事項

- Pi 已於 16:49 `sudo shutdown -h now` 正常關機，使用者負責看綠燈、關總開關、充電；下次從上電檢查開始。
- 使用者的場地目前只有 1×1 公尺（B6 時另備 2 公尺空地）；會跑的演練（M4、M5、M3、A1、A2）開始前要先問場地大小。
- M4／M5 光達避障、A1／A2 導航都會讓車自己跑，速度上限照 0.15 m/s／0.8 rad/s，並沿用背景看門狗。
- App 輪盤無限速，小場地不要讓使用者用 App 開車。
