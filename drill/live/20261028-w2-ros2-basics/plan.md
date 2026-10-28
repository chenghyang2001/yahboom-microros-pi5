# 逐步演練：W2 ROS 2 最小必學（2026-10-28，電腦 WSL）

教材：`lessons/W2.md`。不需要車子，在這台 PC 的 WSL Ubuntu 24.04（ROS 2 Jazzy）上做。
畫面在螢幕 3：左邊是 Windows Terminal，裡面用 tmux session `w2` 切三格；右邊是烏龜視窗。全程錄影。
格子：① turtlesim 節點　② 鍵盤遙控　③ 指令

| 步驟 | 主題 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- | --- |
| 1 | 節點 | ①②③ | `ros2 run turtlesim turtlesim_node`；`ros2 run turtlesim turtle_teleop_key`；`ros2 node list`／`node info /turtlesim` | 藍色烏龜視窗；兩個節點；名片分成 Subscribers／Publishers／Service Servers |
| 2 | 話題 | ③（②送方向鍵） | `ros2 topic list`、`topic echo /turtle1/cmd_vel`、`topic info`、`topic hz /turtle1/pose`、`interface show geometry_msgs/msg/Twist` | 5 個話題；按方向鍵時速度資料跑出來；Twist 的 linear／angular |
| 3 | 自己發話題 | ③ | `ros2 topic pub -r 1 /turtle1/cmd_vel ... "{linear: {x: 2.0}, angular: {z: 1.8}}"`、`--once` | 烏龜持續轉圈；Ctrl+C 停；只發一次走直線 |
| 4 | 服務 | ③ | `service list`／`type /spawn`／`call /spawn`、`pub /turtle2/cmd_vel`、`call /clear`、`call /kill` | 出現 turtle2；清掉軌跡；刪掉烏龜 |
| 5 | 參數 | ③ | `param list`／`get`／`set /turtlesim background_r 255`／`describe`／`dump` | 背景變紅；存成 YAML |
| 6 | 全貌 | ③ | `ros2 run rqt_graph rqt_graph`；`ros2 launch turtlesim multisim.launch.py` | 關係圖 teleop → cmd_vel → turtlesim；兩個烏龜視窗 |
| 7 | ROS_DOMAIN_ID | ①② | `ROS_DOMAIN_ID=5 ros2 run demo_nodes_cpp talker`／`listener`，再換成 7 | 同號收得到 Hello World；不同號收不到 |

## 結果（2026-10-28 08:33 完成）

7 步全部完成。錄影：`~/Videos/pi5-drill/drill-w2-ros2-basics-20261028-073119.mp4`（07:31:20 開始）。

| 步驟 | 結果 | 狀況 |
| --- | --- | --- |
| 1 節點 | ✅ | 第一次 `ros2 node list` 卡住，ros2 daemon 沒起來，手動 `ros2 daemon start` 後正常 |
| 2 話題 | ✅（重做） | tmux 的 `Up` 鍵名遙控器不認，改送字面 `ESC [ A`；截圖檔名寫錯，四張互相覆蓋，修正後重拍 |
| 3 自己發話題 | ✅ | 一次成功 |
| 4 服務 | ✅（重做 spawn） | 烏龜視窗太小、畫布被切掉，turtle2 看不到；放大視窗後重做 |
| 5 參數 | ✅ | 一次成功 |
| 6 全貌 | ⚠️ 部分 | rqt_graph 在 WSLg 上畫面凍住、圖空白，改用 `topic info --verbose` 文字說明；launch 正常 |
| 7 ROS_DOMAIN_ID | ✅（重做兩次） | listener 要 15～20 秒才收到，前兩次只等 9 秒就判斷錯了 |
