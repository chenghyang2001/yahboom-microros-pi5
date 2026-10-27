# 拍五網路架構與 Wi-Fi 備援

這份文件說明拍五（Yahboom MicroROS-Pi5）怎麼連網、電腦怎麼連到車子，以及手機熱點壞掉時的備援機制。
語音版在 `network-explain/`（見文末）。

## 1. 現在的連法（2026-10-28 決定維持）

```
           4G 行動網路（上網）
                 │
     手機 OPPO Reno13 F ──── USB 線（adb nc 轉接 8022→SSH、5900→VNC）──── PC
      開「個人熱點」AnPing                                         PC 用自己原本的網路上網
                 │ Wi-Fi（10.57.201.x）
     拍五大腦 Raspberry Pi 5（wlan0 當用戶端，10.57.201.1）
                 │ USB 序列線（/dev/ttyUSB0）
     拍五小腦 ESP32（馬達、IMU、光達、蜂鳴器、雲台）
```

- **拍五**連手機熱點，透過手機 4G 上網。語音指令要呼叫 Claude API 和 edge-tts，所以拍五必須能上網。
- **PC**用自己原本的網路上網，讓 Claude Code 能運作；另外用 USB 線經手機轉接連到拍五下指令。
- **ESP32**跟 Pi 之間走 USB 序列線，不經過 Wi-Fi。Wi-Fi 怎麼變都不影響馬達和感測器。

### 跟教材的差別

教材（`lessons/`）照 Yahboom 原廠文件，寫的是出廠連法：拍五自己當熱點 `Micro_ros`（IP `10.42.0.1`），電腦的 Wi-Fi 直接連過去。
這種連法簡單，但拍五和電腦都上不了網：Claude Code 不能用，語音也不能用。
所以實際演練改用上面的手機熱點連法。跟書上不一樣沒關係，這是刻意的決定。

## 2. Pi 5 的 Wi-Fi 只有一顆晶片

wlan0 同一時間只能二選一：

| 模式 | 說明 |
| --- | --- |
| 當用戶端 | 連別人的熱點（平常連 AnPing） |
| 當熱點 | 自己發 `Micro_ros` 讓別人連，**不需要網路**，但連上的裝置出不去外網 |

拍五自己當熱點時，能做的只有「連到車子」這件事，例如：

- SSH、VNC、看 log、改設定
- 遙控、讀感測器、SLAM 建圖

語音、安裝軟體、上網對時都不能用。這是保命通道，不是上網用的。
例外：如果有線網孔接著能上網的路由器，`Micro_ros`（共享模式）會把有線網路分享給連上熱點的裝置。

## 3. 拍五存的 Wi-Fi 設定

| 設定名稱 | 用途 | 優先 | 自動連線 | 重試次數 |
| --- | --- | --- | --- | --- |
| Wireless connection 1 | 連手機 AnPing | 2 | 是 | 無限（2026-10-28 改，原本預設 4 次） |
| Micro_ros | 拍五自己發熱點（出廠內建，密碼是出廠預設） | 1 | **否**（2026-10-28 改，原本是） | — |
| Yahboom2 | 出廠留的 Wi-Fi 設定 | 0 | 是 | — |

### 為什麼要改（2026-10-28 實際踩到）

原廠設定下，找不到 AnPing 時，NetworkManager 約 **5 秒**內就改開 `Micro_ros`，而且開了以後**永遠不會回頭**找 AnPing。
那天手機熱點自己關了一下，拍五就切成熱點模式。手機熱點重開後拍五也沒連回來，最後只能把車子斷電重開。

## 4. Wi-Fi 備援看門狗（`pi5-wifi-fallback`）

程式：`drill/wifi-fallback/pi5-wifi-fallback.sh`（車上裝在 `/usr/local/bin/`），以 systemd 服務開機自動執行。

每 15 秒檢查一次 wlan0：

1. **連著 AnPing**：什麼都不做。
2. **連不上任何 Wi-Fi，累計 2 分鐘**：開 `Micro_ros` 熱點。
3. **熱點開著、有裝置連著**：一直保持。
4. **熱點開著、連續 5 分鐘沒人連**：關掉熱點，交回系統去找 AnPing。還是找不到的話，2 分鐘後再開熱點，這樣一直循環。

### 實測（2026-10-28）

| 時間 | 事件 |
| --- | --- |
| 05:04:53 | 關掉手機熱點 |
| 05:06:54 | 看門狗開出 `Micro_ros`（約 2 分鐘） |
| 05:07 | 手機連上 `Micro_ros`，拿到 `10.42.0.152`，經轉接 SSH 進拍五成功 |
| 05:08 | 修正 bug 後，看門狗正確判斷「有 1 台裝置」並保持熱點 |
| 05:09:13 | 手機離開 `Micro_ros`、重開 AnPing 熱點 |
| 05:14:09 | 看門狗關掉 `Micro_ros`（閒置 5 分鐘） |
| 05:14:16 | 拍五自動連回 AnPing，`ycar.py status` 正常 |

修掉的 bug：`ip neigh` 每行最後有空白，原本抓不到裝置狀態，永遠算成 0 台。

### 手機熱點壞掉時怎麼連進拍五

1. 等拍五開出 `Micro_ros`（手機熱點斷掉約 2 分鐘後）。
2. 筆電或手機的 Wi-Fi 連 `Micro_ros`，密碼是出廠預設（見 `research/notes`，不寫在這裡）。
3. 拍五的位址是 `10.42.0.1`：
   - 筆電：`ssh pi@10.42.0.1`，VNC 連 `10.42.0.1:5900`
   - 手機連上時，PC 照樣用 USB 轉接，只要把轉接目標改成 `10.42.0.1`：

     ```bash
     adb -s 84bbb261 shell "nc -L -p 8022 nc 10.42.0.1 22" &
     adb -s 84bbb261 shell "nc -L -p 5900 nc 10.42.0.1 5900" &
     ```

4. 修好以後，所有裝置都離開 `Micro_ros`，5 分鐘後拍五就會自己找回 AnPing。

### 常用指令

```bash
cd ~/workspace/yahboom-microros-pi5/drill
python ycar.py host 'systemctl status pi5-wifi-fallback --no-pager | head -5'      # 服務狀態
python ycar.py host 'journalctl -u pi5-wifi-fallback -n 20 --no-pager -o cat'     # 最近的切換紀錄
python ycar.py host 'sudo bash /usr/local/bin/pi5-wifi-fallback.sh --once'       # 試判斷一次，不真的切換
bash wifi-fallback/pi5-wifi-fallback.sh --selftest                                # PC 上跑自我測試
```

改完程式的部署方式：用 paramiko SFTP 傳到車上 `~/wifi-fallback/`，然後依序執行：

1. `sudo install -m 755 ... /usr/local/bin/`
2. `sudo systemctl restart pi5-wifi-fallback`

### 還原成原廠行為

```bash
python ycar.py host 'sudo systemctl disable --now pi5-wifi-fallback; sudo nmcli con mod Micro_ros connection.autoconnect yes; sudo nmcli con mod "Wireless connection 1" connection.autoconnect-retries -1'
```

原本的設定備份在車上 `~/wifi-fallback/nm-backup-20261028.txt`。

## 5. 其他備援管道

| 管道 | 狀態 | 說明 |
| --- | --- | --- |
| 有線網路 | 已設定 | eth0 自動取得 IP，另有備援固定 IP `192.168.77.2`，見 `POWER-ON-CHECK.md` 附錄 |
| UART 序列除錯 | 未準備 | 網路全掛時的最後手段，需要一條 3.3 V USB 轉 TTL 線 |
| 螢幕＋鍵盤 | 隨時可用 | micro-HDMI 接螢幕，車子要放桌上 |
| 2.4G 手把 | 隨時可用 | 只能遙控行駛 |

## 6. 語音說明（`network-explain/`）

| 檔案 | 內容 |
| --- | --- |
| `01-architecture.mp3`／`.txt` | 現在的連線架構、熱點是不是另一個硬體、早上為什麼連不上、要改什麼、會不會影響、改壞怎麼救 |
| `02-hotspot-offline.mp3`／`.txt` | 拍五自己當熱點時沒有網路，還能做什麼 |
| `03-drill-connection.mp3`／`.txt` | 之前演練時是怎麼連的、為什麼跟教材不一樣 |
| `04-boot-desktop.mp3`／`.txt` | 開機時發生什麼事：VNC 桌面上的兩個終端、`~/.config/autostart` 兩個捷徑檔、怎麼確認、手把控制沒自動啟動 |
| `05-boot-panes` | 開機逐步演練：螢幕 3 tmux 三格、容器是什麼、兩個開機腳本的用途 |
| `06-boot-agent-script` | `start_agent_rpi5.sh` 逐行說明 |
| `07-boot-step2`／`08-...-result` | 第二步：按 ESP32 Reset，小腦連上翻譯官、登記 8 個話題 |
| `09-boot-step3`／`10-...-result` | 第三步：`ros2_humble.sh` 逐行說明、打開 ROS 2 容器，`docker ps` 從 1 個變 2 個 |
| `11-boot-step4`／`12-...-result` | 第四步：`ros2 node list`／`topic list`／讀電池，確認資料流通 |

播放：`python ~/.claude/skills/tts/scripts/tts_play.py play drill/network-explain/01-architecture.txt`，或直接開 mp3。

逐步重現開機流程的做法（2026-10-28）：在 Pi 桌面開一個 `lxterminal`，裡面用 tmux session `boot` 切成三格（① agent、② ROS 2 容器、③ 主機檢查），用 `tmux send-keys` 送指令。先關掉開機自動開的兩個終端，再照順序跑 `start_agent_rpi5.sh` → 按 ESP32 Reset → `ros2_humble.sh` → `ros2 topic list`。重開 agent 後，ESP32 不會自己重連，要按 Reset。
