# 實車演練交接：Part 1 完成 → Part 2（車子放地上）

最後更新：2026-10-27（hp1 筆電）

## Part 1 成果（車子架空）

| 項目 | 位置 |
| --- | --- |
| 精華影片 7 支（YouTube 私人） | 播放清單 <https://www.youtube.com/playlist?list=PLQKoi68bwHw4> |
| 指令＋完整輸出網頁簡報 | <https://chenghyang2001.github.io/yahboom-microros-pi5/real-part1.html> （PDF：`site/real-part1.pdf`） |
| 原始錄影 | hp1 `~/Videos/kindle-drill/yb-real-20261027-0445-s2.mp4`、`-s3.mp4`（55 分鐘） |
| 語音紀錄 | hp1 `~/workspace/ros2-turtle-cli-demo/tts_log_ybreal.tsv`（46 句） |
| 教練提示詞 | `drill/COACH-PROMPT-YB.md` |
| 精華版設定 | hp1 `~/workspace/ros2-turtle-cli-demo/highlights/demos.json` 的 `ybreal` |

做完的段落：1 連線與環境（B2＋W3）、2 agent 與容器（B3）、3 讀懂話題（B5）、4 手把遙控（B4）、5 OpenCV（M1）、6 MediaPipe（M2）、7 自己的避障節點（M5）。
跳過：鍵盤遙控（官方 `yahboom_keyboard` 初速超過安全上限）、顏色追蹤 M3（雲台會抬頭扯掉相機線）。

## Part 1 學到的事（Part 2 一定要照做）

1. **相機 USB 線會被雲台扯鬆**：雲台抬頭（`/servo_s2` > 0）兩次把相機線拉掉。症狀：`dmesg` 出現 `error -71`、`/dev/video0` 消失。
   - 演練前先用束線帶在雲台附近固定相機線並留餘長。
   - `/servo_s2` 只用 -45～0 度；**不要用 `ycar.py stopcar`**（它會把雲台送回 0 度），停車改為只送零 `/cmd_vel`。
   - 重插後若主機是高速（480M）且 `/dev/video0` 的裝置編號仍是 81,19，**容器不用重開**就能讀（實測）。
2. **手把**：要先按 **R1** 開啟控速，搖桿才會發 `/cmd_vel`。Y／A 會轉雲台上下，程式沒有限制角度。
3. `ros2 topic pub` 一定要寫話題名；漏了只會報 `message type invalid`，車不動。
4. `/battery`（UInt16）是電壓 × 10：Part 1 期間從 79 降到 74（7.9 V → 7.4 V），低於 70 要準備充電。
5. 背景跑語音轉文字之類吃 CPU 的工作時，不要同時跑 SLAM（Part 0 模擬時 RViz 會卡住）。

## 重新連線步驟（給下一個 session）

前提：車子開機、手機熱點開著（名稱 AnPing，密碼見本機記憶 `phone-hotspot-original`；原始熱點設定要在全部演練完還原）、手機用 USB 接 hp1 且 `adb devices` 看得到 `84bbb261`。

```bash
# 1. 找車子 IP（MAC 開頭 2c:cf:67 是 Raspberry Pi；Part 1 是 10.57.201.1，可能會變）
adb -s 84bbb261 shell ip neigh
# 2. 手機轉接（兩個都要用 Bash 背景執行並保持開著；adb 斷了就要重開）
adb -s 84bbb261 shell "nc -L -p 8022 nc 10.57.201.1 22"      # SSH
adb -s 84bbb261 shell "nc -L -p 5900 nc 10.57.201.1 5900"    # VNC
adb -s 84bbb261 forward tcp:8022 tcp:8022
adb -s 84bbb261 forward tcp:5900 tcp:5900
# 3. 測試（密碼用環境變數，不寫進檔案；Yahboom 預設帳號 pi）
cd ~/workspace/yahboom-microros-pi5/drill
YCAR_PASS=<車子密碼> PYTHONUTF8=1 python ycar.py status
# 4. Pi 桌面改成 1280x720（剛好填滿螢幕 3）
python ycar.py host "export WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000; wlr-randr --output NOOP-1 --custom-mode 1280x720"
# 5. TigerVNC 全螢幕到螢幕 3（帳密用剪貼簿貼，注音輸入法會打亂字）
"C:\Program Files\TigerVNC\vncviewer.exe" -FullScreen=1 -FullScreenMode=Selected -FullScreenSelectedMonitors=1 -RemoteResize=0 127.0.0.1::5900
```

- 視窗擺放（DPI-aware 實際像素）：螢幕 2 = x 2880～4800，教練 `2880,0,960,1040`、車況 `3840,0,960,1040`；螢幕 3 = x -1920～0。
- ffmpeg 錄影用 gdigrab 座標（另一套）：螢幕 2 `-offset_x 1920 -video_size 1920x1080`、螢幕 3 `-offset_x -1280 -video_size 1280x720`。
- 車況儀表板：`python ycar.py rospy monitor.py --timeout 7200`（在 WT 視窗「YB 車況」）。
- 教練視窗：`claude --dangerously-skip-permissions --remote-control "YB 教練"`，環境變數帶 `YCAR_PASS`、`DISABLE_WRITER_QA_HOOK=1`，工作目錄 `drill/`。
- 語音：`bash ~/workspace/ros2-turtle-cli-demo/say.sh '...'`；開錄前把 `tts_log.tsv` 清空，結束後改名保存。
- 精華版：`highlights/make_highlights.py`（demos.json 加新 key）→ `docs` → `yt_upload_drills.py`（一律私人）。

## Part 2 規劃：車子放到地上

需要：約 2 × 3 公尺淨空地面、捲尺、有人在車旁（隨時可抱起車子或按手把 R1 停控速）。教練提示詞草稿：`drill/COACH-PROMPT-YB-PART2.md`。

| 段 | 單元 | 內容 | 官方指令（容器內） |
| --- | --- | --- | --- |
| 1 | 安全與 IMU 初始化 | 車放地上、靜置 5 秒讓陀螺儀初始化；確認停車方法 | — |
| 2 | B6 線速度校準 | 地上貼 1 公尺膠帶，車走 1 公尺量誤差 | `ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py`＋`ros2 run yahboomcar_bringup calibrate_linear` |
| 3 | B6 角速度校準 | 原地轉 360 度量誤差 | `ros2 run yahboomcar_bringup calibrate_angular` |
| 4 | M4 光達避障／跟隨／警衛 | 注意 `Switch=True` 是「暫停」（和文件相反）；先調慢速度 | `ros2 run yahboomcar_laser laser_Avoidance`、`laser_Tracker`、`laser_Warning` |
| 5 | A1 SLAM 建圖 | 用手把慢慢開繞場地；存圖後 `docker cp` 備份到 Pi 主機 | `ros2 launch yahboomcar_nav map_gmapping_launch.py`、`save_map_launch.py` |
| 6 | A2 Nav2 導航 | 載入剛建的地圖，RViz 設初始位置、點目標 | `ros2 launch yahboomcar_nav navigation_dwb_launch.py maps:=...` |
| 7（選） | A5 電腦與車互通 | 筆電改連 AnPing 熱點、WSL mirrored 網路，電腦 RViz 看 /scan | — |

Part 2 前要先確認的事：

- 確認各 launch 檔與參數（`/root/yahboomcar_ws/src/yahboomcar_nav/launch`、`yahboomcar_bringup`）。
- 官方 Nav2 `robot_radius: 0.22` 比車大，必要時改小。
- RViz 要在 Pi 桌面（VNC）開；Pi 5 跑 SLAM＋RViz 可能吃緊，可只開 RViz 必要顯示。
- 全部演練結束後：手機熱點改回原始設定（見記憶 `phone-hotspot-original`）。
