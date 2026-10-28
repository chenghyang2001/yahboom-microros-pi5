# 拍五逐步演練：B6 狀態估測與校準（2026-10-28）

教材：`lessons/B6.md`。實車，車子會倒退約 0.67 m、原地轉一圈多。使用者準備 2 公尺空地、捲尺、膠帶。電池開場 7.0 V（偏低）。路線圖第 5 場。
畫面：VNC 螢幕 3；tmux `drill`：① bringup（容器）、② 校準程式與指令（容器）、③ 主機。

| 步驟 | 主題 | 格子 | 指令 | 預期 |
| --- | --- | --- | --- | --- |
| 1 | 啟動底層 | ①② | ① `ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py`；② `ros2 node list`、`ros2 topic list \| grep -E "odom\|imu"` | 出現 /ekf_filter_node、/odom、/imu/data |
| 2 | EKF 與 TF | ② | `ros2 node info /ekf_filter_node`；`tf2_echo odom base_footprint`（數秒） | 訂閱 /imu/data＋/odom_raw、發布 /odom；靜止時座標不動 |
| 3 | 線速度校準 | ② | `ros2 run yahboomcar_bringup calibrate_linear --ros-args -p speed:=0.1` 背景；`ros2 param set /calibrate_linear start_test true` | 車往後退，里程約 0.67 m 停；使用者量 |
| 4 | 角速度校準 | ② | `calibrate_angular --ros-args -p speed:=0.8`；`param set start_test true` | 原地轉，odom 角約 480° 停；使用者看車頭 |
| 5 | 總結 | — | 語音 | — |

原始碼確認：linear 用 copysign(speed, distance−1.0) → 起點倒退；預設 speed 0.5、scale 1.5；angular 預設 speed 2.0、scale 0.75、tolerance 1.5°。改用 `ros2 param set` 代替 rqt_reconfigure 視窗。每步結束送零 /cmd_vel。

## 結果

- 五步完成（16:13～16:40）；影片 <https://youtu.be/2VVCQaLF4ME>（23 分 51 秒，播放清單第 8 位）
- IMU 濾波：complementary_filter_gain_node
- 線速度：speed 0.1，倒退 11 秒；捲尺約 70 cm、TF 70.4 cm（側偏 6.3 cm）→ 係數約 1.05
- 角速度：speed 0.8，11 秒；使用者看車頭在膠帶左邊約 10°（實轉約 370°）；程式 478°×0.75=358.5°；TF 約 385° → 係數約 0.77。說明稿預測「多轉 120°」錯誤，結果稿更正
- 電池 7.0 V
