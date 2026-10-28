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

## 進度（2026-10-28 08:58 收工暫停）

- ✅ 準備：tmux session `w4` 三格（已 source `~/yahboom_ws`）、ros2 daemon 已啟動、W4 終端擺在螢幕 3
- ✅ 開場語音 `01-intro`（播了兩次）
- ⬜ 第一步～第六步都還沒做

接續：重開 tmux `w4` 和終端（電腦重開過的話要重建），開新一段錄影，從第一步的說明語音開始。
開始前測過：RViz 只要不改視窗大小就能移到螢幕 3；Gazebo 可以用；關節滑桿改用 `ros2 topic pub /joint_states`。
第 1 段錄影（只有開場）：`~/Videos/pi5-drill/<rec_name.txt>.mp4`。
