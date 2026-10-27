# Session 1 摘要（2026-10-27，session 名稱 hp1-pi5）

主題：把 Yahboom 官方手機 App「ROS Robot」裝到 Android 手機，並經 rosbridge 連上 MicroROS-Pi5 實車。

## 完成事項

### 連線確認

- 確認 adb 看得到手機 `84bbb261`（OPPO CPH2699，Android 16）。手機在熱點網段是 `10.57.201.133`。
- Pi 一開始 ping 不到，使用者開電源後 3/3 通（`10.57.201.1`）。
- 手機上的 `nc -L` 8022/5900 轉接本來就在跑，`ycar.py status` 正常：`/YB_Car_Node` 在、電池 8.1 V、`/scan` 約 12.5 Hz。
- 更正：`127.0.0.1:7896` 不是模擬器，是經手機轉接到熱點另一台裝置 `10.57.201.101` 的 adb 連線。

### 安裝 ROS Robot App

- Play 商店搜尋找不到。直接開套件頁 `com.github.rosjava.android_apps.make_a_map.kinetic`，顯示「僅適用於其他裝置」。
- 從 Yahboom 官網 MicroROS-Pi5 頁的「Mapping_APP(iOS_Android)」連到官方 Google Drive，下載 `Yahboom-ROSROBOT.apk`（10,509,201 bytes，SHA256 `da2945…6cd0`）。
- `adb install` 被 Play 安全防護擋下（`INSTALL_FAILED_VERIFICATION_FAILURE`，理由是「專為舊版 Android 打造」）。
- 由使用者自己關掉 Play 安全防護後安裝成功。實際套件名是 **`com.rosrobot`**，跟 Play 商店上的不同。
- Claude 沒有替使用者改安全設定，只讀取了 `verifier_verify_adb_installs=1` 來判斷狀態。

### 連車與除錯

- 用 `ycar.py gui` 在容器背景啟動三個程式：`yahboomcar_bringup_launch.py`、`map_gmapping_app_launch.xml`（內含 rosbridge 9090）、`usb_cam camera.launch.py`。
- App 設定：IP `10.57.201.1`、改選 **ROS2**、Video Topic 用預設 `/usb_cam/image_raw/compressed`。連上後影像與搖桿正常。
- 地圖空白的根因：ESP32 時鐘比 Pi 慢 **7903 秒**（約 2 小時 12 分），gmapping 把 `/scan` 全部當過期丟掉。使用者按 ESP32 Reset 後兩邊只差約 1 秒，`/map` 約 0.49 Hz 更新，App 地圖正常顯示。
- 按 Reset 期間手機的 `nc` 轉接死掉，已重開兩個 `nc -L` 和 `adb forward`。

### 釐清 App 用到的節點與話題（`ros2 node info /rosbridge_websocket` 實查）

- 車 → 手機：`/usb_cam/image_raw/compressed`、`/map`、`/scan_points`（`laserscan_to_point_publisher` 把 LaserScan 轉成 Path）、`/robot_pose`（`robot_pose_publisher`）。
- 手機 → 車：`/cmd_vel`。
- 服務：`/yahboomAppSaveMap`（`yahboom_app_save_map` 的 `/minimal_service`）。
- 使用者問的「三個」：連線畫面的三個 Video Topic 選項（usb_cam／camera/rgb／csi），這台只有 usb_cam 有資料。
- App 選單只有「建图」「导航」兩個模組（`uiautomator dump` 確認）。

### 收尾

- 依使用者要求停掉三個程式。`ycar.py kill <launch>` 只殺掉 `ros2 launch` 本身，**12 個子程式變孤兒**繼續跑，改用 PID 個別 `kill -TERM`。`rosbridge_websocket` 收到 TERM 不會結束，最後用強制結束才停。

## 關鍵技術筆記

- 官方 APK 的位置：`yahboom.net/study/MicroROS-Pi5` →「Mapping_APP(iOS_Android)」→ Google Drive 資料夾 `1f25ErWgtyv9w0pSxEO0E7r575RcmiKlX`。
- Android 14 以上的新手機：裝舊 targetSdk 的 APK 會被 Play 安全防護擋下，要由使用者自己暫時關掉防護。
- micro-ROS 的時間戳由 ESP32 提供，Pi 校時後兩邊可能差好幾小時。SLAM 或 TF 出現「earlier than all the data in the transform cache」時，先比對 `date +%s` 和 `/scan` 的 header.stamp，按 Reset 就能修好。
- 停 launch 後要用 `ps` 檢查孤兒程式。`ros2 node list` 會被 ros2-daemon 快取騙到。
- App 搖桿的速度不受語音 0.15 m/s 上限保護。

## 產出檔案

| 檔案 | 說明 | commit |
| --- | --- | --- |
| `drill/ROSROBOT-APP.md` | App 安裝、設定、車上程式、節點話題對照、踩坑、待辦 | `8245d09` |
| `drill/ROSROBOT-APP.md`（補充） | 正確的停止方法（孤兒子程式） | `a401081` |
| `summary-02-sessions/2026-10-27/session1-summary.md` | 本摘要 | 收工 commit |

APK 暫存在 scratchpad（不進 git）。

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] 確認使用者已把手機的 Play 安全防護重新打開（裝 App 時由使用者自己關掉）
- [ ] 若要繼續玩 App：照 `drill/ROSROBOT-APP.md` 第 4 節啟動三個程式，用搖桿掃地圖，按「保存地图」，再把地圖從容器備份到 PC（容器有 `--rm`）
- [ ] 試導航：把建圖 launch 換成 `navigation_dwb_app_launch.xml`，在 App 用「设置初始点／导航点」

### 進行中（需接續）

- App 已裝好並驗證可連線。車上三個程式已全部停掉，容器只剩 ros2-daemon，`/YB_Car_Node` 正常。
- 地圖還沒掃，也還沒存；導航和搖桿最高速都還沒實測。

### 注意事項

- 每次開車前先比對 ESP32 和 Pi 的時鐘。差很多就按 ESP32 Reset，按完要重開手機的 `nc` 轉接。
- `ycar.py kill <launch 名>` 不會一併收掉子程式，要用 `ps` 檢查後依 PID 處理。rosbridge 要強制結束才停得下來。
- App 套件名是 `com.rosrobot`，不是 Play 商店那個 `make_a_map.kinetic`。
- 用 App 開車時，不要同時跑語音指令或鍵盤（`/cmd_vel` 只能有一個來源）。
- App 搖桿的速度不受語音 0.15 m/s 上限保護，第一次請輕推。
