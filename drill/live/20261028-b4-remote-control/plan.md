# 拍五逐步演練：B4 遙控：鍵盤、手把、手機 App（2026-10-28）

教材：`lessons/B4.md`。實車，車子會跑（約 2×2 公尺空地）。路線圖第 4 場。
畫面：VNC 螢幕 3；tmux `drill`：① 監視 `/cmd_vel`（容器）、② 遙控程式（容器）、③ 主機。

| 步驟 | 主題 | 格子 | 做法 | 使用者 |
| --- | --- | --- | --- | --- |
| 1 | 三種遙控都是 /cmd_vel | ①② | ① `ros2 topic echo /cmd_vel`；② `ros2 node list` | — |
| 2 | 鍵盤 | ② | `ros2 run yahboomcar_ctrl yahboom_keyboard`；x×6、c×3 降到約 0.106／0.73；i 約 1 秒、`,` 約 1 秒回原位、j／l 各約 1 秒、空白、Ctrl-C | 看 |
| 3 | 手把 | ② | `joy_node` ＋ `yahboom_joy --ros-args -p xspeed_limit:=0.10 -p angular_speed_limit:=0.8 -r servo_s1:=servo_s1_off -r servo_s2:=servo_s2_off` | 按 R1、慢慢開 |
| 4 | 手機 App | ② | `ros2 launch rosbridge_server rosbridge_websocket_launch.xml` | App 連 10.169.179.1、ROS2、輕推輪盤 |
| 5 | 總結 | — | 語音 | — |

安全：
- yahboom_joy 啟動會送 S2=-60、Y/A 鍵動 S2 → 用 remap 把雲台話題改名，節點碰不到雲台（B5 S2 事故）。
- 手把預設 0.33 m/s／1.25 rad/s、檔位鍵可再加速 → 把 limit 參數直接設 0.15／0.8（程式會截斷），預設檔約 0.05 m/s。
- 鍵盤起始 0.2／1.0 → 先按 x、c 各 3 次。
- App 輪盤沒有限速保護 → 請使用者輕推。
- 每步結束送零 /cmd_vel、node list 確認只剩 /YB_Car_Node。

**2026-10-28 15:25 場地修正**：使用者說車子周圍只有 1×1 公尺 → 鍵盤降到約 0.1 m/s、前進後退各約 1 秒；手把上限 0.10 m/s；App 只輕點一下。以原地轉為主。

## 結果

- 五步完成（15:23～16:06）；影片 <https://youtu.be/kSFRabO9FCE>（25 分 37 秒，播放清單第 7 位）
- 鍵盤：x×6、c×3 → 0.106／0.729，各方向約 2.3 秒（遠端送鍵延遲），沒出 1×1 範圍
- 手把：上限 0.10 × 檔位 1/3 = 0.033 m/s 推不動；改 0.30／3.2 正常；雲台話題 remap 有效（/servo_s2 發送者 0）
- App：使用者要求用 adb 填 IP、選 ROS2、按連接（手機先由使用者解鎖）；只開 rosbridge；輪盤出現 0.73 m/s，看門狗（>0.25）關 rosbridge＋送零三次；使用者決定不再測
- 電池 7.4 V
