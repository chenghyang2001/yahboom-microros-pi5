# 逐步演練：W4 在電腦上看這台車：URDF、RViz、TF（2026-10-28，電腦 WSL）

教材：`lessons/W4.md`。不需要車子，用 WSL 的 `~/yahboom_ws` 模擬套件 `microros_pi5_sim`。
畫面在螢幕 3：左邊是 Windows Terminal，裡面用 tmux session `w4` 切三格；右邊放 RViz／Gazebo。全程錄影。
格子：① launch　② 輔助　③ 指令

| 步驟 | 主題 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- | --- |
| 1 | URDF | ③ | `grep` 印出 URDF 的 link／joint | 9 個 link、8 個 joint（模擬多一個 camera） |
| 2 | RViz 看模型 | ①③ | `ros2 launch microros_pi5_sim display.launch.xml`；`ros2 node list` | RViz 3D 車模型；3 個節點 |
| 3 | 關節動起來 | ③ | 關掉滑桿節點；`ros2 topic pub /joint_states`；`topic echo /joint_states` | 雲台轉頭、輪子轉 |
| 4 | TF | ③ | `tf2_echo base_link radar_Link`／`jq2_Link`；`view_frames` | 光達 z≈0.079；雲台數值隨角度變；TF 樹 PDF |
| 5 | Gazebo | ①③ | `sim.launch.xml`；`topic pub /cmd_vel`；送零速度 | 模擬車轉圈，光達紅點跟著轉 |
| 6 | 總結 | — | 語音 | 模擬與真車對照 |

改法：關節滑桿靠滑鼠點擊在 WSLg 上不可靠，改用 `ros2 topic pub /joint_states`。

## 進度（2026-10-28 11:00 全部完成）

| 步驟 | 結果 | 備註 |
| --- | --- | --- |
| 準備＋開場 | ✅ | 第 1 段錄影（只有開場）；第 2 段從第一步開始 |
| 1 URDF | ✅ | 實際 11 link／10 joint（模擬多 `base_footprint`、`camera_link`）；送指令工具一開始壞掉（`wslpath` 在 Git Bash 叫不到），晚約 30 秒補送 |
| 2 RViz | ✅（重開一次） | `display.rviz` 視窗太高、鏡頭太近，改成 Height 600、Distance 0.6 後重開；`Hide Left Dock` 沒生效 |
| 3 關節 | ✅ | 姿勢 A 約 5 秒生效；姿勢 B 約 60 秒才生效（新節點探索延遲），中間座標軸變灰 |
| 4 TF | ✅ | 光達 [0,0,0.079]；攝影機 [0.101,-0.038,0.042]→回正 [0.117,0,0.042]；TF 樹用 `dot` 轉 PNG，Chrome 開在螢幕 3 |
| 5 Gazebo | ✅ | 轉圈約 15 秒生效；說明稿「紅點跟著轉」說錯，結果稿更正（fixed frame 是 odom）；`/odom` 沒填 twist，停車改用兩張截圖比對確認 |
| 6 總結 | ✅ | `12-summary` |

錄影：`rec_name.txt` 兩段，影片要接起來剪（第 1 段只留開場）。
改過的設定：repo `sim/.../display.rviz`、`sim.rviz`（已同步到 WSL）；WSL `~/.gz/sim/8/gui.config` 改 640×560（備份 `gui.config.bak-w4`，沒生效）。

## 影片

- YouTube（私人）：<https://youtu.be/6GyK4SovhKE>，約 36 分 44 秒（兩段錄影 56＋分鐘剪成，長空檔壓縮成頭 20 秒＋尾 15 秒，保留每張截圖前後的畫面）
- 與 W2 一起放進私人播放清單「Yahboom MicroROS-Pi5 逐步演練」
- 剪輯計畫 `video_plan.json`、章節 `chapters.json`；本機成品 `~/Videos/pi5-drill/w4-urdf-rviz-tf-drill.mp4`
- 實際花費：第 2 段演練約 56 分鐘（10:07～11:03），加剪輯上傳約 15 分鐘
