# Yahboom MicroROS-Pi5 × ROS 2 自學教材

給「手上只有一台 Yahboom MicroROS-Pi5 機器人車、完全沒碰過 ROS」的人。從官方文件（155 份 PDF）、官方影片（56 支）和官方原始碼整理成四級、20 個單元的繁體中文教材，每段都有中文語音，並附電腦模擬套件，車子到手前就能先練。

- **互動教材網站**：https://chenghyang2001.github.io/yahboom-microros-pi5/ （原始檔 `site/`）
- **NotebookLM 產物**（語音導覽、影片摘要、簡報、資訊圖表、心智圖）：https://187-127-109-145.sslip.io/yahboom-microros-pi5/
- **YouTube（私人）**：20 單元有聲投影片 https://www.youtube.com/playlist?list=PLL8HRt5nNsd4 ；電腦模擬示範 https://www.youtube.com/playlist?list=PLR7jGHAzkwiY
- **學習規劃**：[LEARNING-PLAN.md](LEARNING-PLAN.md)
- **講義原稿**：`lessons/*.md`（格式見 `lessons/LESSON-FORMAT.md`）
- **研究筆記**：`research/notes/`（A 入門與控制、B 視覺、C1 光達、C2 系統、D ROS 2 基礎、E ESP32/micro-ROS、F 原始碼分析）
- **藍牙耳機語音指令**：`voice/`（部署與操作見 [voice/DEPLOY.md](voice/DEPLOY.md)，測試報告見 `voice/reports/`）
- **電腦模擬套件**：`sim/microros_pi5_sim/`（ROS 2 Jazzy + Gazebo Harmonic，官方 3D 模型＋光達、相機、IMU、四輪差速）

## 四級課程

| 級別 | 單元 |
| --- | --- |
| 0 暖身（不用車） | W1 認識這台車、W2 ROS 2 最小必學、W3 Linux／SSH／Docker、W4 URDF／RViz／TF |
| 1 初級 | B1 組裝、B2 連線、B3 agent 與容器、B4 遙控、B5 讀懂話題、B6 校準 |
| 2 中級 | M1 OpenCV、M2 MediaPipe、M3 視覺互動、M4 光達應用、M5 自己的控制節點 |
| 3 高級 | A1 SLAM、A2 Nav2、A3 多機、A4 ESP32 韌體、A5 電腦與車互通 |

## 電腦模擬（WSL Ubuntu 24.04 + ROS 2 Jazzy）

```bash
mkdir -p ~/yahboom_ws/src && cp -r sim/microros_pi5_sim ~/yahboom_ws/src/
cd ~/yahboom_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch microros_pi5_sim display.launch.xml          # 只看模型（RViz＋關節滑桿）
ros2 launch microros_pi5_sim sim.launch.xml              # Gazebo 小屋＋車（camera:=true 開相機）
ros2 launch microros_pi5_sim slam.launch.xml             # 建圖（另開終端）
ros2 launch microros_pi5_sim nav2.launch.xml             # 導航（另開終端）
```

`sim/scripts/route_driver.py` 是建圖示範用的路線行駛程式（依 /odom 走預設路線）。

模擬話題和真車對照：`/cmd_vel`（收）、`/scan`、`/odom`、`/imu`、`/tf`、`/joint_states`、`/camera/image_raw`；雲台用 `/gimbal/pan`、`/gimbal/tilt`（弧度，真車是 `/servo_s1`、`/servo_s2` 角度）。

## 重建網站與影片

```bash
PYTHONUTF8=1 python tools/build_site.py            # 解析講義、產生語音、輸出 site/
PYTHONUTF8=1 python tools/make_lesson_videos.py    # 每單元一支有聲投影片影片 → videos-out/
```

## 資料來源

- 官方 GitHub：YahboomTechnology/MicroROS-Car-Pi5（文件 PDF；本 repo 不收錄原檔）
- 官方影片播放清單：PL6KtTPU_PfxpQAITcWXgn978DXj3mskCJ
- 官方原始碼：Google Drive「18. Summary of program source code」（本 repo 不收錄）

官方文件與原始碼版權屬 Yahboom；本 repo 只收錄自行撰寫的筆記、講義與模擬套件。
