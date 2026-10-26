# Yahboom MicroROS-Pi5 學習規劃

給「手上只有一台車、完全沒碰過 ROS」的人。分四級，共 19 個單元，每單元有：目標、預估時間、要不要真車、操作步驟、完成標準、對應官方影片與文件。

## 這台車是怎麼組成的（一句話版）

**Pi 5 是大腦、ESP32 是小腦**：ESP32 擴充板跑 micro-ROS，直接控制 4 顆編碼馬達、IMU、蜂鳴器、雲台舵機，並轉發 MS200 光達資料；它用 USB 序列線（`/dev/ttyUSB0`）接到 Pi 5。Pi 5 上用 Docker 跑兩個東西：**micro-ROS agent**（把 ESP32 接進 ROS 2 網路的翻譯官，`sh ~/start_agent_rpi5.sh`）和 **ROS 2 Humble 容器**（裝好所有 `yahboomcar_*` 套件，`sh ros2_humble.sh` 進入）。

```
手機 App / 手把 / 鍵盤 / 電腦 RViz
            │  WiFi（ROS_DOMAIN_ID=20）
┌──────── Raspberry Pi 5（Raspberry Pi OS）────────┐
│  Docker：ROS 2 Humble 容器（yahboomcar_* 套件）   │
│  Docker：micro-ROS agent                          │
└──────────────┬───────────────────────────────────┘
               │ USB 序列 /dev/ttyUSB0
┌──────── ESP32-S3 擴充板（micro-ROS 韌體，節點 /YB_Car_Node）────┐
│ 訂閱 /cmd_vel /beep /servo_s1 /servo_s2                          │
│ 發布 /imu /odom_raw /scan                                        │
└── 4×編碼馬達  IMU  蜂鳴器  雲台舵機  MS200 光達 ─────────────────┘
相機（2MP USB）直接接 Pi 5，由容器內 usb_cam 發布影像。
```

預設值：熱點 `Micro_ros`／`12345678`、熱點 IP `10.42.0.1`、帳號 `pi`／`yahboom`、`ROS_DOMAIN_ID=20`。

## 四級課程總覽

| 級別 | 單元 | 主題 | 時間 | 要真車 |
| --- | --- | --- | --- | --- |
| 0 暖身 | W1 | 認識這台車：硬體與三層架構 | 30 分 | 否 |
| 0 暖身 | W2 | ROS 2 最小必學：節點、話題、服務、參數（turtlesim） | 90 分 | 否 |
| 0 暖身 | W3 | Linux、SSH 與 Docker 速成 | 60 分 | 否 |
| 0 暖身 | W4 | 在電腦上看這台車：URDF、RViz、TF | 60 分 | 否 |
| 1 初級 | B1 | 開箱、組裝與電池安全 | 2 小時 | 是 |
| 1 初級 | B2 | 開機連線：熱點、WiFi、VNC、SSH | 45 分 | 是 |
| 1 初級 | B3 | micro-ROS agent 與 Docker 容器：第一次看到車的節點 | 45 分 | 是 |
| 1 初級 | B4 | 遙控：App、手把、鍵盤 | 45 分 | 是 |
| 1 初級 | B5 | 讀懂車的話題：手動發 /cmd_vel、聽 /imu、/odom_raw、/scan | 60 分 | 是 |
| 1 初級 | B6 | 狀態估測與校準：EKF、線速度與角速度校準、URDF | 60 分 | 是 |
| 2 中級 | M1 | OpenCV 基礎與 ROS 影像話題 | 90 分 | 部分（webcam 可練） |
| 2 中級 | M2 | MediaPipe：手、臉、姿態偵測 | 60 分 | 否（webcam 可練） |
| 2 中級 | M3 | 視覺互動：顏色追蹤、人臉追蹤、巡線、QR、手勢控車 | 2 小時 | 是 |
| 2 中級 | M4 | 光達應用：避障、跟隨、警衛、巡邏 | 90 分 | 是 |
| 2 中級 | M5 | 寫自己的第一個控制節點（Python） | 90 分 | 部分（模擬可練） |
| 3 高級 | A1 | SLAM 建圖：Gmapping、Cartographer、App 建圖 | 2 小時 | 是（模擬可練觀念） |
| 3 高級 | A2 | Nav2 自主導航 | 2 小時 | 是（模擬可練觀念） |
| 3 高級 | A3 | 多機協作：namespace、多車遙控與導航 | 90 分 | 是（需兩台） |
| 3 高級 | A4 | ESP32 與 micro-ROS 韌體開發 | 4 小時以上 | 開發板即可 |
| 3 高級 | A5 | 電腦與車互通：DDS、ROS_DOMAIN_ID、Humble 與 Jazzy | 60 分 | 是 |

建議節奏：暖身 1 週（車子到貨前）→ 初級 1 週 → 中級 2 週 → 高級 3 週以上。

## 每單元的完成標準（摘要）

- **W1**：能畫出 Pi 5、Docker、ESP32 三層和各自負責什麼。
- **W2**：能用 `ros2 node list`、`ros2 topic echo`、`ros2 topic pub` 讓小烏龜轉圈。
- **W3**：能 SSH 進一台 Linux、用 `docker ps`、`docker exec -it` 進容器。
- **W4**：在 RViz 看到這台車的模型並拖動關節。
- **B1**：組好車、充飽電、知道電池安全規則。
- **B2**：電腦連上車的熱點，VNC 看到桌面、SSH 能登入。
- **B3**：容器內 `ros2 node list` 看到 `/YB_Car_Node`。
- **B4**：用三種方式遙控車前後左右。
- **B5**：用 `ros2 topic pub /cmd_vel` 讓車原地轉一圈、`/beep` 叫一聲。
- **B6**：校準後直走 1 公尺誤差在 5 公分內。
- **M1～M3**：完成一個顏色追蹤（雲台會跟著顏色轉）。
- **M4**：車子自己避開障礙物繞行。
- **M5**：自己的 Python 節點讀 `/scan`、前方太近就停車。
- **A1**：建出客廳地圖並存檔。
- **A2**：在地圖上點一個目標，車自己走過去。
- **A3**：兩台車同時被一支手把控制。
- **A4**：在 ESP32 開發板上跑自己的 micro-ROS 發布節點。
- **A5**：在電腦的 RViz 看到車上的光達資料。

## 版本提醒

車上是 **ROS 2 Humble**（在 Docker 內）；這台電腦的 WSL 是 **ROS 2 Jazzy**。暖身單元用 Jazzy 練，指令幾乎相同；差最多的是 Gazebo（Humble 用 Gazebo Classic，Jazzy 用 gz sim）和網路設定（WSL 要用 mirrored 網路才看得到車）。

## 資料來源

- 官方文件：`official/`（GitHub YahboomTechnology/MicroROS-Car-Pi5，155 份 PDF；文字版在 `research/pdf-text/`）
- 官方影片：播放清單 PL6KtTPU_PfxpQAITcWXgn978DXj3mskCJ（56 支），逐字稿在 `videos/transcripts/`
- 研究筆記：`research/notes/`（A 入門與控制、B 視覺、C1 光達、C2 系統、D ROS 2 基礎、E ESP32 與 micro-ROS）
- 原始碼：Google Drive「18. Summary of program source code」（`source-code/`）
