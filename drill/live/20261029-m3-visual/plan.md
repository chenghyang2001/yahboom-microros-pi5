# M3 實車逐步演練：視覺互動（顏色追蹤、人臉追蹤、巡線、手勢控車）

- 日期：2026-10-29（路線圖第 10 場）
- 做法改變：車子充電時先把規劃、程式、說明語音全部備好，備好才請使用者開車；用車部分做完就關車，剪影片等收尾在關車後做。
- 車子：雲台只動 S1（正前方 -30 ±10 度），S2 全程攔下；輪子經限速閥，線速度 ≤ 0.10 m/s、角速度 ≤ 0.6 rad/s。
- 隱私：相機畫面會拍到使用者與室內，截圖只放 scratchpad；影片剪輯時把 OpenCV 視窗打碼。

## 開始前讀原始碼發現的問題

| 程式 | 問題 | 處理 |
| --- | --- | --- |
| `colorTracker` | 一啟動送 S1=0、S2=-50；PID 同時改 S1、S2 | 雲台話題改名給 `servo_guard.py`：S2 攔下，S1 換算成 -30 ±10、每筆最多變 3 度 |
| `face_fllow` | 一啟動送 S2=-60；臉框左上角當目標 | 同上 |
| `follow_line` | 一啟動送 S2=-75（低頭看地）；預設 0.18 m/s；PID 角速度沒上限 | 雲台改名；`-p linear:=0.08`；`/cmd_vel` 改名經限速閥。S2 不能低頭，只能用鏡頭朝前時畫面下半部看到的地面（程式本來就把上半部塗黑） |
| `HandCtrl` | 一啟動送 S2=-45；五指前進 0.3、拳頭後退 0.3 | 雲台改名、`/cmd_vel` 改名經限速閥（0.3 → 0.10）；每個手勢只送一次，限速閥 0.5 秒沒新指令就送零，所以每比一次只走一小段 |
| 全部 | 車上檔案可能和 PC 上的 `source-code/` 不同 | 開車後先 `grep -n "servo_s2\|PWMServo_Y = "` 確認一次 |

改名參數：`R='--ros-args -r servo_s1:=servo_s1_raw -r servo_s2:=servo_s2_raw -r /cmd_vel:=/cmd_vel_raw'`

## 安全裝置（自己寫的）

| 檔案 | 作用 |
| --- | --- |
| `servo_guard.py` | 訂閱 `/servo_s1_raw`、`/servo_s2_raw`。S1：`-30 + clamp(raw, ±10)`，每筆最多變 3 度；S2：一律攔下只印 log。啟動和結束時把 S1 送回 -30 |
| `cmd_vel_limiter.py` | 沿用 M4：`/cmd_vel_raw` → 限速 → `/cmd_vel`；0.5 秒沒指令送零。這次帶 `-p max_linear:=0.10 -p max_angular:=0.6` |

停車：對 ① 的 OpenCV 視窗按 q 或 Ctrl+C 停程式，限速閥 0.5 秒後自動送零；再保險補 `ros2 topic pub --times 3 /cmd_vel geometry_msgs/msg/Twist "{}"`。不用 `ycar.py stopcar`。

## tmux 格子（session `drill`，四格都 docker exec 進 ROS 2 容器，工作目錄 `/root/m3`）

| 格子 | 用途 |
| --- | --- |
| ① 左上 | 視覺主程式（會開 OpenCV 視窗） |
| ② 右上 | 第二個節點（colorTracker）／看話題 |
| ③ 左下 | 雲台守門員 |
| ④ 右下 | 限速閥 |

## 要準備的東西

- 場地：約 1×1 公尺淨空；巡線和手勢步驟車會前後走一小段。
- 顏色鮮豔的物品一個（紅色最好）。
- 巡線用的膠帶或長條紙，和地板顏色反差大，貼一段約 60 公分的直線（可帶一點彎）。

## 步驟

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 安全裝置 | ③ ④ ② | ③`python3 servo_guard.py`；④`python3 cmd_vel_limiter.py --ros-args -p max_linear:=0.10 -p max_angular:=0.6`；②`ros2 topic info /servo_s2 -v` | ③ 印出「S1 送出 -30」，鏡頭朝正前方；④ 印出限速設定；② 看到 /servo_s2 沒有任何發布者 |
| 2 顏色追蹤 | ① ② ③ | ①`ros2 run yahboomcar_astra colorHSV $R`；②`ros2 run yahboomcar_astra colorTracker $R`；在視窗按 r → 框選物品 → 空白鍵 | 右邊遮罩只剩物品是白的；物品左右慢慢移，鏡頭跟著轉（最多 ±10 度）；③ 印出 S1 要求與送出、S2 已攔下 |
| 3 人臉追蹤 | ① ③ | ①`ros2 run yahboomcar_astra face_fllow $R` | 臉被綠框框住；人左右移動，鏡頭跟著轉；③ 同上 |
| 4 巡線（⏸ 以後補做：沒有膠帶） | ① ④ | ①`ros2 run yahboomcar_astra follow_line $R -p linear:=0.08 -p ResponseDist:=0.3`；r → 框選線 → 空白鍵 | 車沿著線慢慢前進、偏了會修正；④ 看到限速 log；找不到線印 Not Found 並停 |
| 5 手勢控車 | ① ④ | ①`ros2 run yahboomcar_mediapipe HandCtrl $R` | 比五前進、握拳後退、只伸食指左轉、食指加中指右轉，每比一次動一小段 |

## 結果

- 錄影 15:10～15:50，約 40 分鐘；上電檢查 1～9 ✅（32.9 °C、throttled 0x0、磁碟 55%、電池 81、/scan 12.5 Hz）；電池 81 → 74。
- 影片：（上傳後補）
- 第 1 步：守門員啟動回正 S1=-30；限速閥 0.10／0.60；`/servo_s2` 發布者 0、訂閱者 1（YB_Car_Node）。
- 第 2 步顏色追蹤（紅白格子毛巾）：
  - 框選紅色後遮罩整片白：`ColorIdentify` 參數變成 H 0～184。**紅色橫跨色環 0／180 接縫**，框到兩種紅，程式取 min／max 就變成全部顏色。
  - 改法：把 `/root/yahboomcar_ws/src/yahboomcar_astra/yahboomcar_astra/colorHSV.text` 寫成 `160, 90, 40, 180, 255, 255`，在視窗按 `i`（辨識模式每張畫面重讀這個檔）→ 遮罩只剩毛巾。改 ROS 參數沒有用（`process()` 只用 ROI 或檔案的範圍）。
  - 鏡頭跟著毛巾左右轉；官方要求 S1 在 -90～+88 之間來回，守門員送出 -40～-20。雲台只能轉 ±10，誤差消不掉，PID 一路加到上限 90（**控制器飽和**）。
  - S2 指令 58 次全攔下（48 次是 -90）。
- 第 3 步人臉追蹤：9 張截圖 3 張有綠框（都是正對鏡頭）；S1 要求一路到 89；S2 要求 +20（抬頭到底）全攔下。
- 第 4 步巡線：⏸ 跳過，以後補做（地板沒有色膠帶；鏡頭不能低頭，只看得到約 30 公分外的地面）。程式關閉後補送 3 次零速度。
- 第 5 步手勢控車：
  - 第一輪：fingers 統計 食指 26、五指 17、拳頭 17、比二 15，**辨識都正確**；前進／後退會動，左右原地轉不動。限速閥 log：線速 0.30→0.10。
  - 原因：HandCtrl 每認出一次只送一筆然後 `sleep(0.5)`，兩筆間隔約 0.7 秒；限速閥看門狗 0.5 秒就送零。對照實驗（`turntest.py`，經限速閥送 0.5 rad/s，odom 量角速度）：連續送平均 0.52；送一筆停 0.7 秒平均 0.02。
  - 修正：`cmd_vel_limiter.py` 加參數 `watchdog_timeout`（預設仍 0.5），這次用 `-p watchdog_timeout:=1.0` → 同樣斷續送平均 0.27，第二輪食指 4、比二 3 次，使用者確認左右轉可以。
- 全場 S2 指令共 276 次，全部被守門員攔下，相機線沒事。
- 收尾：tmux、VNC 關閉；`sudo shutdown -h now` 讓 Pi 正常關機，使用者再關總開關充電。
- 相機截圖只放 scratchpad；影片中相機視窗出現的 5 段全部打碼。
