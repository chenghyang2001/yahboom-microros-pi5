# M2 實車逐步演練：MediaPipe 手、臉、姿態

- 日期：2026-10-29
- 車子：不動，雲台不動。使用者站在車子相機前入鏡比手勢。
- 上電檢查：1～9 ✅（39.5 °C、throttled 0x0、磁碟 55%、電池 70、/scan 12.5 Hz、/imu 20.1 Hz、相機 Microdia、Pi IP 10.169.179.1）。車上 mediapipe 0.10.9（有 solutions）。
- 隱私：相機畫面會拍到使用者與室內，截圖只放 scratchpad；影片剪輯時把 OpenCV 視窗的相機那一半打碼（右半是黑底骨架圖，可保留）。

## tmux 格子（session `drill`，三格都 docker exec 進現有 ROS 2 容器）

| 格子 | 用途 |
| --- | --- |
| ① 左上 | 跑 MediaPipe 程式（會開 OpenCV 視窗） |
| ② 右上 | 觀察 /mediapipe/points 話題 |
| ③ 下方 | 檢查用（版本、程式碼） |

## 步驟

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 環境與三行核心程式 | ③ | `python3 -c "import mediapipe as mp; print(mp.__version__, hasattr(mp,'solutions'))"`、`ros2 pkg executables yahboomcar_mediapipe`、`grep -n` 看 01_HandDetector 的 cvtColor／process／landmark | 0.10.9 True；列出 01～05 等節點；看到「轉 RGB → 丟模型 → 讀關鍵點」 |
| 2 手部 21 點 | ① ② | ①`ros2 run yahboomcar_mediapipe 01_HandDetector`；②`ros2 topic echo --once /mediapipe/points \| grep -c "x:"`、`... \| head -8` | 視窗左邊相機、右邊黑底骨架；一隻手 21 點、兩隻手 42 點、沒手 0；座標是 0～1 比例 |
| 3 姿態 33 點 | ① ② | ①`02_PoseDetector`；②同上計數 | 退後讓上半身入鏡，數到 33 |
| 4 臉部網格 468 點 | ① ② | ①`04_FaceMesh`；②同上計數 | 臉上一片網格，數到 468 |
| 5 規則式手勢辨識 | ① | `cd .../yahboomcar_mediapipe/yahboomcar_mediapipe` → `python3 11_GestureRecognition.py` | 比 0、1、2、5、OK、讚，左下綠框顯示手勢名稱；側手會判斷錯 |
| 6 空中畫筆 | ① | `python3 09_VirtualPaint.py` | 食指＋中指＝選色、只有食指＝畫線 |

## 結果

- 影片：<https://youtu.be/CwEc_1CCXV0>（私人，約 38 分鐘；相機視窗出現的時段全部打碼，手勢名稱與骨架保留）
- 錄影 13:12～13:51，約 39 分鐘；電池從 70 掉到 66（6.6 V）。
- 第 1 步：`0.10.9 True`；第 37／38／45 行是轉 RGB、`hands.process`、讀點。③ 格太矮，版本那行被擠出畫面，拉高到 16 行。
- 第 2 步：第一次啟動相機 `select() timeout` → `NoneType has no attribute shape` 當掉；單獨測相機正常，重跑就好。點數 21／0／42。`dist` 視窗寬 1280 超出 1184 的 VNC 桌面，蓋住終端機。
- 第 3 步：33 點（26 筆中 23 筆 33、3 筆 0），FPS 約 9。
- 第 4 步：`topic echo` 預設截到 128 筆，加 `--full-length` 才是 468；FPS 約 20。
- 第 5 步：Five／Zero／One／Two 正確；OK→Three、讚→Five（一次 Four）、側手→Five；手太近時偵測不到。
- 第 6 步：綠、黃、藍畫線，黑色擦除正常；畫面沒有鏡像。
- 相機截圖只放 scratchpad，`shots/` 只有第 1 步終端機截圖。
