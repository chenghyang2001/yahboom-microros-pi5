# A1 實車逐步演練：SLAM 建圖（Gmapping）

- 日期：2026-10-29（路線圖第 11 場）
- 做法：車子充電時先把規劃、語音備好，備好才開車；用車部分做完就關機。
- 車子：使用者用手把遙控繞房間。手把 `yahboom_joy` 限速 0.10 m/s、0.8 rad/s，雲台話題改名（它一啟動會送 S2=-60）。
- 開始前：ESP32 Reset 讓時鐘對齊（POWER-ON-CHECK 第 10 步），時鐘差要在幾秒以內，否則 Gmapping 會把 /scan 當過期資料丟掉。

## 讀原始碼確認

| 檔案 | 內容 | 影響 |
| --- | --- | --- |
| `yahboomcar_bringup_launch.py` | IMU 濾波、EKF（robot_localization）、base_link→imu_frame、URDF 描述 | 不動雲台、不送速度 |
| `map_gmapping_launch.py` | `slam_gmapping` ＋ base_link→laser_frame 靜態 TF | 不動雲台 |
| `display_launch.py`（yahboomcar_nav） | RViz 載入 `rviz/view.rviz` | 在 VNC 桌面開視窗 |
| `save_map_launch.py` | `nav2_map_server map_saver_cli -f <map_path>`，預設 `src/yahboomcar_nav/maps/yahboom_map` | 用 `map_path:=` 存成 `living_room` |
| `yahboom_joy` | 啟動送 S2=-60、Y/A 鍵動 S2 | `-r servo_s1:=servo_s1_off -r servo_s2:=servo_s2_off`，限速參數 |

## tmux 格子（session `drill`，四格都 docker exec 進 ROS 2 容器）

| 格子 | 用途 |
| --- | --- |
| ① 左上 | 底層 bringup |
| ② 右上 | RViz／檢查 |
| ③ 左下 | Gmapping 建圖、存地圖 |
| ④ 右下 | 手把 |

## 步驟

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 三樣材料 | ② | 時鐘差；`ros2 topic hz /scan`（5 秒）；`ros2 topic echo --once /odom_raw --field pose.pose.position` | 時鐘差 ≤ 幾秒、/scan 約 12 Hz、里程計有位置 |
| 2 底層 | ① ② | ①`ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py`；②`ros2 run tf2_ros tf2_echo odom base_footprint`（看幾行後 Ctrl+C） | EKF 起來，odom → base_footprint 的 TF 開始有值 |
| 3 RViz | ② | `ros2 launch yahboomcar_nav display_launch.py` | VNC 桌面出現 RViz，還沒有地圖（正常） |
| 4 Gmapping | ③ | `ros2 launch yahboomcar_nav map_gmapping_launch.py` | RViz 出現灰色地圖與光達紅點，車子周圍開始有白色空地、黑色牆 |
| 5 繞場建圖 | ④ | `ros2 run joy joy_node &` ＋ `ros2 run yahboomcar_ctrl yahboom_joy --ros-args -p xspeed_limit:=0.10 -p angular_speed_limit:=0.8 -r servo_s1:=servo_s1_off -r servo_s2:=servo_s2_off` | 使用者按 R1 後慢慢開車，沿牆繞一圈；地圖逐漸長出來 |
| 6 存地圖 | ④ ＋主機 | 停手把後、Gmapping 還開著時存：`ros2 launch yahboomcar_nav save_map_launch.py map_path:=/root/yahboomcar_ws/src/yahboomcar_nav/maps/living_room`；`cat living_room.yaml`；主機 `docker cp` 到 `~/maps/` | 產生 .pgm＋.yaml，主機 `~/maps` 有兩個檔 |

## 結果（第一次，2026-10-29 16:13～16:52，中斷）

- 開機後 6 分鐘手機熱點上都找不到 Pi，使用者把總開關關掉再打開才連上。
- 上電檢查 1～9 ✅（48.8 °C、throttled 0x0、電池 72、/scan 12.5 Hz）；第 10 步時鐘差 986 秒，按 ESP32 Reset 後降到 0。
- 第 1 步：時鐘差 0、/scan 12.5 Hz（第一次加 `| tail -3` 被 timeout 一起殺掉，只印 Terminated）、/odom_raw 全為 0。
- 第 2 步：bringup 正常；`tf2_echo odom base_footprint` 平移 0、旋轉 0。joint_state_publisher 印「Waiting for robot_description」不影響。
- 第 3 步：RViz 開啟，Global Status 紅字「Frame [map] does not exist」、一直印 Message Filter dropping（還沒有 map 座標），LaserScan 綠色。
- 第 4 步：Gmapping 開起來後地圖立刻出現，Global Status 變 Ok；Scan Matching Score 約 341。
- 第 5 步：手把程式啟動後（限速 0.10、雲台改名），**電池掉到 68，ESP32 低電量蜂鳴器一直叫**；同時手機 USB 斷線，PC 連不到車。請使用者直接關總開關、充電。**地圖沒有存到。**
- 電池：72 → 71 → 70 → 68，約 40 分鐘掉 4。A1 要開車繞場，**開始前電池至少要 75 以上**。
- 下次重做：充飽後從頭（前 4 步約 10 分鐘），第 5、6 步補完。
