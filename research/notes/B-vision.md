# B 區研究筆記：視覺（ROS+OpenCV、MediaPipe、機器人視覺互動）

資料來源：`research/pdf-text/` 之 `06.ROS+OpenCV course`（7 課）、`07.Mediapipe course`（10 課）、`08.Robot visual interaction`（10 個檔，原編號缺第 3 課）。全部讀完。
指令、套件、節點、話題、檔名皆保留官方原文（含官方的拼字錯誤，如 `face_fllow`，照抄才跑得動）。

## 1. 本區概覽

- 這一區是整套教材「讓車子看得懂」的部分：先學 OpenCV 影像基礎（讀圖、畫圖、二值化、QR code、AR），再學 ROS 2 怎麼傳影像（`sensor_msgs/Image` 與 `cv_bridge`），接著用 MediaPipe 做手、身體、臉的關鍵點偵測，最後把「看到的東西」轉成雲台角度或 `/cmd_vel` 速度，讓車子追顏色、追人臉、巡線、看手勢開車。
- 全部程式在 Pi 5 上的 **Docker 容器**內執行（原文一再寫「After entering the docker container」，路徑是 `/root/yahboomcar_ws/...`）。
- 第 08 資料夾的每一課都有同一個前提：**樹莓派與 micro-ROS 控制板的 `ROS_DOMAIN_ID` 必須一致**，否則雲台舵機與車輪不會動（官方指向「MicroROS Control Board Parameter Configuration」與「Connect MicroROS Agent」兩份教學，不在本區範圍）。
- 官方文件有不少前後不一致的地方（ROS 1 與 ROS 2 混用、foxy 與 humble 混用、攝影機編號 0 與 4），詳見各課「注意事項」與第 5 節。

---

## 2. 逐課筆記

### 06. ROS+OpenCV course

#### 06-1 Getting started with OpenCV（OpenCV 入門）

**觀念**：OpenCV 是開源電腦視覺函式庫。影像在 Python 裡就是一個 numpy 陣列，形狀 `(高, 寬, 3)`，三個值順序是 **B、G、R（不是 RGB）**。`imshow` 顯示、`waitKey` 讓視窗有時間刷新並讀鍵盤。

**核心函式**

- `cv2.imread('yahboom.jpg', flag)`：flag 為 `0` 灰階、`1` 彩色（預設）、`-1` 保持原樣含 alpha。
- `cv.imshow('frame', img)`：開名為 frame 的視窗。
- `cv2.imwrite('new_img_name', img)`：存檔。
- `cv.VideoCapture(0)`：開攝影機（0 = 第一支攝影機；給檔名則開影片）。`ret, img = cap.read()`，`ret` 表示這幀是否讀成功。
- 像素存取：`(b,g,r) = img[100,100]`，賦值 `img[i,j] = (0,0,0)` 塗黑。

**指令**（在 Docker 容器內，需有 `yahboom.jpg` 在同資料夾）

```bash
cd ~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/
python3 1_1.py   # 讀圖並顯示
python3 1_2.py   # 寫圖 imwrite 後再讀回顯示
python3 1_3.py   # 讀攝影機 VideoCapture(0) 顯示即時影像
python3 1_4.py   # 像素操作，把左上一條區域塗黑
```

- 按 `q`（程式判斷 `ord('q')` 或 113）離開。

**注意事項**

- 官方範例結尾寫 `img.release()`，但 `img` 是圖片陣列，沒有 `release()`，按 `q` 離開時會報 `AttributeError`（只有 `1_3.py` 用 `frame.release()` 是對的，因為那是 VideoCapture）。這是官方小 bug，不影響學習，可改成刪掉那行。
- 官方文字說明的 `imread` flag 表把 `IMREAD_UNCHANGED` 列了兩次，第二個（值 2）實際應為 `IMREAD_ANYDEPTH`，別照表背。
- `1_3.py` 的 `VideoCapture(0)` 在車上要看 `/dev/video*` 編號，見第 5 節。
- 這幾課用的是 `imshow` 開視窗，所以必須在有桌面（螢幕或 VNC）的環境執行，純 SSH 不行。

#### 06-2 Geometric transformation（幾何變換）

**觀念**：縮放、裁切、平移、鏡像。重點是 `resize` 的尺寸是 **(寬, 高)**，但 `img.shape` 回傳的是 (高, 寬)，這是初學者最常搞混處。平移用 2x3 仿射矩陣 M：`[[1,0,tx],[0,1,ty]]`。

**指令**

```bash
cd ~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/
python3 2_1.py   # cv2.resize 縮小一半
python3 2_2.py   # 裁切 dst = img[0:100,100:200]
python3 2_3.py   # warpAffine 平移，matShift = np.float32([[1,0,10],[0,1,10]])
python3 2_4.py   # 垂直鏡像（雙層迴圈逐像素複製）
```

**核心**：`cv2.resize(src, (寬,高))`、`img[y1:y2, x1:x2]` 裁切（先 y 後 x）、`cv2.warpAffine(img, M, (寬,高))`。
**注意**：官方文字說裁切 X 300-500、Y 500-700，但程式實際寫 `img[0:100,100:200]`，文與碼不符，以程式為準。

#### 06-3 Image processing and drawing（影像處理與繪圖）

**觀念**：灰階（R=G=B，減少運算量）→ 二值化（超過門檻變白、否則變黑）→ 邊緣偵測（Canny：高斯模糊去雜訊→算梯度→非極大值抑制→雙門檻→連接邊緣）。再來是在影像上畫線、矩形、圓、橢圓、多邊形、文字，這些之後都用來標示「偵測到什麼」。

**指令**

```bash
cd ~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/
python3 3_1.py   # cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
python3 3_2.py   # cv2.threshold(gray,180,255,cv2.THRESH_BINARY_INV)
python3 3_3.py   # GaussianBlur(gray,(3,3),0) + Canny(imgG,50,50)
python3 3_4.py   # cv2.line(img,(50,20),(20,100),(255,0,255),10)
python3 3_5.py   # cv2.rectangle
python3 3_6.py   # cv2.circle(img,(80,80),50,(255,0,255),10)
python3 3_7.py   # cv2.ellipse
python3 3_8.py   # cv2.polylines
python3 3_9.py   # cv2.putText(img,'This is Yahboom!',(50,50),cv2.FONT_HERSHEY_SIMPLEX,1,(0,200,0),2)
```

**注意**：顏色是 BGR 元組，`(255,0,255)` 是紫紅。官方對 `THRESH_TRUNC` 等門檻類型的中文說明有誤（複製貼上錯），要查請看 OpenCV 官方文件。`thickness=-1` 代表填滿。

#### 06-4 Open Source CV image beautification（影像修復與美化）

**觀念**：影像修復（inpaint）= 用「遮罩」標出損壞處，OpenCV 依周圍像素補起來；亮度增強 = 每像素加值並限制在 0–255；美白磨皮 = 對 B、G 通道乘 1.4 再加 5（不動 R）。

**指令**

```bash
cd ~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/
python3 4_1_1.py   # 先把圖弄「壞」並存 damaged.jpg
python3 4_1_2.py   # 建遮罩，cv2.inpaint(dam_img,paint,3,cv2.INPAINT_TELEA)
python3 4_2.py     # 亮度 +100（逐像素迴圈，會很慢）
python3 4_3.py     # 美白：bb=int(b*1.4)+5, gg=int(g*1.4)+5
```

**注意**：`4_1_2.py` 必須先跑 `4_1_1.py` 才有 `damaged.jpg`。逐像素迴圈在大圖上很慢，實務上用 numpy 向量化或 `cv2.convertScaleAbs`。`int(b)+100` 先轉 int 是為了避免 uint8 溢位（255+100 會繞回 99）。

#### 06-5 QR code creation and recognition（QR code 產生與辨識）

**觀念**：QR code 有糾錯碼，最高約 30% 毀損仍可讀；`error_correction` 有 L(7%)/M(15%)/Q/H(30%)。辨識用 `pyzbar` 解碼灰階影像，回傳內容與外框位置。

**指令**（在 **Docker 容器內**；出廠映像已裝好）

```bash
# 原始碼位置：/root/yahboomcar_ws/src/yahboomcar_visual/simple_qrcode
# 若要自行安裝（出廠已裝，通常不需要）：
python3 -m pip install qrcode pyzbar
sudo apt-get install libzbar-dev

cd /root/yahboomcar_ws/src/yahboomcar_visual/simple_qrcode/
python3 QRcode_Create.py    # 執行後依提示輸入內容（例如 yahboom）按 Enter 產生
python3 QRcode_Parsing.py   # 開攝影機，QR code 對準鏡頭，終端機印出內容並在畫面標示
```

**核心**：`qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=5, border=4)` → `add_data` → `make(fit=True)` → `make_image(fill_color="green", back_color="white")`；解碼 `pyzbar.decode(gray)` 得到 `barcode.rect`（x,y,w,h）、`barcode.data`、`barcode.type`。顯示中文用 PIL 的 `ImageDraw` + 字型檔（因為 `cv.putText` 不支援中文）。
**注意**：這課產生 QR code 的程式可選擇貼 logo（`logo_path`）。QR code 內容之後可拿來當 08-6 的「遙控指令」。

#### 06-6 AR vision（擴增實境）

**觀念**：把虛擬圖形疊在真實畫面上。AR 要算出相機姿態，所以**必須有相機內參（camera_matrix）與畸變係數**，否則不能用；每種鏡頭內參不同。

**指令**（Docker 容器內）

```bash
ros2 run yahboomcar_visual simple_AR      # 原始碼 /root/yahboomcar_ws/src/yahboomcar_visual/yahboomcar_visual/simple_AR.py
# 視窗內按 q 離開，按 f 切換效果

ros2 topic list                           # 會看到 /Graphics_topic、/simpleAR/camera
ros2 topic pub /Graphics_topic std_msgs/msg/String "data: Desk"   # 用話題切換效果
ros2 run rqt_image_view rqt_image_view    # 左上選 /simpleAR/camera 看結果影像
```

- 12 種效果：`["Triangle", "Rectangle", "Parallelogram","WindMill","TableTennisTable","Ball","Arrow", "Knife", "Desk","Bench", "Stickman", "ParallelBars"]`。
- 標定：用棋盤格標定得到 `calibrationdata.tar.gz`，解壓後把 `ost.yaml` 裡的 `camera_matrix` 與 `distortion_coefficients` 兩段 `data` 抄進 `astra.yaml`（官方說出廠映像已完成這步）。標定方法見本區 08-1。

**ROS 概念**：這課第一次出現「節點訂閱話題切換行為 + 發布影像話題」。`/Graphics_topic`（訂閱，型別 `std_msgs/msg/String`）、`/simpleAR/camera`（發布，影像）。

#### 06-7 ROS+OpenCV application（ROS 與 OpenCV 結合）

**觀念（本區最重要的一課）**：ROS 傳影像用 `sensor_msgs/Image` 訊息，OpenCV 無法直接處理；**`cv_bridge` 是兩者之間的橋**：`imgmsg_to_cv2` 把 ROS 影像訊息轉成 OpenCV 陣列，`cv2_to_imgmsg` 反向轉換。流程：攝影機節點發布 `/image_raw` → 你的節點訂閱 → 轉成 OpenCV 處理 → （可選）轉回訊息發布。

**指令**（Docker 容器內）

```bash
# 容器啟動需掛載攝影機裝置（出廠主機已設好；新主機才要自己加到啟動檔）：
#   -v /dev/video0:/dev/video0
sudo apt-get install ros-humble-usb-cam    # 出廠映像已裝，不需重裝；套件位置 /opt/ros/humble/share/usb_cam/

# 1) 啟動單目 USB 攝影機節點
ros2 run usb_cam usb_cam_node_exe
ros2 topic list
ros2 topic echo /image_raw                 # 看影像訊息（注意 encoding 欄位）

# 2) 訂閱 RGB 影像並顯示
ros2 run usb_cam usb_cam_node_exe
ros2 run yahboomcar_visual astra_rgb_image
ros2 run rqt_graph rqt_graph               # 看節點與話題關係圖

# 3) 訂閱後轉換再發布
ros2 run yahboomcar_visual pub_image
ros2 run usb_cam usb_cam_node_exe
ros2 topic echo /image
ros2 run rqt_image_view rqt_image_view     # 選 /image
```

**核心程式**（`/root/yahboomcar_ws/src/yahboomcar_visual/yahboomcar_visual/astra_rgb_image.py`、`pub_image.py`）

```python
import cv2 as cv
from cv_bridge import CvBridge
self.bridge = CvBridge()
self.sub_img = self.create_subscription(Image,'/image_raw',self.handleTopic,100)   # astra_rgb_image
frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
# pub_image.py：
self.pub_img = self.create_publisher(Image,'/image',500)
msg = self.bridge.cv2_to_imgmsg(frame, "bgr8")
self.pub_img.publish(msg)
```

**節點/話題**：`/get_astra_rgb_node` 訂閱 `/image_raw`；`pub_image` 訂閱 `/image_raw`、發布 `/image`。
**注意**

- 官方說 `/image_raw` 的 encoding 是 `rgb8`，卻同句寫「表示 yuv422」，這句互相矛盾；轉換時指定 `"bgr8"` 讓 OpenCV 顯示顏色正確，實際 encoding 以 `ros2 topic echo /image_raw` 看到的為準。
- 官方有拼字錯誤 `ros2 topoic list`，正確是 `ros2 topic list`。
- 「astra」是歷史命名（原為 Astra 深度相機），本車是 2MP USB 相機，但套件名沿用 `yahboomcar_astra`。

---

### 07. Mediapipe course

**共同觀念**（每課開頭都重複的簡介）：MediaPipe 是 Google 的開源機器學習管線框架，可在樹莓派等嵌入式平台跑，內建現成模型（手、姿勢、臉…）。使用方式：把影像（RGB）丟給 `solution.process(img_RGB)`，拿回「關鍵點（landmark）」，座標是 **0–1 的正規化比例**（`lm.x * 寬` 才是像素）。

> 本資料夾所有課的啟動指令都在 **Docker 容器內**；有 `ros2 run` 的是 ROS 2 套件節點，寫 `python3 xx.py` 的是要先 `cd` 到該資料夾直接跑。資料夾：`~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe`（絕對路徑 `/root/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe/`）。
> **檔名編號與 PDF 課號不同**：PDF 的第 6 課對應 `06_FaceLandmarks.py`，第 7 課對應 `08_Objectron.py`（沒有 07 檔），第 8 課 `09_VirtualPaint.py`，第 9 課 `10_HandCtrl.py`，第 10 課 `11_GestureRecognition.py`。
> **共同的程式細節**：多數範例設 `capture.set(6, cv.VideoWriter.fourcc('M','J','P','G'))`（MJPG 壓縮格式，提升 FPS）、解析度 640x480，畫面上顯示 FPS，按 `q` 離開。

#### 07-1 Hand detection（手部偵測）

**觀念**：MediaPipe Hands 先偵測手掌，再回歸出 **21 個 3D 關節點**。

```bash
ros2 run yahboomcar_mediapipe 01_HandDetector
```

原始碼 `.../yahboomcar_mediapipe/01_HandDetector.py`。
**核心**：`mp.solutions.hands.Hands(static_image_mode, max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5)`；每個關節轉成 `geometry_msgs/Point` 塞進自訂訊息 `yahboomcar_msgs/PointArray`，發布到話題 **`/mediapipe/points`**；畫面左右並排顯示（原圖 + 純骨架黑底圖，`frame_combine`）。
**注意**

- 範例是 `VideoCapture(4)`（攝影機索引 4），不是 0，見第 5 節。
- 範例程式碼文字內是 `import rospy`、`rospy.Publisher`（ROS 1 寫法），但指令卻是 `ros2 run`。PDF 貼的是舊版（ROS 1）原始碼，車上實際 ROS 2 版應為 rclpy，**以車上檔案為準**，不要照 PDF 抄這段。

#### 07-2 Posture detection（姿勢偵測）

**觀念**：MediaPipe Pose（BlazePose）輸出 **33 個身體關節點**。

```bash
ros2 run yahboomcar_mediapipe 02_PoseDetector
```

原始碼 `02_PoseDetector.py`。`mp.solutions.pose.Pose(static_image_mode, smooth_landmarks=True, ...)`；同樣發布 `/mediapipe/points`（`PointArray`），攝影機索引 0。

#### 07-3 Overall detection（整體偵測 Holistic）

**觀念**：一次偵測臉（468 點 FaceMesh 輪廓）、身體、左右手，等於 07-1/2/4 合體。

```bash
ros2 run yahboomcar_mediapipe 03_Holistic
```

原始碼 `03_Holistic .py`（官方檔名中間有空格）。`mp.solutions.holistic.Holistic(...)`；分別處理 `face_landmarks`、`pose_landmarks`、`left_hand_landmarks`、`right_hand_landmarks`，全部塞進同一個 `PointArray` 發布到 `/mediapipe/points`。
**注意**：在 Pi 5 上 Holistic 算量最大，FPS 會明顯較低。

#### 07-4 Face detection（臉部網格）

**觀念**：用 MediaPipe **FaceMesh** 畫出臉部輪廓關鍵點。文中另外介紹 dlib（68 點人臉標記），但本課程式實際用的是 MediaPipe 而不是 dlib。

```bash
ros2 run yahboomcar_mediapipe 04_FaceMesh
```

原始碼 `04_FaceMesh.py`。`FaceMesh(static_image_mode, max_num_faces=2, ...)`；發布 `/mediapipe/points`。

#### 07-5 Face recognition（臉與眼睛偵測）

**觀念**：這課其實是「偵測」不是「辨認身分」。用 OpenCV 的 **Haar 級聯分類器**（老派但快、不需 GPU）偵測臉與眼。

```bash
ros2 run yahboomcar_mediapipe 05_FaceEyeDetection
```

原始碼 `05_FaceEyeDetection.py`。使用 `haarcascade_eye.xml`、`haarcascade_frontalface_default.xml`；`detectMultiScale(gray, 1.3)`；鍵盤 **`f`** 在「face → eye → face_eye」三種顯示間切換、**`q`** 離開；處理後影像發布到 **`/FaceEyeDetection/image`**（`sensor_msgs/Image`，用 `cv_bridge`）。
**注意**：PDF 程式碼裡 `rospkg.RosPack().get_path("dofbot_mediapipe")`，是從機械手臂 dofbot 課程複製來的殘留，且是 ROS 1 寫法；車上實際路徑以車上檔案為準。

#### 07-6 Face effects（臉部特效／化妝）

**觀念**：用 **dlib** 的 68 點人臉標記（0–67 編號：眉毛 17–26、眼睛 36–47、嘴 48–67），把眼睛塗黑、嘴唇塗紫紅（`(249, 0, 226)`）、眉毛塗白。

```bash
cd ~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe
python3 06_FaceLandmarks.py
```

**核心**：`dlib.get_frontal_face_detector()` + `dlib.shape_predictor("./file/shape_predictor_68_face_landmarks.dat")`；`cv.fillConvexPoly` 填多邊形。
**注意**：`.dat` 路徑是相對的 `./file/`，所以**一定要先 `cd` 到該資料夾再執行**。

#### 07-7 3D object recognition（3D 物體辨識 Objectron）

**觀念**：偵測杯子、鞋子等並畫出 3D 方框與座標軸（旋轉、位移）。可辨識 4 類：`['Shoe', 'Chair', 'Cup', 'Camera']`。

```bash
cd ~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe
python3 08_Objectron.py
```

按 **`f`** 切換辨識類別（每次重建 Objectron 物件）、**`q`** 離開。
**注意**：官方明說**樹莓派需連網**才能按 `f` 切換物件（切換時會下載模型）。`min_tracking_confidence=0.99` 設得很高，追蹤不容易穩。

#### 07-8 Brush（空中畫筆）

**觀念**：用「哪幾根手指伸直」當開關：食指＋中指併攏伸直 = **選擇模式**（畫面頂端出現色彩選擇列，指尖移到顏色上就選色，黑色 = 橡皮擦）；只有食指伸直（且兩指尖距離 > 50）= **繪畫模式**。

```bash
cd ~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe
python3 09_VirtualPaint.py
```

**核心邏輯**

- `tipIds = [4, 8, 12, 16, 20]`（五指指尖的 landmark 編號）。
- `fingersUp()`：食指到小指的指尖 y 座標 **小於**（畫面上方）PIP 關節（`tipId - 2`）即為伸直；拇指改用三點夾角 > 150° 判斷。
- 畫布 `imgCanvas = np.zeros((480, 640, 3))` 與即時畫面用 `bitwise_and`/`bitwise_or` 疊合；筆粗 5、橡皮擦粗 100；顏色表 Red/Green/Blue/Yellow/Black；`detectorCon=0.85`。
**注意**：官方文字描述有些錯亂（寫成「right and middle fingers」「middle and middle fingers」），以上述程式邏輯為準。

#### 07-9 Finger control（手指控制影像特效）

**觀念**：用拇指與食指張開角度當「滑桿」，連續控制特效強度。

```bash
cd ~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe
python3 10_HandCtrl.py
```

按 **`f`** 切換效果（`["color", "thresh", "blur", "hue", "enhance"]`）、**`q`** 離開。
**核心**：`angle = calc_angle(4, 0, 8)`（拇指尖、手腕、食指尖三點夾角）→ `np.interp(angle, [0, 70], [0, 255])` 對應成 value；thresh 用它當門檻、blur 用高斯模糊 sigma、hue 加到 HSV 的 H 通道、enhance 用 CLAHE 對比增強。這裡 `np.interp` 的線性映射（輸入範圍→輸出範圍）後面控制車速也會用到同樣概念。
**注意**：該範例 `VideoCapture(4)`。

#### 07-10 Gesture recognition（手勢辨識）

**觀念**：用「哪幾根指頭伸直 + 指尖距離」的**規則式判斷**（不是神經網路）辨識 14 種手勢：`Zero, One, Two, Three, Four, Five, Six, Seven, Eight, Ok, Rock, Thumb_up, Thumb_down, Heart_single`。官方稱為右手設計。

```bash
cd ~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe
python3 11_GestureRecognition.py
```

**核心邏輯**（`get_gesture()`）：先用 `fingersUp()` 得 5 個 0/1；伸直數 0 → Zero、1 → One、5 → Five；2 根時依拇指＋小指=Six、拇指與食指夾角>90=Eight、拇指食指很近=Heart_single、否則 Two；3–4 根時拇指與食指尖比拇指與食指根部近 = OK、中指無名指都彎 = Rock；拇指尖比其他四指尖都低 = Thumb_down、都高 = Thumb_up；拇指尖與其餘四指尖距離都 < 60 = Seven。
**注意**：規則式，手角度、距離改變會誤判；按 `q` 離開。這個 `fingersUp / get_gesture` 就是 08-7、08-9 背後共用的 `media_library.py` 的來源。

---

### 08. Robot visual interaction（機器人視覺互動）

> **本資料夾所有課都是「真車課」**：需要 micro-ROS Agent 已連線、`ROS_DOMAIN_ID` 一致，雲台舵機與車輪才會動。PDF 沒有寫 micro-ROS Agent 要先啟動，只說「Connect MicroROS Agent」另有教學（本區未涵蓋，由其他組研究）。
> 第 3 課在資料夾中缺檔；無編號的 `Object recognition and tracking.txt` 在內容上補位（推測是第 3 課）。
> 共同程式位置：`/root/yahboomcar_ws/src/yahboomcar_astra/yahboomcar_astra/`（顏色、臉、巡線、QR、物體追蹤）與 `/root/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe/`（手勢相關）。

#### 08-1 Monocular camera calibration（單目相機標定）

**觀念**：鏡頭有徑向與切向畸變（直線變彎，離中心越遠越嚴重）。標定 = 拍很多張已知尺寸棋盤格，反推相機內參與畸變係數。
**準備**：9x6 內角點棋盤格（即 10x7 格），每格邊長 20 mm（`--square 0.02`，單位公尺），平整、不要有遮擋。

```bash
# Docker 容器內（出廠已安裝，不需重裝）
sudo apt install ros-humble-camera-calibration*

ros2 run usb_cam usb_cam_node_exe          # 先開相機（標定完要關掉）
ros2 run camera_calibration cameracalibrator --size 9x6 --square 0.02 --ros-args --remap /image:=/image_raw
```

**操作**：移動棋盤格（左右 X、上下 Y、遠近 Size、傾斜 Skew）直到右側四條進度條都變綠 → 按 **CALIBRATE** → 按 **SAVE**。結果存到 `/tmp/calibrationdata.tar.gz`。

```bash
sudo mv /tmp/calibrationdata.tar.gz ~
cd ~
tar -xvf calibrationdata.tar.gz            # 得到 png、ost.yaml、ost.txt

# 把標定結果換進 usb_cam 設定（PDF 原文寫的路徑是 foxy）：
sudo cp ost.yaml /opt/ros/foxy/share/usb_cam/config
cd /opt/ros/foxy/share/usb_cam/config
sudo mv camera_info.yaml camera_info_BK.yaml     # 備份原檔
sudo mv ost.yaml camera_info.yaml
```

**注意**：這段最後三個指令的路徑是 **`/opt/ros/foxy/...`**，但整套是 Humble，應為 `/opt/ros/humble/share/usb_cam/config`（06-7 說 usb_cam 位於 humble 路徑）。實作前請先 `ls /opt/ros/` 確認，不要直接照抄。

#### 08-2 Color tracking（顏色追蹤）

**觀念**：把影像轉到 **HSV 色彩空間**（H 色相、S 飽和度、V 亮度），用 HSV 範圍做遮罩找出指定顏色的色塊，算出色塊中心座標，再用 **PID 控制器**讓雲台舵機朝目標轉動，使色塊保持在畫面中央（畫面中心 = (320, 240)）。
**兩個節點分工**（原始碼 `.../yahboomcar_astra/yahboomcar_astra/colorHSV.py`、`colorTracker.py`）

- `colorHSV`：開相機、處理鍵盤/滑鼠、算色塊中心，發布 `/Current_point`。
- `colorTracker`：收座標，PID 算舵機角度，發布給底盤。

```bash
# Docker 容器內，兩個終端機（兩個節點都要開）
ros2 run yahboomcar_astra colorHSV
ros2 run yahboomcar_astra colorTracker

# 動態調 PID 參數
ros2 run rqt_reconfigure rqt_reconfigure
```

**操作**：在影像視窗按 `r`/`R` 進入選色模式，用滑鼠框出一塊**只含單一顏色**的區域 → 按 **空白鍵**進入追蹤模式 → 慢慢移動物體，雲台跟隨。其他鍵：`i`/`I` 進入 identify（辨識）模式、`q`/`Q` 離開。改完 rqt_reconfigure 參數後，點 GUI 空白處寫入。若環境光不同、選色效果不佳，需在新環境重新選色；還可即時調 HSV 高低門檻濾掉干擾色。
**話題/型別**

- 發布 `/Current_point`（自訂訊息 `Position`：欄位 `anglex`、`angley`、`distance`）。
- `colorTracker` 訂閱 `/Current_point`、`/image_raw`（`sensor_msgs/Image`）、`/JoyState`（`std_msgs/Bool`，手把狀態）。
- 發布 `/cmd_vel`（`geometry_msgs/Twist`）、`servo_s1`、`servo_s2`（`std_msgs/Int32`，雲台兩個舵機角度）。
**PID 核心**

```python
[x_Pid, y_Pid] = self.linear_pid.update([point_x - 320, point_y - 240])   # 誤差 = 目標中心 - 畫面中心
# 依 img_flip 決定 X 軸正負號，累加到舵機角度
self.PWMServo_X -= x_Pid   # (img_flip=True 時為 +=)
self.PWMServo_Y += y_Pid
# 角度限幅：X 在 -90~90，Y 在 -90~20
```

**注意**：`servo_s1`/`servo_s2` 話題名**沒有前導斜線**；雲台限位 X ±90、Y −90～20。

#### 08-3 Object recognition and tracking（物體選取追蹤；無編號檔，推測為第 3 課）

**觀念**：與顏色追蹤原理相同，但不用事先選顏色，而是**直接用滑鼠框選目標物體**後追蹤，雲台保持目標在畫面中央。

```bash
ros2 run yahboomcar_astra mono_Tracker
ros2 run rqt_reconfigure rqt_reconfigure   # 調雲台 PID，改完按 refresh
ros2 run rqt_graph rqt_graph               # 看節點/話題關係（PDF 原文只有圖）
```

**操作**：按 `r` 選取模式，框選目標 → 放開開始辨識 → 按空白鍵追蹤；`q` 離開。**物體必須慢慢移動**，太快會丟失目標。
**核心**：找最大輪廓（`cv.contourArea`、`cv.minAreaRect`、`cv.minEnclosingCircle`）取中心；框選區中心 `center_x = targEnd_x/2 + targBegin_x/2`；其餘 PID → `target_servox`/`target_servoy` → 限幅同 08-2。
**注意**：這份程式碼的 `img_flip` 兩個分支寫成完全一樣（`target_servox -= x_Pid`、`target_servoy += y_Pid`），應是官方複製貼上的小瑕疵，翻轉影像時方向可能反。

#### 08-4 Face recognition tracking（人臉追蹤）

**觀念**：用 Haar 級聯找人臉，取臉框位置當目標，其餘與顏色追蹤相同（PID + 雲台）。

```bash
ros2 run yahboomcar_astra face_fllow       # 注意官方節點名拼成 fllow，照打
ros2 run rqt_reconfigure rqt_reconfigure   # 調 PID
```

原始碼 `.../yahboomcar_astra/yahboomcar_astra/face_fllow.py`。
**核心**：

```python
face_patterns = cv2.CascadeClassifier('/root/yahboomcar_ws/src/yahboomcar_astra/yahboomcar_astra/haarcascade_frontalface_default.xml')
faces = face_patterns.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
# 臉框座標 (x,y) 丟給 self.execute(m, n)；PID 與舵機限位同 08-2
[x_Pid, y_Pid] = self.PID_controller.update([point_x - 320, point_y - 240])
```

**注意**：官方程式取的是臉框**左上角** (x,y) 而非中心，因此雲台會稍偏；且有多張臉時只用最後一張。`minSize=(100,100)` 表示臉要夠大（離鏡頭近）才會被偵測到。畫面出現綠框＋終端機印出舵機角度即成功。

#### 08-5 Autonomous driving line patrol（自動巡線）

**觀念**：選一個顏色當「線」，每幀找出線的中心 x 座標，與畫面中心 320 的偏差經 PID 轉成**角速度 z**，讓車子沿線走；安全措施：遇障礙物（用 MS200 光達）會停車並響蜂鳴器。

```bash
ros2 run yahboomcar_astra follow_line
ros2 run rqt_reconfigure rqt_reconfigure
```

**操作**：先把雲台俯仰角調低，讓相機看得到地上的線 → 在影像視窗按 `r` 進入選色 → 滑鼠框住線的區域 → 放開後右側顯示處理後影像（只剩線的部分）→ 按空白鍵開始巡線。
**可調參數**（rqt_reconfigure）：`Kp`、`Ki`、`Kd`（PID）、`scale`（PID 縮放係數）、`LaserAngle`（光達偵測角度）、`linear`（線速度）、`ResponseDist`（避障偵測距離）、`refresh`（刷新按鈕）。
**核心**

```python
rgb_img, self.hsv_range = self.color.Roi_hsv(rgb_img, self.Roi_init)
rgb_img, binary, self.circle = self.color.line_follow(rgb_img, self.hsv_range)
# circle 的半徑為 0 代表沒偵測到線 -> 發布停車
[z_Pid, _] = self.PID_controller.update([(point_x - 320)*1.0/16, 0])   # 偏差除以 16 縮小後給角速度
```

**注意**：PDF 文字說「以黃線為例」卻寫「框選藍色線區域」，前後不一致，選哪種顏色都可以，重點是框到線本身。這課用到光達話題，但 PDF 沒列出話題名稱，需看原始碼確認（本區未取得）。

#### 08-6 QR code motion control（QR code 控制車子）

**觀念**：相機看到 QR code → `pyzbar` 解出文字 → 文字當指令 → 發布速度。

```bash
ros2 run yahboomcar_astra qrTracker
# 若自行開發環境缺套件（出廠已配置）：
pip3 install pyzbar
sudo apt install libzbar-dev
```

**指令表**（QR code 內容 → 車子動作，`pub_vel(x, y, z)` 三個參數順序為官方函式簽名）：

| QR 內容 | 速度參數 | 動作 |
| --- | --- | --- |
| `forward` | `pub_vel(0.3,0.0,0.0)` | 前進 |
| `back` | `pub_vel(-0.3,0.0,0.0)` | 後退 |
| `left` | `pub_vel(0.0,0.0,1.0)` | 左轉（官方文字寫 move left） |
| `right` | `pub_vel(0.0,0.0,-1.0)` | 右轉 |
| `turnleft` | `pub_vel(0.3,0.0,0.5)` | 邊前進邊左轉 |
| `turnright` | `pub_vel(0.3,0.0,-0.5)` | 邊前進邊右轉 |
| `stop` | `pub_vel(0.0,0.0,0.0)` | 停止 |

沒偵測到 QR code 時也持續發布停止。按 `q` 關閉相機。
**注意**：`left`/`right` 的速度參數只有第三個（角速度）有值，所以其實是**原地旋轉**，不是橫移；官方文字說 move left/right 容易誤導。可用 06-5 的 `QRcode_Create.py` 自己產生這些指令的 QR code。

#### 08-7 Gesture control of basic movement of the car（手勢控制基本移動）

**觀念**：MediaPipe Hands 找出手 → `fingersUp` 判斷哪幾根伸直 → 對應方向 → 發布速度到底盤。

```bash
ros2 run yahboomcar_mediapipe HandCtrl
```

| 手勢 | 動作 |
| --- | --- |
| 手勢「5」（五指全開） | 前進 |
| 拳頭 | 後退 |
| 手勢「1」 | 左 |
| 手勢「2」 | 右 |

**核心**：

```python
from media_library import *      # 這個函式庫包含 findHands、fingersUp、get_gesture、pub_vel 等
frame, lmList, _ = self.hand_detector.findHands(frame)
fingers = self.hand_detector.fingersUp(lmList)    # 例如 fingers[1] 是食指，sum(fingers) 是伸直的指頭數
self.media_ros.pub_vel(x,y,z)    # 在 media_library.py 內
```

**注意**：與 07 課自己的 `handDetector` 類別不同，這裡的 `media_library.py` 版本 `findHands` 回傳 `(frame, lmList, bbox)`、`fingersUp` 需傳 lmList。

#### 08-8 Control the car movement with your palm（手掌位置控制移動）

**觀念**：看手掌「中心」在畫面哪個區域，決定車子往哪走（用 landmark 9 = 中指根部關節的座標）。官方提醒：**這課在車上主控跑得可能很慢**，建議先把車架高（輪子離地）測試，辨識到手掌後再放地上。

```bash
ros2 run yahboomcar_mediapipe RobotCtrl
```

- 手掌在畫面上方 → 前進；下方 → 後退；左 → 向左；右 → 向右（官方原文把右寫成 bottom，是筆誤）。

```python
fingers = self.hand_detector.fingersUp(lmList)
point_x = lmList[9][1]   # x
point_y = lmList[9][2]   # y
```

#### 08-9 Gesture control car action group（手勢觸發動作組）

**觀念**：辨識到特定手勢 → 車子完整執行一整套預設動作（走方形、轉圈、S 形…）→ 回到起點並響蜂鳴器 → 等下一個手勢。

```bash
ros2 run yahboomcar_mediapipe FingerCtrl
```

**手勢與動作**：手勢「5」停止；其餘手勢有 yes（比讚）、ok、rock（食指＋小指伸直）、contempt（握拳拇指向下）；動作有方形、原地轉圈、S 形、前進再後退。
**注意**：PDF 的對照表因排版錯亂，**哪個手勢對應哪個動作無法確定**（依文字順序推測 yes=方形、ok=轉圈、rock=S 形、拇指向下=前進後退，但不可靠）；以 `FingerCtrl.py` 原始碼為準。核心流程：`findHands → fingersUp → get_gesture → 依 gesture 執行動作`。

#### 08-10 Palm control of the two-dimensional gimbal servo（手掌控制雲台）

**觀念**：手掌在畫面中的位置控制雲台，把手掌「保持在畫面中央」。畫面中央 = 一塊**死區**，手掌在死區內不動。

```bash
ros2 run yahboomcar_mediapipe control_shape
```

**核心**（死區與限位）：

```python
point_x = lmList[9][1]
point_y = lmList[9][2]
if point_y >= 270: self.y -= 2
elif point_y <= 210: self.y += 2
if point_x >= 350: self.x -= 2
elif point_x <= 290: self.x += 2
# 限幅：x 在 -90~90，y 在 -90~20
```

即 x 在 290–350、y 在 210–270 內不動；超出才每幀轉 2 度。`angle = self.hand_detector.ThumbTOforefinger(lmList)` 算拇指與食指夾角，原本是用來控制機械手爪開合（從機械臂課程沿用，本車沒有機械手爪）。
**注意**：手要慢慢動，太快影像處理跟不上會卡頓。

---

## 3. 本區節點／話題／launch 檔總表

**本區沒有任何 launch 檔**；全部用 `ros2 run <套件> <可執行檔>` 直接起單一節點，或 `python3 xx.py` 直接跑腳本。

### 3.1 ros2 run 指令總表（均在 Docker 容器內）

| 課 | 指令 | 說明 |
| --- | --- | --- |
| 06-6 | `ros2 run yahboomcar_visual simple_AR` | AR 擴增實境，f 切效果 |
| 06-7 | `ros2 run usb_cam usb_cam_node_exe` | USB 相機驅動，發布 `/image_raw` |
| 06-7 | `ros2 run yahboomcar_visual astra_rgb_image` | 訂閱 `/image_raw` 並顯示 |
| 06-7 | `ros2 run yahboomcar_visual pub_image` | 訂閱 `/image_raw` 轉換後發布 `/image` |
| 07-1 | `ros2 run yahboomcar_mediapipe 01_HandDetector` | 手部 21 點 |
| 07-2 | `ros2 run yahboomcar_mediapipe 02_PoseDetector` | 姿勢 33 點 |
| 07-3 | `ros2 run yahboomcar_mediapipe 03_Holistic` | 臉＋身體＋雙手 |
| 07-4 | `ros2 run yahboomcar_mediapipe 04_FaceMesh` | 臉部網格 |
| 07-5 | `ros2 run yahboomcar_mediapipe 05_FaceEyeDetection` | Haar 臉與眼 |
| 08-1 | `ros2 run camera_calibration cameracalibrator --size 9x6 --square 0.02 --ros-args --remap /image:=/image_raw` | 相機標定 |
| 08-2 | `ros2 run yahboomcar_astra colorHSV` + `ros2 run yahboomcar_astra colorTracker` | 顏色追蹤（兩個一起開） |
| 08-3 | `ros2 run yahboomcar_astra mono_Tracker` | 框選物體追蹤 |
| 08-4 | `ros2 run yahboomcar_astra face_fllow` | 人臉追蹤 |
| 08-5 | `ros2 run yahboomcar_astra follow_line` | 巡線 |
| 08-6 | `ros2 run yahboomcar_astra qrTracker` | QR code 控車 |
| 08-7 | `ros2 run yahboomcar_mediapipe HandCtrl` | 手勢控制移動 |
| 08-8 | `ros2 run yahboomcar_mediapipe RobotCtrl` | 手掌位置控制移動 |
| 08-9 | `ros2 run yahboomcar_mediapipe FingerCtrl` | 手勢觸發動作組 |
| 08-10 | `ros2 run yahboomcar_mediapipe control_shape` | 手掌控制雲台 |
| 工具 | `ros2 run rqt_reconfigure rqt_reconfigure` | 動態調 PID 等參數（08-2/3/4/5） |
| 工具 | `ros2 run rqt_image_view rqt_image_view` | 看影像話題 |
| 工具 | `ros2 run rqt_graph rqt_graph` | 看節點/話題關係圖 |

### 3.2 直接 python3 執行的腳本

| 課 | 腳本 | 資料夾 |
| --- | --- | --- |
| 06-1 | `1_1.py`、`1_2.py`、`1_3.py`、`1_4.py` | `~/yahboomcar_ws/src/yahboomcar_astra/scripts/opencv/` |
| 06-2 | `2_1.py`～`2_4.py` | 同上 |
| 06-3 | `3_1.py`～`3_9.py` | 同上 |
| 06-4 | `4_1_1.py`、`4_1_2.py`、`4_2.py`、`4_3.py` | 同上 |
| 06-5 | `QRcode_Create.py`、`QRcode_Parsing.py` | `/root/yahboomcar_ws/src/yahboomcar_visual/simple_qrcode/` |
| 07-6 | `06_FaceLandmarks.py` | `~/yahboomcar_ws/src/yahboomcar_mediapipe/yahboomcar_mediapipe` |
| 07-7 | `08_Objectron.py` | 同上 |
| 07-8 | `09_VirtualPaint.py` | 同上 |
| 07-9 | `10_HandCtrl.py` | 同上 |
| 07-10 | `11_GestureRecognition.py` | 同上 |

### 3.3 話題

| 話題 | 型別 | 方向／節點 | 說明 |
| --- | --- | --- | --- |
| `/image_raw` | `sensor_msgs/Image` | `usb_cam_node_exe` 發布；`astra_rgb_image`、`pub_image`、`colorTracker`、標定程式訂閱 | 原始相機影像 |
| `/image` | `sensor_msgs/Image` | `pub_image` 發布 | 轉換後影像 |
| `/Graphics_topic` | `std_msgs/msg/String` | `simple_AR` 訂閱 | 指定 AR 效果名稱 |
| `/simpleAR/camera` | 影像 | `simple_AR` 發布 | AR 結果影像 |
| `/mediapipe/points` | `yahboomcar_msgs/PointArray`（內含 `geometry_msgs/Point`） | 01～04 發布 | 手／姿勢／臉的關鍵點 |
| `/FaceEyeDetection/image` | `sensor_msgs/Image` | `05_FaceEyeDetection` 發布 | 臉眼偵測結果影像 |
| `/Current_point` | `Position`（`anglex`,`angley`,`distance`） | `colorHSV` 發布、`colorTracker` 訂閱 | 目標中心座標 |
| `/JoyState` | `std_msgs/Bool` | `colorTracker` 訂閱 | 手把是否接管 |
| `/cmd_vel` | `geometry_msgs/Twist` | 追蹤、巡線、QR、手勢節點發布 | 車輪速度 |
| `servo_s1` | `std_msgs/Int32` | 追蹤類節點發布 | 雲台舵機 1（水平，X 軸 ±90） |
| `servo_s2` | `std_msgs/Int32` | 追蹤類節點發布 | 雲台舵機 2（俯仰，−90～20） |

### 3.4 套件與其他重要檔案

- 套件：`yahboomcar_visual`、`yahboomcar_astra`、`yahboomcar_mediapipe`、`yahboomcar_msgs`、`usb_cam`、`camera_calibration`、`rqt_*`
- 資源：`haarcascade_frontalface_default.xml`、`haarcascade_eye.xml`、`./file/shape_predictor_68_face_landmarks.dat`、`astra.yaml`（相機內參）、`camera_info.yaml`（`usb_cam` 設定）、`media_library.py`（手勢共用函式庫）

---

## 4. 沒有車也能先練嗎？

**可以，而且大部分都能先練。** 建議筆電先裝 Python + `opencv-python` + `mediapipe`，用筆電 webcam（`cv.VideoCapture(0)`）。

| 課 | 筆電 webcam 能否練習 | 說明 |
| --- | --- | --- |
| 06-1～06-4 OpenCV 基礎 | 完全可以 | 純 `opencv-python` + `numpy`，換一張自己的圖即可。不需 ROS |
| 06-5 QR code | 可以 | `pip install qrcode pyzbar`（Windows 的 pyzbar 常需另裝 zbar DLL，可改用 OpenCV 內建 `cv2.QRCodeDetector`） |
| 06-6 AR | 部分可以 | 需要相機內參；可先用 08-1 標定自己的 webcam，但 ROS 話題部分要有 ROS 2 |
| 06-7 ROS+OpenCV | 需要 ROS 2 環境 | 若筆電已有 ROS 2（例如 WSL 的 ROS 2），可用 `usb_cam` 或自己寫節點練 `cv_bridge`；Windows/WSL 的 webcam 轉進 WSL 較麻煩。也可在車上練 |
| 07-1～07-5、07-8～07-10 MediaPipe | 可以 | 去掉 `rospy`/發布 `/mediapipe/points` 的部分，只留 `process()` 與畫圖。注意 `mp.solutions` 是舊版 API，需裝支援的 mediapipe 版本 |
| 07-6 臉部特效 | 可以，但 dlib 在 Windows 安裝較麻煩 | 也需下載 `shape_predictor_68_face_landmarks.dat` |
| 07-7 Objectron | 不確定 | Objectron 為較舊的 solution，新版 mediapipe 可能已移除或不支援，未驗證 |
| 08-1 相機標定 | 部分可以 | 可用 OpenCV 的 `findChessboardCorners` + `calibrateCamera` 自己標定筆電鏡頭（概念相同，不需 ROS） |
| 08-2～08-5 顏色/物體/人臉追蹤、巡線 | 演算法可練，控制不行 | HSV 選色、輪廓、PID 計算都能在筆電做，把輸出的「舵機角度／角速度」印出或畫在畫面上即可；真正轉動雲台與車輪必須實車 |
| 08-6 QR code 控車 | 辨識可練 | 只要把 `pub_vel` 改成 `print`；進階：發布到 `turtlesim` 的 `/turtle1/cmd_vel`（需 ROS 2）用小烏龜取代車子 |
| 08-7～08-10 手勢控車、控雲台 | 手勢辨識可練 | 同上，把輸出改為 print 或操控小烏龜；雲台舵機與車速一定要實車 |

**一定要實車的部分**：micro-ROS Agent 與 ESP32 通訊、`servo_s1`/`servo_s2` 雲台轉動、`/cmd_vel` 讓車輪動、MS200 光達避障（巡線）、車載相機實際視野與 HSV 在真實光線下的調校、蜂鳴器、Pi 5 上的實際 FPS/延遲、`rqt_reconfigure` 調 PID 的體感。

**建議學習順序**：先在筆電練會 06-1～06-5、07 全部、08 的 HSV/PID 邏輯；上車後再專注在 ROS 話題、`ROS_DOMAIN_ID`、Docker 與硬體問題，這樣除錯範圍小很多。

---

## 5. 初學者最容易卡住的 5 個地方

1. **GUI 視窗跑不出來**：所有範例都用 `cv.imshow`／`rqt_*`，卻在 Docker 容器內執行。純 SSH 看不到視窗；必須在 Pi 的桌面（螢幕＋鍵鼠、VNC）下操作，容器還要有 X11 顯示轉發設定。PDF 沒有講這件事，屬於前提被省略。
2. **攝影機編號與裝置**：範例有的 `VideoCapture(0)`、有的 `VideoCapture(4)`（07-1、07-9），容器要掛載 `-v /dev/video0:/dev/video0`，而且 ROS 的 `usb_cam` 與你自己的 `cv.VideoCapture` **不能同時搶同一支相機**。畫面全黑或 `ret` 為 False，先用 `ls /dev/video*` 確認編號，並確認沒有別的節點占用相機。
3. **`ROS_DOMAIN_ID` 不一致或 micro-ROS Agent 沒連線**：08 資料夾每課開頭都警告。症狀是程式看起來正常（有畫面、終端機有印角度），但雲台與車輪完全不動。這時先用 `ros2 topic list`／`ros2 topic echo servo_s1` 確認話題有沒有被控制板收到。
4. **官方文件自己前後矛盾，照抄會出錯**：PDF 的範例程式碼是 `rospy`（ROS 1）卻用 `ros2 run`；標定儲存路徑寫 `/opt/ros/foxy/...` 而系統是 humble；檔名編號與課號不對（07 的 06、08…）；節點名 `face_fllow` 拼錯但必須照打；`img.release()` 對圖片陣列會報錯；`./file/` 相對路徑需先 `cd`。遇到問題先檢查車上實際檔案，不要全信 PDF。
5. **選色／追蹤的操作順序與環境光**：顏色追蹤、巡線都要先在視窗按 `r`、用滑鼠框出「單一顏色」區域、**再按空白鍵**才開始追蹤，少一步車子都不會動。框到雜色、環境光改變或移動太快都會丟失目標。巡線還要記得先把雲台俯仰調低，讓相機看到地上的線。另外 PID 參數（`Kp/Ki/Kd`）改完要在 GUI 空白處點一下或按 refresh 才會寫入。

---

## 附：本次閱讀發現的缺漏

- 08 資料夾缺第 3 課檔案（編號 2 之後直接是 4）；`Object recognition and tracking.txt` 無編號，內容推測為第 3 課。
- `media_library.py`、`colorHSV.py` 全文、光達話題名稱、自訂訊息 `Position`／`PointArray` 的完整定義，PDF 都只有節錄或完全沒有，需從車上原始碼取得。
- 並未說明如何啟動 micro-ROS Agent（屬其他組範圍）。
