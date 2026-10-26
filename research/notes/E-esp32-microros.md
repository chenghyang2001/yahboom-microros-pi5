# E 組研究筆記：microROS 控制板開發環境、ESP32 基礎課、micro-ROS 基礎課

> 範圍：官方文件 `15. microROS control board development environment`（6 篇）、`16. ESP32 basic course`（17 篇）、`17. microros basic course`（10 篇）。
> 第 4、5 節需要的「出廠韌體／參數設定／話題清單」，另外交叉參考了 `01.Introduction/4. FAQ`、`03.Preparation/1~3`、`05.Robot control/1`、`10.Multi-machine course` 的相關段落。
> 標記說明：**【文件原文】** = 官方文件明寫；**【推測】** = 我依程式碼或常識推斷，文件沒寫；**【文件矛盾】** = 官方文件前後不一致。
> 指令、路徑、API、話題名一律逐字照官方文件。

---

## 1. 概覽

### 1.1 micro-ROS 是什麼

- ROS 2 原本設計給 Linux 電腦（例如 Raspberry Pi 5）。微控制器（MCU，如 ESP32）沒有 Linux、記憶體只有幾百 KB，跑不了完整 ROS 2。
- **micro-ROS** 是 ROS 2 的「瘦身版」，讓 MCU 也能當 ROS 2 的一個「節點（node）」，可以發布（publish）／訂閱（subscribe）話題（topic）。
- 在 MCU 上寫程式用的是 C 語言的 **rclc** 函式庫（`rcl` 的 C 簡化包裝）。它底層用 **Micro XRCE-DDS** 協定，跟電腦端的 agent 對話（設定裡可以看到 `rmw_microxrcedds`、`RMW_UXRCE_*` 這類名稱）。

### 1.2 為什麼這台車要用 ESP32 + micro-ROS（白話版）

| 角色 | 硬體 | 比喻 | 負責 |
| --- | --- | --- | --- |
| 大腦 | Raspberry Pi 5（跑 ROS 2 Humble、Docker） | 大腦 | 建地圖、導航、影像辨識、遙控邏輯等「慢但聰明」的事 |
| 小腦／脊髓 | microROS 控制板上的 ESP32-S3 | 小腦／脊髓反射 | 每 10 毫秒量一次編碼器、跑 PID 控制馬達、讀 IMU、讀雷達、驅動蜂鳴器／舵機等「快且要準時」的事 |

- 馬達速度控制（PID）要求固定週期（文件的 PID 週期為 10 ms 級），Linux 不是即時系統，容易抖動；MCU 專職做這件事更穩。
- ESP32 把「輪子轉速、IMU、雷達」整理成標準 ROS 話題送給 Pi 5，Pi 5 只要發 `/cmd_vel`（我要前進 0.5 m/s）就好，不用管馬達細節。**【推測】** 這是典型「高階控制／低階控制分層」設計。

### 1.3 micro-ROS agent 在中間做什麼

- MCU 不會說完整的 DDS，所以需要一個「翻譯官」：**micro-ROS agent**，跑在 Pi 5 或電腦上。
- 流程：`ESP32 (micro-ROS client)  <—— UDP(WiFi) 或 序列埠 ——>  micro-ROS agent  <—— DDS ——>  一般 ROS 2 節點（ros2 topic、rviz…）`
- agent 代替 MCU 在 ROS 2 網路裡「現身」。所以只要 agent 沒開，ESP32 就一直卡在「Connecting agent」；agent 開了、ESP32 連上，`ros2 node list` 才看得到這個節點。
- 文件原文：agent 只能在**一個**終端開，重複開會報錯。

```
  ESP32-S3 (韌體, rclc)                Pi 5 / 電腦                          其他 ROS 2 節點
 ┌──────────────────┐   序列埠 /dev/ttyUSB0 @921600   ┌──────────────────┐   DDS   ┌────────────┐
 │ 編碼器/PID/IMU/  │ ═══════ 或 WiFi UDP:8090 ══════▶│ micro-ROS agent  │════════▶│ ros2 topic │
 │ 雷達/蜂鳴器/舵機 │◀═══════════════════════════════ │ (Docker 或原始碼)│◀════════│ rviz / nav2│
 └──────────────────┘                                  └──────────────────┘         └────────────┘
```

---

## 2. 開發環境（文件 15）

> 此組文件以 **Ubuntu（虛擬機／電腦）** 為例；官方配套虛擬機已預先裝好 ESP-IDF 與 micro-ROS 元件，**一般使用者不必重裝**（4 號文件明寫）。

### 2.1 microROS 控制板硬體（15-1）

- 主晶片 **ESP32-S3**（雙核）；模組 **ESP32-S3-WROOM-1U-N4R2**（4MB Flash + 2MB PSRAM，見 16-12）。支援 WiFi、藍牙、序列埠。
- 板上資源：4 路編碼馬達（310 馬達）、2 路 PWM 舵機、1 個雷達介面（MS200）、六軸 IMU、主動式蜂鳴器、MCU 指示燈、BOOT 鍵、Reset 鍵、自訂按鍵 KEY1、電池電壓偵測、天線介面、7.4V 電池輸入（T 型頭）、DC8.4V 充電口。
- 兩個 Type-C：**標 Serial 的**用於通訊／設定／燒錄；**標 5V OUT 的**用來給 Pi 5 供電（FAQ 4）。
- **GPIO 對照表（逐字）**：

| 週邊 | GPIO | 週邊 | GPIO |
| --- | --- | --- | --- |
| M1-PWM-M1A | GPIO4 | M3-PWM-M3A | GPIO9 |
| M1-PWM-M1B | GPIO5 | M3-PWM-M3B | GPIO10 |
| M1-Encoder-H1A | GPIO6 | M3-Encoder-H3A | GPIO11 |
| M1-Encoder-H1B | GPIO7 | M3-Encoder-H3B | GPIO12 |
| M2-PWM-M2A | GPIO15 | M4-PWM-M4A | GPIO13 |
| M2-PWM-M2B | GPIO16 | M4-PWM-M4B | GPIO14 |
| M2-Encoder-H2A | GPIO47 | M4-Encoder-H4A | GPIO1 |
| M2-Encoder-H2B | GPIO48 | M4-Encoder-H4B | GPIO2 |
| BOOT 鍵 IO0 | GPIO0 | 自訂按鍵 KEY1 | GPIO42 |
| 電池電壓偵測 BAT | GPIO3 | MCU 指示燈 LED | GPIO45 |
| 蜂鳴器 | GPIO46 | 舵機 S1 | GPIO8 |
| 舵機 S2 | GPIO21 | IMU 中斷 INT | GPIO41 |
| IMU I2C SCL | GPIO39 | IMU I2C SDA | GPIO40 |
| 雷達 RX（串口1 TXD1） | GPIO17 | 雷達 TX（串口1 RXD1） | GPIO18 |
| Type-C 燒錄串口 RX（TXD0） | GPIO43 | Type-C 燒錄串口 TX（RXD0） | GPIO44 |

- 馬達編號：左前輪 Motor1、左後輪 Motor2、右前輪 Motor3、右後輪 Motor4。

### 2.2 安裝 ESP-IDF（15-2）

- **ESP-IDF 版本：v5.1.2**；晶片目標 **esp32s3**。Windows 另有官方 ESP-IDF、Arduino IDE、VS Code+PlatformIO 等途徑，但文件只教 Ubuntu 從原始碼安裝。

```bash
# 1) 安裝相依套件
sudo apt-get install git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0

# 2) 下載 ESP-IDF v5.1.2
mkdir -p ~/esp
cd ~/esp
git clone -b v5.1.2 --recursive https://github.com/espressif/esp-idf.git

# 3) 安裝工具鏈（只裝 esp32s3）
cd esp-idf
./install.sh esp32s3

# 4) 啟用環境（每開一個新終端都要做一次！）
source ~/esp/esp-idf/export.sh
```

### 2.3 編譯／燒錄／監看指令（逐字）

```bash
cd examples/get-started/hello_world
idf.py set-target esp32s3
idf.py build                       # 編譯；成功後可 ls build/*.bin、build/bootloader/*.bin、build/partition_table/*.bin
idf.py flash                       # 燒錄（電腦只能接一個序列裝置）
idf.py flash -p /dev/ttyUSB0       # 多個序列裝置時指定埠號
idf.py monitor                     # 開序列埠監看器；離開按 Ctrl+]
idf.py build flash monitor         # 一次做完（本教材每課都用這行）
```

- 編譯後的 `build/*.bin` 即燒錄用檔案。進度到 100% 並顯示 `Done` 代表燒錄完成。

### 2.4 序列埠設定

- 監看器（`idf.py monitor`）由 ESP-IDF 自動處理；用外部序列埠助手（16-4）時：**115200、8 data bit、1 stop bit、無 parity、無流控**，接收／傳送都選 ASCII。
- 板上 USB 轉序列晶片為 **CP2102**（Windows 需裝 CP2102 驅動，見 03.Preparation/1）。Linux 下通常是 `/dev/ttyUSB0`。
- 在 VMware 虛擬機：插上板子後系統會問要接到主機還是虛擬機，要選「連接到虛擬機」；要換到 Windows 的序列助手時，在虛擬機右上角對 CP2102 圖示按右鍵 → Disconnect（連接到主機）。
- 序列口分工（16-4）：UART0 = TXD GPIO43 / RXD GPIO44（Type-C 燒錄口，115200）；UART1 = TXD GPIO17 / RXD GPIO18（雷達，230400）。

### 2.5 menuconfig 設定（15-3）

新專案：

```bash
mkdir ~/esp/Samples/esp32_samples
cd ~/esp/Samples/esp32_samples
idf.py create-project main
cd main
idf.py set-target esp32s3
idf.py menuconfig
```

推薦設定（文件原文逐項）：

1. `Serial flasher config` → Flash size 改 **4MB**，勾選 `Detect flash size when flashing bootloader`。
2. `Component config` → `ESP PSRAM` → 啟用 `Support for external, SPI-connected RAM`，`SPI RAM config` 保持預設。
3. `Component config` → `ESP System Settings` → `CPU frequency` → **240MHz**。
4. `Component config` → `FreeRTOS` → `Kernel` → `configTICK_RATE_HZ` 改 **1000**（也就是 1 ms 一個 tick，`vTaskDelay(pdMS_TO_TICKS(10))` 才精準）。
5. `Partition Table` → 選 `Single factory app (large), no OTA`（給程式更大空間）。

存檔按 `S`、離開按 `Q`。設定存在專案根目錄的 `sdkconfig`。

### 2.6 安裝 micro-ROS ESP-IDF 元件（15-4）

> 這份元件託管在 GitHub，網路不佳會下載失敗；**官方虛擬機已編好**，非必要不要重裝。

```bash
mkdir -p ~/esp/Samples/extra_components
cd ~/esp/Samples/extra_components
git clone -b humble https://github.com/micro-ROS/micro_ros_espidf_component.git
cd micro_ros_espidf_component

source ~/esp/esp-idf/export.sh
pip3 install catkin_pkg lark-parser empy colcon-common-extensions     # 務必先 source export.sh 再裝
```

- **預設只支援** 1 node、2 publishers、2 subscribers、1 service、1 client、1 history。文件建議把 publisher／subscriber／history 都改成 3（改 `micro_ros_espidf_component/colcon.meta` 的 `rmw_microxrcedds`）：

```json
"rmw_microxrcedds": {
    "cmake-args": [
        "-DRMW_UXRCE_XML_BUFFER_LENGTH=400",
        "-DRMW_UXRCE_TRANSPORT=udp",
        "-DRMW_UXRCE_MAX_NODES=1",
        "-DRMW_UXRCE_MAX_PUBLISHERS=3",
        "-DRMW_UXRCE_MAX_SUBSCRIPTIONS=3",
        "-DRMW_UXRCE_MAX_SERVICES=1",
        "-DRMW_UXRCE_MAX_CLIENTS=1",
        "-DRMW_UXRCE_MAX_HISTORY=3"
    ]
},
```

- 改完要清除再重編，產生 `libmicroros.a` 靜態庫：

```bash
cd ~/esp/Samples/extra_components/micro_ros_espidf_component/examples/int32_publisher
idf.py clean-microros
idf.py set-target esp32s3        # 觸發下載與編譯，成功提示 "Configuring done"、"Generating done"
ls ../../*.a
```

- 專案使用：在專案根 `CMakeLists.txt` 加 `set (EXTRA_COMPONENT_DIRS "../../extra_components")`（路徑依實際位置調整）。
- 想改編譯參數：再跑一次 `idf.py clean-microros` 後重編。
- **【推測】** 出廠韌體要同時 3 個 publisher（`/imu`、`/odom_raw`、`/scan`）加 4 個 subscriber（`/cmd_vel`、`/beep`、`/servo_s1`、`/servo_s2`），超過這份文件建議的「3 / 3」，代表出廠版本用了更大的上限設定。自己改練習程式若發現「建立 subscriber 失敗」，先檢查這組上限。

### 2.7 安裝與啟動 micro-ROS agent（15-5）

文件建議用 **Docker 方式**（出廠系統已設好 Docker）。與原始碼方式二選一，不要同時啟動。

**WiFi（UDP）agent：**

```bash
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4
```

**序列埠 agent：**

```bash
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 921600 -v4
```

- `--port 8090` 為網路埠；`--dev /dev/ttyUSB0` 為序列裝置；`-b 921600` 為鮑率；`-v4` 為 log 等級（數字越大印越多）。
- 結束按 Ctrl+C，**不要直接關終端**，否則 Docker 容器會留在背景。
- 重複啟動導致 `ros2 node list` 看到多個同名節點：不影響使用；Ctrl+C 結束 agent、重置單片機再連即可。
- agent 啟動失敗（上次被硬關）：

```bash
docker ps -a | grep microros/micro-ros-agent
docker stop xxxxxxxxxx
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4
```

也可重開機。

**原始碼方式（備用，比較麻煩）：** 裝 tinyxml2（`git clone https://github.com/leethomason/tinyxml2.git` → `mkdir build` → `cmake ..` → `make` → `make install`）→ `sudo apt install python3-rosdep` → `source /opt/ros/humble/setup.bash` → 建 `~/uros_ws/src`，`git clone -b $ROS_DISTRO https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup` → `sudo rosdep init`（網路問題加 `-E`）→ `rosdep update && rosdep install --from-paths src --ignore-src -y` → `colcon build` → `source install/local_setup.bash` → `ros2 run micro_ros_setup create_agent_ws.sh` → `ros2 run micro_ros_setup build_agent.sh`（失敗就再編一次）→ 之後：

```bash
source ~/uros_ws/install/local_setup.sh
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090 -v4
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 921600 -v4
```

`rosdep init` 失敗時，文件教你手動在 `/etc/ros/rosdep/sources.list.d/20-default.list` 寫入 rosdistro 的 yaml 清單。

### 2.8 用 Flash 下載工具燒錄 .bin（15-6，Windows 可用）

- 工具：Espressif 官網「其他工具」下載 `flash_download_tool`（網址：`https://www.espressif.com.cn/zh-hans/support/download/other-tools`），選 ESP32-S3。
- 把 `build/bootloader/bootloader.bin`、`build/partition_table/partition-table.bin`、`build/main.bin` 複製到工具的 `bin` 資料夾。**自己編的專案**位址如下：

| 檔案 | 位址 | 用途 |
| --- | --- | --- |
| bootloader.bin | 0x0000 | 開機檔 |
| partition-table.bin | 0x8000 | 分區表 |
| main.bin | 0x10000 | 功能程式 |

- 其他設定保持預設，選 COM 埠，按 Start。完成會出現藍色 FINISH，斷電重啟或按 Reset。
- 不會自動開始燒錄時：**按住 BOOT0 → 按一下 Reset → 放開 BOOT0**，手動進入燒錄模式。
- 注意與出廠韌體的差別：出廠韌體是**單一合併檔 `microROS_Robot_Vx.x.x.bin` 燒在 0x0**（第 5 節）。

---

## 3. 逐課筆記

### 3.0 課程共通模板

- 每課結構：實驗目的 → 硬體連接 → 核心程式碼 → 編譯／燒錄 → 實驗結果。
- 每課共通指令（以下各課省略）：

```bash
source ~/esp/esp-idf/export.sh
cd ~/esp/Samples/esp32_samples/<專案資料夾>
idf.py build flash monitor      # 離開監看器 Ctrl+]
```

- 每課 `app_main` 開頭都 `printf("hello yahboom\n"); ESP_LOGI(TAG, "Nice to meet you!");`，所以**每課的預期結果都包含序列埠印出 `hello yahboom`**。
- 範例原始碼位置（官方虛擬機）：`~/esp/Samples/esp32_samples/<課>`（第 16 組）、`~/esp/Samples/microros_samples/<課>`（第 17 組）。

### 第 16 組：ESP32 基礎課（純 ESP-IDF，不涉及 ROS）

| 課 | 專案資料夾 | 在做什麼／關鍵 API | 預期結果 |
| --- | --- | --- | --- |
| 16-1 點亮 LED | `led` | `gpio_config_t`（`GPIO_MODE_OUTPUT`）、`gpio_set_level(LED_GPIO, ...)`；LED=GPIO45；`Led_Flash(50)` 每 10 ms 呼叫、interval 單位 10ms，即 0.5 秒翻轉 | 印 `hello yahboom`，MCU 指示燈每 0.5 秒閃 |
| 16-2 按鍵 | `key` | 兩鍵：`KEY_GPIO_BOOT0`=GPIO0、`KEY_GPIO_USER1`=GPIO42，上拉輸入；`Key1_Read_State()` 每 10ms 呼叫、連續偵測到才算按下（軟體消抖）；`esp_get_free_internal_heap_size()`、`esp_get_free_heap_size()` | 按 BOOT 印 `KEY 0 PRESS` 與可用記憶體；按 KEY1 印 `KEY 1 PRESS` |
| 16-3 蜂鳴器 | `beep` | 主動式蜂鳴器 GPIO46，高電位響；`Beep_On_Time(uint16_t time)`：0=關、1=持續響、≥10=響 time 毫秒後自動關（程式內夾在 10~10000 ms）；背景 `Beep_Task` 每 10ms 呼叫 `Beep_Handle()` 倒數 | 每秒響一次，每次 500 ms |
| 16-4 序列通訊 | `uart` | `uart_config_t`、`uart_driver_install`、`uart_param_config`、`uart_set_pin`、`uart_read_bytes`、`uart_write_bytes`；自製 ring buffer（`RingBuffer_Init/Push/Pop`）+ 接收 task（`xTaskCreate`）；UART0=GPIO43/44 @115200，UART1=GPIO17/18 @230400 | 收到什麼就回傳什麼（自收自發）。要先 Ctrl+] 離開 monitor，把 USB 接回 Windows，用序列助手以 115200/8N1 測試，送字元會被回傳 |
| 16-5 電池電壓 | `voltage` | ADC：`adc_oneshot_new_unit`（ADC_UNIT_1）、`adc_oneshot_config_channel`、`adc_oneshot_read`、校準 `adc_cali_create_scheme_curve_fitting`、`adc_cali_raw_to_voltage`；GPIO3 = ADC1 channel 2；換算 `battery_voltage = gpio_voltage_mV / 1000.0 * 4.03`（註解寫分壓 (10+3.3)/3.3） | 每 500ms 印 `Voltage:%.2fV`（例 7.05V） |
| 16-6 PWM 舵機 | `pwm_servo` | `mcpwm_new_timer`/`mcpwm_new_operator`/`mcpwm_new_comparator`/`mcpwm_new_generator`；50Hz；脈寬 500~2500 µs 對應 -90~90 度；`Servo_Set_Angle(servo_id_t, int8_t)`。S1=GPIO8（程式內角度**取負號**）、S2=GPIO21；為配合雲台限制角度：S1 -90~90 預設 0；S2 -90~20 預設 -60（改 `servo.h`）。接線：棕=GND、紅=5V、黃=訊號；板上下方是 S1、上方是 S2 | 舵機 S1 每秒在 -90 與 90 間來回 |
| 16-7 驅動馬達 | `pwm_motor` | 用 `bdc_motor` 元件（`idf_component.yml` 加 `bdc_motor: "^0.1.0"`）；`bdc_motor_new_mcpwm_device`、`bdc_motor_forward/reverse/brake/coast/set_speed`；PWM 25kHz；ESP32-S3 一個 timer group 最多驅動 3 顆馬達，所以 M1~M3 用 group 0、M4 用 group 1；有「死區補償」`PwmMotor_Ignore_Dead_Zone`（310 馬達起轉電壓約 3~5V）；`PwmMotor_Stop(id, brake)`：brake=煞停、coast=滑行停 | **先把車架空**。四輪正轉 1 秒→煞停 1 秒→反轉 1 秒→滑行停 1 秒，循環 |
| 16-8 編碼器 | `encoder` | 用 ESP32 的 **PCNT**（脈衝計數器）：`pcnt_new_unit`、`pcnt_unit_set_glitch_filter`、`pcnt_new_channel`、`pcnt_channel_set_edge_action/level_action`、`pcnt_unit_get_count`。A、B 兩相互為 edge/level，做正交解碼 | 每 200ms 印 `Encoder:%d, %d, %d, %d`。手轉輪子一圈約 ±**1040** 脈衝（減速比 1:20、13 線 AB 相霍爾、軟體雙邊緣觸發；13×4×20=1040）；Reset 歸零 |
| 16-9 PID 控速 | `pid_speed` | 用 `pid_ctrl` 元件（`pid_ctrl: "^0.1.1"`）；**增量式 PID**，預設 `kp=1.0, ki=0.2, kd=0.2`，積分限幅 ±1000；`Motor_Task` 用 `xTaskCreatePinnedToCore(...,core 1)` 與 `vTaskDelayUntil` 定週期；`Motor_Set_Speed(m1,m2,m3,m4)` 單位 m/s、範圍 -1.0~1.0；每個週期用編碼器脈衝差算實際速度，PID 輸出為 PWM；`Motor_Update_PID_Parm/Read_PID_Parm` | **架空**。`Motor_Set_Speed(0.5, 0.5, -0.30, -0.30)`，每 100ms 印 `Read_Speed:`，5 秒後 `Motor_Stop(STOP_COAST)`；想再動要按 Reset |
| 16-10 讀 IMU | `read_imu` | IMU 晶片 **ICM42670P**，I2C（SDA=GPIO40、SCL=GPIO39、400kHz）、INT=GPIO41（中斷，資料就緒時 `gpio_isr_handler` 計數）；`inv_imu_init`、`inv_imu_get_who_am_i`（驗證 WHO_AM_I）、設定加速度 ±4g、陀螺儀 ±2000dps、輸出 400Hz、低雜訊模式；`Icm42670p_Get_Accel_g()`、`Icm42670p_Get_Gyro_dps()` | 每 200ms 印 `Accel_g:... Gyro_dps:...`，搖晃板子數值會變 |
| 16-11 讀雷達 | `read_lidar` | MS200 雷達走 UART1（GPIO17 TX / GPIO18 RX，**230400**）；自己解析封包：CRC8 驗證、`Ms200_Parse_Package`、處理 0 度跨越；`Lidar_Ms200_Get_Distance(point)` 單位 mm。雷達線有防反插 | 每 200ms 印 0°/90°/180°/270° 距離；雷達箭頭方向為 0°，順時針增加；用手擋即可看數值變化 |
| 16-12 Flash 存取 | `flash` | **NVS**：`nvs_flash_init`、`nvs_open`、`nvs_get_i32/u16/blob`、`nvs_set_i32/u16/blob`、**`nvs_commit`（寫入後一定要呼叫）**；key 如 `FKEY_TEST_INT32`；ESP32-S3-WROOM-1U-N4R2 = 4MB Flash + 2MB PSRAM | 第一次燒錄 blob 會印亂碼（尚無資料），按 KEY1 寫入後即正常。BOOT 鍵讓 u16 +1、KEY1 讓 i32/blob +1；Reset 後仍讀回存的值（斷電不遺失） |
| 16-13 分區表 | `partition_table` | 專案根目錄新增 `partitions.csv`（`nvs`、`phy_init`、`factory`3M），並在 menuconfig 指定為自訂分區表 | 編譯與開機訊息中 `boot: Partition Table` 與 csv 一致 |
| 16-14 藍牙 | `bluetooch`（原文拼寫） | 先在設定啟用藍牙並手動開 BLE 4.2；`SAMPLE_DEVICE_NAME "YahBoom_BL"`，廣播資料 `spp_adv_data[]`（長度 0x0B、型態 0x09、字元逐一填入）；`BLE_Parse_Rx_Data()` 收資料 | 印 `BLE_SERVER: BLE_Init init bluetooth`。手機用 LightBlue 搜尋、連線，進服務 `0000ffe1`，資料格式改 UTF-8 String，WRITE `hello yahboom`，序列埠會印出 `BLE RX: ...`。**【文件矛盾】** 程式名稱 `YahBoom_BL`，圖文說明寫 `Yahboom_BL`（大小寫不同），以實際掃到的為準 |
| 16-15 WiFi 連線 | `wifi_sta` | STA 模式：`esp_netif_init`、`esp_event_loop_create_default`、`esp_netif_create_default_wifi_sta`、`esp_wifi_init`、`esp_event_handler_instance_register`、`esp_wifi_set_mode(WIFI_MODE_STA)`、`esp_wifi_set_config`、`esp_wifi_start`；事件組 + 重試次數；SSID/密碼來自 `idf.py menuconfig` → `Example Configuration` | 連上會印 SSID 與密碼（`connected to ap SSID:...`），超過重試次數印失敗後結束 |
| 16-16 車體運動學 | `car_motion` | 四輪差速模型：`Vm1=Vx-Vz*(A+B)`、`Vm2=Vx-Vz*(A+B)`、`Vm3=Vx+Vz*(A+B)`、`Vm4=Vx+Vz*(A+B)`（A=左右輪距的一半，B=前後輪距的一半；程式裡常數叫 `ROBOT_APB`）。`Motion_Ctrl(V_x, V_y, V_z)`：Vx 範圍 [-1.0, 1.0]、Vy 無效、Vz 範圍 [-5.0, 5.0]；反向 `Motion_Get_Speed()`：`Vx=(m1+m2+m3+m4)/4`、`Wz=-(m1+m2-m3-m4)/4/ROBOT_APB`。Vz 正＝左轉 | **架空**。以 0.5 m/s 前進，每 100 ms 印 `Read Motion:`，5 秒後 `Motion_Stop(STOP_COAST)` |
| 16-17 ROS-WiFi 相機模組 | （無程式課） | 硬體：7.4V 鋰電池 + microROS 控制板 + WiFi 相機。開擴充板開關後，電腦 WiFi 清單會出現 `Yahboom_ESP32_WIFI`（免密碼） | 連上後瀏覽器開 `http://192.168.4.1:81/stream` 看畫面。**【推測】** 這是相機模組自己的 AP 串流，不經 ROS 話題（雖然標題有 ROS） |

**第 16 組的學習價值（給初學者）：** 這 16 課其實是在教「從零把車子的每個零件各自驅動起來」（LED→按鍵→蜂鳴器→序列→ADC→舵機→馬達→編碼器→PID→IMU→雷達→儲存→無線），第 16-16 課把它們組成「會依速度指令走的車」；接著第 17 組才把這輛車接上 ROS 話題。

### 第 17 組：micro-ROS 基礎課（rclc + 話題）

#### 3.17.0 所有課共用的「micro-ROS 程式骨架」

每課的 `app_main` 都長這樣（逐字來自文件）：

```c
// 1) 連 WiFi（SSID/密碼來自 menuconfig 的 micro-ROS Settings->WiFi Configuration）
ESP_ERROR_CHECK(uros_network_interface_initialize());

// 2) 取 ROS 參數（來自 menuconfig 的 micro-ROS example-app settings 與 micro-ROS Settings）
#define ROS_NAMESPACE   CONFIG_MICRO_ROS_NAMESPACE
#define ROS_DOMAIN_ID   CONFIG_MICRO_ROS_DOMAIN_ID
#define ROS_AGENT_IP    CONFIG_MICRO_ROS_AGENT_IP
#define ROS_AGENT_PORT  CONFIG_MICRO_ROS_AGENT_PORT

// 3) 建立 init options，設 domain id 與 agent 位址
rcl_allocator_t allocator = rcl_get_default_allocator();
rclc_support_t support;
rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
RCCHECK(rcl_init_options_init(&init_options, allocator));
RCCHECK(rcl_init_options_set_domain_id(&init_options, ROS_DOMAIN_ID));
rmw_init_options_t *rmw_options = rcl_init_options_get_rmw_init_options(&init_options);
RCCHECK(rmw_uros_options_set_udp_address(ROS_AGENT_IP, ROS_AGENT_PORT, rmw_options));

// 4) 反覆嘗試連 agent，成功才往下（沒開 agent 就永遠卡在這個迴圈，每 500ms 重試）
while (1) {
    ESP_LOGI(TAG, "Connecting agent: %s:%s", ROS_AGENT_IP, ROS_AGENT_PORT);
    state_agent = rclc_support_init_with_options(&support, 0, NULL, &init_options, &allocator);
    if (state_agent == ESP_OK) { ESP_LOGI(TAG, "Connected agent: %s:%s", ROS_AGENT_IP, ROS_AGENT_PORT); break; }
    vTaskDelay(pdMS_TO_TICKS(500));
}

// 5) 建節點 → 建 publisher / subscription / timer → 加進 executor
rcl_node_t node;
RCCHECK(rclc_node_init_default(&node, "節點名", ROS_NAMESPACE, &support));
// publisher：rclc_publisher_init_default(&publisher, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(包, msg, 型別), "話題名")
// subscription：rclc_subscription_init_default(同上)
// timer：rclc_timer_init_default(&timer, &support, RCL_MS_TO_NS(週期毫秒), callback)
rclc_executor_t executor;
RCCHECK(rclc_executor_init(&executor, &support.context, handle_num, &allocator)); // handle_num >= publisher 的 timer 數 + subscriber 數
RCCHECK(rclc_executor_add_timer(&executor, &timer));
RCCHECK(rclc_executor_add_subscription(&executor, &subscriber, &recv_msg, &callback, ON_NEW_DATA));

// 6) 主迴圈
while (1) {
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
    usleep(1000);
}
```

核心概念白話翻譯：

- **support**：micro-ROS 的「執行環境」。**node**：節點（程式在 ROS 網路的身分）。**publisher/subscription**：發布者／訂閱者。**timer**：定時器，到時間觸發 callback（例：10Hz 發布）。**executor**：調度員，負責看「哪個 timer 到點、哪個 subscriber 有新資料」並呼叫對應 callback。`rclc_executor_spin_some` 要放在無窮迴圈裡持續呼叫，否則 callback 永遠不執行。
- `RCCHECK`／`RCSOFTCHECK`：錯誤檢查巨集（前者失敗會中止，後者只記錄）。**【推測】** 由 micro-ROS 範例定義，文件沒展開。
- **ROS_NAMESPACE**：預設為空；若設非空（10 字元內）會加在節點與話題前。**ROS_DOMAIN_ID** 預設 **20**（多人同一區網時可改以避免衝突）。
- 用 `msg.data` 的訊息型別在 C 中叫 `std_msgs__msg__Int32` 這種「包名__msg__型別」。

**每課共通的 menuconfig 步驟：**

```bash
idf.py menuconfig
# micro-ROS Settings：Agent IP、Agent Port 填 agent 所在主機
# micro-ROS Settings -> WiFi Configuration：WiFi SSID、WiFi Password
# micro-ROS example-app settings：ROS domain id（預設 20）、Ros namespace（預設空）
# 按 S 存檔、Q 離開
idf.py build flash monitor
```

**每課共通的驗證：**

```bash
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4   # 先開 agent（已開就不用）
ros2 node list
ros2 node info /<節點名>
```

#### 逐課重點

**17-1 發布話題**（`microros_samples/publisher`）

- 目的：發布 `std_msgs/msg/Int32`。節點 `esp32_publisher`，publisher 名/話題 `publisher`，timer 100ms（10Hz），callback `timer_callback` 印 `Publishing: %d`、`rcl_publish(&publisher, &msg, NULL)`、`msg.data++`。`handle_num = 1`。
- 驗證：

```bash
ros2 node list
ros2 node info /esp32_publisher
ros2 topic echo /publisher
ros2 topic hz /publisher        # 約 10Hz 為正常
```

**17-2 訂閱話題**（`subscriber`）

- 節點 `esp32_subscriber`，話題 `subscriber`，型別 `std_msgs/msg/Int32`，`rclc_executor_add_subscription(..., ON_NEW_DATA)`，callback `subscription_callback(const void *msgin)` 強制轉型成 `std_msgs__msg__Int32 *` 後印 `Received: %d`。
- 驗證：

```bash
ros2 topic pub /subscriber std_msgs/msg/Int32 "data: 123"
```

序列埠印出 123 即成功。

**17-3 多話題收發**（`publisher_subscriber`）

- 節點 `esp32_pub_sub`；3 個 publisher（`publisher_1/2/3`）+ 3 個 subscriber（`subscriber_1/2/3`），型別都是 `std_msgs/msg/Int32`；3 個 timer 各 100ms；`handle_num = 6`（3 timer + 3 subscription）。這正好用滿「3 / 3」的上限設定（見 2.6）。
- 驗證：

```bash
ros2 topic pub /subscriber_1 std_msgs/msg/Int32 "data: 123"
ros2 topic pub /subscriber_2 std_msgs/msg/Int32 "data: 456"
ros2 topic pub /subscriber_3 std_msgs/msg/Int32 "data: 789"
ros2 topic hz /publisher_1     # 另外 /publisher_2、/publisher_3 同理
ros2 topic echo /publisher_1
```

**17-4 訂閱蜂鳴器話題**（`beep_subscriber`）

- 需把 16-3 的蜂鳴器元件複製到專案 `components` 目錄並呼叫 `Beep_Init`。節點 `beep_subscriber`，話題 **`beep`**，型別 **`std_msgs/msg/UInt16`**，callback 內 `Beep_On_Time(msg->data)`。
- 驗證：

```bash
ros2 topic pub --once /beep std_msgs/msg/UInt16 "data: 1"      # 持續響
ros2 topic pub --once /beep std_msgs/msg/UInt16 "data: 0"      # 關
ros2 topic pub --once /beep std_msgs/msg/UInt16 "data: 300"    # 響 300 毫秒後自動關
```

**17-5 訂閱 PWM 舵機話題**（`servo_subscriber`）

- 節點 `servo_subscriber`，兩個話題 **`servo_s1`**、**`servo_s2`**，型別 **`std_msgs/msg/Int32`**；`handle_num = 2`；callback 內 `int8_t angle = (msg->data) & 0xFF;` 再 `Servo_Set_Angle(SERVO_ID_S1/S2, angle)`。S1 範圍 -90~90，S2 範圍 -90~20。
- 注意（**【推測】**，由程式碼推得）：`& 0xFF` 後轉 int8，若傳入超出 -128~127 的數字會「繞圈」變成別的角度，所以請只送範圍內數值。官方 05-1 也說：超出範圍舵機不會轉。
- 驗證：

```bash
ros2 topic pub --once /servo_s1 std_msgs/msg/Int32 "data: 30"
ros2 topic pub --once /servo_s2 std_msgs/msg/Int32 "data: -60"
```

**17-6 訂閱速度控制話題**（`twist_subscriber`）

- 把 16-9／16-16 的馬達（含編碼器 + PID + 運動學）元件複製進專案，呼叫 `Motor_Init`。節點 `twist_subscriber`，話題 **`cmd_vel`**，型別 **`geometry_msgs/msg/Twist`**；callback `twist_Callback`：印 `cmd_vel:` 並 `Motion_Ctrl(twist_msg.linear.x, 0, twist_msg.angular.z)`（只用 linear.x 與 angular.z；四輪差速車不橫移，linear.y 被忽略）。
- **架空後才測**：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"   # 前進 0.5 m/s
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 1.5}}"   # 旋轉 1.5 rad/s
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"   # 停止
```

**17-7 發布速度（里程計）話題**（`odom_publisher`）

- 在 17-6 基礎上加發布。節點 `odom_publisher`；話題 **`odom_raw`**，型別 **`nav_msgs/msg/Odometry`**；timer 50ms = **20Hz**；`handle_num = 2`（1 timer + 1 subscription）。
- `odom_ros_init()`：`header.frame_id = "odom_frame"`，`child_frame_id = "base_footprint"`；若 ROS_NAMESPACE 非空，會變成 `<ns>/odom_frame`。
- `odom_update(vel_dt, vx, vy, wz)`：用編碼器速度做**航位推算**（dead reckoning）：`heading += wz*dt`，`x += (vx*cos(h) - vy*sin(h))*dt`，`y += (vx*sin(h) + vy*cos(h))*dt`；再用 `odom_euler_to_quat` 轉成四元數；pose covariance [0]、[7]、[35] = 0.001，twist covariance 同位置 = 0.0001。
- 驗證：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
ros2 topic echo /odom_raw
ros2 topic hz /odom_raw        # 約 20Hz 為正常
```

**17-8 發布 IMU 話題**（`imu_publisher`）

- 節點 `imu_publisher`；話題 **`imu`**，型別 **`sensor_msgs/msg/Imu`**；timer 50ms = **20Hz**；`frame_id = "imu_frame"`（有 namespace 則加前綴）。背景 `imu_update_data_task` 每 10ms 更新一次，把 `Icm42670p_Get_Gyro_dps()` 填到 `angular_velocity`、`Icm42670p_Get_Accel_g()` 填到 `linear_acceleration`；`orientation` 預設 (0,0,0,1)。
- **【推測】需留意單位**：官方範例程式碼把「度/秒」與「g」直接放進 Imu 訊息，而 ROS 標準（REP-103）是 rad/s 與 m/s²。出廠韌體是否轉換，文件沒說；做 EKF／導航時要自己確認。
- **【文件矛盾】** 17-8 的驗證小節寫 `Subscribe to the data of the /odom_raw topic,` 但指令是 `ros2 topic echo /imu`（文字複製錯誤，以指令為準）。

```bash
ros2 topic echo /imu
ros2 topic hz /imu             # 約 20Hz 為正常
```

**17-9 發布雷達話題**（`lidar_publisher`）

- 把 16-11 的雷達元件複製進來，先 `Uart1_Init()`、`Lidar_Ms200_Init()`。節點 `lidar_publisher`；話題 **`scan`**，型別 **`sensor_msgs/msg/LaserScan`**；timer 90ms ≈ **11Hz**。
- `lidar_ros_init()`：`angle_min = -180°`、`angle_max = 180°`（以弧度）、`angle_increment = 1°`、`range_min = 0.12`、`range_max = 8.0`（公尺）、`ranges` 與 `intensities` 各 360 個 float、`frame_id = "laser_frame"`。
- `lidar_update_data_task` 每 20ms 更新，並做索引轉換（`index = (MS200_POINT_MAX-i) % MS200_POINT_MAX`，再 ±180），把雷達「順時針、0° 在箭頭」的資料轉成 ROS 習慣的「逆時針」排列。距離 mm → m（`/1000.0`）。

```bash
ros2 topic echo /scan
ros2 topic hz /scan            # 約 11Hz 為正常
```

**17-10 自訂傳輸方式（序列埠傳輸）**（`custom_transport`）

- 目的：不走 WiFi，改走序列埠連 agent。需要**重編 `libmicroros.a`**：專案不使用 `extra_components`，改用 `custom_components`（官方虛擬機已裝好）；`colcon.meta` 的 `"-DRMW_UXRCE_TRANSPORT=custom"`（其他上限同 2.6）。
- 預設參數（menuconfig 的 micro-ROS example-app settings）：序列埠 2、鮑率 **921600**、TX **GPIO43**、RX **GPIO44**、namespace 空、domain id **20**。**【文件矛盾／推測】** 文件寫「串口 2」，但 GPIO43/44 在 15-1 表中是 UART0（Type-C 燒錄口）；程式裡 `uart_driver_delete(UART_NUM_0)` 先卸掉 UART0 後再用，所以實際效果是「把 Type-C 序列線改成 micro-ROS 通道」。
- 關鍵 API：`rmw_uros_options_set_custom_transport(true, &uart_port, transport_serial_open, transport_serial_close, transport_serial_write, transport_serial_read, rmw_options)`，自行實作四個 callback（`uart_param_config`、`uart_set_pin`、`uart_driver_install`、`uart_write_bytes`、`uart_read_bytes`）。節點 `custom_transport`，publisher 話題 `custom_publisher`（`std_msgs/msg/Int32`）。
- 結果：燒完 monitor 會印**亂碼**（因為 micro-ROS 在序列埠上傳的是二進位協定，不是文字），這是正常的。Ctrl+] 離開後改開序列 agent：

```bash
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 921600 -v4
ros2 node list
ros2 node info /custom_transport
ros2 topic echo /custom_publisher
```

- **重要**：序列 agent 會佔用序列埠，下次要燒錄前必須先 Ctrl+C 關掉 agent。

---

## 4. 這台車 ESP32（出廠）韌體對外提供的 ROS 介面

> 出廠韌體**只提供 .bin，不提供原始碼**（03-1 明寫）。以下以 05-1「Robot information release」為準，並對照第 17 組同名範例。

### 4.1 節點與話題

- 出廠節點名：**`/YB_Car_Node`**（`ros2 node list` 看不到 → 先檢查 ROS_DOMAIN_ID 是否一致；03-3 明寫）。
- 訂閱（Pi 5 → ESP32，下指令）：

| 話題 | 訊息型別 | 用途 | 值域／備註 |
| --- | --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 車速控制 | linear.x（前後 m/s）、angular.z（旋轉 rad/s）；範例韌體限制 Vx∈[-1.0,1.0]、Vz∈[-5.0,5.0] |
| `/beep` | `std_msgs/msg/UInt16` | 蜂鳴器 | 0 關、1 持續響、≥10 為毫秒數（05-1 查證型別 `std_msgs/msg/UInt16`） |
| `/servo_s1` | `std_msgs/msg/Int32` | 舵機 S1（雲台） | **[-90, 90]**，超出範圍舵機不轉 |
| `/servo_s2` | `std_msgs/msg/Int32` | 舵機 S2（雲台） | **[-90, 20]**，超出範圍舵機不轉 |

- 發布（ESP32 → Pi 5，回報狀態）：

| 話題 | 訊息型別 | 內容 | 範例韌體的頻率／frame |
| --- | --- | --- | --- |
| `/imu` | `sensor_msgs/msg/Imu` | 六軸 IMU（ICM42670P） | 20Hz，frame `imu_frame` |
| `/odom_raw` | `nav_msgs/msg/Odometry` | 輪速里程計原始值 | 20Hz，`odom_frame` → `base_footprint` |
| `/scan` | `sensor_msgs/msg/LaserScan` | MS200 雷達 | 約 11Hz，frame `laser_frame`，360 點，0.12~8.0m |

- **【文件矛盾】** 05-1 的「發布話題清單」寫 `/odom：Odometer module data`，但同一頁的查詢指令是 `ros2 topic echo /odom_raw`，且 05-4（狀態估計）明說：`/ekf_filter_node` 訂閱 `/imu/data` 與 `/odom_raw`，再發布 `/odom`。結論：**ESP32 發的是 `/odom_raw`；`/odom` 是 Pi 端 EKF 融合後的產物**。
- `/imu/data`（EKF 的輸入）是由哪個 Pi 端節點由 `/imu` 產生，在我負責的文件裡沒有說明（**【推測】** 在 `yahboomcar_bringup` 內以 IMU 濾波節點處理）。
- 出廠頻率／frame_id 沒有逐字寫，上表頻率是「第 17 組範例」數值，出廠版請以 `ros2 topic hz` 實測為準。
- **電池電壓沒有對應的 ROS 話題**（文件未見）。電量低時板子自己蜂鳴器嗶嗶響（每 100ms 一次），且**車子此時無法控制**（FAQ 5）。

### 4.2 通訊方式

| 版本 | 通訊方式 | 說明 |
| --- | --- | --- |
| **樹莓派版（Pi 5，本車）** | **序列埠**（USB 序列，`/dev/ttyUSB0`） | 配置 `robot.CAR_TYPE_RPI5` |
| 虛擬機／電腦版 | **WiFi UDP** | 出廠韌體相同，靠「參數」區分（FAQ 2） |

- 兩種版本**出廠韌體是同一個檔**，差異只在 `config_robot.py` 寫入板子的參數。

### 4.3 agent 啟動指令（出廠 Pi 5 環境）

```bash
sh ~/start_agent_rpi5.sh          # 在 Pi 5 主機終端：啟動 agent（腳本內容文件沒貼，推測內部就是上面的 serial agent docker 指令）
./ros2_humble.sh                  # 另開終端進入 ROS 2 Humble Docker（部分文件寫成 sh ros2_humble.sh）
ros2 node list                    # 應看到 /YB_Car_Node
ros2 node info /YB_Car_Node
ros2 topic list
```

- 開機流程：Pi 開機會**自動啟動**「連接 agent 的終端」與「Docker 終端」兩個視窗（03-2）；要手動做時要先 `exit` 退出 Docker、Ctrl+C 關掉 agent 的自啟動。
- 手動啟動順序：**先啟動 agent → 再打開車子電源（或按 Reset）→ 自動連上**。
- 通用 agent 指令（WiFi 版）：`docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4`；序列版見 2.7。

### 4.4 MCU 指示燈狀態（FAQ 6）

| 狀態 | 指示燈 |
| --- | --- |
| 設定狀態（開機後約 5 秒內） | 每 300ms 閃一次 |
| 連線 agent 中 | 每 1 秒慢閃一次 |
| microROS 錯誤 | 每 50ms 快閃 |
| 正常 | 每 3 秒快閃 2 次 |
| 低電壓 | 每 100ms 閃一次（並伴隨蜂鳴器嗶嗶） |

---

## 5. 燒錄出廠韌體與參數設定

> 前提：板子出廠已燒好韌體；**若沒燒過其他韌體，不需要重燒**。若跑過第 16、17 組的練習程式，**必須重燒出廠韌體**才能回到車子用的狀態（03-2）。

### 5.1 燒錄出廠韌體（Windows，03-1）

1. 安裝 **CP2102 驅動**（隨附資料 `Hardware related information → CP2102 serial port chip → CP2102-Windows driver file.zip`；64 位元 Win10 執行 `CP210xVCPInstaller_x64.exe`）。裝完在「裝置管理員 → 連接埠」要看到 CP210x。Type-C 線接到控制板的 Serial 孔。
2. 下載並解壓 Espressif `flash_download_tool`（`https://www.espressif.com.cn/zh-hans/support/download/other-tools`），晶片選 **ESP32-S3**。
3. `SPIDownload` 裡選檔案 **`microROS_Robot_Vx.x.x.bin`**（Vx.x.x 為版本號），位址填 **`0x0`**，**勾選 `DoNotChgBin`**，選 COM 埠，其他保持預設。
4. 按 **Start**。不自動開始：按住 **BOOT0** → 按 **Reset** → 放開 BOOT0。
5. 完成出現藍色 **FINISH**，斷電重啟或按 Reset。
6. 驗證：序列助手 `UartAssist.exe`（隨附資料內），**115200、8 bit、1 stop、無 parity、無流控**；按 Reset，要看到 **`hello Yahboom`** 與下一行的韌體版本號。

> 與自己編的程式不同：出廠 = **單一檔 @ 0x0 + DoNotChgBin**；自編 = 三個檔分別在 0x0000 / 0x8000 / 0x10000。

### 5.2 設定參數（03-2，在 Pi 5 上，出廠已設好，熟悉後才改）

1. 出廠 Pi 開機後可連原廠熱點，用 VNC 登入桌面：預設 IP **10.42.0.1**，帳號 `pi`，密碼 `yahboom`（文件原文）。
2. 要設定參數前，先在 Docker 終端輸入 `exit` 離開 Docker，並在 agent 終端 Ctrl+C 關掉 agent。
3. 檢查序列裝置：`ls /dev/ttyUSB*`。
4. 編輯家目錄的 `config_robot.py`：
   - 車型改為 **`robot.CAR_TYPE_RPI5`**（本車）。
   - ROS_DOMAIN_ID：`set_ros_domain_id(20)`（FAQ 說合法範圍 **0~101**，預設 **20**，一般不用改）。
   - 其他參數（舵機初始角度、馬達 PID）保持預設。
   - 多車用 `robot.set_ros_namespace()`（如 `robot1`、`robot2`，見 10.Multi-machine 課；兩車 ROS_DOMAIN_ID 需設相同）。
5. 先**短按板子 Reset**；開機 5 秒內是「設定狀態」（MCU 燈每 300ms 閃一次），此時執行：

```bash
python3 config_robot.py            # 多機課文件寫 sudo python3 config_robot.py
```

   檢查回傳的資料是否與你設定的一致。
6. 再按一次 Reset 讓板子重新載入設定。

### 5.3 讓 Pi 端的 ROS_DOMAIN_ID 與板子一致

- 進 Docker 後 `ros2 node list` 看不到 `/YB_Car_Node` → 兩邊 ID 不一致。在 Docker 終端 `vi ~/.bashrc`，改成對應的 ID（例如 `export ROS_DOMAIN_ID=20`）。
- 多台機器一起用：不同車用不同 ROS_DOMAIN_ID 可避免互相干擾（FAQ 7）。電腦端要在 `~/.bashrc` 加一行 `export ROS_DOMAIN_ID=20`（改成你的數字）並重開終端。

### 5.4 自己燒 WiFi 版（第 17 組練習用）要設定的東西

- `idf.py menuconfig` → `micro-ROS Settings`：`Agent IP`（跑 agent 那台機器的 IP）、`Agent Port`（對應 `--port 8090`）。
- `micro-ROS Settings → WiFi Configuration`：`WiFi SSID`、`WiFi Password`。
- `micro-ROS example-app settings`：`ROS domain id`（預設 20）、`Ros namespace`（預設空）。
- WiFi 練習裡 agent 與 ESP32 必須在**同一個區域網路**，且 agent IP 要寫對（不是 localhost）。

---

## 6. 為何屬於「高級」＋學習建議

### 6.1 屬於高級的理由

1. **兩套工具鏈同時要學**：ESP-IDF（C、FreeRTOS、CMake、menuconfig、Kconfig）＋ ROS 2（話題、節點、QoS、agent）。
2. **嵌入式觀念門檻高**：GPIO、PWM、I2C、UART、ADC、PCNT、中斷、ring buffer、FreeRTOS task／tick、分區表、NVS——一般 ROS 使用者完全不用懂。
3. **回饋鏈長，除錯困難**：問題可能出在 韌體 / WiFi / agent / Docker / DOMAIN_ID / 序列埠被佔用 任一環，而且很多失敗是「靜默」的（只是一直 Connecting agent）。
4. **硬體風險**：馬達會真的轉（文件反覆提醒「**先把車架空**」）；燒錯韌體會讓車子失去原本功能（需重燒出廠 .bin）。
5. **環境重**：ESP-IDF v5.1.2 + micro-ROS 元件 + colcon，在 Windows 難裝；官方預設以 Ubuntu 虛擬機為準。
6. **出廠韌體沒有原始碼**：只能學範例；要改出廠行為只能自己重寫。

### 6.2 學習建議（給從零開始的人）

- **先不要碰這三章。** 先把「初級／中級」學完：能用 `ros2 topic pub/echo/hz`、`ros2 node list`，理解 topic、node、`/cmd_vel`、`/odom`、`/scan`、DOMAIN_ID。這些概念在第 17 組驗證步驟中全會用到。
- 要學時的順序：16-1 LED → 16-2 按鍵 → 16-3 蜂鳴器 → 16-4 UART → 16-5 ADC → 16-6 舵機 → 16-10 IMU → 16-8 編碼器 → 16-7 馬達 → 16-9 PID → 16-16 運動學 → 17-1、17-2（先用 Int32）→ 17-4~17-9 → 17-10。
- 17 組前 3 課（發布／訂閱／多話題）是學 micro-ROS **最乾淨的入門**：不碰馬達，只要 WiFi + agent。
- 每改一次程式就用 `idf.py build flash monitor` 驗證一次；改 `sdkconfig` 後若怪怪的，`idf.py fullclean` 再 build（**【推測】** 常見做法，文件沒寫）。
- 燒完自己的程式，要回到車子的正常狀態：重燒出廠 .bin（第 5.1 節）並用 `config_robot.py` 確認參數。

### 6.3 沒有車也能練的部分（只買一片 ESP32-S3 開發板）

> 控制板核心就是 ESP32-S3，所以「ESP32-S3 開發板（如 DevKitC 類）」大部分基礎課程可以練。**板子選 ESP32-S3**（文件目標 `idf.py set-target esp32s3`）。以下的「GPIO 編號要改」是我的推測，開發板接腳與本控制板不同。

| 課 | 沒車能練嗎 | 備註 |
| --- | --- | --- |
| 16-1 LED | 能 | 改 LED GPIO（開發板的 LED 腳位不同；有些是 RGB 燈） |
| 16-2 按鍵 | 能 | BOOT 鍵（GPIO0）通用；KEY1 要自己接按鈕 |
| 16-3 蜂鳴器 | 能（要外接） | 買主動蜂鳴器 + 接 GPIO |
| 16-4 序列通訊 | 能 | USB 序列回送；UART1 可兩腳短接自測 |
| 16-5 電池電壓 | 部分 | 需外接分壓電路 |
| 16-6 舵機 | 能（要外接舵機） | 5V 與 GND 要正確 |
| 16-7 馬達／8 編碼器／9 PID／16 運動學 | 需要馬達驅動板與編碼馬達 | 沒有就只能讀程式 |
| 16-10 IMU | 需外接 ICM42670P（或改寫給別顆 IMU） | |
| 16-11 雷達 | 需 MS200 或同協定雷達 | |
| 16-12 Flash／16-13 分區表 | **完全能** | 純軟體；注意開發板 Flash 大小可能不是 4MB（要與 menuconfig 相符） |
| 16-14 藍牙／16-15 WiFi | **完全能** | 需手機 App 與 WiFi 熱點 |
| 17-1 發布／17-2 訂閱／17-3 多話題 | **完全能** | 只要 WiFi + agent（Docker）；最推薦 |
| 17-4 蜂鳴器話題／17-5 舵機話題 | 需外接元件 | 可先把 callback 改成印出數值 |
| 17-6~17-9（速度／odom／IMU／雷達） | 需對應硬體 | 沒硬體也能改成「假資料」練習訊息結構（**【推測】**） |
| 17-10 自訂序列傳輸 | **完全能** | 一條 USB 線 + 序列 agent 即可（記得關 monitor） |
| 15 環境建置、agent 操作 | **完全能** | ESP-IDF、Docker、agent 可在 Ubuntu／WSL／VM 上練（USB 直通要設定） |

- 另外 **【文件外常識，非官方文件內容】** micro-ROS 元件對 ESP32 其他型號也有支援；但本教材與腳本都以 `esp32s3` 為目標，建議直接買 S3，避免差異。

---

## 7. 初學者最容易卡住的 5 個地方

1. **新開終端忘了 `source ~/esp/esp-idf/export.sh`** → `idf.py: command not found`。文件在幾乎每一課都重複強調「每次開新終端都要先啟用」。
2. **一直停在 `Connecting agent: ...`**：
   - agent 沒開，或開在錯的埠（要對應 `--port 8090`）。
   - menuconfig 的 `Agent IP` 填錯（要是跑 agent 那台的區網 IP）。
   - WiFi SSID／密碼錯，或 ESP32 與 agent 不在同一區網。
   - agent 已開過一份（只能開一個）；上次直接關終端造成 Docker 容器殘留 → `docker ps -a | grep microros/micro-ros-agent`、`docker stop <id>`。
   - 解法：Ctrl+C 結束 agent、按板子 Reset 重新連。
3. **`ros2 node list` 看不到節點（或看不到 `/YB_Car_Node`）**：多半是 **ROS_DOMAIN_ID 不一致**（板子預設 20，Pi／電腦 `~/.bashrc` 沒設）。其次是忘了進 ROS 2 Docker（`./ros2_humble.sh`）。
4. **序列埠被佔用，燒錄失敗／連不到板子**：序列 agent、monitor、序列助手任何一個占著序列埠，`idf.py flash` 就會失敗；17-10 文件明說「燒錄前先 Ctrl+C 關序列 agent」。在虛擬機要選「連接到虛擬機」；`idf.py flash` 時電腦只能接一個序列裝置，否則要 `-p /dev/ttyUSB0`。進不了燒錄模式時：按住 BOOT0 → 按 Reset → 放開 BOOT0。
5. **燒了練習程式後車子「不能動了」／ 馬達亂轉**：
   - 練習程式會覆蓋出廠韌體，要回到車子功能需**重燒 `microROS_Robot_Vx.x.x.bin`（0x0，DoNotChgBin）**並用 `config_robot.py` 重設參數（車型 `CAR_TYPE_RPI5`、ID 20）。
   - 馬達類課程（16-7、16-9、16-16、17-6、17-7）燒完就會轉，**一定先把車子架空**；想再動要按 Reset。
   - 電池電量低時蜂鳴器會一直嗶且車子不聽指令，先充電（FAQ 5）。

> 補充（較次要）：micro-ROS 預設上限只有 2 publisher／2 subscriber，超過要改 `colcon.meta` 並重編 `libmicroros.a`（`idf.py clean-microros`）；17-10 燒完 monitor 出現亂碼是正常的；16-12 第一次讀 blob 亂碼也是正常的。
