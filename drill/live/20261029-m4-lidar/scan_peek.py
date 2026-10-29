"""讀一筆 /scan，用「角度 = angle_min + angle_increment × i」算出八個方向的距離（M4 演練第 1 步）"""
import math
import sys

TARGETS = [0, 45, 90, 135, 180, -135, -90, -45]
NAMES = {0: "正前方", 45: "左前", 90: "正左", 135: "左後", 180: "正後方",
         -135: "右後", -90: "正右", -45: "右前"}


def index_of(angle_deg, angle_min, angle_inc, count):
    """把角度（度）換成 ranges 的格數，超出一圈就繞回來"""
    i = round((math.radians(angle_deg) - angle_min) / angle_inc)
    return i % count


def nearest_valid(ranges, i, rmin, rmax, half=2):
    """取該格前後各 2 格裡的最小有效值；0、inf、nan 都當無效（單點容易是雜訊）"""
    vals = [ranges[(i + k) % len(ranges)] for k in range(-half, half + 1)]
    good = [v for v in vals if math.isfinite(v) and rmin <= v <= rmax]
    return min(good) if good else None


def main():
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan

    rclpy.init()
    node = Node("scan_peek")
    box = {}
    node.create_subscription(LaserScan, "/scan", lambda m: box.setdefault("m", m), 1)
    for _ in range(50):
        rclpy.spin_once(node, timeout_sec=0.2)
        if "m" in box:
            break
    if "m" not in box:
        print("錯誤：5 秒內沒收到 /scan", file=sys.stderr)
        sys.exit(1)
    m = box["m"]
    n = len(m.ranges)
    print(f"點數 {n}，angle_min {math.degrees(m.angle_min):.0f}°，每格 {math.degrees(m.angle_increment):.1f}°")
    for deg in TARGETS:
        i = index_of(deg, m.angle_min, m.angle_increment, n)
        d = nearest_valid(m.ranges, i, m.range_min, m.range_max)
        txt = f"{d:.2f} m" if d is not None else "無有效值"
        print(f"{NAMES[deg]:<4} {deg:>5}°  第 {i:>3} 格  {txt}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        assert index_of(0, -math.pi, math.radians(1), 360) == 180
        assert index_of(-90, -math.pi, math.radians(1), 360) == 90
        assert index_of(180, -math.pi, math.radians(1), 360) == 0
        assert nearest_valid([0.0, float("inf"), 0.5, 0.4, float("nan")], 2, 0.12, 8.0) == 0.4
        assert nearest_valid([0.0] * 5, 2, 0.12, 8.0) is None
        print("selftest OK")
    else:
        main()
