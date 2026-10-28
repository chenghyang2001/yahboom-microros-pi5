# 拍五逐步演練：B5 讀懂車的話題（2026-10-28）

教材：`lessons/B5.md`。實車，車子原地轉一圈。路線圖第 3 場。電池開場 8.1 V。
畫面：螢幕 3 是 VNC；tmux `drill`：① 聽（echo，docker exec 進開機自動開的容器）、② 說（pub，同一容器）、③ 主機。

| 步驟 | 主題 | 格子 | 指令 | 預期 |
| --- | --- | --- | --- | --- |
| 1 | 聽光達 | ② | `ros2 topic echo /scan --once --no-arr` | angle、range 結構 |
| 2 | 聽輪子里程（使用者手推） | ① | `ros2 topic echo /odom_raw --field pose.pose.position` | 推 10 cm，x 增加約 0.1 |
| 3 | 原地轉一圈 | ①② | ① echo /imu angular_velocity；② `pub -r 10` angular.z 0.5，約 12.6 秒 Ctrl-C，觀察會不會自己停，再送零 | 轉一圈；實測韌體逾時停車 |
| 4 | 蜂鳴器 | ② | `pub --once /beep "data: 100"` | 嗶 0.1 秒（需實車確認） |
| 5 | 雲台 | ② | S1 20 → -20 → 0；S2 -30 → 0 | 鏡頭左右、低頭回正 |
| 6 | /odom vs /odom_raw | ② | `ros2 topic list \| grep odom` | 只有 /odom_raw |
| 7 | 總結 | — | 語音 | — |

安全：角速度 0.5 rad/s（上限 0.8）；停車只送零 /cmd_vel；雲台 S1 ±20、S2 -30～0。
準備時小插曲：重開 VNC 出現「Unknown encoding」，清掉手機上新舊重複的 nc 轉接後正常；清理時誤對手機上的 7896 轉接送了 kill，但沒有生效、未受影響。

## 結果

- 七步完成（14:36～15:16）；影片 <https://youtu.be/b-A144Ayd7o>（30 分 14 秒，播放清單第 6 位）
- 實車確認：Ctrl+C 停送 /cmd_vel 後車子不會停（需送零）；/beep data:100 短嗶自停；手推 10 cm 得 x=0.087；光達 0.12～8 m、360 點
- **事故**：S2 送 -10 大幅上仰扯掉相機線（dmesg usb 1-1 disconnect），送 0 沒回；依使用者指示送 S2 -45，使用者插回線，lsusb／/dev/video0 恢復、抓圖成功（抓圖拍到室內與人，未進 repo）
- 使用者先前要求雲台只做小角度各動一次；之後規則改為 S2 禁止用指令動
- 電池 8.1 → 7.5 V
