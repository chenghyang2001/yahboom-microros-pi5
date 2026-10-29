# M4 實車逐步演練：光達應用（避障、跟隨、警衛、巡邏）

- 日期：2026-10-29（第 7 場）
- 車子：會動。全程經過限速閥，線速度 ≤ 0.15 m/s、角速度 ≤ 0.8 rad/s；雲台不動。
- 上電檢查：1～9 ✅（29.6 °C、throttled 0x0、磁碟 55%、電池 81、/scan 12.5 Hz、/imu 20.7 Hz）。第 10 步原本 38841 秒，按 ESP32 Reset 後降到 1 秒。

## 開始前發現的問題（讀車上程式碼）

| 問題 | 處理 |
| --- | --- |
| `laser_Avoidance` 一啟動就跑，預設 0.3 m/s、1.0 rad/s | 啟動時帶 `-p linear:=0.15 -p angular:=0.8`，再經過限速閥 |
| `laser_Tracker`、`laser_Warning` 用 PID 算速度，沒有上限 | 自己寫的 `cmd_vel_limiter.py`：官方程式改名送到 `/cmd_vel_raw`，限速閥夾住後轉發到 `/cmd_vel`；0.5 秒沒收到就送零 |
| `patrol` 預設 0.2、0.9；讀 `/scan` 的那行被註解掉，遇障礙不會停 | 帶 `-p Linear:=0.15 -p Angular:=0.8`，路線上不放東西 |
| 手把開機不會自動啟動，R1 不能接管 | 第 2 步啟動 `joy_node`＋`yahboom_joy`，雲台話題改名 |

## tmux 格子（session `drill`，四格都 docker exec 進 ROS 2 容器）

| 格子 | 用途 |
| --- | --- |
| ① 左上 | 光達程式 |
| ② 右上 | 限速閥 |
| ③ 左下 | 檢查與調參數 |
| ④ 右下 | 手把 |

## 步驟

改名參數：`R='--ros-args -r cmd_vel:=cmd_vel_raw -r /cmd_vel:=/cmd_vel_raw'`

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 讀懂 /scan | ③ | `ros2 topic echo /scan --once --no-arr`；用 python 算出 0°、+90°、-90°、180° 的距離 | angle_min、angle_increment、點數；四個方向的距離與實際相符 |
| 2 安全裝置 | ② ④ | ②`python3 cmd_vel_limiter.py`；④`joy_node`＋`yahboom_joy`（限速、雲台改名） | 限速閥印出設定；手把按 START 嗶一聲 |
| 3 警衛 | ① | `ros2 run yahboomcar_laser laser_Warning $R` | 原地轉向最近的紙箱；≤ 0.3 m 時蜂鳴器響；② 看到限速 log |
| 4 避障 | ① | `ros2 run yahboomcar_laser laser_Avoidance $R -p linear:=0.15 -p angular:=0.8` | 車子直走，遇到紙箱轉開；① 印出判斷表的訊息 |
| 5 調參數 | ③ | `ros2 param get/set /laser_Avoidance ResponseDist 0.3` | 反應距離變短，車子更靠近紙箱才轉 |
| 6 跟隨 | ① | `ros2 run yahboomcar_laser laser_Tracker $R` | 紙箱前後移動，車子跟著保持約 0.55 m |
| 7 巡邏 | ① ③ | bringup ＋ `patrol $R -p Linear:=0.15 -p Angular:=0.8 -p Length:=0.5`；③ `ros2 param set /YahboomCarPatrol Switch true` | 走一個 0.5 m 的小正方形 |

## 插話紀錄

- 第 1 步後，使用者發現鏡頭偏右，要求用 S1 往左調。送 `/servo_s1` 10（--once）、20（--times 3）鏡頭都不動；`/servo_s1` 有 YB_Car_Node 訂閱，`/beep` 150 ms 有響 → ESP32 收得到指令，判斷是雲台舵機本身（線鬆或卡住，可能與 10/28 B5 扯線有關）。改由使用者手動把鏡頭轉正，演練後再查。
- 使用者手也轉不動（舵機有出力鎖住）。改用指令依序送 0、-10、-20、-30（每個停約 10 秒，語音報數），使用者在送完 -30 後喊停，確認鏡頭朝正前方 → 這台車目前 **S1 = -30 才是正前方**（零點偏掉）。手把節點啟動會把 S1 設 0，所以 yahboom_joy 一定要改名雲台話題。

## 結果（前半場，2026-10-29 09:19～09:53）

- 錄影：`~/Videos/pi5-drill/pi5drill-m4-lidar-20261029-091945`（進行中）。
- 第 1 步：/scan 360 點、angle_min -180°、每格 1°（0.01745 rad）、range 0.12～8.0 m；0° 是車頭，左正右負；正前 2.96、正左 1.97、正右 0.73、正後 0.63 m。③ 格只有 16 行，echo 輸出被 scan_peek 擠掉。
- 第 2 步：限速閥、joy_node、yahboom_joy（雲台改名 servo_s1_off）都正常；節點 4 個。
- 第 3 步：紙箱 0.39 m 正前方，minDistID 在 -3°～0° 時官方 PID 仍要求 0.81～1.33 rad/s，全被夾成 0.80（限速閥真的有用）。使用者確認紙箱移左／右前方車頭會轉過去、推到 30 cm 內蜂鳴器響（tmux 捲動緩衝 2000 行，警報行已被擠掉，沒留紀錄）。
- 第 4 步：帶 `-p linear:=0.15 -p angular:=0.8`，限速閥沒出手。約 610 次判斷：10 直走 430、9 右有→左轉 78、6 前有→左轉 38、2 前右有→左轉 30、4 前左有 16、8 左有→右轉 13、7 左右有 5、1 三邊都有 1。
- 電池：開場 81 → 第 3 步前 72 → 第 4 步中 70 → 停下後 71。第 4 步後暫停充電，第 5～7 步待續。
- 第 5 步：Switch:=true 啟動確實不動（只印 start it）；param list 6 個參數；ResponseDist 0.55→0.3（Double）；Switch false 開跑。約 615 次判斷：10 直走 505（82%，上一步 70%）、9 78→60、6 38→20、2 30、8/7/4/1 都是 0。電池 70。
- 第 6 步：Switch:=true 啟動後改 false 開跑。minDist 0.29～0.80 m；限速閥出手 52 次，官方要求最高 linear 0.65 m/s、angular 7.50 rad/s（上限的 4 倍、9 倍）。電池 70。
- 第 7 步：bringup 後 TF odom→base_footprint 在 (0,0,0)；patrol 帶 Linear 0.15／Angular 0.8／Length 0.5，Switch true 開跑。**第一段沒有在 0.5 m 停**：`distance` 一路印到 4.2 m（中間一度降到 0.76 再升），最後印 `obstacles`；使用者喊停，Ctrl+C＋連送零速度 4 秒。停車後 TF 在 (-1.29, 3.15)、偏航 -20°，/odom 18 Hz、/odom_raw 11 Hz 都正常且不再飄 → 不是里程計壞掉，懷疑 `advancing()` 的 `abs(error) < LineTolerance(0.05)` 沒觸發（原因待查，先在 WSL 模擬重現）。`obstacles` 分支會送 `/beep data=1`，程式被關掉後蜂鳴器一直叫 → 補送 `/beep 0`。
- 電池 69（6.9 V）結束演練，Pi 正常關機充電。
