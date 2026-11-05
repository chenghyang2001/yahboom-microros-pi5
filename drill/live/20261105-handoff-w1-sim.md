# 交接：W1 模擬版做到步驟 4、W2 未開始（2026-11-05，HP1）

手上沒有實車，W1 改用 WSL 模擬車 `microros_pi5_sim` 重做。**不錄影、不上傳**（使用者指定）。
計畫檔：`drill/live/20261105-w1-sim-tour/plan.md`；語音稿與 mp3 同目錄，截圖在 `shots/`。

## 進度

| 步驟 | 狀態 | 重點結果 |
| --- | --- | --- |
| 0 開機（sim.launch.xml） | ✅ | Gazebo 小屋＋RViz 光達紅點 |
| 1 大腦 | ✅ | x86_64、Ubuntu 24.04.5、8 核、15 GB、jazzy、Domain 0（真車 aarch64／4 核／8 GB／humble／20） |
| 2 翻譯官 | ✅ | `/hw_bridge`（ros_gz_bridge）；`[` Gazebo→ROS、`]` ROS→Gazebo |
| 3 零件在哪 | ✅ | 光達 z 0.079、IMU z 0.032、相機 x 0.117 z 0.042；TF 樹 `shots/06-step3-tftree.png` |
| 4 小腦話題介面 | ✅（使用者要求重念結果，重念中暫停） | 收 /cmd_vel /gimbal/*；送 /scan /imu /odom /tf /joint_states /clock；rqt_graph 節點加話題模式 |
| **5 資料是活的** | ⏭ **下一步** | `ros2 topic hz /scan`（預期 10 Hz）、`/imu`（50 Hz）、`echo --once /imu --field linear_acceleration`（z≈9.8） |
| 6 總結 | 待做 | 模擬與真車對照（plan.md 下方表格） |

之後：W2 ROS 2 最小必學（turtlesim，7 步），計畫檔 `drill/live/20261028-w2-ros2-basics/plan.md`，同樣不錄影。

## 接續前先確認畫面（暫停時都還開著，若電腦重開過就要重建）

HP1 螢幕排列是 **2｜1｜3**（螢幕 2 在左、主螢幕 1 在中、螢幕 3 在右）：

- 螢幕 2：Windows Terminal「W1-模擬演練」最大化，WSL tmux session `w1`：① 0.0 launch、② 0.1 觀察（ros2 daemon、rqt_graph 從這格開）、③ 0.2 指令
- 螢幕 3：Gazebo（左）、rqt_graph（蓋在 Gazebo 上）、RViz（右）

重建：

```bash
# WSL 保持開著
powershell -NoProfile -Command "Start-Process wsl.exe -WindowStyle Hidden -ArgumentList '-d','Ubuntu-24.04','--','sleep','infinity'"
# tmux 三格 + 每格 source ~/.w1env.sh（Jazzy＋yahboom_ws＋CycloneDDS＋LOCALHOST，檔案已在 WSL 家目錄）
# ① 格：export QT_QPA_PLATFORM=xcb; ros2 launch microros_pi5_sim sim.launch.xml
# ② 格：ros2 daemon start
```

## 這次踩到的坑

| 狀況 | 原因 | 解法 |
| --- | --- | --- |
| Gazebo、RViz、rqt_graph 開在主螢幕 | WSLg 新視窗預設出現在主螢幕；守門員背景程式沒設 DISPLAY；rqt_gui.ini 預寫位置沒生效 | `wsl -- bash -c` 內先 `export DISPLAY=:0`；`xdotool search` 抓不到時改用 `xwininfo -root -tree` 取視窗代號再 `xdotool windowmove`。螢幕 3 = WSLg X 3840～5760（y+116） |
| `ros2 node list` 卡住 | daemon 從外部 `wsl -- bash -c` 啟動，連線結束就被關掉 | 在 tmux 格子裡 `ros2 daemon start`，跟著 tmux 一直活著 |
| rqt_graph 圖太小 | 預設 Nodes only＋視窗被縮放後沒重新 fit | 選 Nodes/Topics (active)，再按 fit 鈕（用 PowerShell SetCursorPos＋mouse_event 點） |
| 截圖函式沒存到檔 | bash 函式內 PowerShell 路徑引號 | 直接一次 powershell 指令截多張 |
