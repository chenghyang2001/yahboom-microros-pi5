# 拍五逐步演練：W1 認識這台車：實車導覽（2026-10-28）

教材：`lessons/W1.md`。實車，車子完全不動。路線圖第 1 場（`drill/DRILL-ROADMAP.md`）。
畫面：螢幕 3 是 VNC 的 Pi 桌面，tmux `drill` 三格沿用開機流程演練：① agent 終端（第 2 層容器 B）、② ROS 2 容器終端（第 2 層容器 A）、③ 主機（第 1 層）。

| 步驟 | 主題 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- | --- |
| 1 | 第 1 層大腦 Pi 5 | ③ | `/proc/device-tree/model`、`uname -m`、`os-release`、`free -h` | Pi 5、aarch64、Debian 12、8 GB |
| 2 | 第 2 層兩個容器 | ③→② | ③ `docker ps`；② `os-release`、`echo $ROS_DISTRO $ROS_DOMAIN_ID` | 2 個容器；容器內 Ubuntu 22.04、humble 20 |
| 3 | 硬體接在哪 | ③ | `lsusb`、`ls -l /dev/ttyUSB0 /dev/video0` | CP210x、Microdia 相機、DragonRise 手把接收器 |
| 4 | 第 3 層小腦話題介面 | ② | `ros2 node info /YB_Car_Node` | 訂閱 4、發布 4（含講義漏列的 `/battery`；是 `/odom_raw` 不是 `/odom`） |
| 5 | 資料是活的 | ② | `ros2 topic hz /scan`；`echo --once /imu --field linear_acceleration` | 約 12.5 Hz；z≈9.8 |
| 6 | 總結 | — | 語音 | 兩條路徑 |

試跑發現與講義不同：`/battery` 是 `/YB_Car_Node` 發布的（講義發布表漏列）；沒有 `/rpi5_ip` 話題。

## 結果

- 六步全部完成（12:03～12:36），車子全程不動
- 影片（YouTube 私人）：<https://youtu.be/0TUN2ofL1t4>，29 分 33 秒；播放清單第 4 位
- 講義 `lessons/W1.md` 依實測修正 5 處
- 小插曲：螢幕 3 被全螢幕的教材簡報 Chrome 蓋住，移到螢幕 2；容器 bash 會改 tmux 格子標題，用 `unset PROMPT_COMMAND; PS1=...` 擋掉（tmux 3.3a 沒有 allow-set-title）
