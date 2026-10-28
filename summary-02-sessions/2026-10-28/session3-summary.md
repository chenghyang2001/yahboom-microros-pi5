# Session 3 摘要（2026-10-28 10:00～13:30）

完成 4 場逐步演練並上傳影片（播放清單累計 5 支）：W4（WSL）、開機流程（實車，續完）、W1、W3＋B2（實車）；排出剩下單元的實車演練路線圖；書目總表 901 登錄演練播放清單。最後讓 Pi 正常關機充電。

## 完成事項

### 演練與影片（全部 YouTube 私人，在播放清單「Yahboom MicroROS-Pi5 逐步演練」PLLyok0IrjeqE）

| # | 演練 | 影片 | 長度 | 資料夾 |
| --- | --- | --- | --- | --- |
| 1 | W4 URDF、RViz、TF、Gazebo（WSL，接續上午開場） | <https://youtu.be/6GyK4SovhKE> | 36:44 | `drill/live/20261028-w4-urdf-rviz-tf/` |
| 2 | 開機流程拆解（實車，第 2 段從頭重做） | <https://youtu.be/WSqQgIOrT24> | 26:45 | `drill/live/20261028-boot-sequence/` |
| 3 | W1 認識這台車：實車導覽（路線圖第 1 場） | <https://youtu.be/0TUN2ofL1t4> | 29:33 | `drill/live/20261028-w1-car-tour/` |
| 4 | W3＋B2 Linux、SSH、Docker 與正確關機（第 2 場） | <https://youtu.be/f1iO97zIU9M> | 33:41 | `drill/live/20261028-w3-linux-ssh-docker/` |

（W2 <https://youtu.be/E2xuUzat6B8> 是 Session 2 做的，播放清單共 5 支。）

### 規劃與登錄

- 新增 `drill/DRILL-ROADMAP.md`：剩餘單元 14 場由簡單到困難（W1 → W3＋B2 → B5 → B4 → B6 → M1 → M4 → M5 → M2 → M3 → A1 → A2 → A5 → A4）；不排 B1（實體組裝）、A3（只有一台車）；B3 由開機流程演練完成。已完成 2 場。
- 書目總表（私有 repo `chenghyang2001/mermaid-viewer` 的 `books.json`）901 號新增 drills 項目「逐步演練（語音＋實錄）」count 5，連到播放清單。
- 教材網站 `site/links.json` 新增 W4（本教材影片區）、開機流程實錄版、W1、W3＋B2（實車演練區）；每次都 `build_site.py` + `git subtree push --prefix site origin gh-pages` 並 curl 驗證上線。

### 依實車驗證修正教材

- `lessons/W1.md`：映像實為 `ros-humble:4.1.2`（講義 4.0.3）、`/YB_Car_Node` 有發布 `/battery`（講義漏列）、確認是 `/odom_raw` 不是 `/odom`、熱點模式下沒有 `/rpi5_ip`、光達實測 12.5 Hz（規格 10 Hz）。
- W3 講義「需實車確認」：`docker exec -it <ID> bash` 互動殼直接有 `ros2`（`bash -c` 非互動沒有）。
- `sim/microros_pi5_sim/config/display.rviz`（Height 600、Distance 0.6）、`sim.rviz`（Height 600）調小，讓 RViz 放得進 1280×720 的螢幕 3（已同步到 WSL `~/yahboom_ws`）。
- `drill/POWER-ON-CHECK.md` 實測紀錄：熱點換網段後 Pi IP 變成 `10.169.179.1`。

## 關鍵技術筆記

- **WSL 新節點探索延遲約 60 秒**：W4 每次新開 `ros2 topic pub`／`echo` 都要等十幾秒到一分鐘才互相看到；RViz 座標軸變灰＝TF 過期。對策：pub 一路開著不換、監看到有輸出才截圖。已寫入 skill pitfalls。
- **視窗與 DPI**：win.ps1 用 `SetProcessDpiAwarenessContext(-4)`；WSLg 的 Qt 視窗（RViz、Gazebo）只移位置不改大小，大小改由設定檔控制；Gazebo `~/.gz/sim/8/gui.config` 改了沒生效，已還原。Chrome app 視窗跨螢幕後再 SetWindowPos 一次才會對。
- **PowerShell hashtable 鍵不分大小寫**（`T` 與 `t` 衝突），win.ps1 第一版 `list` 誤當 `move`，把使用者的「hp1-pi5」視窗搬走過一次。
- **gz sim 的 `/odom` 沒填 twist**，停車要用 Gazebo 截圖比對確認。
- **開機流程準備**：`pkill -x lxterminal` 只會停 ROS 2 容器，agent 容器要另外 `docker stop`。
- **ESP32 Reset 後時鐘差歸零**（15083 → 0 秒）；這次手機轉接沒斷。
- **容器 bash 會改 tmux 格子標題**；tmux 3.3a 沒有 `allow-set-title`，用 `unset PROMPT_COMMAND; PS1=...` 擋，`docker exec` 新開的殼仍會改，要手動 `select-pane -T` 改回。
- **TigerVNC 對方斷線時直接關視窗**（不是顯示斷線訊息）。
- **剪輯法**：tts_log 對齊語音；超過 60 秒無語音的空檔留頭 20 秒＋尾 15 秒，另外保留每張截圖前 10 秒到後 3 秒；4 秒 Pillow 片頭；inline python 組 ffmpeg trim/concat＋adelay/amix。
- **上傳**：`~/workspace/ros2-turtle-cli-demo/highlights/yt_upload_drills.py`，manifest 集中在 `~/Videos/pi5-drill/w2-work/manifest.json`（同清單 ≥2 支才建清單，已上傳的會略過）。
- 電池：開機 8.1 V → W3 結束 6.9 V，約 2 小時演練。

## 產出檔案

本 session 共 53 個 commit（`6df29cb..896c9ca`），關鍵：`77bf494` W4 影片、`cf5ff8f` 開機流程影片、`fb88ef5` 路線圖、`91994c3` 修正 W1 講義、`22cc659` W1 影片、`fbe8b39` W3＋B2 影片、`896c9ca` IP 變動紀錄；mermaid-viewer `86db82e`／`117ba85`／`c7955d8`。

| 檔案 | 說明 |
| --- | --- |
| `drill/DRILL-ROADMAP.md` | 14 場實車演練路線圖（已完成表＋排程＋安全規則） |
| `drill/live/20261028-w4-urdf-rviz-tf/` | W4 語音稿 02～12、截圖 shots/、plan、video_plan、chapters |
| `drill/live/20261028-boot-sequence/` | 開機流程 04-resume～12-summary、shots/05～12 |
| `drill/live/20261028-w1-car-tour/` | W1 01～12、shots/ |
| `drill/live/20261028-w3-linux-ssh-docker/` | W3＋B2 01～14、shots/ |
| `lessons/W1.md` | 5 處實車修正 |
| `sim/microros_pi5_sim/config/display.rviz`、`sim.rviz` | 視窗高度、鏡頭距離 |
| `site/links.json`、`site/index.html`、`site/W1.html` | 新增 4 筆影片連結 |
| `drill/POWER-ON-CHECK.md` | IP 變動實測紀錄 |
| `~/.claude/skills/pi5-live-drill/references/pitfalls.md` | 新增 3 條 WSL 坑 |
| mermaid-viewer `books.json` | 901 新增「逐步演練（語音＋實錄）」count 5 |
| `~/Videos/pi5-drill/*.mp4`（不進 git） | 4 支成品影片 |

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] **路線圖第 3 場 B5「讀懂車的話題」**：車子充飽電、放地上周圍淨空 50 公分後，說「拍五逐步演練：B5」。先跑 `drill/POWER-ON-CHECK.md` 上電檢查（第 2 步看 `ip neigh` 實際 IP，可能不是 10.169.179.1），再開 VNC＋tmux。車會原地轉、蜂鳴器、雲台小角度（速度上限 0.15／0.8、`/servo_s2` 只能 -45～0）。
- [ ] 每場做完照固定流程：剪影片 → manifest 加一筆上傳 → `site/links.json` → build＋subtree push → mermaid-viewer `books.json` 901 count+1 → roadmap 打勾。

### 進行中（需接續）

- 路線圖 14 場已完成 2 場（W1、W3＋B2）；另有 W2、W4、開機流程 3 場在路線圖之前完成。
- `drill/NETWORK.md` 仍寫舊 IP 10.57.201.1，尚未更新（POWER-ON-CHECK 已補註）。
- Pi 上有 14 個已停止的舊容器、`ros-humble:4.1.0` 舊映像 13.6 GB，未清（可 `docker container prune`，需先問使用者）。

### 注意事項

- Pi 已於 13:16 `sudo shutdown -h now` 正常關機，使用者已關總開關充電；下次一定從上電檢查開始。
- 網站上舊的開機流程截圖版影片（br1-xZYNp-A）保留，與實錄版並列，使用者沒說要刪。
- 演練時 Chrome 的教材簡報可能全螢幕蓋在螢幕 3，要先移到螢幕 2（3840,0）再叫 VNC 到前面。
- `tts_play.py play` 偶爾 exit 9 沒出聲，重播即可；tts_log 要刪掉失敗那筆再記一次。
