# C2 筆記：Linux 基礎、樹莓派 5 設定、Docker

> 資料來源：`research/pdf-text/11.Linux basic course/`（20 檔）、`12.RPi basic setting course/`（12 檔）、`13.Docker course/`（5 檔）。
> 為了核對帳號密碼、agent 指令，我另外交叉參考了 `03.Preparation`、`01.Introduction/4. FAQ`、`15. microROS control board development environment/5. Install and start microros agent`，凡是出自這些檔案會註明。
> 標記【補充】＝文件沒寫、我補的說明；標記【警告】＝文件內容不適用本車或有誤導風險。

## 0. 先看這個：這批文件的「雜質」

Yahboom 的 Linux／樹莓派／Docker 課程是**多款產品共用的通用教材**，裡面混了不屬於 MicroROS-Pi5 的內容。教材編寫時**不要照抄**：

| 文件 | 雜質 | 為什麼不適用 |
| --- | --- | --- |
| 11-6、11-7、11-9 | 帳號 `jetson`、密碼 `yahboom`、IP 範例 `192.168.2.93`／`192.168.16.66` | 那是 Jetson Nano 範例；**本車樹莓派帳號是 `pi`**（見 2.2） |
| 11-10 | `Muto`、`MutoLib`、`/dev/myserial` | 另一款機器人（Muto）的驅動，與本車無關 |
| 11-14 | `deb http://mirrors.aliyun.com/raspbian/raspbian/ buster ...` | 這是舊版 Raspbian Buster 的中國大陸軟體源；Pi 5 必須使用 Bookworm 以上，**照抄會把系統弄壞**【警告】 |
| 11-18 | Jetson Nano／JetPack 版本查詢 | 與 Pi 無關 |
| 11-19 | Jetson 版與 Pi 版 service 範例，OLED | OLED 是範例；只有 `User=pi` 那份適用 |
| 11-12 | `rplidar.rules` 綁定 `10c4:ea60` 等 | 範例是 RPLidar／CH340；本車是 MS200 光達，**ID 要自己用 `lsusb` 查**（見 1.6） |
| 13-2、13-4 | 範例映像 `yahboomtechnology/ros-foxy`（Foxy）、使用者 `jetson` | 本車是 **Humble**，不是 Foxy |
| 12 各篇 | 帳號 `pi`、密碼 `yahboom`、IP `192.168.2.93` | 是範例；車子的實際 IP 要自己查（熱點時為 `10.42.0.1`） |

**文件中沒有「燒錄映像」的教學**：〈11-20〉只講備份（backup）系統映像，〈11-13〉只講擴容；Pi 5 的 SD 卡燒錄方法請查 `02.Assembly course`／`03.Preparation` 或樹莓派官方 Imager。車子出廠已預灌系統，初學者通常**不需要**燒錄。

---

## 1. Linux 基礎指令重點（初學者速查）

### 1.1 Linux 是什麼（11-1）

- 免費開源、多使用者、多工；Ubuntu 是 Debian 衍生，桌面、伺服器、雲端、嵌入式都常見。本車系統是 Ubuntu 系（車上 ROS 2 Humble 對應 Ubuntu 22.04；【補充】樹莓派主機本身是 Raspberry Pi OS，文件有些篇寫 Ubuntu、有些篇寫 Raspberry Pi OS，見第 4 節）。
- 其他常見發行版：Red Hat Enterprise Linux、Debian（穩定）、CentOS、Ubuntu。

### 1.2 檔案系統結構（11-2）

只有一個根目錄 `/`，所有東西都在它底下：

| 目錄 | 放什麼 |
| --- | --- |
| `/bin` | 最常用的可執行檔（Binary） |
| `/boot` | 核心與開機檔 |
| `/dev` | 裝置檔（硬碟、鍵盤、USB…）。本車的 `ttyUSB0` 等序列埠就在這 |
| `/etc` | 系統設定檔（passwd、hostname…） |
| `/home` | 使用者家目錄，例如 `/home/yahboom`（文件範例）；內有 Desktop、Documents、Downloads… |
| `/lib` | 共用函式庫 |
| `/media`、`/mnt` | 自動掛載的光碟／USB；手動掛載點 |
| `/opt` | 第三方軟體（【補充】ROS 2 Humble 裝在 `/opt/ros/humble`，導航課有出現） |
| `/proc` | 虛擬目錄，系統記憶體映射（`cpuinfo` 等） |
| `/root` | 管理員 root 的家目錄（【補充】車上 Docker 容器內的工作空間就在 `/root/yahboomcar_ws`） |
| `/sbin` | 系統管理程式 |
| `/sys` | 裝置與核心資訊（溫度檔在這，見 2.12） |
| `/usr` | 使用者相關程式與資料（`/usr/bin`、`/usr/lib`、`/usr/local`…） |
| `/var` | 常變動資料：`/var/log` 日誌、`/var/cache` 等 |
| `/tmp` | 暫存檔，所有人可讀寫 |

### 1.3 常用指令（11-3）

**新增**

```
touch test.txt                 # 建立檔案
mkdir test                     # 建立資料夾
mkdir -p test/src              # 連同上層一起建立
sudo cp test.txt test_copy.txt # 複製檔案
```

**刪除**（`-i` 互動確認、`-f` 強制、`-r` 遞迴）

```
sudo rm test.txt               # 刪檔案或空資料夾
sudo rm -r test                # 刪資料夾及其內容
```

**搬移／改名／權限**

```
sudo mv test test_new          # 資料夾改名
sudo mv test.txt test_new.txt  # 檔案改名
sudo chmod +rwx test.txt       # 加所有權限
sudo chmod 777 test.txt        # 所有權限的快捷寫法
sudo passwd root               # 設 root 密碼
sudo passwd 使用者名稱         # 設使用者密碼
```

權限符號：`+` 加、`-` 去、`=` 設定；`r` 讀（資料夾沒有 r 就不能 `ls`）、`w` 寫（資料夾沒 w 不能建檔）、`x` 執行（資料夾沒 x 不能 `cd` 進去）。

**查看**

```
lsb_release -a                 # 發行版本
uname -a                       # 核心版本與位元數
cat /proc/version              # 核心與 gcc 版本
curl cip.cc  或  ifconfig      # 看 IP
cat /proc/cpuinfo  或  lscpu   # CPU 資訊
sudo dmidecode -t memory       # 記憶體資訊
df -h                          # 磁碟空間
which python3                  # 指令位置
v4l2-ctl --list-formats-ext    # 相機裝置參數
nproc                          # CPU 核心數
la                             # 列出含隱藏檔（文件寫法；【補充】標準指令是 ls -a）
ll                             # 詳細列表
ls -h                          # 用易讀方式顯示大小
cat test.txt                   # 看檔案內容
tree                           # 看目錄樹（需 sudo apt install tree）
```

**找檔案**

```
find ./ -name test.sh          # 目前目錄下找名稱為 test.sh 的檔案或資料夾
find ./ -name '*.sh'           # 找所有 .sh
find ./ -name "[A-Z]*"         # 找大寫開頭
```

**打包／壓縮**

```
tar -cvf xxx.tar *             # 打包目前目錄所有檔案
tar -cvf xxx.tar *.txt         # 只打包 .txt
tar -cvf xxx.tar my-file my-dir
tar -xvf xxx.tar               # 解到目前目錄
tar -xvf xxx.tar -C my-dir     # 解到指定目錄（要先建好）
zip bak *                      # 壓縮
zip -r bak *                   # 遞迴壓縮
unzip bak.zip                  # 解壓
unzip -d ./target_dir bak.zip  # 解壓到指定目錄
```

（tar 參數：`-c` 建立、`-v` 顯示過程、`-f` 指定檔名（要放最後）、`-t` 列內容、`-x` 解開。）

**連結**

```
ln -s 來源檔 連結檔            # 軟連結（來源刪了就失效；可連目錄）
ln 來源檔 連結檔               # 硬連結（只能連一般檔案）
```

**遠端複製／下載／其他**

```
scp jetson@192.168.16.66:/home/jetson/xxx.tar.gz /home/yahboom/   # 遠端→本機
scp /home/yahboom/xxx.png jetson@192.168.16.66:/home/jetson/       # 本機→遠端
scp -r 目錄 ...                                                     # 目錄加 -r
wget "網址"        wget -O yahboom.jpg "網址"                       # 下載（-O 指定檔名）
nautilus .         # 以檔案管理員開啟目前資料夾
cd ~   cd .   cd -   cd /      # 回家目錄／目前／上一次所在目錄／根目錄
pwd                # 顯示目前路徑
echo "HelloWorld"
```

（`scp` 範例使用者 `jetson` 是 Jetson 範例，在本車請換成 `pi`。）

### 1.4 編輯器（11-4）

- **vim**：`sudo apt install vim`。三種模式：命令模式（預設）／插入模式（`i`、`a`、`o`、`O` 進入，`Esc` 離開）／末行模式（按 `:`）。
  末行指令：`w` 存檔、`q` 離開、`q!` 強制離開、`x` 存檔並離開、`set nu` 顯示行號、`/字串` 往後搜尋（`n` 下一個）。
  命令模式：`yy` 複製一行、`p` 貼上、`3yy` 複製 3 行、`dd` 剪下／刪行、`u` 復原、`gg` 檔頭、`G` 檔尾、`^` 行首、`$` 行尾、`h j k l` 左下上右。
- **nano**（最適合新手）：`sudo apt install nano`；`nano 檔名`。`Ctrl+x` 離開（會問是否存檔，按 `y` 再 Enter）、`Ctrl+w` 搜尋、`Ctrl+k` 剪下一行、`Ctrl+u` 貼上、`Ctrl+c` 顯示游標位置。
- **gedit**：圖形介面編輯器，`Ctrl+s` 存檔、`Ctrl+f` 搜尋。**只能在有桌面時用，SSH 等無介面連線不能開**。

### 1.5 軟體安裝（apt，11-5、12-1）

```
sudo apt-get update                  # 更新套件來源清單（先做）
sudo apt-get install 套件名          # 安裝
sudo apt-get remove 套件名           # 移除
sudo apt-get remove 套件名 --purge   # 連設定檔一起移除
sudo apt-cache search 套件名         # 搜尋
sudo apt-cache show 套件名           # 看套件資訊
sudo apt-get upgrade                 # 更新已安裝套件
sudo apt-get dist-upgrade            # 升級系統
sudo apt-get clean && sudo apt-get autoclean   # 清理
```

樹莓派那篇（12-1）建議用 `sudo apt update`、`sudo apt full-upgrade`、`sudo apt install tree -y`、`sudo apt remove tree`、`sudo apt purge tree`、`apt-cache search`、`apt-cache show`。`/etc/apt/sources.list` **除非必要不要改**。`sudo rpi-update` 更新韌體（更新前要備份系統，可能開不了機；更新後 `sudo reboot`；回復穩定版用 `sudo apt-get update` ＋ `sudo apt install --reinstall raspi-firmware`）。**文件提醒：開發者不建議隨意更新系統**（本車的 ROS 環境與驅動版本是配好的）。

### 1.6 裝置綁定（udev，11-12）

問題：有兩個以上 USB 序列裝置時，`/dev/ttyUSB0`、`ttyUSB1` 是依插入順序分配，重開機後可能對調。解法：用 udev 規則給固定別名。

```
lsusb                           # 看每個 USB 裝置的 idVendor:idProduct
ll /dev/                        # 看裝置名
cd /etc/udev/rules.d/
sudo touch rplidar.rules
sudo chmod 777 rplidar.rules
sudo vim rplidar.rules
```

規則內容（文件範例）：

```
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE:="0777", SYMLINK+="myserial"
KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE:="0777", SYMLINK+="rplidar"
```

讓規則生效：

```
sudo udevadm trigger
sudo service udev reload
sudo service udev restart
```

欄位說明：`KERNEL` 裝置名稱、`ATTRS{idVendor}`／`ATTRS{idProduct}` 廠商／產品號、`SYMLINK+=` 在 `/dev/` 下建立別名、`MODE` 權限。
若兩個裝置 ID 相同，要綁 USB 埠位置：`udevadm info --attribute-walk --name=/dev/ttyUSB0 |grep KERNELS`，把規則的 `KERNEL=="ttyUSB*"` 改成 `KERNELS=="1-2.1.3"`（值依你查到的）。【補充】本車控制板在其他文件寫成 `/dev/ttyUSB0`；綁定不是必須，但多裝置時有用。

### 1.7 其他系統管理（11 系列）

- **取得 root 密碼（11-15）**：`sudo passwd root`（輸入兩次）→ `sudo passwd --unlock root` → `su`。
- **sudo 免密碼（11-16）**：`sudo visudo`，找到 `%sudo` 那行，把最後的 `ALL` 改成 `NOPASSWD:ALL`，`Ctrl+s` 存檔、`Ctrl+x` 離開，重開機後生效。【警告】降低安全性，建議教材標為「選用」。
- **連 Wi-Fi 指令（11-17）**：

  ```
  sudo iwlist scan
  sudo nmcli device wifi list
  sudo nmcli device wifi connect [WiFi名稱] password [WiFi密碼]
  ```

  範例：`sudo nmcli device wifi connect Yahboom1_5G password 12345678`。桌面連線較簡單，優先用桌面右上角 Wi-Fi 圖示。
- **自訂服務 systemd（11-19）**：把程式變成開機自動執行的服務（以 OLED 為例）：
  1. 建立 `yahboom_oled.service`，內容（Raspberry Pi 版）：

     ```
     [Unit]
     Description=yahboom_oled start service
     After=multi-user.target
     [Service]
     Type=idle
     User=pi
     ExecStart=/bin/sh -c "python3 /home/pi/software/oled_yahboom/yahboom_oled.py"
     WorkingDirectory=/home/pi
     [Install]
     WantedBy=multi-user.target
     ```

  2. `sudo cp yahboom_oled.service /etc/systemd/system/` → `sudo systemctl daemon-reload`
  3. 管理：`sudo systemctl status yahboom_oled.service`／`start`／`restart`／`stop`／`enable`（開機自動啟動）／`disable`
  （文件寫「exit editing and enter: qw」，vim 正確是 `:wq`。）
- **擴容（11-13）**：若 SD 卡映像比卡小，剩餘空間沒用到：`sudo apt install gparted` → 右鍵 `/dev/mmcblk0p1` → Resize/Move → 拉滿 → Apply；用 `df -h` 驗證。**用 Yahboom 提供的卡或映像可跳過**。（Pi 的另一種做法：`raspi-config` → Advanced Options → Expand file system，見 2.4。）
- **備份映像（11-20）**：需要 TF 卡＋讀卡機；在 Windows 下新建空白 `.img` 檔，用映像工具直接「讀取」備份，重燒就是還原。備份檔大小等於整張卡大小。
- **虛擬機（11-6）**：Yahboom 提供 Ubuntu 22.04 虛擬機（VMware Player），開啟 `Ubuntu22.04.vmx`，第一次選「I Copied It」，用 `ifconfig` 看 `ens33` 底下的 `inet` 就是虛擬機 IP。【補充】對於沒有 Ubuntu 電腦的學習者，這是練習 ROS 2 的備案，但**Humble（22.04）**才與車一致。
- **驅動函式庫（11-10）**：`sudo pip3 install pyserial`（序列埠）；MutoLib 部分不適用。

---

## 2. 樹莓派 5（Pi 5）設定

### 2.1 預設帳號、密碼、IP（文件有寫的全部列出）

| 項目 | 值 | 出處 |
| --- | --- | --- |
| 樹莓派使用者名稱 | `pi` | 12-5、12-6（「My current login user name is pi」）；03.Preparation 的 First Trial 也寫 `username：pi` |
| 密碼 | `yahboom` | 同上 |
| 範例區網 IP | `192.168.2.93` | 12-5、12-6（只是作者環境，不是預設值） |
| 車子自帶熱點時 Pi 的 IP | `10.42.0.1` | `03.Preparation/First Trial`（「The IP corresponding to Raspberry Pi hotspot mode is 10.42.0.1」）、12-12 網頁預覽範例 |
| 範例網頁預覽 | `192.168.2.93:8081`（USB 相機 Motion）、`10.42.0.1:8000`（MIPI 相機） | 12-11、12-12 |
| 另一範例 | `jetson` / `yahboom` / `192.168.2.93` | 11-9【警告】Jetson 範例，別用 |
| VNC 範例密碼 | `mima` | 11-8（設定 vino 用；【警告】屬於舊範例，本車已預設好 VNC，不要再配置） |

【補充】車子自帶熱點的名稱與密碼在本組文件沒寫，查 `03.Preparation`。

### 2.2 SSH 與 VNC 遠端（11-7、11-8、12-5）

**啟用**

- 圖形：應用程式選單 → Preferences → Raspberry Pi Configuration → Interfaces，開 SSH、VNC。
- 指令：`sudo raspi-config` → Interface Options → SSH／VNC → enable。
- 若 VNC 開不起來：先更新軟體並重開機再試。
- 11-7、11-8 說明：Yahboom 提供的系統**已配置好**，不需再安裝（不要照 11-8 去安裝 vino）。

**取得 IP**：`hostname -I` 或 `ifconfig`；或桌面連上 Wi-Fi 後滑鼠停在 Wi-Fi 圖示上。

**SSH 登入**

```
ssh 使用者名稱@IP
ssh pi@192.168.2.93
```

（文件原文把空格吃掉寫成 `sshpi@192.168.2.93`，是排版錯誤；正確有空格。）第一次連線會問 yes/no，輸入 `yes`，再輸入密碼。

**VNC 登入**：電腦安裝 **RealVNC Viewer**（<https://www.realvnc.com/en/connect/download/viewer/> ），輸入 Pi 的 IP，輸入帳號 `pi`、密碼 `yahboom`，看到 Pi 桌面。電腦與車需在**同一區網**；車出廠就有熱點，電腦連該熱點即可，此時連 `10.42.0.1`。

### 2.3 傳檔（11-9、12-6）

- **WinSCP**（Windows，建議優先）：輸入主機（IP）、使用者 `pi`、密碼 `yahboom`，拖曳檔案。
- **scp**：

  ```
  scp 檔名 使用者@IP:路徑
  scp Test.txt pi@192.168.2.93:             # 複製到使用者家目錄
  scp Test.txt pi@192.168.2.93:Desktop/     # 複製到桌面
  scp pi@192.168.2.93:Test.txt .            # 從 Pi 複製到目前目錄
  ```

### 2.4 raspi-config 與 config.txt（12-2、12-3）

`sudo raspi-config` 重點選項：

- System Options：Wireless LAN、Audio、Password（改使用者密碼）、Hostname（網路上的名字）、Boot/Auto Login（開機進桌面或主控台、是否自動登入）、Splash Screen、Browser。（Pi 5 不支援改電源指示燈。）
- Display Options：Screen Blanking（螢幕休眠）、VNC Resolution、Composite。
- Interface Options：SSH、VNC、SPI、I2C、Serial Port、1-Wire、Remote GPIO。
- Performance Options：Overlay File System（唯讀檔案系統）、USB Current。
- Localisation Options：Locale、Time Zone、Keyboard、WLAN Country。
- Advanced Options：Expand Filesystem、Network Interface Names、Network Proxy、Boot Order、Bootloader Version、Wayland（X11／Wayland 切換）、Audio Config（PulseAudio／PipeWire）。
- Update；About raspi-config。
`config.txt`（本文件寫 `/boot/config.txt`，**Pi 5 的實際路徑在 12-12 寫 `/boot/firmware/config.txt`**）：開機設定檔，每行一個設定，`#` 為註解，一行最多 98 字元。查看：`vcgencmd get_config arm_freq`、`vcgencmd get_config int`、`vcgencmd get_config str`。常見：`dtparam=audio=on`、`camera_auto_detect=1`、`display_auto_detect=1`、`dtoverlay=vc4-kms-v3d`。GPIO 開機狀態：`gpio=12=op,dh`（輸出、拉高）、`gpio=18,20=pu`（上拉）、`gpio=17-21=ip`（輸入）。更完整看 <https://www.raspberrypi.com/documentation/> 。

### 2.5 網路：Wi-Fi 與熱點（12-4、11-11、11-17）

- **第一次要先設地區**：`sudo raspi-config` → Localization Options → WLAN Country → `CN China` → OK → Finish。（台灣使用者可選 `TW`，【補充】文件範例是 CN。）
- **指令連 Wi-Fi**：

  ```
  nmcli radio wifi            # 看 Wi-Fi 狀態
  nmcli radio wifi on         # 開
  nmcli radio wifi off        # 關
  sudo nmcli dev wifi list    # 掃描
  sudo nmcli --ask dev wifi connect <example_ssid>
  ```

  沒權限就在前面加 `sudo`。
- **桌面開熱點**：點右上角網路圖示建立；手機可看到該熱點。
- **開機自動連 Wi-Fi 或開熱點**：改網路連線的**優先權（priority）數字，越高越優先**（文件只給觀念，未給步驟）。
- **靜態 IP（11-11，桌面操作）**：右上角 Wi-Fi 圖示 → Edit Connections… → 雙擊目前 Wi-Fi（例如 `Yahboom`）→ Wi-Fi 頁籤 Mode 選 Client → IPv4 Settings 按 Add 輸入 IP → Save。然後 `sudo vim ~/.bashrc`，把 `ROS_IP` 設為剛設定的 IP；**沒連這個 Wi-Fi 時要把該行註解掉（行首加 `#`）**。之後開新終端若出現 `binary operator expected` 可忽略。
- **熱點模式（11-11）**：Edit Connections… → `+` → 選 Wi-Fi → Create… → Wi-Fi 頁籤：SSID 填（範例 `yah`）、Mode 選 Hotspot；Wi-Fi Security 選 WPA & WPA2 Personal 並輸入密碼；IPv4 Settings → Add 輸入 IP，Method 選 Ignore → Save；再到連線清單選該 Wi-Fi 按 Connect。

### 2.6 系統更新（12-1）

已見 1.5。注意：「保持樹莓派更新可提高安全性，但不建議開發者隨意更新」。

### 2.7 顯示解析度與旋轉（12-7）

- 圖形：選單 → Preferences → Screen Configuration，在對應 HDMI 輸出上按右鍵選解析度、旋轉。
- 設定檔：家目錄 `.config/wayfire.ini`（要先顯示隱藏檔）。
- VNC 遠端解析度（沒接螢幕時）：Raspberry Pi Configuration → Display，或 `raspi-config` → Display Options → VNC Resolution；改後要重啟並重連 VNC。有接螢幕時，VNC 解析度以螢幕為準。
- 解析度選錯會模糊，依產品支援的解析度設定。

### 2.8 螢幕休眠（12-8）

- 預設無操作 10 分鐘自動關螢幕。
- 建議做法：Raspberry Pi Configuration → Display → Screen Blanking；或 `raspi-config` → Display Options → Screen Blanking；重啟生效。
- 另法：`sudo nano /etc/lightdm/lightdm.conf`，取消 `xserver-command=X` 的註解並改為 `xserver-command=X -s 0 -dpms`（`-s 0` 螢幕保護程式不啟動；`-dpms` 關閉電源管理），存檔後 `reboot`。（文件原文為 `-s 0-dpms`，疑為排版；教材請實測。）

### 2.9 CPU 溫度（12-9）

```
cd /sys/class/thermal/thermal_zone0
cat temp
```

數值除以 1000 才是攝氏溫度（【補充】文件說「convert it to actual temperature」，未寫換算；一般為毫度）。

### 2.10 播放音訊影片（12-10）

```
vlc Test.mp4
vlc --play-and-exit Test.mp4
vlc --play-and-exit --fullscreen Test.mp4
cvlc --play-and-exit Test.mp4            # 無介面
cvlc --play-and-exit --drm-vout-display HDMI-A-1 Test.mp4
kmsprint | grep Connector                # 看 DRM 裝置
cvlc --play-and-exit Test.mp3
cvlc --play-and-exit -A alsa --alsa-audio-device vc4hdmi0 Test.mp3
aplay -L | grep sysdefault               # 看 ALSA 裝置
```

Pi 5 要接上音訊裝置才能正常播放音訊。

### 2.11 USB 相機（12-11）

```
sudo apt install fswebcam
sudo usermod -a -G video pi        # 把使用者加入 video 群組
groups                              # 確認
lsusb
ls /dev/video*
fswebcam image.jpg
fswebcam -r 1280x720 image2.jpg
fswebcam -r 1280x720 --no-banner image3.jpg
```

縮時攝影：建 `Webcam` 資料夾，`webcam.sh` 內容 `#!/bin/bash`／`DATE=$(date +"%Y-%m-%d_%H%M")`／`fswebcam -r 1280x720 --no-banner /home/pi/Webcam/$DATE.jpg`，`sudo chmod +x webcam.sh`；`crontab -e` 加入 `* * * * * /home/pi/Webcam/webcam.sh 2>&1`（每分鐘一次）；`sudo service cron start/stop`，停不下來就 `crontab -e` 刪掉那行。
網頁預覽（Motion，**CSI 相機不能用**）：`sudo apt install motion`，編輯 `sudo nano /etc/motion/motion.conf`：`daemon on`、`stream_localhost off`、`picture_output off`、`movie_output off`、`stream_maxrate 100`、`framerate 70`、`width 640`、`height 480`；`sudo nano /etc/default/motion` 加 `start_motion_daemon=yes`；`sudo service motion start`、`sudo motion`；瀏覽器開 `車子IP:8081`（如 `192.168.2.93:8081`）。

### 2.12 MIPI（CSI）相機（12-12）

- Pi 5 有兩個 CSI/DSI 雙用 MIPI 埠。第三方相機要在 `sudo nano /boot/firmware/config.txt` 加 `dtoverlay`：V1(OV5647)=`dtoverlay=ov5647`、V2(IMX219)=`dtoverlay=imx219`、HQ(IMX477)=`dtoverlay=imx477`、GS(IMX296)=`dtoverlay=imx296`、Camera Module 3(IMX708)=`dtoverlay=imx708`、IMX290/IMX327=`dtoverlay=imx290,clock-frequency=74250000`（或 37125000）、IMX378=`dtoverlay=imx378`、OV9281=`dtoverlay=ov9281`；改完要重開機。使用 IMX219 要接到 Pi 5 的 **J4** 介面才會被辨識。
- 預覽：`rpicam-hello`（約 5 秒）、`rpicam-hello -t 0`（一直顯示，`Ctrl+C` 離開）。
- 拍照：`rpicam-jpeg -o test.jpg`、`rpicam-jpeg -o test.jpg -t 2000 --width 640 --height 480`；`rpicam-still -e png -o test.png`（也可 bmp、rgb、yuv420）、`rpicam-still -r -o test.jpg`（RAW）、縮時 `rpicam-still -t 30000 --timelapse 2000 -o image%04d.jpg`。
- 錄影：`rpicam-vid -t 10000 -o test.h264`；播放 `vlc test.h264`（無法播放要調整 H264 播放幀率）。
- 網頁預覽：`cd /home/pi/Camera_Web_Preview/` → `python3 mjpeg_server.py` → 瀏覽器開 `車子IP:8000`。
- 【補充】本車相機是 2MP USB 相機（文件第 8、9 課用 `ros2 launch usb_cam camera.launch.py`），MIPI 相機這篇主要是通用教材。

---

## 3. Docker：車上的 ROS 2 為什麼在容器裡？

### 3.1 為什麼用 Docker（13-1）

- 原文：「目前 ROS2 的課程都放在 Docker 容器中，客戶可以體驗用容器化開發的方式學習。」
- 解決的問題：「我電腦上能跑，換一台就壞」——環境（版本、相依套件、設定）不同。Docker 把**程式＋它需要的整個環境**一起打包。
- 核心概念：容器彼此隔離（不同程式不會搶 port 或相依版本）。比虛擬機輕：虛擬機啟動以分鐘計，容器以毫秒計；容器不含完整作業系統，省磁碟與資源。
- 【補充，為什麼對本車特別有用】車上主機系統是 Raspberry Pi OS／Ubuntu 的某個版本，ROS 2 Humble 原生要 Ubuntu 22.04；用容器就能在 Pi 5 上跑固定的 Humble 環境，不用動主機系統，壞了刪掉容器重開即可。

### 3.2 三個核心物件

| 名詞 | 意義 | 比喻 |
| --- | --- | --- |
| 映像 Image | 唯讀範本，含程式、函式庫、設定 | 類別（class） |
| 容器 Container | 由映像啟動的執行個體，頂層可讀寫 | 物件（object） |
| 倉庫 Repository／Registry | 存放映像的地方，最大公開庫 Docker Hub（<https://hub.docker.com/）> | 應用商店 |

架構：Docker client（你下的 `docker` 指令）↔ Docker daemon（背景服務，管理映像／容器／網路／卷）↔ registry。

- `docker pull`：client 發指令 → daemon 看本地有沒有 → 沒有就向倉庫下載。
- `docker run`：檢查映像（沒有就下載）→ 建立並啟動容器 → 配檔案系統（映像唯讀層上加一個可寫層）→ 橋接虛擬網卡 → 配 IP → 執行指定程式。

### 3.3 安裝（13-1，車上已裝好）

```
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
sudo docker version
sudo docker run hello-world
```

官方安裝手冊：<https://docs.docker.com/engine/install/ubuntu/> 。

### 3.4 本車的關鍵名稱（逐字）

| 項目 | 內容 | 出處 |
| --- | --- | --- |
| 啟動 microROS agent 的腳本（主機） | `sh ~/start_agent_rpi5.sh` | 09 Lidar 各課；03.Preparation |
| 進入 ROS 2 容器的腳本 | `sh ros2_humble.sh`（Docker 課寫成 `./ros2_humble.sh`），放在家目錄 | 09 Lidar 各課；13-5 |
| microROS agent 映像 | `microros/micro-ros-agent:humble` | 13-3、13-4；15 / 5. Install and start microros agent |
| 啟動 agent 的完整 docker 指令（WiFi／UDP） | `docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4` | 15 / 5、01.Introduction FAQ |
| 序列埠版 agent | `docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 921600 -v4` | 15 / 5 |
| 車子 ROS 2 容器的映像名 | **本組文件沒有寫** | — |
| 範例映像（Docker 課，Foxy、Jetson） | `yahboomtechnology/ros-foxy`（tag 3.3.6～3.4.0） | 13-2 範例輸出【警告】Foxy，非 Humble |

> **重點：agent 腳本與容器腳本是兩件不同的事。**
>
> - `start_agent_rpi5.sh`：在主機啟動 micro-ROS agent（內部應該就是上面 `docker run ... micro-ros-agent:humble ...`），負責「讓 ESP32 控制板的訊息變成 ROS 2 話題」。**一台車同一時間只能開一個 agent**。
> - `ros2_humble.sh`：開一個「裝滿車上 ROS 套件的容器」並給你一個終端，你在這裡跑 `ros2 launch`／`ros2 run`。
> 【補充】兩者的完整內容文件沒給，請在車上 `cat ~/ros2_humble.sh` 抄錄補進教材（可確認映像名稱與掛載）。

參數意義：`--privileged`（給容器近乎主機權限以存取硬體）、`--net=host`（容器直接用主機網路，所以 ROS 2 的 DDS 才能與區網其他機器／控制板互通）、`-v /dev:/dev`（把主機的裝置目錄掛進容器）、`-v /dev/shm:/dev/shm`（共享記憶體，DDS 使用）、`--rm`（結束後自動刪除容器）、`-it`（互動式終端）、`--port 8090`（UDP 埠）、`-v4`（日誌等級，越大越多）。

### 3.5 進入容器、多開終端（13-5、13-2）

**進入**（第一次）：

```
./ros2_humble.sh
ros2 node list
```

容器的 `ROS_DOMAIN_ID` 必須與 microROS 控制板參數一致，才能通訊；`ros2 node list` 若看不到車子的節點（如 `YB_Car_Node`），去檢查 ID。ID 不同時可在容器內 `vi ~/.bashrc` 改成一致（出自 03.Preparation）。

**在同一個容器開第二、第三個終端**（初學者最常卡住的地方）：

```
docker ps -a
docker exec -it ef0e1b7da319 /bin/bash
```

- `docker ps -a` 會列出 CONTAINER ID、IMAGE、STATUS、NAMES；**每次進容器 ID 都不同**，`ef0e1b7da319` 只是範例。
- ID 可以縮寫，只要能唯一辨識（文件範例：`docker exec -it c5 /bin/bash`）。
- 不要在第二個終端再跑一次 `./ros2_humble.sh`，那會產生**另一個新容器**，看不到前一個終端啟動的東西（也可能和第一個容器爭資源）。
- `docker exec`：在容器內**新開**一個終端／行程；`docker attach`：接到容器**原本**的終端（不開新行程，兩個視窗會一起顯示）。多開終端用 `exec`。

### 3.6 常用 docker 指令（13-2）

**免 sudo（11-2 節的做法）**

```
sudo groupadd docker
sudo gpasswd -a $USER docker
newgrp docker
```

（文件把 `newgrp docker` 寫成 `Newgrp Docker`；Linux 指令區分大小寫，要小寫。）若出現 `permission denied` 的 `.docker/config.json` 警告：

```
sudo chown "$USER":"$USER" /home/"$USER"/.docker -R
sudo chmod g+rwx "/home/$USER/.docker" -R
```

**資訊與說明**

```
docker info        # 系統資訊（映像、容器數量）
docker --help
docker version     # （文件用 sudo docker version）
```

**映像**

```
docker pull ubuntu              # 下載；不寫 tag 預設 latest
docker images                   # 列本機映像（-a 全部、-q 只顯示 ID、--digests 摘要）
docker search ros2              # 搜尋 Docker Hub（--filter=stars=50 可篩）
docker rmi -f 映像ID            # 刪一個
docker rmi -f 映像名:tag 映像名:tag   # 刪多個
docker rmi -f $(docker images -qa)    # 刪全部（危險）
```

`docker images` 欄位：REPOSITORY（來源）、TAG（版本標籤）、IMAGE ID、CREATED、SIZE。以 `REPOSITORY:TAG` 區分版本。

**容器**

```
docker run [OPTIONS] IMAGE [COMMAND][ARG...]
docker run -it ubuntu:latest /bin/bash    # 互動式開容器，進 bash
```

常用選項：`--name="名稱"`、`-d`（背景執行）、`-i`（互動）、`-t`（配終端，常 `-it`）、`-P`（隨機 port 映射）、`-p`（指定 port 映射；格式 `ip:hostPort:containerPort`、`ip::containerPort`、`hostPort:containerPort`（最常用）、`containerPort`）。

```
docker ps                       # 執行中的容器；-a 含已結束、-l 最近建立、-n=? 最近 n 個、-q 只顯示 ID
exit                            # 離開並停止容器
Ctrl+P 再 Ctrl+Q                # 離開但容器繼續執行
docker exec -it 容器ID /bin/bash   # 另開終端進入執行中的容器
docker attach 容器ID               # 接到原本的終端
docker start 容器ID或名稱       # 啟動
docker restart 容器ID或名稱
docker stop 容器ID或名稱        # 停止
docker kill 容器ID或名稱        # 強制停止
docker rm 容器ID                # 刪容器
docker rm -f $(docker ps -a -q) # 刪全部容器（危險）
docker ps -a -q|xargs docker rm # 另一種刪全部
docker top 容器ID               # 容器內行程
docker inspect 容器ID或映像ID   # 詳細中繼資料（JSON）
```

**停掉殘留的 agent 容器**（來自 15 / 5 與 FAQ：agent 一次只能開一個；若直接關閉終端，docker 會繼續在背景跑，之後再開 agent 會報錯）：

```
docker ps -a | grep microros/micro-ros-agent
docker stop xxxxxxxxxx
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4
```

結束 agent 的正確方式：在 agent 終端按 `Ctrl+C`，**不要直接關閉視窗**。

### 3.7 映像分層與自製映像（13-3）

- 映像由唯讀層疊起來（UnionFS 聯合檔案系統）；容器啟動時在最上面加一個可寫層，所以「容器裡改的東西」刪掉容器就沒了。好處：多個映像共用相同底層，省空間、省下載。
- 看分層：`docker image inspect microros/micro-ros-agent:humble`。
- 把容器存成映像：`docker commit -m="說明" -a="作者" 容器ID 新映像名:標籤`（例如 `docker commit 7a2861823744 ubuntu:test`），再 `docker images` 確認。**這對本車很實用：在容器內裝了套件或改了程式，要 commit 才會保留**（【補充】或用資料卷／`docker cp` 把檔案放到主機）。
- 發布到 Docker Hub：註冊帳號 → `docker login -u 帳號` → 用 tag 改名成 `帳號/映像名` → `docker push 帳號/映像名`。（文件內容簡略；【補充】改名指令是 `docker tag 原名 帳號/映像名`。）

### 3.8 硬體、圖形介面、檔案交換（13-4）

**硬體（序列埠、光達）進容器**：先在主機建 udev 規則（見 1.6），再用 `--device`：

```
docker run -it --device=/dev/myserial --device=/dev/rplidar ubuntu:latest /bin/bash
```

進容器後 `ls /dev` 就能看到 `myserial`、`rplidar`。（車上腳本用 `-v /dev:/dev --privileged` 把整個 `/dev` 掛進去，所以不用逐一 `--device`。）

**容器內顯示 GUI（rviz2）**：Yahboom 系統已裝好，不用再裝。步驟：

```
sudo apt-get install tigervnc-standalone-server tigervnc-viewer
sudo apt-get install x11-xserver-utils
xhost +
```

然後（主機執行，每行 `\` 為續行）：

```
docker run -it \
--env="DISPLAY" \
--env="QT_X11_NO_MITSHM=1" \
-v /tmp/.X11-unix:/tmp/.X11-unix \
microros/micro-ros-agent:humble \
/bin/bash
```

進入後執行 `rviz2` 測試。（文件把每行右側的中文註解混在指令中；上面已去除。【警告】`xhost +` 會關閉 X11 存取控制，只在可信區網使用。）

**主機與容器傳檔**

```
docker cp 容器ID:容器內路徑 主機目的路徑     # 容器 → 主機
docker cp 主機檔案路徑 容器ID:容器內路徑     # 主機 → 容器
```

資料卷（volume，讓資料不隨容器刪除而消失、兩邊同步）：

```
docker run -it -v 主機絕對路徑:容器內路徑 映像名
docker run -it -v /home/jetson/temp:/root/temp ubuntu:latest /bin/bash
```

特性：容器間可共享、修改立即生效、不會進映像、生命週期持續到沒有容器使用為止。

---

## 4. 初學者最容易卡住的地方（整理自文件＋我的判斷）

1. **多開終端卻開了新容器**：一律用 `docker ps -a` ＋ `docker exec -it <ID> /bin/bash`；ID 每次不同。（文件 13-5 與 09-8 才有寫。）
2. **`ROS_DOMAIN_ID` 不一致**：容器內與控制板不同 → `ros2 node list` 沒有車子節點。到容器 `~/.bashrc` 對齊。
3. **agent 重複開啟或直接關視窗**：一次只能開一個；關視窗會留下背景 docker，再開會失敗 → 先 `docker ps -a | grep microros/micro-ros-agent`、`docker stop <ID>`，或重開機。
4. **控制板要按 reset 才連得上**：每次啟動 agent 後要按控制板 reset，等約 10 秒。（03.Preparation：「It is common that the agent fails to connect successfully…press the RESET button…wait about 10 seconds」。）
5. **IMU 沒初始化**：建圖／導航前要放穩並靜置 5 秒（09 Lidar 注意事項），否則 rviz 裡模型自己旋轉飄移。
6. **主機指令與容器指令混用**：`docker ...`、`sh ~/start_agent_rpi5.sh` 在主機；`ros2 ...` 在容器。提示符號不同（容器內常是 `root@...`）。
7. **容器內改的東西不見**：容器是暫時的；用 `docker commit` 或資料卷／`docker cp` 保存重要檔案（例如地圖；車上地圖存在 `/root/yahboomcar_ws/src/yahboomcar_nav/maps`，那是容器內路徑！）。【補充】我無法從文件確認 `ros2_humble.sh` 是否把這路徑掛載回主機，請在車上查證；若未掛載，建好圖後務必 `docker cp` 備份。
8. **照抄 Jetson／Muto／Buster 範例**：見第 0 節表格，特別是 `jetson` 帳號與 `aliyun buster` 軟體源。
9. **Linux 指令大小寫與空格**：`Newgrp Docker`、`sshpi@…` 這類文件排版錯誤要更正；`sudo` 才有權限修改 `/etc` 底下的檔案。
10. **IP 位址**：家裡路由器分配的 IP 會變；直接連車子熱點最穩（Pi 為 `10.42.0.1`）。在 `~/.bashrc` 寫死 `ROS_IP` 後換網路會出錯，要註解掉（11-11）。
11. **Pi 5 的 `config.txt` 路徑**：`/boot/firmware/config.txt`（不是舊的 `/boot/config.txt`）。
12. **不要隨便 `apt full-upgrade`／`rpi-update`**：可能破壞預先配好的驅動；做之前先備份映像（11-20）。
13. **VNC 解析度／螢幕休眠**：沒接螢幕時 VNC 畫面小，要在 `raspi-config` 設 VNC Resolution；螢幕 10 分鐘自動關。
14. **系統名稱混用**：文件有時稱 Ubuntu、有時稱 Raspberry Pi OS（Raspbian）；Pi 的設定篇（12 系列）都是 Raspberry Pi OS（含 `raspi-config`、`wayfire`），而 ROS 課程的「容器內」是 Ubuntu 22.04 + Humble。教材要明確區分「主機」與「容器」兩層。

---

## 5. 還需要別人補的資訊（本組文件缺漏）

- `~/ros2_humble.sh`、`~/start_agent_rpi5.sh` 的**完整內容**（映像名稱、掛載、環境變數）。
- 車子 ROS 2 容器的**映像名稱與 tag**。
- 燒錄／重灌系統映像的步驟（若要提供「重置」教學）。
- 車子熱點的 SSID 與密碼（`03.Preparation` 可能有）。
