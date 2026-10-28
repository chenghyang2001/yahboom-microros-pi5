# Session 2 摘要（2026-10-27～10-28）

## 完成事項

### 拍五（車子代號）與上電檢查

- 訂定代號：說「拍五」（Pi5、派五）就是這台 Yahboom MicroROS-Pi5。寫進全域 `~/.claude/CLAUDE.md`，任何專案都適用。
- 新增 `drill/POWER-ON-CHECK.md`：上電檢查 0～10 步，依序是 adb、網路、轉接、SSH、VNC、Pi 健康、Docker、ESP32、ROS 話題、時鐘差。附 10-27、10-28 實測紀錄。
- 找到 ESP32 和 Pi 時鐘差的成因：Pi 沒有 RTC 電池，開機先沿用上次關機的時間，ESP32 這時候對時，之後 Pi 用 NTP 校正，ESP32 不會跟著改。實測差 5409 秒和 42582 秒。要跑 SLAM 前按 ESP32 Reset。

### 網路備援

- 手機熱點的「逾時自動關閉」用 adb 操作畫面關掉了，兩份設定都確認是 `AutoShutdownEnabled=false`。
- 有線備援：Pi 的 eth0 改成自動取得 IP，再加備援固定 IP `192.168.77.2/24`（route-metric 700，不搶 Wi-Fi 路由）。還沒接線實測。
- Wi-Fi 備援看門狗 `pi5-wifi-fallback`（`drill/wifi-fallback/`，systemd 服務）：
  - 找到 10-28 早上斷線的真因：原廠 `Micro_ros` 熱點 autoconnect=yes，找不到 AnPing 約 5 秒就切成熱點模式，而且回不來。
  - 改成 Micro_ros autoconnect=no、AnPing 自動重試改成無限次，再由看門狗管理：連不上 2 分鐘才開熱點，熱點閒置 5 分鐘就關掉、回頭找 AnPing。
  - 實測完整循環：05:04 關掉手機熱點 → 05:06 開出 Micro_ros → 05:14 連回 AnPing。
  - 修了一個 bug：`ip neigh` 每行最後有空白，原本永遠判斷成 0 台裝置。
- 使用者決定：**維持「拍五連手機熱點、PC 經 USB 轉接」的連法**，不用教材的「電腦連車子熱點」，因為 Claude Code 和語音指令都要上網。寫成 `drill/NETWORK.md`。

### 語音說明與逐步演練形式

- 使用者聽語音比看文字好懂。建立「先 TTS 說明 → 念完才下指令 → 念結果 → 等『繼續』」的演練節奏，記成記憶。
- `drill/network-explain/` 共 12 段 mp3 和文字稿：網路架構 3 段、開機桌面 1 段、開機逐步演練 8 段。
- 開機流程逐步演練：VNC 開到螢幕 3，用 tmux 切三格。關掉開機自動開的終端後，依序跑 `start_agent_rpi5.sh` → 按 ESP32 Reset → `ros2_humble.sh` → `ros2 topic list`。截圖加語音做成影片 <https://youtu.be/br1-xZYNp-A>（私人，長 18 分 44 秒）。
- **新增全域 skill `pi5-live-drill`**（`~/.claude/skills/pi5-live-drill/`）：VNC 加 tmux、每步 TTS、全程錄影、收尾上傳 YouTube 並加網站連結。pitfalls 累積了 26 條，也補了電腦 WSL 版的做法。

### 用 skill 實測

- **開機流程（實車）第一次實測**：做完準備和第一步，因為手機沒電暫停。進度在 `drill/live/20261028-boot-sequence/plan.md`。
- **W2 ROS 2 最小必學（WSL 加 turtlesim）**：7 步全部完成。63.5 分鐘的錄影剪成 39 分鐘，上傳 <https://youtu.be/E2xuUzat6B8>（私人），也加到網站首頁「本教材影片」區。
- **W4 URDF／RViz／TF（WSL）**：開始前先測過 RViz、Gazebo 都能用。做完準備和開場語音，使用者喊收工，暫停。

### 網站與上傳

- 網站是從 **`gh-pages` 分支**部署的（推 main 不會更新）。要用 `git subtree push --prefix site origin gh-pages`，已經寫進專案 CLAUDE.md。
- YouTube 上傳改用 Data API 腳本 `~/workspace/ros2-turtle-cli-demo/highlights/yt_upload_drills.py`。只會上傳私人影片，沒有大小限制。這次第一次正式用，授權金鑰有效。

## 關鍵決定

| 決定 | 原因 |
| --- | --- |
| 「拍五」＝這台車，全域生效 | 使用者不想每次講一長串車名 |
| 維持手機熱點連法，不用教材的「電腦連車子熱點」 | Claude Code 和語音指令都要上網 |
| Wi-Fi 看門狗：連不上 2 分鐘開 Micro_ros、閒置 5 分鐘切回 | 原廠 5 秒就切成熱點而且回不來，只能斷電重開 |
| 演練一律「TTS 說明 → 下指令 → 念結果 → 等繼續」，做成全域 skill `pi5-live-drill`，全程錄影 | 使用者聽語音比看文字好懂，要親眼看到每一步的效果 |
| YouTube 改用 Data API 腳本上傳 | Chrome 上傳一次最多 10 MB；腳本沒有大小限制，而且只會上傳私人影片 |
| 網站更新要 `git subtree push --prefix site origin gh-pages` | Pages 讀的是 gh-pages 分支 |

## 關鍵技術筆記

- 螢幕 3 是 `DISPLAY7`，位置 (-1280,0)，1280×720。`drill-record.ps1` 要傳 `-Monitor 2` 才是螢幕 3（它的編號是主螢幕 = 1，其他螢幕由左到右）。
- WSLg 的坑：
  - rqt_graph（Qt）被程式移動或改大小後會凍住，圖的區域也是空白，改用 `ros2 topic info --verbose` 用文字說明。
  - turtlesim、RViz 只移動、不改大小就沒事。
  - 放到最大會跑到主螢幕。
- tmux 送方向鍵：`send-keys Up` 遙控器不認得，要送字面跳脫碼 `-l $'\e[A'`。
- 從 Git Bash 送指令進 WSL 時，多層引號很容易壞掉，要用 `wsl ... bash -s <<'EOF'`。
- 視窗擺放要先呼叫 `SetProcessDpiAwarenessContext(-4)`。EnumWindows 縮小視窗時要排除 Program Manager（桌面本身）。
- 判斷 ROS 2 listener「收不到」之前，至少要等 20 秒。這次原本以為是 DISCOVERY_RANGE 的問題，判斷錯了。

## 產出檔案

| 檔案 | 說明 |
| --- | --- |
| `drill/POWER-ON-CHECK.md` | 上電檢查 0～10 步、有線備援附錄 |
| `drill/NETWORK.md` | 網路架構、Wi-Fi 備援、語音清單 |
| `drill/wifi-fallback/pi5-wifi-fallback.sh`、`.service` | Wi-Fi 備援看門狗（車上 `/usr/local/bin/`） |
| `drill/network-explain/01～12-*.txt/.mp3` | 語音說明 |
| `drill/live/20261028-boot-sequence/` | 開機流程實測（暫停） |
| `drill/live/20261028-w2-ros2-basics/` | W2 完整演練：18 段語音、截圖、剪輯資料 |
| `drill/live/20261028-w4-urdf-rviz-tf/` | W4 準備與開場（暫停） |
| `site/links.json`、`site/index.html` | 新增兩支影片連結 |
| `.gitattributes` | `*.sh`、`*.service` 一律 LF |
| `~/.claude/skills/pi5-live-drill/` | 新 skill（全域） |
| `~/.claude/CLAUDE.md` | 「拍五」代號規則、pi5-live-drill 觸發 |
| 本機 `~/Videos/pi5-drill/` | 錄影原檔與成品（不進 git） |

主要 commit：33ecb86（上電檢查）、6e622b8（Wi-Fi 看門狗）、b388d2b（開機影片）、6669e2f（W2 影片）、cab5e00（W4 暫停）。~/.claude 的 commit：328a131e、d12f3ad7。

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] **接續 W4 演練**（不需要車子）：說「繼續 W4 演練」。先讀 `drill/live/20261028-w4-urdf-rviz-tf/plan.md`，重建 tmux `w4` 和終端、開新一段錄影，從第一步「URDF 的 link 與 joint」的說明語音開始，共 6 步。
- [ ] **接續開機流程演練**（要車子）：手機和車子都充好電後，說「繼續開機流程演練」。車子重開過，要從準備重來，見 `drill/live/20261028-boot-sequence/plan.md`。
- [ ] 兩場都做完後各自剪輯上傳。開機流程有兩段錄影要接起來。

### 進行中（需接續）

- W4：只完成準備和開場（第 1 段錄影 26 分鐘，大部分是空等，剪輯時只要開場那段）。
- 開機流程：完成第一步（第 1 段錄影 10 分鐘）。
- 有線備援 `192.168.77.2` 還沒接線實測。

### 注意事項

- 車子電池 10-28 早上掉到 6.7 V，使用者已經關機充電。
- Micro_ros 熱點密碼是出廠預設 `12345678`，很弱，之後可以改。
- 手機上有一條連到 10.57.201.101 的 7896 轉接，不是 Claude 開的，不要動。
- 做 WSL 演練前，先看 skill pitfalls 裡「WSL 版演練」那幾列。
