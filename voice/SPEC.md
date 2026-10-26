# 語音指令 MVP 規格（藍牙耳機 → Pi 5 → 小車）

最後更新：2026-10-27｜模式：快速 demo（未經 QA／審查）

## 目標

戴 K200 Pro 藍牙耳機說中文指令，車子執行蜂鳴器與簡單移動。對應教材圖「ALM（STT＋SLU＋TTS）＋ LLM」的最小原型。

## 輸入／輸出

- 輸入：耳機 HFP 麥克風（PipeWire 來源 `bluez_input.00_12_12_00_D9_C2.0`，16 kHz 單聲道）
- 輸出：ROS 2 話題 `/beep`（std_msgs/UInt16，毫秒）、`/cmd_vel`（geometry_msgs/Twist），ROS_DOMAIN_ID=20

## 管線

1. **收音斷句**（Pi 主機）：每 30 ms 算音量，超過門檻開始錄，靜音 0.8 秒結束；最長 6 秒，太短（< 0.4 秒）丟掉
2. **STT**：faster-whisper（Pi 用 `base`／`small` int8，實測後決定），`language=zh`，initial_prompt 放指令詞彙
3. **喚醒詞**：文字含「小車」才往下走（相近寫法：小車／小手／小區 等用拼音近似比對，MVP 先只比「小車」「小ㄔㄜ」常見誤辨字清單）
4. **停車捷徑**：文字含「停」且不含「蜂鳴」→ 直接 `stop`，不經 LLM
5. **LLM（SLU）**：Claude Haiku（`claude-haiku-5-5`），強制 tool use 輸出 JSON
6. **安全檢查**：白名單＋夾限
7. **執行**：一行 JSON 經 `docker exec -i` 常駐管道送給容器內小節點，節點發布話題
8. **回饋**：耳機播提示音（成功＝高音短嗶、聽不懂＝兩聲低音）

## 指令 JSON（LLM tool 輸出）

| action | 參數 | 夾限 | 範例說法 |
| --- | --- | --- | --- |
| `beep` | `ms` 整數 | 0～60000（0＝停） | 蜂鳴器響三十秒／蜂鳴器停止 |
| `move` | `linear` m/s、`angular` rad/s、`seconds` | 線速 ±0.15、角速 ±0.8、秒數 0.5～3 | 直線前進／後退一點／左轉 |
| `stop` | — | — | 停止轉動／停 |
| `unknown` | `reason` | — | 聽不懂或不在白名單 |

## 容器內節點（ROS 端）

- 從 stdin 一行讀一個 JSON，發布對應話題
- `move` 期間每 0.1 秒重發 Twist，時間到送零速度
- **看門狗**：收到新指令會取消舊動作；stdin 關閉（主機程式掛掉）→ 立即送零速度並結束

## 邊界情況

| 情況 | 處理 |
| --- | --- |
| 沒說「小車」 | 忽略，不出聲 |
| 說「停」 | 捷徑停車（不等 LLM） |
| 網路斷／API 逾時（3 秒） | 不動作、播兩聲低音；「停」捷徑仍可用 |
| LLM 回超出範圍的數值 | 夾到上限，記 log |
| LLM 回非白名單動作 | 當 `unknown` |
| 耳機斷線 | 收音迴圈等待重連，期間送一次 `stop` |
| 蜂鳴器送 0 能否中斷 | 待實車確認；不能的話 MVP 文件註明 |

## 依賴

- Pi 主機：python3、faster-whisper（venv）、anthropic SDK、PipeWire（`parec`）
- 容器：rclpy（已有）
- 機密：`ANTHROPIC_API_KEY` 只放車上 `~/voice/.env`（權限 600），不設全域、不進 git

## 實作步驟

0. 本規格
1. 筆電離線原型：wav → STT → LLM → 驗證後 JSON（`voice/intent_proto.py`）
2. Pi 環境：`free -h`、裝 faster-whisper、量辨識速度
3. 容器節點 `voice/ros_cmd_node.py`
4. 主機收音迴圈 `voice/voice_agent.py`，串起整條
5. 架空測試 → 地上測試 → 示範影片
