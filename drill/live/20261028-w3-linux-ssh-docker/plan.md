# 拍五逐步演練：W3＋B2 Linux、SSH、Docker 與正確關機（2026-10-28）

教材：`lessons/W3.md`、`lessons/B2.md`（§6 健康檢查與正確關機）。實車，車子不動，最後讓 Pi 關機。路線圖第 2 場。
畫面：螢幕 3 是 VNC，tmux `drill` 沿用三格，主要用 ③ 主機格（拉高）。

| 步驟 | 主題 | 格子 | 指令 | 預期 |
| --- | --- | --- | --- | --- |
| 1 | Linux 基本指令 | ③ | `pwd`、`ls`、`ls /dev/ttyUSB* /dev/video*`、`hostname -I` | 家目錄、開機腳本、裝置檔、IP |
| 2 | SSH 怎麼連進來 | ③ | `ss -tn \| grep -E ':22 \|:5900 '` | 對方是手機 10.169.179.x |
| 3 | Docker 三個名詞 | ③ | `docker images`、`docker ps`、`docker ps -a` | 映像 3、執行中 2、全部 16 |
| 4 | docker exec 進同一個容器 | ③ | `docker exec -it <ID> bash` → `ros2 node list` → `exit` | 互動殼直接有 ros2 |
| 5 | 健康檢查 | ③ | `df -h /`、thermal、`vcgencmd get_throttled` | 55%、約 48 °C、0x0 |
| 6 | 正確關機 | ③ | `sudo shutdown -h now` | VNC 斷線；使用者看綠燈不閃再關總開關 |
| 7 | 總結 | — | 語音 | — |

試跑：`docker exec -it` 的互動 bash 有 ros2（講義「需實車確認」→ 可以）；`bash -c` 非互動沒有。sudo 免密碼。`who` 看不到 paramiko 的 SSH，改用 `ss`。車上有 humble 4.1.2 與 4.1.0 兩個映像各 13.6 GB。

## 結果

- 七步全部完成（12:44～13:21），13:16:13 送關機、13:16:43 Pi 不回 ping；使用者確認綠燈不閃、總開關已關
- 影片（YouTube 私人）：<https://youtu.be/f1iO97zIU9M>，33 分 41 秒；播放清單第 5 位
- 電池：開場 7.1 V，第五步後 6.9 V
- 小插曲：TigerVNC 對方斷線時直接關視窗，不是顯示斷線訊息；第五步 tts_play 第一次 exit 9 沒出聲，重播正常；③ 格標題又被 docker exec 進去的 bash 改掉，手動改回
