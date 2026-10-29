# M5 逐步演練：寫自己的第一個控制節點（遇障礙就停）

- 日期：2026-10-29（第 8 場）
- 教材：`lessons/M5.md`。程式三個檔案從講義原樣抽出，放在本資料夾 `my_obstacle_stop/`（obstacle_stop.py 118 行、setup.py、package.xml、setup.cfg）。
- 上電檢查：1～9 ✅（33.4 °C、throttled 0x0、磁碟 55%、NTP yes、兩個容器 Up、ttyUSB0／相機／手把接收器都在、電池 81、/scan 12.5 Hz）。時鐘差 3514 秒，本節點用「收到的時間」判斷逾時、不看 header 時間戳，不影響。
- 事前在 WSL 用無畫面模式試跑：模擬車從原點往 +x 走，約 13 秒後印「前方 0.29 m 有障礙，停車」✅。

## 安全

- 節點前進速度 0.1 m/s（講義預設），不改大。
- 實車上節點改名送到 `/cmd_vel_raw`，經 M4 的限速閥（0.15 m/s、0.8 rad/s、0.5 秒沒收到就送零）再到 `/cmd_vel`。
- 停車只送零 `/cmd_vel`；雲台不動。
- 先架高（輪子懸空）測，再落地測。

## 畫面

前半場（模擬車）：螢幕 3 左邊 Windows Terminal 跑 `wsl tmux`（session `m5`），右邊 Gazebo。
後半場（實車）：螢幕 3 換成 VNC，Pi 上 tmux session `drill`。

| 格子 | 前半場 WSL | 後半場實車 |
| --- | --- | --- |
| ① | 模擬車（Gazebo） | 我的節點（容器內） |
| ② | 編譯並執行我的節點 | 限速閥（容器內） |
| ③ | 建套件、觀察、改參數 | 主機：解壓、docker cp；之後進容器檢查 |

## 步驟

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 建套件 | WSL ③ | `ros2 pkg create my_obstacle_stop --build-type ament_python --dependencies rclpy sensor_msgs geometry_msgs --node-name obstacle_stop`（在新的 `~/m5_ws/src`）；`find` 看結構 | 產生 package.xml、setup.py、setup.cfg、resource、obstacle_stop.py 骨架 |
| 2 放入程式 | WSL ③ | 把講義的三個檔案複製進去；`grep` 印出三塊重點（參數、訂閱發布、計時器、entry_points） | 看懂「感測 → 判斷 → 動作」三段 |
| 3 模擬車測試 | WSL ①②③ | ① `sim.launch.xml rviz:=false`；② `colcon build --symlink-install` → `source` → `ros2 run`；③ `ros2 topic echo /cmd_vel --field linear.x` | 車往前走，約 13 秒後印「前方 0.29 m 有障礙，停車」，linear.x 從 0.1 變 0.0 |
| 4 改參數與斷線保護 | WSL ③①② | ③ `ros2 param set /obstacle_stop stop_distance 0.2` → 印「前方淨空」再走、0.19 停；① Ctrl+C 關模擬 → ② 印「超過…秒沒收到 /scan，先停車」；② Ctrl+C | 參數即時生效；遲滯；光達斷線就停 |
| 5 搬上車 | WSL ③ → Pi ③ | `tar czf` + `scp -P 8022` 到 Pi；切到 VNC；Pi ③ `tar xzf`、`docker cp ~/my_ws`、`docker cp ~/drill-m4/cmd_vel_limiter.py` | 容器裡有 `/root/my_ws/src/my_obstacle_stop` |
| 6 容器內編譯＋架高測試 | Pi ①②③ | ② 限速閥；① `colcon build` → `source` → `ros2 run my_obstacle_stop obstacle_stop --ros-args -r /cmd_vel:=/cmd_vel_raw`；手放正前方 20 cm、放後方各一次 | 正前方停（輪子停）、後方不停；Ctrl+C 後輪子停 |
| 7 落地測試 | Pi ①③ | 車放地上、前方約 1 m 放紙箱，執行節點 | 以 0.1 m/s 前進，約 30 cm 處停；紙箱移開繼續走；Ctrl+C 停 |
| 8 總結 | — | 語音 | 模擬與實車對照 |

## 結果（2026-10-29 11:31～12:43）

| 步驟 | 結果 | 備註 |
| --- | --- | --- |
| 開場 | ✅ | 使用者要求重播一次 |
| 1 建套件 | ✅ | 4 個資料夾、9 個檔案；授權 TODO 的 WARNING |
| 2 放入程式 | ✅（補送一次） | 第一次 grep 含括號與直線符號，被 `wsl -- bash -c` 二次展開弄壞沒送出；改 `wsl -e` 後補念 `05-step2-redo` 再送 |
| 3 模擬車 | ✅ | 約 30 秒後「前方 0.30 m 有障礙，停車」；`/odom` x = 1.146；③ echo 因 ros2 daemon 卡住逾時，強制重開 daemon 後補念 `08-step3-fix` 再看（linear.x 0.0）；Gazebo 畫面不更新、看不到車 |
| 4 參數與斷線 | ✅ | scan_timeout 1.0 後黃色警告消失；stop_distance 0.2 → 淨空 0.28 再走、0.18 停，x = 1.266；關模擬 → 1.0/3.0/4.8/7.4 秒警告；Ctrl+C 乾淨結束 |
| 5 搬上車 | ✅ | tgz 3859 bytes，WSL `scp -P 8022 ... pi@127.0.0.1`；容器 cc8a72674c13；docker cp 19.5 kB＋10.2 kB |
| 6 架高 | ✅ | build 約 3 秒（setuptools 警告）；停 5 次／淨空 5 次（首次 0.29/0.37）；手在後方 18 秒沒停；Ctrl+C 後限速閥看門狗補零 |
| 7 落地 | ✅ | 約 8.4 秒後 0.29 m 停；紙箱拿開後「淨空 1.81 m」繼續；約 5 秒後 Ctrl+C |
| 總結 | ✅ | `20-summary` |

- 電池：81（開場）→ 73（第 5 步）→ 72（第 6、7 步）。
- 收尾：使用者訂下規則「演練結束一律做影片上傳、現場全部關掉，不用再問」，已寫進 skill 與記憶。
