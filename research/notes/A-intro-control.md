# 研究筆記 A：入門介紹、前置準備、快速上手、機器人控制、多機課程

> 範圍：`01.Introduction/`、`03.Preparation/`、`04.Quick start control course/`、`05.Robot control/`、`10.Multi-machine course/`（共 28 個檔案，全部讀完）。
> 資料來源是官方英文 PDF 的機器翻譯文字，有些用語怪（Yahboom 被譯成「Yabo」、servo 被譯成「steering gear」、gimbal 被譯成「PTZ」），本筆記已還原。表格版面被 PDF 轉文字弄亂的地方，會明講「原文表格錯亂，依上下文推定」。
> 截圖與接線圖沒有轉成文字，凡是文件寫「如下圖所示」的畫面只能依文字描述推測。

---

## 1. 本區概覽

- 這一區是「讓車先動起來」的實作入門：認識硬體 → 連上 WiFi/VNC → 啟動 micro-ROS agent → 進入 Docker 容器 → 用手把、鍵盤、手機 APP 遙控 → 讀感測器、校正里程、看 URDF 模型 → 兩台車協同。
- **系統架構（最重要）**：ESP32-S3 擴充板（跑 micro-ROS client，管馬達/IMU/雷達/舵機）透過 USB 序列線（`/dev/ttyUSB0`）接到 Pi 5；Pi 5 上用 Docker 跑 `micro-ros-agent` 當橋樑，把 ESP32 上的話題轉成真正的 ROS 2 網路；另一個 Docker 容器（用 `ros2_humble.sh` 進入）裡才是裝好 `yahboomcar_*` 套件的 ROS 2 Humble 工作環境。
- 原廠把「agent」與「容器」都設成開機自動啟動，還預設自動啟動手把控制，所以開機後 VNC 桌面上會看到兩個終端機視窗。
- 官方建議：先做實作課讓車跑完所有案例，再回頭學理論課（Linux、Pi 5 設定、Docker、ROS 2 基礎、micro-ROS 開發環境、ESP32 基礎）。
- 幾乎每一課開頭都警告：**Pi 5（容器）與 micro-ROS 控制板的 `ROS_DOMAIN_ID` 必須一致（預設 20）**，否則看不到車的節點。

---

## 2. 逐課筆記

指令位置標記：

- 【Pi 5 本機】= 在車上 Pi 5 的桌面/終端機（透過 VNC 或接螢幕）
- 【容器內】= 在 `sh ros2_humble.sh` 進入的 Docker 容器終端機
- 【電腦/虛擬機】= 官方附贈的 Ubuntu 虛擬機或自己的電腦
- 【Windows】= 你的 Windows 電腦

---

### 01.Introduction / 1. ReadMe - learning route（學習路線）

- 教材分兩半。實作課：快速上手控制、機器人控制、ROS+OpenCV、Mediapipe 視覺辨識、機器人視覺互動、雷達使用、多機玩法；上這些之前必須先做完「開發前準備」（本區 03）。理論課：Linux、Pi 5 基本設定、Docker 開發環境、ROS 2 基礎、micro-ROS 控制板開發環境建置、ESP32 基礎範例、micro-ROS 基礎範例，依需求選修。
- 官方建議先實作、再理論。這與我們「初級（先動起來）→ 中級 → 高級」的順序一致。

---

### 01.Introduction / 2. Introduction to lidar（MS200 雷達介紹）

**學到什麼**：雷達（LiDAR）用光的「飛行時間」（TOF）量距離，單線雷達每圈 360 度在各角度量一個距離，產出 `/scan`（`sensor_msgs/LaserScan`）。
**硬體**：MS200 單線 TOF 雷達，接在 ESP32 擴充板的「Radar interface」。

規格（原文表格欄位嚴重錯位，以下依上下文與數值合理性重組，標「推定」者請以規格書確認）：

| 項目 | 數值 |
| --- | --- |
| 量測範圍 | 0.03 m ~ 12.0 m（90% 反射率） |
| 量測精度 | 典型 ≤4 mm（0.2~2.0 m）、≤15 mm（2.0~12.0 m）（推定） |
| 掃描角度 | 360° |
| 取樣率 | 4500 點/秒 |
| 掃描頻率 | 10 Hz |
| 角解析度 | 0.8° @10Hz |
| 雷射發射俯仰角 | 0.5°~2°（以雷達底座為基準，推定） |
| 雷射零位方位角 | 0±2°（推定） |
| 工作電壓 | DC 5.0±0.5 V（4.5~5.5 V） |
| 工作溫度 | -10℃ ~ 50℃（典型 25℃） |
| 工作電流 | 典型 260 mA；啟動電流 < 500 mA |
| 尺寸／重量 | 37.7 × 37.5 × 33.0 mm（長×寬×高）；約 40 g |
| 壽命 | 無刷直流馬達 > 10,000 小時 |
| 序列埠 | 230400 baud，8 資料位元、1 停止位元、無同位、無流控 |

接腳（4 pin）：1 Tx（0~3.3V）、2 Rx（0~3.3V）、3 GND、4 VCC（DC 5V）。（原文把 Rx 與電源描述錯位，依常識整理。）
**注意**：雷達接在 ESP32 的 UART1（TXD1=GPIO17、RXD1=GPIO18），不是直接接 Pi 5；所以 `/scan` 是由 micro-ROS 節點發布。

---

### 01.Introduction / 3. Introduction to microROS control board（micro-ROS 控制板介紹）

**學到什麼**：這塊板子是「輕量 ROS 2 驅動控制器」，本質是 ESP32-S3 雙核開發板，加上馬達驅動、舵機驅動、六軸 IMU。出廠已燒好韌體，插電就能接 ROS 2。
**板上資源**：

- 7.4V 電池接口（T 型）、充電孔（DC 8.4V 充電器）、總電源開關。
- Reset 鍵（ESP32-S3 重置）、BOOT 鍵（也可當自訂按鍵）、自訂按鍵 KEY1。
- 雷達介面（MS200）、馬達介面（4 路編碼馬達，文件寫「310 編碼馬達」；你的資料寫 370，以實物標示為準）、2 路 PWM 舵機介面（雲台）。
- 兩個 Type-C：標 **Serial** 用於通訊/設定/燒錄；標 **5V OUT** 用來供電給 Pi 5（PD 供電）。
- 天線介面、有源蜂鳴器（低電壓警報）、電源燈、MCU 燈、D1/D2 自訂燈、六軸 IMU、自訂 GPIO（GPIO35、GPIO36）。

GPIO 對照表：

| 週邊 | GPIO |
| --- | --- |
| M1 PWM A/B；編碼 H1A/H1B | 4/5；6/7 |
| M2 PWM A/B；編碼 H2A/H2B | 15/16；47/48 |
| M3 PWM A/B；編碼 H3A/H3B | 9/10；11/12 |
| M4 PWM A/B；編碼 H4A/H4B | 13/14；1/2 |
| BOOT | GPIO0 |
| 自訂按鍵 KEY1 | GPIO42 |
| 電池電壓偵測 BAT | GPIO3 |
| MCU 燈 LED | GPIO45 |
| 蜂鳴器 | GPIO46 |
| 舵機 S1 / S2 | GPIO8 / GPIO21 |
| IMU 中斷 INT | GPIO41 |
| IMU I2C SCL / SDA | GPIO39 / GPIO40 |
| 雷達 TXD1 / RXD1（UART1） | GPIO17 / GPIO18 |
| Type-C 燒錄串口 TXD0 / RXD0 | GPIO43 / GPIO44 |
| 自訂 GPIO | GPIO35、GPIO36 |

「Expansion board wiring diagram」是圖片，文字檔無內容。

---

### 01.Introduction / 4. FAQ（常見問題）

這課濃縮了許多除錯知識：

1. **為什麼要設定參數？** 每人的 WiFi 環境與 IP 不同。
2. **樹莓派版與虛擬機/電腦版差別？** 韌體相同，靠「設定參數」區分。**樹莓派版走序列埠（USB 線）；虛擬機/電腦版走 WiFi-UDP。**
3. **樹莓派版設定完讀寫不到設定？** 按板子 Reset，開機 5 秒內處於「設定狀態」（MCU 燈每 300 ms 閃一次），此時執行設定檔才能讀寫。
4. **兩個 Type-C 差別？** Serial：通訊/設定/燒錄；5V OUT：供電給 Pi 5。
5. **蜂鳴器一直嗶嗶響？** 電量低（每 100 ms 響一次），此時機器人**無法控制**，要存檔、關機、充電。
6. **MCU 狀態燈：**

| 狀態 | LED 現象 |
| --- | --- |
| 設定狀態（開機後約 5 秒） | 每 300 ms 閃一次 |
| 連線 agent 狀態 | 慢閃，每 1 秒一次 |
| micro-ROS 錯誤 | 快閃，每 50 ms 一次 |
| 正常狀態 | 每 3 秒快閃 2 次 |
| 低電壓 | 快閃，每 100 ms 一次 |

   流程：開機 → 設定狀態（約 5 秒）→ 自動進入連線 agent 狀態 → agent 連上後初始化 ROS 話題 → micro-ROS 出錯會自動結束 micro-ROS 任務 → 初始化完成進入正常狀態。
7. **同一區網多台機器人怎麼避免干擾？** 設不同的 `ROS_DOMAIN_ID`（0~101）：修改 `config_robot.py` 的 `set_ros_domain_id(20)` 並寫入控制板；再於電腦/虛擬機使用者目錄 `.bashrc` 加一行 `export ROS_DOMAIN_ID=20`，存檔後重開終端機。
8. （第 8 題問題句在 PDF 轉換時遺失，只剩答案）答案：**再按一次 Reset 鍵重新連接 agent。** 推測問的是「agent 沒連上/斷線怎麼辦」。
9. **開 micro-ROS agent 報錯？** agent 只能在**一個**終端機開；背景已有就會報錯，先在原終端機 Ctrl+C。若 agent 異常關閉造成 docker 行程殘留：

```bash
# 【Pi 5 本機】查出殘留的 agent 容器
docker ps -a | grep microros/micro-ros-agent
# 停掉它（xxxxxxxxxx 換成實際容器 ID）
docker stop xxxxxxxxxx
# 重新手動啟動 agent（這是 UDP 版，連接埠 8090，對應虛擬機/電腦 WiFi-UDP 版）
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4
```

**重要觀察**：這條 `micro-ros-agent:humble udp4 --port 8090` 是 UDP 版。Pi 5 序列版走的是 `~/start_agent_rpi5.sh`（內容文件沒給，推測是 `serial --dev /dev/ttyUSB0` 版本，需實車讀取確認）。

---

### 01.Introduction / 5. About charging（充電與電池安全）

**重點規則**：

- 只能用原廠電池與充電器；不可接超過負載的設備。
- **充電時必須關閉擴充板總電源開關，不可邊充邊用**。蜂鳴器響（低電）就關機充電。
- 充電器紅燈 = 充電中；綠燈 = 充飽。充電要有人看著，充飽盡快拔掉。
- 久放不用：電池電壓保持約 7V，取出電池放安全區，勿與金屬物混放，外層絕緣膜不可撕。
- 使用環境 0℃~35℃；遠離熱、火、液體、潮濕；禁止穿刺、短路、反接、擅自焊接、撞擊、擠壓。
- 電池冒煙/發熱：立即切斷總開關、拔充電器、把電池放空曠處；起火用沙或乾粉滅火器。
- 不可擅自改裝電路板；兒童須成人監督。

**電池規格**：標稱 7.4V；供電電壓 5.6V~8.4V；容量 2000mAh；2 顆 18650；額定電流 15A（7.5C）；最大放電 20A（10C）；過充/過放/過流/短路保護；約 115g；67×37×22 mm；放電線 15 cm（AWG14）；充電線 10 cm。
**充電步驟**：充電器插插座（綠燈）→ 關機器人總開關 → 充電頭插擴充板充電孔（轉紅燈）→ 亮綠燈即充飽 → 拔下。

`MicroROS-Pi5_Manual.txt` 是空檔（15 bytes，無內容）。

---

### 03.Preparation / 1. Write firmware（燒錄韌體）

**這課在做什麼**：用 Windows 電腦把原廠韌體 `.bin` 燒到 ESP32-S3。**出廠已燒好，沒燒過其他韌體就不必做**。原廠只提供 bin，不提供原始碼。
**ROS 觀念**：無（嵌入式工具操作）；但要知道「韌體」就是跑在 ESP32 上的 micro-ROS client。
**硬體**：控制板（Serial Type-C 口）、Windows 電腦、Type-C 資料線。

步驟（【Windows】）：

1. 安裝 CP2102 序列埠驅動（已裝可跳過）。檔案在隨附資料「Hardware related information → CP2102 serial port chip → CP2102-Windows driver file.zip」，解壓後依系統選 x64/x86，64 位元雙擊 `CP210xVCPInstaller_x64.exe` → Next → 顯示「Ready for use」→ Finish。用 Type-C 線接 Serial 口到電腦，「裝置管理員 → 連接埠」出現 CP210x 即成功。
2. 下載 Espressif Flash Download Tool：`https://www.espressif.com.cn/zh-hans/support/download/other-tools`；解壓得 `flash_download_tool`，雙擊開啟，晶片選 **ESP32-S3**。
3. 設定：SPIDownload 選 `microROS_Robot_Vx.x.x.bin`（Vx.x.x 為版本號），**位址填 `0x0`**，勾選 **DoNotChgBin**，選 COM 埠，其餘預設。

| 韌體名稱 | 位址 | 備註 |
| --- | --- | --- |
| microROS_Robot_Vx.x.x.bin | 0x0 | 原廠韌體 |

1. 按 Start。若沒自動開始：**先按住 BOOT0 鍵，再按 Reset，放開 BOOT0**，手動進入燒錄模式。
2. 完成出現藍色 FINISH；斷電重啟或按 Reset 開始執行。
3. 驗證：用序列埠助手（隨附 `UartAssist.exe`），選控制板的埠，**115200**、8 資料位元、1 停止位元、無同位、無流控；按 Reset，在輸出中找 **`hello Yahboom`**，下一行是韌體版本號，正確即成功。

**坑**：沒進燒錄模式（要手動 BOOT+Reset）；驅動沒裝好看不到 COM 埠；忘了勾 DoNotChgBin 或位址不是 0x0。

---

### 03.Preparation / 2. microROS control board configuration parameters（控制板設定參數）

**這課在做什麼**：用 Pi 5 上的 `config_robot.py` 把「車型、ROS_DOMAIN_ID、（多機時的 namespace）、舵機初始角度、馬達 PID」寫進控制板。出廠已設好，**通常不需重設**。
**ROS 觀念**：`ROS_DOMAIN_ID`（相同 ID 的節點才互相看得到）；序列埠通訊。
**硬體**：Pi 5、控制板、兩者間的 USB 序列線（接線圖為圖片）。

流程：

1. 若燒過其他範例韌體，先重燒原廠韌體再開電源。
2. 設定腳本 `config_robot.py` 在 Pi 5 家目錄（`/home/pi`）。
3. 開機後可連原廠熱點，用 VNC 遠端登入桌面。VNC Viewer 輸入 IP **`10.42.0.1`**（出廠預設），帳號 **`pi`**，密碼 **`yahboom`**。桌面上有兩個終端機：**自動啟動的 agent 連線介面**與**自動啟動的 docker 介面**。
4. 改設定前，先在 docker 終端機輸入 `exit` 離開 docker，並對 agent 終端機按 Ctrl+C。

```bash
# 【Pi 5 本機】確認序列裝置有被辨識
ls /dev/ttyUSB*
```

1. 編輯 `config_robot.py`（序列啟動模式）：**車型改為 `robot.CAR_TYPE_RPI5`**；ID 預設 20，一般不改；其他參數（舵機初始角度、馬達 PID）保持預設。
2. 短按控制板 Reset，**5 秒內**處於設定狀態（MCU 燈每 300 ms 閃一次），此時執行：

```bash
# 【Pi 5 本機】（多機課程寫成 sudo python3 config_robot.py，在 /home/pi 目錄）
python3 config_robot.py
```

   檢查回傳資料是否與設定一致，一致即成功。
7. 再按一次 Reset，重新載入設定。

**坑**：一定要在 Reset 後 5 秒內執行；要改成自己的 WiFi 請看「第 12 章 Pi 基本設定第 4 節」（不在本區）；原文兩個步驟都編號為 4。

---

### 03.Preparation / 3. Connect to microROS agent（連接 micro-ROS agent）

**這課在做什麼**：啟動「agent」讓 ESP32 上的 micro-ROS 節點接進 ROS 2 網路，再進入 Docker 容器操作車。
**ROS 觀念（白話）**：micro-ROS 是縮小版 ROS 2，跑在小型微控制器上；微控制器沒辦法直接加入 DDS 網路，需要 Pi 5 上的**代理人（agent）**把它說的話翻譯成一般 ROS 2 話題。沒有 agent，ESP32 就是孤島。
**硬體**：Pi 5 + 控制板（USB 序列線，裝置 `/dev/ttyUSB0`）。

```bash
# 1. 【Pi 5 本機】啟動 agent（序列版）
sh ~/start_agent_rpi5.sh
# 2. 打開車子電源開關 → 自動連上 agent（連上畫面為圖片）
# 3. 【Pi 5 本機】另開終端機，進入車載 Docker 容器
./ros2_humble.sh
# 4. 【容器內】測試通訊
ros2 node list
```

**預期結果**：看到 **`/YB_Car_Node`**。
**注意／坑**：

- 沒連上：先檢查 `/dev/ttyUSB0` 是否被辨識。
- 看不到 `/YB_Car_Node`：檢查容器內與控制板的 `ROS_DOMAIN_ID` 是否相同；不同就在容器內 `vi ~/.bashrc` 改成對應 ID。
- 本課寫 `./ros2_humble.sh`，其他課寫 `sh ros2_humble.sh`，兩者等效（腳本在 Pi 5 家目錄）。
- 開機時 agent 與容器**已自動啟動**，再手動開一個 agent 會衝突（FAQ #9）。

---

### 03.Preparation / 4. Connect to WIFI in hotspot mode（熱點模式下連自己的 WiFi）

**這課在做什麼**：車出廠自己開熱點，電腦要連車的熱點才能操作。這課教你讓 Pi 5 去連**你家 WiFi**，並找出它的 IP。

兩種方式：

1. **有螢幕**：接螢幕到 Pi 5 主板（需拆外殼），直接關熱點並連 WiFi。
2. **沒螢幕**（VNC 登入後）：
   ① 右上角 WiFi 圖示 → Advanced Options → Edit Connections...
   ② 左下角「+」→ Wireless，設定：SSID；General 勾選「Connect automatically with priority」並提高優先級，**建議 ≥ 2（熱點模式為 1，WiFi 優先級必須大於熱點）**；WiFi Security 有密碼選 WPA/WPA2/WPA3 Personal 並輸入密碼；儲存。
   ③ 重啟 Pi 5 會優先連此 WiFi。
   ④ 找 Pi 5 的 IP：等十幾秒後，打開官方提供的虛擬機：

```bash
# 【電腦/虛擬機】（需與車同一 WiFi 且 ROS_DOMAIN_ID 相同）
ros2 topic echo /rpi5_ip
```

   會看到目前的 WiFi IP；同一 WiFi 下有多台車會出現多個 IP，需自行辨識。
   ⑤ 知道 IP 後即可遠端登入 Pi 5。

**重點觀察**：車子會**發布 `/rpi5_ip` 話題**回報自己的 IP。
**坑**：優先級沒設比熱點高，重啟後仍回熱點模式。

---

### 03.Preparation / First Trial（第一次試玩）

**這課在做什麼**：簡化版快速試玩，搭配影片：手把控制、VNC 遠端、鍵盤控制、自動巡線。事前需照組裝教學裝好車，並接上 Type-C 資料線、手把接收器、USB 相機。

**一、手把控制**

- 開電源，約 30 秒開機後按手把 START 鍵，車蜂鳴器「嗶」一聲代表手把可用。
- 沒聲音：可能是韌體錯或 agent 沒連上。常見是 agent 沒連成功，可按控制板 RESET 等約 10 秒。最準確的解法是進 Pi 5 系統查看。
- 正式用手把前先按 **R1**。按鍵：左搖桿上/下 = 前進/後退；右搖桿右/左 = 右轉/左轉；X = 舵機向左；B = 舵機向右；A = 舵機向下；Y = 舵機向上。

**二、遠端控制（VNC）**

- VNC Viewer：`https://www.realvnc.com/en/connect/download/viewer/`。兩設備必須同一區網；車自帶熱點，電腦連上即同網。
- 熱點模式 Pi IP **`10.42.0.1`**；系統帳號 **`pi`** / 密碼 **`yahboom`**；**熱點名稱 `Micro_ros` / 密碼 `12345678`**。
- 想連自己的 WiFi：見 03-4。

**關閉開機自動手把控制**（開機會自動啟動 agent 與 docker 兩個終端機）：

```bash
# 暫時關閉（【Pi 5 本機】）
ps -A            # 列出所有行程，找手把相關行程 PID
kill -9 [PID]    # 強制終止
# 永久關閉（【Pi 5 本機】）
vi /home/pi/ros2_humble.sh
```

**三、鍵盤控車**

```bash
# 【Pi 5 本機】
sh ~/start_agent_rpi5.sh
# 【Pi 5 本機】另開終端機
sh ros2_humble.sh
# 【容器內】
ros2 node list
ros2 run yahboomcar_ctrl yahboom_keyboard
```

滑鼠必須停在執行鍵盤程式的終端機上才收得到按鍵。

**四、自動巡線**

```bash
# 【Pi 5 本機】
sh ~/start_agent_rpi5.sh
# 【Pi 5 本機】另開終端機
sh ros2_humble.sh
# 【容器內】
ros2 run yahboomcar_astra follow_line
```

相機畫面載入後按 **`R`** 選取路線（建議選顏色鮮豔的路線），選好後按**空白鍵**開始巡線。**預期**：車沿著所選顏色的線走（需在 VNC 桌面操作才看得到畫面）。

---

### 04.Quick start control / 1. Self start handle control（開機自動啟動手把控制）

**這課在做什麼**：說明出廠開機即可用無線手把遙控；以及當你把 `ROS_DOMAIN_ID` 改成非 20 時，要如何改自動啟動設定（會用到 `docker commit`）。
**ROS 觀念**：容器內有 `supervisor` 服務在開機時自動啟動手把節點（`joy_node` + `yahboom_joy`）。改過的容器要用 `docker commit` 存成新映像（image），並讓開機腳本改用新映像，否則重開機後修改會消失。
**硬體**：USB 手把接收器插 Pi 5、USB 相機、Type-C 資料線。

啟動與按鍵同 First Trial（開機約 30 秒，按 START 聽蜂鳴；沒聲音按 RESET 並等約 30 秒；用手把前先按 R1）。

**3. 在自己的環境（ID 非 20）下讓自動啟動仍有效**

```bash
# 3.1 【Pi 5 本機】進入容器
sh ros2_humble.sh
# 【容器內】確認手把已掛載
ls /dev/input*
# 3.2 【容器內】把 .bashrc 的 ROS_DOMAIN_ID 改成你的 ID（例如 20）
vi ~/.bashrc
# 3.3 【容器內】改自動啟動服務裡的 ID
vi /usr/lib/systemd/system/supervisor.service
# 3.4 【Pi 5 本機】另開終端機，查剛才修改的容器 ID
docker ps -a
# 把修改後的容器存成新映像（bfe7cdaccb2d 與映像名為文件範例）
docker commit bfe7cdaccb2d 192.168.2.51:5000/ros-humble:10.8
# 確認新映像存在
docker images
# 3.5 【Pi 5 本機】改開機腳本，使它改用你新提交的映像版本
vi ros2_humble.sh
# 存檔後重開機
```

**預期**：`ls /dev/input*` 顯示手把裝置；`docker images` 看到 `192.168.2.51:5000/ros-humble:10.8`。
**坑**：映像名稱 `192.168.2.51:5000/ros-humble:10.8` 是原廠本地 registry 標籤格式，實際以 `ros2_humble.sh` 裡的映像名為準；容器 ID 每次不同；原文把 `ROS_DOMAIN_ID` 誤譯為 `do_main_id`。

---

### 04.Quick start control / 2. Close the self-starting handle control process（關閉自啟動手把控制）

**這課在做什麼**：想自己手動執行手把控制程式，必須先關掉開機自啟的那份，不然兩份同時發布 `/cmd_vel` 會打架。

```bash
# 1. 【Pi 5 本機】
sh ~/start_agent_rpi5.sh
# 打開車子電源，等連上 agent
# 2. 【Pi 5 本機】另開終端機
sh ros2_humble.sh
# 【容器內】確認手把掛載
ls /dev/input*
# 4.1 暫時關閉：【容器內】
ps -A
# 找到手把控制節點與 joy 節點的 PID（文件範例為 171 與 173，實際每次不同）
kill -9 171
kill -9 173
# 4.2 永久關閉：【Pi 5 本機】
vi ros2_humble.sh
# 刪除其中的 /root/1.sh 指令即可關閉開機自啟；要恢復就加回去
```

**重點**：`/root/1.sh` 是容器啟動時呼叫的腳本，裡面啟動手把節點。
**坑**：PID 171/173 只是示範，以 `ps -A` 實際輸出為準；`kill -9` 強制終止。

---

### 04.Quick start control / 3. Quick start keyboard control（快速鍵盤控制）

**這課在做什麼**：查詢車的節點，用鍵盤驅動車。
**ROS 觀念**：連上 agent 後，車會發布雷達、IMU 等感測資料，也可接收速度、蜂鳴器等控制資料；可在 Pi 5 或虛擬機查詢。

```bash
# 【Pi 5 本機】
sh ~/start_agent_rpi5.sh
# 按控制板 reset 鍵等待連上 agent
# 【Pi 5 本機】另開終端機
sh ros2_humble.sh
# 【容器內】
ros2 node list
ros2 run yahboomcar_ctrl yahboom_keyboard
```

簡表：`i` 前進、`,` 後退、`l` 右旋轉、`j` 左旋轉、`u` 左轉、`o` 右轉、`m` 倒車左、`.` 倒車右。完整表見 05-2。

---

### 04.Quick start control / 4. APP mapping control（手機 APP 建圖）

**這課在做什麼**：用手機 App「**ROS Robot**」連到車，用虛擬搖桿慢慢開，同時用 gmapping（雷達 SLAM）建地圖，最後存地圖。
**ROS 觀念**：SLAM（同步定位與建圖）：車一邊移動一邊用雷達畫地圖；存成檔案後可給導航使用。
**硬體**：雷達、USB 相機、手機（與車同 WiFi）。

```bash
# 【Pi 5 本機】
sh ~/start_agent_rpi5.sh
# 按 reset，等連上
# 【Pi 5 本機】另開終端機
sh ros2_humble.sh
# 【容器內】
ros2 node list
# 【容器內】啟動底層資料處理
ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py
# 【Pi 5 本機】新開終端機，查容器 ID（最上面一筆是目前啟動的）
docker ps -a
# 【Pi 5 本機】用該 ID 進入「同一個」容器（ID 每次不同）
docker exec -it ef0e1b7da319 /bin/bash
# 【容器內（第二個終端機）】啟動手機 App 建圖
ros2 launch yahboomcar_nav map_gmapping_app_launch.xml
# 【容器內（第三個終端機，同樣用 docker exec 進入）】啟動相機
ros2 launch usb_cam camera.launch.py
```

手機 App：輸入車的 IP；[zh]=中文、[en]=英文；選 **ROS2**；影像話題選 **`/usb_cam/image_raw/compressed`**；按 Connect。連線後用滑動輪盤慢速走過要建圖的區域，按「儲存地圖」，輸入名稱後提交。
**地圖儲存位置（容器內）**：`/root/yahboomcar_ws/src/yahboomcar_nav/maps`
**坑**：這課第一次需要多個終端機進**同一個容器**——要用 `docker exec -it <容器ID> /bin/bash`，不是再跑 `sh ros2_humble.sh`（那會開新容器）。建完圖可接「手機 APP 導航」課（不在本區）。

---

### 05.Robot control / 1. Robot information release（機器人資訊發布）

**這課在做什麼（最適合初學者的 ROS 話題課）**：用 `ros2 node info`、`ros2 topic list/echo/info/pub` 看懂車在「說什麼」「聽什麼」，並手動發布指令控制蜂鳴器、速度、舵機。
**ROS 觀念**：節點（Node）、話題（Topic）、發布者/訂閱者、訊息型別、`ros2 topic pub`。

```bash
# 【Pi 5 本機】sh ~/start_agent_rpi5.sh ；開車電源等連上
# 【Pi 5 本機】另開
sh ros2_humble.sh
# 【容器內】
ros2 node list
ros2 node info /YB_Car_Node
ros2 topic list
# 查詢感測器資料
ros2 topic echo /scan
ros2 topic echo /imu
ros2 topic echo /odom_raw
```

`/YB_Car_Node` 訂閱：`/beep`（蜂鳴器）、`/cmd_vel`（車速）、`/servo_s1`、`/servo_s2`（雲台舵機）；發布：`/imu`、`/odom`、`/scan`（原文如此；但後續查詢用的是 `/odom_raw`，且 05-4 說 EKF 訂閱 `/odom_raw` 再輸出 `/odom`，**車本體實際發布應為 `/odom_raw`**，請實車驗證）。

```bash
# 蜂鳴器：先看型別，再發布
ros2 topic info /beep                                   # std_msgs/msg/UInt16
ros2 topic pub /beep std_msgs/msg/UInt16 "data: 1"      # 開
ros2 topic pub /beep std_msgs/msg/UInt16 "data: 0"      # 關
# 速度：線速度 0.5、角速度 0.2
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.2}}"
# 停車
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
# 雲台舵機（S1 範圍 [-90,90]；S2 範圍 [-90,20]，超出範圍舵機不動）
ros2 topic pub /servo_s1 std_msgs/msg/Int32 "data: 30"
ros2 topic pub /servo_s2 std_msgs/msg/Int32 "data: -30"
```

**預期**：蜂鳴器響/停；車移動；雲台轉到指定角度。
**坑**：`ros2 topic pub` 預設以 1 Hz 持續重複發布，要 Ctrl+C 才停；發完速度指令要再發零速度；0.5 m/s 室內偏快，初學請先用小值（如 0.1，此為建議，非文件內容）；舵機超出範圍是「不轉」而非報錯。

---

### 05.Robot control / 2. Robot keyboard control（機器人鍵盤控制）

**這課在做什麼**：`yahboom_keyboard` 節點把按鍵轉成 `/cmd_vel`。

```bash
# 【Pi 5 本機】sh ~/start_agent_rpi5.sh ；開車電源
# 【Pi 5 本機】另開：
sh ros2_humble.sh
# 【容器內】
ros2 node list
ros2 run yahboomcar_ctrl yahboom_keyboard
```

**方向鍵**（大小寫皆可）：

| 鍵 | 意義 | 鍵 | 意義 |
| --- | --- | --- | --- |
| `i`/`I` | linear, 0（前進） | `u`/`U` | linear, angular（前進+左轉） |
| `,` | -linear, 0（後退） | `o`/`O` | linear, -angular（前進+右轉） |
| `j`/`J` | 0, linear（原地左旋） | `m`/`M` | -linear, -angular（後退+右轉） |
| `l`/`L` | 0, -linear（原地右旋） | `.` | -linear, angular（後退+左轉） |

**速度鍵**（原文表格錯位，依上下文整理）：`q` 線速度與角速度同時 +10%；`z` 同時 -10%；`w` 線速度 +10%；`x` 線速度 -10%；`e` 角速度 +10%；`c` 角速度 -10%；`t` 線速度 X/Y 軸切換（**本車四輪普通輪胎，不能側移，`t` 無意義**）；`s` 停止鍵盤控制（切換）。
**坑**：每次使用前要點一下執行程式的終端機，否則偵測不到按鍵；本課開頭要求 Pi 與車在同一區網、`ROS_DOMAIN_ID` 相同。

---

### 05.Robot control / 3. Robot handle control（機器人手把控制）

**這課在做什麼**：手動啟動手把控制程式（需先關掉自動啟動那份），並解讀原始碼：搖桿 → `/joy` → `/cmd_vel`、`/beep`、`/servo_s1`、`/servo_s2`。
**ROS 觀念**：`joy_node`（讀手把原始按鍵並發布 `/joy`，型別 `sensor_msgs/msg/Joy`）＋自己的控制節點訂閱 `/joy` 再發布控制指令，這是 ROS 常見的「驅動節點＋應用節點」分層；`launch` 檔一次啟動多個節點；`rqt_graph` 看節點關係圖。

```bash
# 前置（同前）：agent → ros2_humble.sh
# 【容器內】確認手把掛載
ls /dev/input*
# 【容器內】先關掉開機自動的手把行程
ps -A
kill -9 171
kill -9 173        # PID 為示範，以實際為準
# 【容器內】手動啟動
ros2 launch yahboomcar_ctrl yahboom_joy_launch.py
# 【容器內】看節點關係圖（沒顯示就選 Nodes/Topics(all) 再按左上刷新）
ros2 run rqt_graph rqt_graph
# 想看全部按鍵值
ros2 topic echo /joy
```

**按鍵功能**：左搖桿前/後 = 前進/後退（左右無效）；右搖桿左/右 = 左/右旋轉（前後無效）；**START = 蜂鳴器**；Y = S2 舵機向上；A = S2 向下；X = S1 向左；B = S1 向右；**R1 = 速度控制開關**（按下才允許手把控速，再按一次失去控速；同時是「功能玩法開關」——按下即停，再按繼續執行雷達避障、雷達警衛等功能）；MODE = 切模式（用預設即可，切換後鍵值不對程式會報錯退出）。
**launch 原始碼**（`/root/yahboomcar_ws/src/yahboomcar_ctrl/launch/yahboom_joy_launch.py`）：啟動兩個節點——`package='yahboomcar_ctrl', executable='yahboom_joy'` 與 `package='joy', executable='joy_node'`。
**節點原始碼要點**（`.../yahboomcar_ctrl/yahboomcar_ctrl/yahboom_joy.py`）：

- 訂閱：`Joy` 於 `joy`（depth 10）。
- 發布：`cmd_vel`（Twist, 10）、`beep`（UInt16, 1）、`JoyState`（Bool, 10）、`servo_s1`（Int32, 10）、`servo_s2`（Int32, 10）。
- `buttons[7]==1` 呼叫 `cancel_nav()`；`buttons[11]` 切換蜂鳴器。
- 線速度 = `filter_data(axes[1]) * xspeed_limit * linear_Gear`；角速度 = `filter_data(axes[2]) * angular_speed_limit * angular_Gear`，並限幅。只有 `Joy_active == True` 才發布 `cmd_vel`。
- 舵機：每次按鍵角度 ±1，持續按持續增減；S1 限制 [-90, 90]、S2 限制 [-90, 20]。

**按鍵值對照**（預設 Controller 模式；原文表格錯位，依順序重組）：左搖桿上 `axes[1]=1`、下 `axes[1]=-1`；右搖桿向左 `axes[2]=1`、向右 `axes[2]=-1`；X `button[3]`；B `button[1]`；Y `button[4]`；R1 `button[7]`；START `button[11]`；左搖桿按下 `button[13]`；右搖桿按下 `button[14]`。（程式裡 `buttons[0]` = A。）
**坑**：沒先關自啟的手把行程，兩份程式同時發布 `/cmd_vel`；程式碼的 `user_jetson` 是從 Jetson 版移植的函式名，不必在意；換別牌手把鍵值不同要改程式。

---

### 05.Robot control / 4. Robot state estimation（機器人狀態估計）

**這課在做什麼**：啟動「底層資料處理」`yahboomcar_bringup_launch.py`，把 IMU 與輪式里程計融合成更準的 `/odom`（EKF）。建圖與導航都依賴它。
**ROS 觀念**：

- **里程計（odometry）**：由輪子編碼器累加推算位置，會漂移。
- **IMU**：陀螺儀/加速度計，提供角速度與姿態。
- **EKF 融合**：`robot_localization` 的 `ekf_node` 合併兩者，輸出 `/odom`。
- **TF（座標轉換）**：`odom -> base_footprint -> base_link -> imu_frame` 等座標關係。

```bash
# 前置（同前）：agent → ros2_humble.sh
# 【容器內】
ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py
# 【容器內，另一終端機（同一容器）】看節點關係圖
ros2 run rqt_graph rqt_graph
# 查看融合節點資訊
ros2 node info /ekf_filter_node
```

**預期**：`/ekf_filter_node` 訂閱 `/imu/data` 與 `/odom_raw`，發布 `/odom`。
**launch 原始碼**（`/root/yahboomcar_ws/src/yahboomcar_bringup/launch/yahboomcar_bringup_launch.py`）啟動：

- `imu_filter_madgwick` 的 `imu_filter.launch.py`：濾波 IMU，讀 `yahboomcar_bringup/param/imu_filter_param.yaml`。
- `robot_localization` 的 `ekf.launch.py`：融合 odom 與濾波後 IMU。
- `tf2_ros static_transform_publisher`（節點名 `base_link_to_base_imu`）：參數 `-0.002999 -0.0030001 0.031701 0 0 0 base_link imu_frame`。
- `yahboomcar_description` 的 `description_launch.py`：載入 URDF。
**坑**：開頭會印 `robot_type = x3`（沿用其他車型程式，不必在意）。

---

### 05.Robot control / 5. Linear speed calibration（線速度校正）

**這課在做什麼**：車子「說走 1 公尺」實際可能不是 1 公尺（輪徑、打滑）。用 `calibrate_linear` 節點測量並調整比例係數 `odom_linear_scale_correction`。
**ROS 觀念**：TF 查詢（`tf_buffer.lookup_transform`）、動態參數（`rqt_reconfigure` 即時改節點參數）。

```bash
# 前置：agent → ros2_humble.sh
# 【容器內】啟動底層（發布 odom->base_footprint 的 TF）
ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py
# 【容器內，新終端機（同一容器）】
ros2 run yahboomcar_bringup calibrate_linear
# 【容器內，新終端機】動態參數調整器
ros2 run rqt_reconfigure rqt_reconfigure
```

rqt 裡先按 Refresh 才看得到節點；選 `calibrate_linear`，勾 `start_test` 開始。參數：`test_distance`（測試距離，前進 1 m）、`speed`（線速度）、`tolerance`（容許誤差）、`odom_linear_scale_correction`（比例係數，結果不理想就改它）、`start_test`（開關）、`direction`（可忽略，給麥輪車左右移動校正）、`base_frame`、`odom_frame`。
**流程**：車監看 `base_footprint` 與 `odom` 的 TF，算出行進距離，誤差小於 tolerance 後發停車指令。若實際距離不是 1 m（用捲尺量），修改 `odom_linear_scale_correction`，**改完要點一下空白處才會寫入**，把 `start_test` 取消再重新勾選。
**原始碼要點**（`.../yahboomcar_bringup/yahboomcar_bringup/calibrate_linear.py`）：用 TF 取得 x、y，算與起點的距離，乘 `odom_linear_scale_correction`，減 `test_distance` 得誤差。
**坑**：需空曠平地、預留 1 m 以上；TF 未就緒會印 `transform not ready`。

---

### 05.Robot control / 6. Angular velocity calibration（角速度校正）

與 5 對稱：讓車旋轉 360 度，看實際轉多少。

```bash
# 前置：agent → ros2_humble.sh
# 【容器內】
ros2 launch yahboomcar_bringup yahboomcar_bringup_launch.py
# 【容器內，新終端機】
ros2 run yahboomcar_bringup calibrate_angular
# 【容器內，新終端機】
ros2 run rqt_reconfigure rqt_reconfigure
```

參數：`test_angle`（360°）、`speed`（角速度）、`tolerance`、`odom_angular_scale_correction`（比例係數）、`start_test`、`base_frame`、`odom_frame`。操作同線速度（先 Refresh、選 `calibrate_angular`、勾 `start_test`；改參數後點空白處、重置 `start_test` 再測）。
**原始碼要點**（`calibrate_angular.py`）：用 `PyKDL.Rotation.Quaternion(...)` 把四元數轉 RPY 取 yaw（`GetRPY()[2]`）；累加角度差並以 `normalize_angle` 處理 ±π 跳變；`error = test_angle - turn_angle`。原文說 `turn_angle` 單位是**弧度**。
**坑**：原文把 `odom_angular_scale_correction` 誤稱為「線速度比例係數」，實為角速度比例係數。

---

### 05.Robot control / 7. Robot URDF model（URDF 模型）

**這課在做什麼**：在 rviz2 顯示車子 3D 模型，用 `joint_state_publisher_gui` 滑桿控制輪子與雲台關節，同時介紹 URDF 格式。
**ROS 觀念**：URDF（統一機器人描述格式，XML）；`link`（連桿）、`joint`（關節）；`robot_state_publisher`（URDF 與關節狀態 → TF 與 `/robot_description`）；rviz2 視覺化。

```bash
# 前置：agent → ros2_humble.sh
# 【容器內】載入 URDF 並產生滑桿控制視窗
ros2 launch yahboomcar_description display_launch.py
# 【容器內，另一終端機（同一容器，見 Docker 課「進入機器人容器」）】
rviz2
```

rviz2 操作：左下 Add → **RobotModel** → Description Topic 選 `/robot_description`；**Fixed Frame 改為 `base_link`**（原文誤打成 base_linke）。移動滑桿可看到輪子/相機變化。滑桿關節：`zq_Joint`（左前輪）、`yq_Joint`（右前輪）、`yh_Joint`（右後輪）、`zh_Joint`（左後輪）、`jq1_Joint`（雲台 1）、`jq2_Joint`（雲台 2）；`Randomize` 隨機發布各關節值；`Center` 全部歸中。
**launch 原始碼**（`.../yahboomcar_description/launch/display_launch.py`）：參數 `model` 預設 `urdf/MicroROS.urdf`（用 `xacro` 展開）；啟動 `joint_state_publisher_gui`、`robot_state_publisher`、靜態 TF `base_footprint -> base_link`（`0 0 0.05 0 0 0`）。
**URDF 基礎重點**：

- XML 宣告；`<robot name="micro4.0">`。
- `link`：`<visual>`（外觀）、`<collision>`（碰撞）、`<inertial>`（慣性）；子標籤 `origin`（xyz 位置、rpy 姿態）、`mass`、`inertia`（ixx ixy ixz iyy iyz izz）、`geometry/mesh`（STL，路徑 `package://yahboomcar_description/meshes/base_link.STL`）、`material/color rgba`。
- `joint` 類型：`fixed`、`continuous`、`revolute`、`prismatic`、`floating`、`planar`。必要屬性 `name`（唯一）、`type`；子標籤 `origin`、`parent`、`child`、`axis`、`limit`（lower/upper/effort/velocity）、`mimic`、`safety_controller`。
- 範例：輪子關節 `zq_Joint` 為 `continuous`，origin `0.0455 0.0675 -0.02125`，parent `base_link`，child `zq_Link`，axis `0 1 0`；`base_link` 質量約 0.2226 kg。

---

### 10.Multi-machine course / 1. Multi-machine handle control（多機手把控制）

**這課在做什麼**：一支手把同時控制兩台車（`robot1`、`robot2`）。
**ROS 觀念**：**namespace（命名空間）**——兩台車的話題都叫 `/cmd_vel` 會衝突，所以加前綴變成 `/robot1/cmd_vel`、`/robot2/cmd_vel`；兩台要用**同一個 `ROS_DOMAIN_ID`**（才看得到彼此），再用不同 namespace 區分。
**硬體**：兩台 Pi 版車；一支手把接收器（只接其中一台 Pi；程式以官方「ROS Robot USB Wireless Controller」為例，其他手把需改程式）。

**基本設定（兩台車各自）**：改 `config_robot.py`，`robot.set_ros_namespace()` 分別設 `robot1`、`robot2`，兩車 `ROS_DOMAIN_ID` 設相同（虛擬機也要相同）；在 `/home/pi` 執行：

```bash
# 【Pi 5 本機】（各台各自執行）
sudo python3 config_robot.py
```

**注意：跑多機以外的課程時，必須改回來並重新執行此程式。**

```bash
# 【Pi 5 本機】每台：sh ~/start_agent_rpi5.sh ；按 reset ，等連上
# 【Pi 5 本機】每台另開：
sh ros2_humble.sh
# 【容器內】任選一台
ros2 node list
ros2 topic list
# 【容器內】在接手把接收器的那台 Pi
ros2 run joy joy_node
ros2 run yahboomcar_multi multi_joy_ctrl
# 看節點關係圖
ros2 run rqt_graph rqt_graph
```

按鍵同 05-3，但 R1 只是「按下後才能手把控速」（無功能玩法開關說明）。
**原始碼要點**（`.../yahboomcar_multi/yahboomcar_multi/multi_yahboom_joy.py`）：訂閱 `joy`；發布 `/robot1/cmd_vel`、`/robot2/cmd_vel`（Twist）、`/robot1/beep`、`/robot2/beep`（UInt16）、`/robot1/servo_s1`、`robot2/servo_s1`、`/robot1/servo_s2`、`/robot2/servo_s2`（Int32）、`move_base/cancel`（GoalID）、`JoyState`（Bool）；同一份 twist/蜂鳴器/舵機資料同時發給兩台。
**坑**：看不到另一台車的話題 → 兩台 Domain ID 不同或區網 DDS 探索失敗；原始碼 `robot2/servo_s1` 少了前導 `/`（疑為原廠小瑕疵）。

---

### 10.Multi-machine course / 2. Multi-machine keyboard control（多機鍵盤控制）

與上一課幾乎相同，控制來源改為鍵盤。基本設定同前（`set_ros_namespace` 為 `robot1`/`robot2`、同 Domain ID、`sudo python3 config_robot.py`）。

```bash
# 【Pi 5 本機】sh ~/start_agent_rpi5.sh ；按 reset
# 【Pi 5 本機】sh ros2_humble.sh
# 【容器內】
ros2 node list
ros2 topic list
ros2 run yahboomcar_multi multi_keyboard_ctrl
ros2 run rqt_graph rqt_graph
```

鍵位同 05-2（i 前進、`,` 後退、l/j 旋轉、q/z/w/x/e/c 調速、s 停止；原始碼另有空白鍵 `' '` 歸零）。
**原始碼要點**（`multi_yahboom_keyboard.py`）：建立兩個 Twist 發布者 `/robot1/cmd_vel`、`/robot2/cmd_vel`（depth 1000）；用 `tty.setraw` + `select`（0.1 秒逾時）讀鍵；按鍵後設 `(x, th)`，連續無按鍵計數超過 4 次自動歸零（鬆鍵自動停）；超過速度上限印 `Linear speed limit reached!`；Ctrl+C（`\x03`）離開。
**坑**：要先點終端機視窗；終端機進入 raw 模式，異常結束後可能亂掉，可輸入 `reset`（此為經驗建議）。

---

### 10.Multi-machine course / 3. Multi-machine navigation（多機導航）

**這課在做什麼**：在 rviz 為兩台車各自指定目標，兩台各自規劃路徑自主導航（Nav2 + AMCL + DWB）。
**ROS 觀念**：

- **Nav2**（ROS 2 導航堆疊）；**AMCL**（用已知地圖＋雷達判斷車在地圖哪裡）；**map_server**（載入地圖）；**lifecycle node**（有生命週期狀態，由 lifecycle_manager 啟動）；**DWB**（局部路徑規劃器）。
- **namespace + TF 前綴**：`robot1/base_link`、`robot1/odom` 等，避免兩車 TF 打架。
- **初始位姿**：要在 rviz 指定車在地圖上的起點（2D Pose）。
**硬體**：兩台 Pi 版車（含雷達）、電腦/虛擬機（跑 rviz，Pi 上跑 rviz 會很卡）。事前需有一張地圖（預設 `yahboom_map.yaml`）。

設定同前（namespace robot1/robot2、同 Domain ID、`sudo python3 config_robot.py`）。

```bash
# 【Pi 5 本機】每台：sh ~/start_agent_rpi5.sh ；按 reset ；sh ros2_humble.sh
# 【容器內】任一台確認兩車節點都在
ros2 node list

# 5.1 顯示 rviz（建議在配套虛擬機執行）
ros2 launch yahboomcar_nav multi_nav_display_launch.py
# rviz 工具列：【1】robot1 校準初始位姿 【2】robot1 目標點 【3】robot2 校準初始位姿 【4】robot2 目標點

# 5.2 載入地圖（原文章節號誤寫為 4.2；建議在虛擬機）
ros2 launch yahboomcar_multi map_server_launch.py
# 預設載入 /root/yahboomcar_ws/src/yahboomcar_multi/maps/yahboom_map.yaml ；可能載入失敗，Ctrl+C 後重跑
```

換預設地圖：把地圖的 `.yaml` 與 `.pgm` 複製到 `/root/yahboomcar_ws/src/yahboomcar_multi/maps/`，修改 `/root/yahboomcar_ws/src/yahboomcar_multi/launch/map_server_launch.py` 內的地圖名稱，然後：

```bash
cd ~/yahboomcar_ws
colcon build
source ~/.bashrc
```

```bash
# 5. 啟動各車底層（namespace 由 robot_name 參數決定）
# 在 robot1 的 Pi：
ros2 launch yahboomcar_multi yahboomcar_bringup_multi.launch.xml robot_name:=robot1
# 在 robot2 的 Pi：
ros2 launch yahboomcar_multi yahboomcar_bringup_multi.launch.xml robot_name:=robot2

# 6. 啟動 AMCL 定位
# robot1：
ros2 launch yahboomcar_multi robot1_amcl_launch.py
# robot2：
ros2 launch yahboomcar_multi robot2_amcl_launch.py
# 出現 "Please set the initial pose..." 後，用 rviz 的 2D Pose 工具分別為兩車設初始位姿（點擊拖曳）；
# 雷達掃描點與實際障礙大致重合代表位姿準確。紅色 = robot1，藍色 = robot2。

# 7. 啟動導航
# robot1：
ros2 launch yahboomcar_multi robot1_navigation_dwb_launch.py
# robot2：
ros2 launch yahboomcar_multi robot2_navigation_dwb_launch.py
# 出現 "Creating bond timer..." 表示載入完成；之後用 rviz 的 2D Goal Pose 給兩車目標點。
```

**預期**：黃線 = robot1 規劃路徑，綠線 = robot2 規劃路徑；兩車各自走向目標並避障。
**`yahboomcar_bringup_multi.launch.xml` 重點**（XML 格式 launch）：`<push-ros-namespace namespace="$(var robot_name)"/>`，群組內節點全部加上 `robot_name` 命名空間；啟動 `imu_filter_madgwick_node`（`fixed_frame=$(var robot_name)/base_link`，`use_mag=false`，`publish_tf=false`，`world_frame=$(var robot_name)/enu`，`orientation_stddev=0.00`，`imu/data_raw` remap 到 `imu`）、`robot_localization` 的 `ekf_node`（名稱 `ekf_filter_node`，frame 加前綴，參數檔 `param/ekf_$(var robot_name).yaml`，`odometry/filtered` remap 為 `odom`）、靜態 TF `base_link_to_base_imu`，並 include `description_multi_$(var robot_name).launch.py`。
**`robot1_amcl_launch.py` 重點**：`nav2_amcl/amcl`（節點名 `robot1_amcl`，參數 `param/robot1_amcl_params.yaml`，`/initialpose` remap 到 `/robot1/initialpose`）、`nav2_lifecycle_manager`（管理 `robot1_amcl`，`autostart: True`）、靜態 TF `robot1/base_link -> robot1/laser_frame`（`-0.0046412 0 0.094079 0 0 0`）。
**加第三台車（8.1~8.5）**：複製並改名 URDF（`MicroROS_robot1.urdf` → robot3）與載入 launch（`description_multi_robot1.launch.py`）；複製 `ekf_robot1.yaml`、`robot1_amcl_params.yaml`、`robot1_nav_params.yaml`；複製 `robot1_amcl_launch.py`、`robot1_navigation_dwb_launch.py`；改 `yahboomcar_nav/rviz/multi_nav.rviz`，複製 `SetInitialPose`（Topic `/robot1/initialpose`）與 `SetGoal`（`/robot1/goal_pose`）兩個工具並改名；回 `yahboomcar_ws` 做 `colcon build`。
**坑**：

- 看不到 "Please set the initial pose..." 通常是**時間戳不同步**：按車的 Reset 讓車重新連 agent，再試幾次。
- 地圖可能載入失敗，Ctrl+C 重跑。
- 在 Pi 上開 rviz 會非常卡，用虛擬機。
- 原文章節編號有誤，但指令順序清楚。

---

## 3. 本區出現的 ROS 節點／話題／服務／launch 檔總表

### 節點

| 節點 | 來源 | 說明 |
| --- | --- | --- |
| `/YB_Car_Node` | micro-ROS（ESP32） | 車本體節點，連上 agent 後出現 |
| `joy_node`（`joy`） | ROS 2 | 讀手把，發布 `/joy` |
| `yahboom_joy`（`yahboomcar_ctrl`） | 原廠 | 手把 → 速度/蜂鳴器/舵機 |
| `yahboom_keyboard`（`yahboomcar_ctrl`） | 原廠 | 鍵盤 → `/cmd_vel` |
| `follow_line`（`yahboomcar_astra`） | 原廠 | 相機巡線 |
| `/ekf_filter_node`（`robot_localization`） | ROS 2 | IMU+odom 融合 |
| `imu_filter_madgwick` | ROS 2 | IMU 濾波 |
| `static_transform_publisher`（`tf2_ros`） | ROS 2 | 靜態 TF（`base_link_to_base_imu`、`base_footprint->base_link`） |
| `robot_state_publisher` | ROS 2 | URDF → TF/`/robot_description` |
| `joint_state_publisher_gui` | ROS 2 | URDF 關節滑桿 |
| `calibrate_linear`、`calibrate_angular`（`yahboomcar_bringup`） | 原廠 | 校正節點 |
| `rqt_reconfigure`、`rqt_graph`、`rviz2` | ROS 2 工具 | 動態參數、節點圖、視覺化 |
| `multi_joy_ctrl`、`multi_keyboard_ctrl`（`yahboomcar_multi`） | 原廠 | 多機控制 |
| `robot1_amcl`、`robot1_amcl_lifecycle_manager`、`map_server` | Nav2 | 多機定位/地圖 |
| `usb_cam`（`camera.launch.py`） | ROS 2 | 相機 |

### 話題

| 話題 | 型別 | 方向（相對車） | 說明 |
| --- | --- | --- | --- |
| `/cmd_vel` | geometry_msgs/msg/Twist | 訂閱 | 車速（linear.x、angular.z） |
| `/beep` | std_msgs/msg/UInt16 | 訂閱 | 蜂鳴器 1/0 |
| `/servo_s1` | std_msgs/msg/Int32 | 訂閱 | 雲台 S1，[-90, 90] |
| `/servo_s2` | std_msgs/msg/Int32 | 訂閱 | 雲台 S2，[-90, 20] |
| `/scan` | sensor_msgs/LaserScan | 發布 | 雷達 |
| `/imu` | sensor_msgs/Imu | 發布 | IMU 原始；經濾波得 `/imu/data` |
| `/imu/data` | sensor_msgs/Imu | 濾波後 | EKF 輸入 |
| `/odom_raw` | nav_msgs/Odometry | 發布 | 輪式里程計原始值 |
| `/odom` | nav_msgs/Odometry | EKF 輸出 | 融合後里程計（05-1 把它寫成車發布，與 05-4 矛盾） |
| `/joy` | sensor_msgs/Joy | 手把 | 手把原始按鍵 |
| `/JoyState` | std_msgs/Bool | 發布 | 手把是否啟用 |
| `/rpi5_ip` | （文件未寫） | 發布 | 回報 Pi 5 IP |
| `/robot_description` | std_msgs/String | 發布 | URDF |
| `/usb_cam/image_raw/compressed` | 壓縮影像 | 發布 | 手機 App 影像 |
| `/robot1/…`、`/robot2/…`：`cmd_vel`、`beep`、`servo_s1`、`servo_s2`、`initialpose`、`goal_pose`、`odom`、`odom_raw`、`imu` | 同上 | | 多機 namespace 版 |
| `move_base/cancel` | GoalID | 發布 | 取消導航 |

型別欄中非文件明寫者（`/scan`、`/imu`、`/odom_raw`、`/joy` 等的標準型別）為依 ROS 慣例補上。

### 服務

本區沒有明確使用 ROS 服務；地圖儲存由 App 內部觸發（文件沒說服務名）。

### Launch 檔與可執行檔

| 套件 | 檔案 | 用途 |
| --- | --- | --- |
| `yahboomcar_bringup` | `yahboomcar_bringup_launch.py` | 底層：IMU 濾波 + EKF + TF + URDF |
| `yahboomcar_ctrl` | `yahboom_joy_launch.py` | 手把控制 |
| `yahboomcar_nav` | `map_gmapping_app_launch.xml` | gmapping 建圖（App 用） |
| `yahboomcar_nav` | `multi_nav_display_launch.py` | 多機 rviz |
| `usb_cam` | `camera.launch.py` | 相機 |
| `yahboomcar_description` | `display_launch.py` | URDF 顯示 + 滑桿 |
| `yahboomcar_multi` | `yahboomcar_bringup_multi.launch.xml`（`robot_name:=`） | 多機底層 |
| `yahboomcar_multi` | `map_server_launch.py` | 載入地圖 |
| `yahboomcar_multi` | `robot1_amcl_launch.py`、`robot2_amcl_launch.py` | AMCL |
| `yahboomcar_multi` | `robot1_navigation_dwb_launch.py`、`robot2_navigation_dwb_launch.py` | 導航 |
| `ros2 run` | `yahboomcar_ctrl yahboom_keyboard`、`yahboomcar_astra follow_line`、`yahboomcar_bringup calibrate_linear / calibrate_angular`、`yahboomcar_multi multi_joy_ctrl / multi_keyboard_ctrl`、`joy joy_node`、`rqt_reconfigure rqt_reconfigure`、`rqt_graph rqt_graph` | |

### 腳本與檔案

| 檔案 | 位置 | 用途 |
| --- | --- | --- |
| `~/start_agent_rpi5.sh` | Pi 5 家目錄 | 啟動序列版 micro-ROS agent |
| `ros2_humble.sh` | Pi 5 家目錄（`/home/pi`） | 啟動/進入 Humble 容器；內含 `/root/1.sh`（自動啟動手把） |
| `config_robot.py` | Pi 5 家目錄 | 寫入控制板設定 |
| `/usr/lib/systemd/system/supervisor.service` | 容器內 | 容器內自動啟動服務 |
| 工作區 | `/root/yahboomcar_ws`（容器內）；`/home/yahboom/yahboomcar_ws`（虛擬機） | 原廠套件原始碼 |

---

## 4. 硬體規格重點

| 項目 | 內容 |
| --- | --- |
| 主控 | Raspberry Pi 5（ROS 2 Humble 跑在 Docker 內） |
| 控制板 | ESP32-S3 雙核；整合馬達驅動、舵機驅動、六軸 IMU；WiFi、藍牙、序列；4 路編碼馬達、2 路 PWM 舵機、1 路雷達、PD 供電給 Pi 5 |
| 馬達 | 4 路編碼馬達（文件稱「310 encoder motor」；你的資料說 370，以實物為準）；四輪驅動，普通輪胎，**不能側移** |
| IMU | 六軸，I2C（SCL=GPIO39、SDA=GPIO40、INT=GPIO41） |
| 雷達 | MS200，TOF，360°，10 Hz，4500 點/秒，0.03~12 m，序列 230400 baud |
| 雲台 | 2 個 PWM 舵機：S1 [-90, 90]，S2 [-90, 20] |
| 相機 | USB 相機（`usb_cam`，話題 `/usb_cam/image_raw/compressed`） |
| 電池 | 7.4V（2×18650），2000mAh，供電 5.6~8.4V，額定 15A，最大 20A，約 115g，67×37×22 mm |
| 充電 | DC 8.4V 充電器；紅燈充電中，綠燈充飽；充電時關總開關 |
| 低電警報 | 蜂鳴器每 100 ms 一響，此時車不可控 |
| 預設熱點 IP | `10.42.0.1`（熱點名 `Micro_ros`，密碼 `12345678`） |
| Pi 5 帳號密碼 | `pi` / `yahboom`（VNC 與系統登入） |
| 預設 ROS_DOMAIN_ID | `20` |
| 預設節點 | `/YB_Car_Node` |
| 序列裝置 | `/dev/ttyUSB0` |
| UDP agent 埠（虛擬機版） | `udp4 --port 8090` |
| 開機時間 | 約 30 秒 |
| 設定窗口 | Reset 後 5 秒內 |
| 燒錄 | 位址 `0x0`、`microROS_Robot_Vx.x.x.bin`、DoNotChgBin、序列助手 115200 |
| 使用溫度 | 電池/充電 0~35℃ |
| 車體尺寸／重量 | **本區文件未提供**（組裝課 02 可能有） |

---

## 5. 沒有車也能先練嗎？

**可以先在電腦練（Ubuntu 24.04 + ROS 2 Jazzy，或 Docker 跑 Humble）：**

- ROS 2 基本觀念：`ros2 node list`、`ros2 topic list/echo/info/pub`、`ros2 node info`、`rqt_graph`。可用 `turtlesim`（發布 `/turtle1/cmd_vel`）代替車。
- 手動發布 `/cmd_vel`、`/beep`、`/servo_s1` 的語法與 Twist/UInt16/Int32 型別：可自建簡單訂閱者練習。
- `joy_node` 與手把控制邏輯：有任何 USB 手把就能練 `/joy`（鍵值對應可能不同）。
- Launch 檔（Python 與 XML）、namespace、`push-ros-namespace`、remap：可用 turtlesim 練。
- URDF + rviz2 + `robot_state_publisher` + `joint_state_publisher_gui`：完全不需車；可寫自己的簡單 URDF，或取得原廠 `yahboomcar_description` 套件。
- TF 觀念：`static_transform_publisher`、`ros2 run tf2_tools view_frames`。
- EKF（`robot_localization`）、`imu_filter_madgwick`：可用 Gazebo 或 rosbag 練。
- Nav2/AMCL/map_server/gmapping 或 slam_toolbox：可用 TurtleBot3 模擬（Gazebo）先熟悉。
- Docker 的 `docker ps/exec/commit/images` 流程：可在電腦練。
- 燒錄工具與 CP2102 驅動：要實板才能驗證，但可先下載熟悉。
- Jazzy 與 Humble 套件 API 大致相容，但部分套件名/參數有差異；若要完全一致，用 Docker 跑 Humble 映像。

**一定要實車：**

- micro-ROS agent 與 ESP32 的實際連線（序列/UDP）、`/YB_Car_Node`、`config_robot.py`、Reset 設定窗口。
- 韌體燒錄。
- 真實的 `/scan`（MS200）、`/imu`、`/odom_raw` 資料與線/角速度校正。
- 舵機實際轉動、蜂鳴器、電池與充電。
- `follow_line` 相機巡線的實景調參、手機 App 建圖。
- 多機課程（需兩台車）。

---

## 6. 初學者最容易卡住的 5 個地方

1. **ROS_DOMAIN_ID 不一致**：車、容器、虛擬機任何一端不同，`ros2 node list` 就看不到 `/YB_Car_Node`。要檢查控制板（`config_robot.py` 的 `set_ros_domain_id(20)`）、容器的 `~/.bashrc`、虛擬機的 `~/.bashrc`，以及手把自啟用的 `supervisor.service`。
2. **「Pi 本機」與「容器內」搞混**：`ros2 ...` 要在容器內；`docker`、`sh ros2_humble.sh`、`config_robot.py` 在 Pi 本機。多個終端機要進**同一個容器**必須用 `docker exec -it <ID> /bin/bash`（ID 每次不同），再跑一次 `sh ros2_humble.sh` 會變成新容器。
3. **agent 衝突與沒連上**：agent 只能開一個，而**開機已經自動開了一個**；再手動開會報錯。車沒連上要按控制板 Reset 並等 10~30 秒；agent 異常結束留下的 docker 行程要 `docker stop`。MCU 燈的閃爍節奏是診斷工具，要學會讀。
4. **自動啟動的手把程式搶著發 `/cmd_vel`**：手動控制（鍵盤、`ros2 topic pub`、導航）時自啟的手把程式也在發布，造成車抖動或不聽話。要先 `kill -9` 兩個行程（PID 以 `ps -A` 為準）或永久移除 `/root/1.sh`。手把要先按 R1 才有速度輸出。
5. **設定窗口、低電壓與 namespace 殘留**：`config_robot.py` 必須在 Reset 後 5 秒內執行；低電壓時蜂鳴器一直響且車**不可控**（常被誤認為程式問題）；多機課程改了 namespace 後，跑別的課要**改回來並重新執行 `config_robot.py`**，否則話題全變成 `/robot1/...`，單車課程全部失敗。

---

## 附：本筆記發現的文件矛盾／缺漏（教材撰寫時請注意）

- `/odom` 與 `/odom_raw`：05-1 說車發布 `/odom` 又查 `/odom_raw`；05-4 說 `/odom_raw` 經 EKF 變 `/odom`。傾向後者。
- 馬達型號：文件寫 310，使用者說 370。
- 手把沒反應等待時間：First Trial 說 10 秒，04-1 說 30 秒。
- `ros2_humble.sh` 呼叫方式：`./ros2_humble.sh` 與 `sh ros2_humble.sh` 並存。
- FAQ 第 8 題問題句遺失。
- `start_agent_rpi5.sh` 與 `ros2_humble.sh` 的內容文件沒給，需實車讀取。
- `/rpi5_ip` 的訊息型別沒寫。
- `MicroROS-Pi5_Manual.txt` 為空；所有接線圖、畫面截圖均未包含在文字中。
