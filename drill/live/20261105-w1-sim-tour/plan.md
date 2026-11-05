# 逐步演練：W1 認識這台車（模擬版，2026-11-05，HP1 WSL）

手上沒有實車，改用 WSL Ubuntu 24.04（ROS 2 Jazzy）裡的模擬車 `microros_pi5_sim` 重做 W1。
**不錄影、不上傳**（使用者指定）。對照：真車版 `drill/live/20261028-w1-car-tour/plan.md`。

畫面：螢幕 2 左半是 Windows Terminal（tmux session `w1`），右半是 RViz；Gazebo 放螢幕 3。
格子：① 模擬車 launch（上方）　② 觀察（左下）　③ 指令（右下）
每格都 `source ~/.w1env.sh`（Jazzy＋yahboom_ws＋CycloneDDS＋LOCALHOST）。

| 步驟 | 主題 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- | --- |
| 0 | 開機（啟動模擬車） | ① | `ros2 launch microros_pi5_sim sim.launch.xml` | Gazebo 小屋＋車；RViz 有車模型與光達紅點 |
| 1 | 大腦 | ③ | `uname -m`、`os-release`、`nproc`、`free -h`、`echo $ROS_DISTRO` | x86_64、Ubuntu 24.04、jazzy；對照真車 Pi 5 aarch64／Debian 12／8 GB／容器內 humble |
| 2 | 誰當翻譯官 | ③ | `ros2 node list`、`ps` 找 `parameter_bridge` | 有 `/hw_bridge`（取代真車的 micro-ROS agent）、`/robot_state_publisher`、`/rviz2` |
| 3 | 零件在哪 | ③＋RViz | `ros2 run tf2_ros tf2_echo base_link radar_Link`、`imu_Link`；`ros2 run tf2_tools view_frames` | 光達 z≈0.079；TF 樹 PDF；RViz 看零件位置 |
| 4 | 小腦話題介面 | ③＋rqt_graph | `ros2 node info /hw_bridge`、`ros2 topic list`；`GALLIUM_DRIVER=llvmpipe rqt_graph` | 訂閱 /cmd_vel、/gimbal/*；發布 /scan /imu /odom /tf /joint_states /clock；對照真車 `/YB_Car_Node` |
| 5 | 資料是活的 | ②③ | `ros2 topic hz /scan`、`/imu`；`echo --once /imu --field linear_acceleration` | /scan 約 10 Hz、/imu 約 50 Hz（真車 12.5／20）；z≈9.8 |
| 6 | 總結 | — | 語音 | 模擬與真車對照 |

## 進度（2026-11-05 14:51 暫停）

步驟 0～4 ✅，下一步是步驟 5。交接見 `drill/live/20261105-handoff-w1-sim.md`。

## 模擬與真車差異（結果稿要講）

| 項目 | 真車 | 模擬 |
| --- | --- | --- |
| 大腦 | Pi 5、aarch64、Debian 12 主機＋Ubuntu 22.04 容器、ROS humble | PC WSL、x86_64、Ubuntu 24.04、ROS jazzy |
| 翻譯官 | micro-ROS agent 容器（USB 序列 ↔ ROS 2） | `ros_gz_bridge` 的 `/hw_bridge`（Gazebo ↔ ROS 2） |
| 小腦節點 | `/YB_Car_Node`（ESP32） | 沒有，Gazebo 外掛直接產生資料 |
| 里程計 | `/odom_raw` | `/odom` |
| 電池／蜂鳴器／雲台 | `/battery`、`/beep`、`/servo_s1`、`/servo_s2` | 無、無、`/gimbal/pan`、`/gimbal/tilt` |
| /scan、/imu 頻率 | 約 12.5 Hz、約 20 Hz | 10 Hz、50 Hz（URDF 設定） |
