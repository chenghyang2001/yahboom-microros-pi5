# 拍五上電檢查流程

拍五（Yahboom MicroROS-Pi5）每次開機後，照 1～10 的順序檢查，確認每一層都起來了。
跟 Claude 說「**檢查拍五的連線**」或「**拍五上電檢查**」，它就會照這份從頭跑到尾。

```
PC ─USB─ 手機(adb) ─熱點─ Pi 5「大腦」─ Docker(ROS 2) ─ micro-ROS agent ─USB 序列─ ESP32「小腦」─ 馬達/IMU/光達
```

所有指令都在 `~/workspace/yahboom-microros-pi5/drill` 執行。`ycar.py` 前面要加 `YCAR_PASS=yahboom PYTHONUTF8=1`，下文省略。

## 0. 實體準備（人做）

- 車子總開關打開，等 Pi 開機約 30 秒。
- 手機打開「個人熱點」（AnPing）。
- 手機用 USB 線接 PC，手機上若跳出「允許 USB 偵錯」就按允許。

## 1. 手機 adb

```bash
adb devices -l
```

✅ 看到 `84bbb261  device`
❌ 清單是空的：重插 USB 線、換一個孔，或換一條能傳資料的線，再確認手機已允許 USB 偵錯。

## 2. 網路：Pi 有連上熱點

```bash
adb -s 84bbb261 shell ip neigh
```

✅ 有一筆 MAC 是 `2c:cf:67:...` 開頭，那就是 Pi，IP 通常是 `10.57.201.1`。
❌ 找不到這筆：檢查熱點是否開著，Pi 是否已開機完成。IP 如果變了，後面步驟的 IP 都要跟著換。

## 3. 手機轉接（SSH／VNC 的通道）

```bash
adb -s 84bbb261 shell "nc -L -p 8022 nc 10.57.201.1 22"   &
adb -s 84bbb261 shell "nc -L -p 5900 nc 10.57.201.1 5900" &
adb -s 84bbb261 forward tcp:8022 tcp:8022
adb -s 84bbb261 forward tcp:5900 tcp:5900
adb -s 84bbb261 shell "ps -A | grep -w nc"
```

✅ `ps` 看到兩個 `nc`。
⚠️ USB 線一拔，或按了 ESP32 的 Reset，轉接就會斷，要重做這一步。

## 4. SSH

```bash
python ycar.py host 'uptime'
```

✅ 印出 Pi 的開機時間。也可以直接連 `127.0.0.1:8022`，回應開頭應該是 `SSH-2.0-OpenSSH`。

## 5. VNC（Pi 桌面）

```bash
python ycar.py host 'pgrep -a -f "^wayvnc"'
```

✅ 有 `wayvnc` 程序在跑。用 TigerVNC 連 `127.0.0.1:5900` 看得到 Pi 桌面，連進去時的回應是 `RFB 003.008`。

## 6. 大腦（Pi 5）健康

```bash
python ycar.py host 'vcgencmd measure_temp; vcgencmd get_throttled; df -h / | tail -1; timedatectl show -p NTPSynchronized'
```

| 項目 | 正常值 |
| --- | --- |
| 溫度 | < 70 °C（閒置約 40 多度） |
| `throttled` | `0x0`（不是 0 代表供電不足或過熱降頻） |
| 磁碟 | 使用率 < 90% |
| `NTPSynchronized` | `yes`（Pi 已經對好時間） |

## 7. Docker 容器

```bash
python ycar.py host 'docker ps --format "{{.Image}} | {{.Status}}"'
```

✅ 兩個容器都是 `Up`：

- `yahboomtechnology/ros-humble:4.1.2`：ROS 2 主環境，指令要送進這一個
- `microros/micro-ros-agent:humble`：負責和 ESP32 通訊的橋接，不要把指令送進這個

## 8. 小腦（ESP32 擴展板）

```bash
python ycar.py host 'ls -l /dev/ttyUSB0; lsusb | grep -i cp210'
python ycar.py host 'docker logs --tail 5 $(docker ps -q --filter ancestor=microros/micro-ros-agent:humble)'
```

✅ 有 `/dev/ttyUSB0`，`lsusb` 也看到 `Silicon Labs CP210x`（ESP32 的 USB 序列晶片），agent 紀錄裡有 `session established` 或 `... created`。
❌ 紀錄停在等待連線：按一下 ESP32 擴展板的 Reset，再回去做第 3 步。

其他 USB 裝置（有接的話）：`Microdia USB 2.0 Camera`（相機）、`DragonRise Controller`（手把接收器）。

## 9. ROS 2 節點與話題

```bash
python ycar.py status
python ycar.py ros 'ros2 topic list; timeout 5 ros2 topic hz /imu'
```

| 項目 | 正常值 |
| --- | --- |
| 節點 | 有 `/YB_Car_Node` |
| 話題 | `/battery /beep /cmd_vel /imu /odom_raw /scan /servo_s1 /servo_s2` 都在 |
| `/scan` | 約 12 Hz |
| `/imu` | 約 20 Hz |
| `/battery` | ≥ 70（數值是電壓×10，70 就是 7.0 V；低於 70 要準備充電） |

## 10. 時鐘差（要跑 SLAM／導航時一定要查）

```bash
python ycar.py ros 'S=$(timeout 5 ros2 topic echo --once /scan --field header.stamp.sec | head -1); echo 差=$(( $(date +%s) - S )) 秒'
```

✅ 差距在幾秒以內。
❌ 差到上千秒：Pi 沒有 RTC 電池，開機時先沿用上次關機的時間，ESP32 這時候對時；之後 Pi 用 NTP 校正，ESP32 不會跟著改，所以幾乎每次斷電重開都會這樣：只開車沒關係，但 SLAM／導航會把 `/scan` 當成過期資料丟掉。要用這些功能前，先按 ESP32 的 Reset，再重做第 3 步。

## 實測紀錄

| 日期 | 結果 |
| --- | --- |
| 2026-10-27 | 1～9 全部 ✅：溫度 42.8 °C、throttled 0x0、磁碟 55%、電池 70、/scan 12.4 Hz、/imu 21.5 Hz。第 10 步 ❌，時鐘差 5409 秒。 |
| 2026-10-28 | 熱點自動關閉導致 Pi 斷線，改用 adb 關閉自動關閉並重開車後恢復。1～9 ✅：41.1 °C、0x0、電池 79、/scan 12.5 Hz、/imu 21.1 Hz、耳機 K200 Pro 已連線（HFP 16 kHz）。第 10 步 ❌，時鐘差 42582 秒。 |
| 2026-10-28 下午 | 充電重開後 **Pi 的 IP 變成 `10.169.179.1`**（手機熱點換網段），第 3 步 nc 轉接要改新 IP；1～9 ✅：33.4 °C、0x0、電池 81、/scan 12.5 Hz、/imu 21.1 Hz；第 10 步時鐘差 15083 秒，按 ESP32 Reset 後歸零。**第 2 步一定要看 `ip neigh` 的實際 IP，不要沿用舊值。** |

## 附錄：有線備援（Wi-Fi／手機壞掉時）

拍五的有線網卡（eth0）已經設成「**自動取得 IP＋備援固定 IP `192.168.77.2/24`**」（2026-10-28 設定）。

- 自動取得 IP 會一直重試，不會因為逾時就斷開連線。
- 固定 IP 只用在區網，不設預設閘道（route-metric 700），不會搶走 Wi-Fi 的上網路由。
- Wi-Fi 設定完全沒動，原本的熱點流程照用。

### 接法

| 接法 | 筆電要做什麼 | 拍五的位址 |
| --- | --- | --- |
| 兩邊都接**路由器**（會發 IP） | 什麼都不用做 | `raspberrypi.local`，或到路由器的裝置清單查 |
| **一般 hub／交換器**，或網路線直接對接 | 有線網卡手動設成 `192.168.77.10`，遮罩 `255.255.255.0`，閘道留空 | `192.168.77.2` |

筆電設定固定 IP（Windows，用系統管理員身分開 PowerShell。網卡名稱用 `Get-NetAdapter` 查）：

```powershell
New-NetIPAddress -InterfaceAlias "乙太網路" -IPAddress 192.168.77.10 -PrefixLength 24
# 用完改回自動：
Remove-NetIPAddress -InterfaceAlias "乙太網路" -IPAddress 192.168.77.10 -Confirm:$false
Set-NetIPInterface -InterfaceAlias "乙太網路" -Dhcp Enabled
```

### 連線

```bash
ping 192.168.77.2
ssh pi@192.168.77.2                       # SSH
# VNC：TigerVNC 連 192.168.77.2:5900
cd ~/workspace/yahboom-microros-pi5/drill
YCAR_HOST=192.168.77.2 YCAR_PORT=22 YCAR_PASS=yahboom PYTHONUTF8=1 python ycar.py status
```

有線連上以後，上電檢查的第 1～3 步（adb、熱點、手機轉接）都跳過，從第 4 步開始做。ROS 2 容器用的是主機網路，送指令（`ycar.py ros`／`rospy`）跟走 Wi-Fi 時一樣。

### 還原（拿掉備援固定 IP）

```bash
python ycar.py host 'sudo nmcli con mod "Wired connection 1" ipv4.addresses "" ipv4.dhcp-timeout 0 ipv4.route-metric -1'
```

⚠️ 設定當下沒有接網路線，所以只確認了設定有存進去（`nmcli` 讀回 `192.168.77.2/24`），**還沒有接線實測**。第一次用有線時，請照上面的「連線」步驟驗證一次。
