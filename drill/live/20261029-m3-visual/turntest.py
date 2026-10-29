# 診斷：原地轉 0.5 rad/s，連續送 vs 像 HandCtrl 一下一下送，比較 odom 量到的角速度
import time
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
rclpy.init()
n = rclpy.create_node("turntest")
pub = n.create_publisher(Twist, "/cmd_vel_raw", 10)
state = {"z": None}
n.create_subscription(Odometry, "/odom_raw", lambda m: state.update(z=m.twist.twist.angular.z), 10)
def run(label, on, off, total):
    zs = []
    t0 = time.time()
    while time.time() - t0 < total:
        t1 = time.time()
        while time.time() - t1 < on:
            m = Twist(); m.angular.z = 0.5; pub.publish(m)
            rclpy.spin_once(n, timeout_sec=0.05)
            if state["z"] is not None: zs.append(abs(state["z"]))
        t2 = time.time()
        while time.time() - t2 < off:
            rclpy.spin_once(n, timeout_sec=0.05)
            if state["z"] is not None: zs.append(abs(state["z"]))
    for _ in range(5):
        pub.publish(Twist()); time.sleep(0.05)
    if zs: print(label, "odom 角速度 最大 %.2f 平均 %.2f rad/s（%d 筆）" % (max(zs), sum(zs)/len(zs), len(zs)), flush=True)
    else: print(label, "沒收到 odom", flush=True)
    time.sleep(1.5)
try:
    pass
    run("B 送一筆停 0.7 秒 共 3 秒", 0.05, 0.7, 3.0)
finally:
    for _ in range(5):
        pub.publish(Twist()); time.sleep(0.05)
    n.destroy_node(); rclpy.shutdown()
