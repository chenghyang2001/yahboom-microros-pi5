# 手機 App「ROS Robot」連車紀錄（2026-10-27）

Yahboom 官方手機 App **ROS Robot** 的安裝方式、連線設定、車上要跑的程式，以及 App 透過 rosbridge 用到哪些 ROS 節點與話題。這份紀錄是 2026-10-27 實際裝到手機（OPPO CPH2699，Android 16）並連上車後整理的。

## 1. 目前狀態（2026-10-27 13:10）

| 項目 | 狀態 |
| --- | --- |
| App | 已安裝，套件名 `com.rosrobot` |
| 連線 | 「已连接」：`ws://10.57.201.1:9090` |
| 攝影機畫面 | 正常，即時顯示 |
| 搖桿 | 已出現，**還沒實際開車** |
| 地圖 | 正常（gmapping 約 0.5 Hz 更新），**還沒掃完整，也還沒存檔** |
| 導航 | 還沒試 |
| 車上程式 | 三個 launch 在容器 `e576bc1f3677` 背景執行中（見第 4 節） |

## 2. 安裝 App

### 從哪裡下載

- Play 商店有上架（套件名 `com.github.rosjava.android_apps.make_a_map.kinetic`），但在這支手機上顯示「僅適用於其他裝置」，**搜尋也找不到**。
- 改用官方 APK：Yahboom 官網 [MicroROS-Pi5 頁面](https://www.yahboom.net/study/MicroROS-Pi5) 的「Mapping_APP(iOS_Android)」連結，指向官方 Google Drive 資料夾，裡面有 `Yahboom-ROSROBOT.apk`。
  - 大小 10,509,201 bytes，上傳日期 2024-10-22
  - SHA256 `da29458246db01443ebfc33971ce31452e465aa378b05036f7a99bb785206cd0`
  - 裝好後的套件名是 **`com.rosrobot`**，和 Play 商店那個不同。

### 安裝時被 Play 安全防護擋下

```bash
adb -s 84bbb261 install Yahboom-ROSROBOT.apk
# Failure [INSTALL_FAILED_VERIFICATION_FAILURE]
# 手機跳出「已封鎖不安全的應用程式：這個應用程式是專為舊版 Android 打造」
```

解法：由使用者自己在手機上暫時關閉 Play 安全防護（Play 商店 → 頭像 → Play 安全防護 → 齒輪 → 關閉「使用 Play 安全防護掃描應用程式」），裝完後**再打開**。App 已經裝好，重新打開防護不影響使用。

## 3. App 連線設定

打開 App 會跳出「输入机器人IP」對話框：

| 欄位 | 填什麼 |
| --- | --- |
| 語言 | `zh`（簡中）或 `en` |
| IP 地址 | `10.57.201.1`（車子在手機熱點上的 IP） |
| ROS 版本 | **ROS2**（預設是 ROS1，一定要改） |
| Video Topic | `/usb_cam/image_raw/compressed`（預設第一個，不用改） |

按「连接」。

### Video Topic 的三個選項

使用者看到的「三個」就是這裡。它們是**三種不同攝影機的影像話題**，App 一次只訂閱一個：

| 選項 | 對應的攝影機 | 這台車 |
| --- | --- | --- |
| `/usb_cam/image_raw/compressed` | USB 攝影機（`usb_cam` 套件） | ✅ **有**，這台用這個 |
| `/camera/rgb/image_raw/compressed` | 深度攝影機（如 Astra）的彩色畫面 | ❌ 沒有這個話題 |
| `/csi/image_raw/compressed` | 樹莓派 CSI 排線攝影機 | ❌ 沒有這個話題 |

App 是 Yahboom 多款車共用的，所以列出各種攝影機。MicroROS-Pi5 只有 USB 攝影機，選後兩個不會有畫面。

## 4. 車上要跑的程式

全部在 ROS 容器裡跑，三個缺一不可。這次用 `ycar.py gui` 在背景啟動（log 在容器內 `/tmp/gui_*.log`）：

```bash
cd drill
export YCAR_PASS=yahboom PYTHONUTF8=1
python ycar.py gui "ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py"   # 1. 底層：里程計、IMU 融合、TF
python ycar.py gui "ros2 launch yahboomcar_nav map_gmapping_app_launch.xml"       # 2. App 建圖（含 rosbridge）
python ycar.py gui "ros2 launch usb_cam camera.launch.py"                          # 3. 攝影機
```

要玩**導航**時，把第 2 個換成 `ros2 launch yahboomcar_nav navigation_dwb_app_launch.xml`（同樣內含 rosbridge）。

停止（只停這三個，不動 micro-ROS agent）：

```bash
python ycar.py kill map_gmapping_app_launch
python ycar.py kill usb_cam
python ycar.py kill yahboomcar_bringup_launch
```

## 5. App 用到的節點與話題

App 本身不懂 ROS，它透過 WebSocket 連到車上的 **`/rosbridge_websocket`** 節點，由這個節點代為訂閱和發布。下表是 2026-10-27 用 `ros2 node info /rosbridge_websocket` 實際查到的。

### rosbridge 代 App 收的資料（車 → 手機）

| 話題 | 型別 | 誰發出來 | 在 App 上的用途 |
| --- | --- | --- | --- |
| `/usb_cam/image_raw/compressed` | `sensor_msgs/CompressedImage` | `/camera1`（usb_cam） | 「视频」區的即時影像 |
| `/map` | `nav_msgs/OccupancyGrid` | `/slam_gmapping` | 地圖底圖（白＝空地、灰＝未知、黑＝牆） |
| `/scan_points` | `nav_msgs/Path` | `/laserscan_to_point_publisher` | 地圖上的**橘色點**：光達目前掃到的障礙物 |
| `/robot_pose` | `geometry_msgs/PoseStamped` | `/robot_pose_publisher` | 地圖上**車子的位置和朝向** |

### rosbridge 代 App 發的指令（手機 → 車）

| 話題 | 型別 | 用途 |
| --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/Twist` | 「机器人控制」搖桿的速度指令，和手把、鍵盤、語音用的是同一個話題 |

### 服務

| 服務 | 誰提供 | 用途 |
| --- | --- | --- |
| `/yahboomAppSaveMap` | `/minimal_service`（`yahboom_app_save_map` 套件） | 「保存地图」按鈕。地圖存到容器內 `/root/yahboomcar_ws/src/yahboomcar_nav/maps/<名稱>.pgm/.yaml` |

### 幾個專門給 App 的轉接節點

ROS 原生資料不好直接在手機上畫，所以官方加了兩個小節點：

- **`/laserscan_to_point_publisher`**：把光達的 `/scan`（LaserScan，一圈距離值）轉成 `/scan_points`（一串座標點），手機只要照座標畫點。
- **`/robot_pose_publisher`**：從 TF 算出車子在地圖上的位置，發成 `/robot_pose`，手機不用自己算 TF。

### 整體資料流

```
                    ┌──────────── 車上 Docker 容器 ────────────┐
光達 /scan ─┬─► /slam_gmapping ──► /map ─────────────┐         │
            └─► /laserscan_to_point_publisher ─► /scan_points ─┤         │
TF ────────────► /robot_pose_publisher ──► /robot_pose ────────┤         │
USB 攝影機 ────► /camera1 ──► /usb_cam/image_raw/compressed ───┤         │
                                                           /rosbridge_websocket ◄══ WebSocket 9090 ══► 手機 App
/YB_Car_Node（ESP32 馬達）◄── /cmd_vel ◄───────────────────────┘         │
                    └──────────────────────────────────────────┘
```

## 6. App 有哪些功能

選單只有兩個模組（用 `uiautomator dump` 確認）：

| 模組 | 功能 |
| --- | --- |
| **建图** | 攝影機影像、搖桿開車、即時地圖、保存地圖 |
| **导航** | 載入存好的地圖 → 「设置初始点」標出車子目前位置 → 「设置导航点」點目的地 → 車子自己規劃路線開過去 |

App **沒有**的功能：蜂鳴器、雲台、燈光、電池電量、語音。

## 7. 這次踩到的坑

1. **地圖一片空白**：ESP32 的時鐘比 Pi 慢約 2 小時 12 分（7903 秒），gmapping 把光達資料當成過期全部丟掉（log：`Message Filter dropping message ... earlier than all the data in the transform cache`）。
   - 檢查：比對 Pi 的 `date +%s` 和 `ros2 topic echo --once /scan --field header.stamp`。
   - 解法：按 ESP32 擴展板的 **Reset**，重連時會重新對時。按完兩邊只差約 1 秒，地圖就出來了。
   - 推測原因：ESP32 開機時跟 Pi 對時，之後 Pi 才透過網路校正時間。
2. **按 Reset 後 SSH 轉接斷了**：手機上的 `nc -L` 轉接程式不見了，`ycar.py` 回「連不上 127.0.0.1:8022」。照 `NEW-PC-SETUP.md` 4-2 重開兩個 `nc` 和 `adb forward` 就好。
3. **`127.0.0.1:7896` 那台 adb 裝置**不是模擬器，是透過手機轉接到熱點上另一台裝置（`10.57.201.101`）的連線，跟連車無關。

## 8. 安全提醒

- App 搖桿的速度**不受**語音指令 0.15 m/s 上限保護。第一次請輕推，放開搖桿車子就會停；緊急時用手把 R1 接管。
- 同一時間只能有一個來源發 `/cmd_vel`。用 App 開車時，不要同時跑語音指令或鍵盤控制。

## 9. 下一步（尚未做）

- [ ] 用搖桿把房間掃一圈，按「保存地图」
- [ ] 把地圖從容器備份到 PC（容器有 `--rm`，關掉就沒了）
- [ ] 換成導航 launch，試「设置初始点／导航点」
- [ ] 實測搖桿推到底的最高速度（同時 `ros2 topic echo /cmd_vel`）
