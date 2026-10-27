#!/bin/bash
# 拍五 Wi-Fi 備援看門狗：連不上手機熱點一段時間就開 Micro_ros 熱點（AP），
# AP 閒置太久沒人連就關掉，讓 NetworkManager 回頭自動連 client。
#
# 為什麼需要：出廠 Micro_ros 設 autoconnect=yes 時，手機熱點一消失 NM 5 秒內就切成 AP，
# 之後永遠不會回到 client。部署時把 Micro_ros 改成 autoconnect=no，由本腳本決定開關時機。
#
# 用法：
#   pi5-wifi-fallback.sh            常駐模式（systemd 以 root 執行）
#   pi5-wifi-fallback.sh --once     用真實指令判斷一次，只印出「會做的動作」，不真的 up/down
#   pi5-wifi-fallback.sh --selftest 不碰真實 nmcli/ip/ping，用假函式驗證決策邏輯（PC Git Bash 也能跑）
#
# 可用環境變數覆寫：AP_CON、IFACE、CHECK_INTERVAL、CLIENT_GRACE、AP_IDLE
#
# 不用 set -e：常駐程式不能因為單次 nmcli 失敗就整支結束。
set -uo pipefail

readonly LOG_TAG="pi5-wifi-fallback"

# 外部指令一律透過變數呼叫，selftest 時換成假函式
NMCLI="${NMCLI:-nmcli}"
IP="${IP:-ip}"
PING="${PING:-ping}"
LOGGER="${LOGGER:-logger}"
QUIET="${QUIET:-0}"

# 執行期狀態
GRACE=0          # 未以 client 身分連上的累計秒數
IDLE=0           # AP 開著且 0 裝置的累計秒數
LAST_MODE=""     # 上一輪的模式，只在變化時記 log
DEV_STATE=0      # 剖析出的 GENERAL.STATE 狀態碼
DEV_CONN=""      # 剖析出的 GENERAL.CONNECTION 連線名稱
SLEEP_PID=""

# 決策函式輸出
D_ACTION="none"
D_GRACE=0
D_IDLE=0
D_MODE=""

# ---------- 共用工具 ----------

log_msg() {
  local msg="$1"
  if [[ "$QUIET" != "1" ]]; then
    echo "[$LOG_TAG] $msg"
  fi
  # PC 上沒有 logger 也要能跑；logger 失敗不影響主流程
  if [[ -n "$LOGGER" ]] && command -v "$LOGGER" >/dev/null 2>&1; then
    "$LOGGER" -t "$LOG_TAG" -- "$msg" >/dev/null 2>&1 || true
  fi
}

is_positive_int() {
  [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

# 讀環境變數並驗證；不合法回傳 1（由呼叫端決定 exit）
load_config() {
  AP_CON="${AP_CON:-Micro_ros}"
  IFACE="${IFACE:-wlan0}"
  CHECK_INTERVAL="${CHECK_INTERVAL:-15}"
  CLIENT_GRACE="${CLIENT_GRACE:-120}"
  AP_IDLE="${AP_IDLE:-300}"

  local name
  for name in CHECK_INTERVAL CLIENT_GRACE AP_IDLE; do
    if ! is_positive_int "${!name}"; then
      echo "錯誤：$name 必須是正整數，目前是「${!name}」" >&2
      return 1
    fi
  done
  return 0
}

# ---------- 剖析與量測 ----------

# 剖析 `nmcli -t -f GENERAL.STATE,GENERAL.CONNECTION device show` 的輸出，
# 結果放在 DEV_STATE / DEV_CONN。-t 模式下值裡的冒號會被跳脫成「\:」。
parse_device_state() {
  local raw="$1" line value code
  DEV_STATE=0
  DEV_CONN=""
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in
      GENERAL.STATE:*)
        value="${line#GENERAL.STATE:}"
        code="${value%% *}"
        if [[ "$code" =~ ^[0-9]+$ ]]; then
          DEV_STATE="$code"
        fi
        ;;
      GENERAL.CONNECTION:*)
        value="${line#GENERAL.CONNECTION:}"
        value="${value//\\:/:}"
        value="${value//\\\\/\\}"
        DEV_CONN="$value"
        ;;
    esac
  done <<< "$raw"
  # 沒有連線時 nmcli 會印「--」
  if [[ "$DEV_CONN" == "--" ]]; then
    DEV_CONN=""
  fi
}

# 取 AP 自己在 IFACE 上的 IPv4（可能多個，以空白分隔）
get_own_ips() {
  local line word take_next own=""
  while IFS= read -r line; do
    take_next=0
    for word in $line; do
      if [[ "$take_next" == "1" ]]; then
        own+="${word%%/*} "
        take_next=0
      elif [[ "$word" == "inet" ]]; then
        take_next=1
      fi
    done
  done < <("$IP" -4 -o addr show dev "$IFACE" 2>/dev/null)
  echo "$own"
}

# 計算 AP 下 REACHABLE 的裝置數。先對 neigh 表裡非 FAILED 的 IP 各 ping 一次，
# 目的不是看 ping 結果（Windows 筆電常擋 ICMP），而是觸發 ARP，讓真的在線的裝置變 REACHABLE。
count_ap_clients() {
  local own_ips line addr state count=0
  local -a targets=()
  own_ips=" $(get_own_ips) "

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    addr="${line%% *}"
    read -r -a neigh_fields <<<"$line"; state="${neigh_fields[-1]}"  # ip neigh 行尾有空白，不能用 ${line##* }
    [[ "$state" == "FAILED" ]] && continue
    [[ "$own_ips" == *" $addr "* ]] && continue
    targets+=("$addr")
  done < <("$IP" -4 neigh show dev "$IFACE" 2>/dev/null)

  for addr in "${targets[@]+"${targets[@]}"}"; do
    "$PING" -c1 -W1 "$addr" >/dev/null 2>&1 &
  done
  wait

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    addr="${line%% *}"
    read -r -a neigh_fields <<<"$line"; state="${neigh_fields[-1]}"  # ip neigh 行尾有空白，不能用 ${line##* }
    [[ "$own_ips" == *" $addr "* ]] && continue
    if [[ "$state" == "REACHABLE" ]]; then
      count=$((count + 1))
    fi
  done < <("$IP" -4 neigh show dev "$IFACE" 2>/dev/null)

  echo "$count"
}

# ---------- 純決策函式 ----------

# 輸入：狀態碼、連線名稱、裝置數、目前 grace、目前 idle
# 輸出（全域）：D_ACTION（none / ap_up / ap_down）、D_GRACE、D_IDLE、D_MODE
# 不呼叫任何外部指令，方便 selftest。
decide_action() {
  local state="$1" conn="$2" clients="$3" grace="$4" idle="$5"
  [[ "$clients" =~ ^[0-9]+$ ]] || clients=0
  D_ACTION="none"
  D_GRACE="$grace"
  D_IDLE="$idle"

  if [[ "$state" == "100" && -n "$conn" && "$conn" != "$AP_CON" ]]; then
    D_MODE="client"
    D_GRACE=0
    D_IDLE=0
    return 0
  fi

  if [[ "$conn" == "$AP_CON" ]]; then
    D_GRACE=0
    if [[ "$state" != "100" ]]; then
      # AP 正在啟動中：不累計、不重複 up
      D_MODE="ap_pending"
      return 0
    fi
    if (( clients > 0 )); then
      D_MODE="ap_busy"
      D_IDLE=0
    else
      D_MODE="ap_idle"
      D_IDLE=$((idle + CHECK_INTERVAL))
      if (( D_IDLE >= AP_IDLE )); then
        D_ACTION="ap_down"
      fi
    fi
    return 0
  fi

  # 未連線、連線中（30~90）等都算「沒以 client 連上」；NM 正在嘗試的 client 連線會被 AP 取代
  D_MODE="offline"
  D_IDLE=0
  D_GRACE=$((grace + CHECK_INTERVAL))
  if (( D_GRACE >= CLIENT_GRACE )); then
    D_ACTION="ap_up"
  fi
  return 0
}

# ---------- 動作與主迴圈 ----------

describe_mode() {
  case "$1" in
    client)     echo "client 已連線（$DEV_CONN）" ;;
    ap_busy)    echo "AP 模式，有 $2 台裝置" ;;
    ap_idle)    echo "AP 模式，0 台裝置（閒置 ${IDLE}/${AP_IDLE} 秒後關閉）" ;;
    ap_pending) echo "AP 啟動中（狀態碼 $DEV_STATE）" ;;
    offline)    echo "未以 client 連上（狀態碼 $DEV_STATE，${CLIENT_GRACE} 秒後開 AP）" ;;
    error)      echo "讀取 $IFACE 狀態失敗" ;;
    *)          echo "$1" ;;
  esac
}

set_mode() {
  local mode="$1" detail="${2:-}"
  if [[ "$mode" != "$LAST_MODE" ]]; then
    log_msg "狀態變化：${LAST_MODE:-（啟動）} → $mode｜$detail"
    LAST_MODE="$mode"
  fi
}

run_ap_up() {
  local out
  if out=$("$NMCLI" con up "$AP_CON" 2>&1); then
    log_msg "已啟用 AP「$AP_CON」（client 累計 ${GRACE} 秒未連上）"
  else
    # 失敗也歸零：避免每 CHECK_INTERVAL 秒狂打 nmcli，等下一個 CLIENT_GRACE 再試
    log_msg "啟用 AP「$AP_CON」失敗，${CLIENT_GRACE} 秒後重試：$out"
  fi
  GRACE=0
  IDLE=0
}

run_ap_down() {
  local out
  if out=$("$NMCLI" con down "$AP_CON" 2>&1); then
    log_msg "已關閉 AP「$AP_CON」（連續 ${IDLE} 秒無裝置），交回 NM 自動連 client"
  else
    log_msg "關閉 AP「$AP_CON」失敗：$out"
  fi
  GRACE=0
  IDLE=0
}

# 讀取目前狀態並更新 DEV_STATE / DEV_CONN；失敗回傳 1
read_device_state() {
  local raw
  if ! raw=$("$NMCLI" -t -f GENERAL.STATE,GENERAL.CONNECTION device show "$IFACE" 2>&1); then
    set_mode "error" "nmcli device show 失敗：$raw"
    return 1
  fi
  parse_device_state "$raw"
  return 0
}

# 單輪檢查：讀狀態 → 決策 → 執行
tick() {
  local clients=0
  read_device_state || return 0
  if [[ "$DEV_CONN" == "$AP_CON" && "$DEV_STATE" == "100" ]]; then
    clients=$(count_ap_clients)
  fi
  decide_action "$DEV_STATE" "$DEV_CONN" "$clients" "$GRACE" "$IDLE"
  GRACE="$D_GRACE"
  IDLE="$D_IDLE"
  set_mode "$D_MODE" "$(describe_mode "$D_MODE" "$clients")"
  case "$D_ACTION" in
    ap_up)   run_ap_up ;;
    ap_down) run_ap_down ;;
  esac
}

on_term() {
  log_msg "收到 $1，看門狗結束"
  if [[ -n "$SLEEP_PID" ]]; then
    kill "$SLEEP_PID" 2>/dev/null || true
  fi
  exit 0
}

require_commands() {
  local cmd
  for cmd in "$NMCLI" "$IP" "$PING"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "錯誤：找不到指令 $cmd" >&2
      return 1
    fi
  done
  return 0
}

log_params() {
  log_msg "參數：AP_CON=$AP_CON IFACE=$IFACE CHECK_INTERVAL=$CHECK_INTERVAL CLIENT_GRACE=$CLIENT_GRACE AP_IDLE=$AP_IDLE"
}

run_loop() {
  trap 'on_term SIGTERM' TERM
  trap 'on_term SIGINT' INT
  log_msg "看門狗啟動"
  log_params
  while true; do
    tick
    # sleep 放背景再 wait，SIGTERM 才能立刻被 trap 處理
    sleep "$CHECK_INTERVAL" &
    SLEEP_PID=$!
    wait "$SLEEP_PID" 2>/dev/null
    SLEEP_PID=""
  done
}

action_text() {
  case "$1" in
    ap_up)   echo "nmcli con up \"$AP_CON\"" ;;
    ap_down) echo "nmcli con down \"$AP_CON\"" ;;
    *)       echo "不動作" ;;
  esac
}

# dry-run：用真實指令讀一次，印出判斷，不真的 up/down
run_once() {
  local clients=0
  QUIET=1
  echo "參數：AP_CON=$AP_CON IFACE=$IFACE CHECK_INTERVAL=$CHECK_INTERVAL CLIENT_GRACE=$CLIENT_GRACE AP_IDLE=$AP_IDLE"
  if ! read_device_state; then
    echo "錯誤：無法讀取 $IFACE 狀態（nmcli device show 失敗）" >&2
    return 1
  fi
  echo "GENERAL.STATE=$DEV_STATE"
  echo "GENERAL.CONNECTION=${DEV_CONN:-（無）}"
  if [[ "$DEV_CONN" == "$AP_CON" && "$DEV_STATE" == "100" ]]; then
    clients=$(count_ap_clients)
    echo "AP 連線裝置數（REACHABLE）=$clients"
  fi

  decide_action "$DEV_STATE" "$DEV_CONN" "$clients" 0 0
  echo "模式=$D_MODE"
  echo "本輪動作（計時從 0 起算）：$(action_text "$D_ACTION")"

  # 再模擬「狀態持續到門檻」時的動作，讓使用者知道之後會發生什麼
  decide_action "$DEV_STATE" "$DEV_CONN" "$clients" \
    $((CLIENT_GRACE - CHECK_INTERVAL)) $((AP_IDLE - CHECK_INTERVAL))
  echo "若此狀態持續到門檻：$(action_text "$D_ACTION")"
  echo "（--once 為 dry-run，未執行任何 up/down）"
  return 0
}

# ---------- selftest ----------

SELFTEST_FAILS=0
STUB_LOG=""
STUB_STATE_LINE=""
STUB_CONN_LINE=""
STUB_NEIGH=""

stub_nmcli() {
  case "$*" in
    *"device show"*)
      printf 'GENERAL.STATE:%s\nGENERAL.CONNECTION:%s\n' "$STUB_STATE_LINE" "$STUB_CONN_LINE"
      ;;
    "con up "*|"con down "*)
      # 寫檔而非改變數：呼叫端在 $(...) 子 shell 內，變數改了帶不回來
      echo "$*" >> "$STUB_LOG"
      ;;
  esac
  return 0
}

stub_ip() {
  case "$*" in
    *neigh*) printf '%s\n' "$STUB_NEIGH" ;;
    *addr*)  echo "3: wlan0    inet 10.42.0.1/24 brd 10.42.0.255 scope global noprefixroute wlan0" ;;
  esac
  return 0
}

stub_ping() { return 0; }

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "PASS: $desc"
  else
    echo "FAIL: $desc（預期「$expected」，實際「$actual」）"
    SELFTEST_FAILS=$((SELFTEST_FAILS + 1))
  fi
}

stub_calls() {
  grep -c -- "$1" "$STUB_LOG" 2>/dev/null || true
}

reset_sim() {
  GRACE=0
  IDLE=0
  LAST_MODE=""
  : > "$STUB_LOG"
}

run_ticks() {
  local n="$1" i
  for ((i = 0; i < n; i++)); do
    tick
  done
}

selftest_cases() {
  # 1. client 已連線 → 不動作
  reset_sim
  STUB_STATE_LINE="100 (connected)"; STUB_CONN_LINE="Wireless connection 1"
  run_ticks 20
  assert_eq "1. client 已連線：不呼叫 con up/down" "0" "$(stub_calls "con ")"
  assert_eq "1. client 已連線：GRACE 維持 0" "0" "$GRACE"

  # 2. 未連線累計到 CLIENT_GRACE（60 秒 = 4 輪）才 con up
  reset_sim
  STUB_STATE_LINE="30 (disconnected)"; STUB_CONN_LINE="--"
  run_ticks 3
  assert_eq "2. 未連線 45 秒：尚未 con up" "0" "$(stub_calls "con up")"
  run_ticks 1
  assert_eq "2. 未連線 60 秒：呼叫 con up Micro_ros" "1" "$(stub_calls "con up Micro_ros")"
  assert_eq "2. con up 後 GRACE 歸零" "0" "$GRACE"

  # 2b. NM 連線中（狀態 70）也算未連線
  reset_sim
  STUB_STATE_LINE="70 (connecting (getting IP configuration))"; STUB_CONN_LINE="Wireless connection 1"
  run_ticks 4
  assert_eq "2b. 卡在連線中 60 秒：呼叫 con up" "1" "$(stub_calls "con up")"

  # 3. AP 模式有裝置 → 不關（FAILED 與自己的位址不算）
  reset_sim
  STUB_STATE_LINE="100 (connected)"; STUB_CONN_LINE="Micro_ros"
  STUB_NEIGH=$'10.42.0.23 lladdr aa:bb:cc:dd:ee:01 REACHABLE\n10.42.0.50 FAILED\n10.42.0.1 lladdr aa:bb:cc:dd:ee:02 REACHABLE'
  assert_eq "3. count_ap_clients 只算 REACHABLE、排除自己" "1" "$(count_ap_clients)"
  run_ticks 20
  assert_eq "3. AP 有裝置：不呼叫 con down" "0" "$(stub_calls "con down")"
  assert_eq "3. AP 有裝置：IDLE 維持 0" "0" "$IDLE"

  # 4. AP 0 裝置累計到 AP_IDLE（45 秒 = 3 輪）才 con down
  reset_sim
  STUB_NEIGH=$'10.42.0.23 lladdr aa:bb:cc:dd:ee:01 STALE\n10.42.0.50 FAILED'
  assert_eq "4. STALE/FAILED 不算在線裝置" "0" "$(count_ap_clients)"
  run_ticks 2
  assert_eq "4. AP 閒置 30 秒：尚未 con down" "0" "$(stub_calls "con down")"
  run_ticks 1
  assert_eq "4. AP 閒置 45 秒：呼叫 con down Micro_ros" "1" "$(stub_calls "con down Micro_ros")"
  assert_eq "4. con down 後 IDLE 歸零" "0" "$IDLE"

  # 5. 剖析：連線名稱含空白、含跳脫冒號
  parse_device_state $'GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Wireless connection 1'
  assert_eq "5. 剖析狀態碼" "100" "$DEV_STATE"
  assert_eq "5. 剖析含空白的連線名稱" "Wireless connection 1" "$DEV_CONN"
  parse_device_state $'GENERAL.STATE:30 (disconnected)\nGENERAL.CONNECTION:--'
  assert_eq "5. 未連線時連線名稱為空" "" "$DEV_CONN"
  parse_device_state $'GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Lab\\:5G'
  assert_eq "5. 還原 -t 跳脫的冒號" "Lab:5G" "$DEV_CONN"

  # 5b. 純決策函式
  decide_action 100 "Wireless connection 1" 0 45 0
  assert_eq "5b. decide：client 連上時 grace 歸零" "none 0 client" "$D_ACTION $D_GRACE $D_MODE"
  decide_action 30 "" 0 45 0
  assert_eq "5b. decide：45+15 達門檻 → ap_up" "ap_up 60 offline" "$D_ACTION $D_GRACE $D_MODE"

  # 6. 參數不合法
  local rc
  ( CHECK_INTERVAL=abc; load_config ) 2>/dev/null; rc=$?
  assert_eq "6. CHECK_INTERVAL=abc → 錯誤" "1" "$rc"
  ( CLIENT_GRACE=0; load_config ) 2>/dev/null; rc=$?
  assert_eq "6. CLIENT_GRACE=0 → 錯誤" "1" "$rc"
  ( AP_IDLE=-5; load_config ) 2>/dev/null; rc=$?
  assert_eq "6. AP_IDLE=-5 → 錯誤" "1" "$rc"
  ( CHECK_INTERVAL=15; CLIENT_GRACE=120; AP_IDLE=300; load_config ) 2>/dev/null; rc=$?
  assert_eq "6. 合法參數 → 通過" "0" "$rc"
}

run_selftest() {
  NMCLI=stub_nmcli
  IP=stub_ip
  PING=stub_ping
  LOGGER=""
  QUIET=1
  AP_CON="Micro_ros"
  IFACE="wlan0"
  CHECK_INTERVAL=15
  CLIENT_GRACE=60
  AP_IDLE=45

  STUB_LOG=$(mktemp) || { echo "FAIL: 無法建立暫存檔"; return 1; }
  selftest_cases
  rm -f "$STUB_LOG"

  if (( SELFTEST_FAILS == 0 )); then
    echo "PASS"
    return 0
  fi
  echo "FAIL: 共 $SELFTEST_FAILS 項失敗"
  return 1
}

# ---------- 進入點 ----------

usage() {
  echo "用法：$0 [--once | --selftest | --help]"
}

main() {
  local mode="${1:-loop}"
  case "$mode" in
    --selftest)
      run_selftest
      exit $?
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --once|loop)
      ;;
    *)
      echo "錯誤：未知參數 $mode" >&2
      usage >&2
      exit 1
      ;;
  esac

  load_config || exit 1
  require_commands || exit 1

  if [[ "$mode" == "--once" ]]; then
    run_once
    exit $?
  fi
  run_loop
}

main "$@"
