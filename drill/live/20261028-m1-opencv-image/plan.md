# M1 實車逐步演練：OpenCV 與 ROS 影像話題

- 日期：2026-10-28
- 車子：不動。雲台不動（S2 禁止用指令動）。
- 上電檢查：1～9 ✅（34.0 °C、throttled 0x0、磁碟 55%、電池 81、/scan 12.5 Hz、/imu 20.4 Hz、相機 Microdia 在 /dev/video0）。
- 相機畫面若拍到室內或人，截圖只放 scratchpad，不進 shots/。

## tmux 格子（session `drill`，三格都 docker exec 進同一個 ROS 2 容器）

| 格子 | 用途 |
| --- | --- |
| ① 左上 | 相機節點／OpenCV 程式 |
| ② 右上 | 訂閱與轉發（astra_rgb_image、pub_image、rqt_image_view） |
| ③ 下方 | 檢查用（話題清單、頻率、格式） |

## 步驟

| 步驟 | 格子 | 指令 | 預期效果 |
| --- | --- | --- | --- |
| 1 影像就是數字表格 | ① | `cd ~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/` → `python3 -c "import cv2;img=cv2.imread('yahboom.jpg');print(img.shape, img[100,100])"` → `python3 3_3.py` | 印出（高, 寬, 3）與一個像素的 B G R；跳出原圖、灰階、Canny 邊緣三個視窗 |
| 2 OpenCV 直接開鏡頭 | ① | `python3 1_3.py` | 跳出即時相機畫面；按 q 關閉 |
| 3 QR code 辨識 | ① | `cd ~/yahboomcar_ws/src/yahboomcar_visual/simple_qrcode/` → `python3 QRcode_Parsing.py` | 手機秀出 QR code 對準鏡頭，畫面框起來並印出 `Found QRCODE barcode: ...` |
| 4 相機節點發布 /image_raw | ① ③ | ①`ros2 run usb_cam usb_cam_node_exe`；③`ros2 topic list`、`ros2 topic hz /image_raw`、`ros2 topic echo /image_raw --no-arr --once` | 出現 /image_raw，約 30 Hz（實測為準），看到 width/height/encoding |
| 5 鏡頭被占用 | ③ | `python3 .../opencv/1_3.py` | 相機節點開著時打不開鏡頭（失敗訊息），證明一支鏡頭只能一個程式開 |
| 6 cv_bridge：訂閱、轉發、看畫面 | ② ③ | ②`ros2 run yahboomcar_visual pub_image`；③`ros2 topic info /image_raw --verbose`、`ros2 run rqt_image_view rqt_image_view` 選 /image | /image_raw 有兩個訂閱者；rqt_image_view 看到經 cv_bridge 轉發的 /image 畫面 |

## 結果

- 影片：<https://youtu.be/gL69VqADwG8>（私人，約 31 分鐘；相機拍到室內的畫面已打碼，長空檔已壓縮）
- 錄影 19:08～19:48，約 40 分鐘；結束時電池 74（7.4 V）。
- 第 1 步：shape (169, 343, 3)、像素 [255 255 255]；3_3.py 三個視窗疊在一起，灰階視窗沒有標題列拖不動；按 q 出現 img.release() 的 AttributeError。
- 第 2 步：1_3.py 開鏡頭正常，按 q 乾淨結束。
- 第 3 步：紙本 QR code 一直沒讀到，只誤讀 `I25 barcode: 880622`，使用者決定跳過。
- 第 4 步：/image_raw 29.8 Hz、640×480、yuv422_yuy2、step 1280；`timeout ros2 topic hz` 被中斷會印一大段 Traceback，要加 `2>/dev/null`。
- 第 5 步：相機節點開著時 1_3.py 印 `can't open camera by index`／`Camera index out of range`。
- 第 6 步：/image_raw 發布者 usb_cam、訂閱者 pub_image_node；/image 29.5 Hz；`rqt_image_view /image` 直接帶話題名稱就不用選下拉選單。
