"""
main.py —— 主程序入口

当前阶段: 只做"环境自检", 确认 Python / OpenCV / NumPy / Matplotlib
能不能正常导入, 并打印出版本号。

这样做的目的:
    在你写任何检测算法之前, 先确认环境是好的。
    如果这一步就报错, 说明是环境问题, 不是你的代码问题。

运行方式:
    在 VS Code 里直接按 F5
    或者在终端里执行:  .venv\\Scripts\\python.exe src\\main.py
"""

import sys
import platform


def check_environment() -> bool:
    """检查环境是否正常。全部通过返回 True, 有失败返回 False。"""

    print("=" * 58)
    print(" camera-quality-diagnostics  --  环境自检")
    print("=" * 58)
    print()

    # ---------- 1. Python 本身 ----------
    print("[1] Python")
    print(f"    版本      : {sys.version.split()[0]}")
    print(f"    解释器路径: {sys.executable}")
    print(f"    操作系统  : {platform.system()} {platform.release()}")

    # 判断当前用的是不是项目里的 .venv
    # sys.prefix 是"当前环境"的根目录, sys.base_prefix 是"最底层 Python"的根目录
    # 两者不同 => 说明正在虚拟环境里
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print("    虚拟环境  : 是 (正在使用项目 .venv, 正确)")
    else:
        print("    虚拟环境  : 否  <-- 警告: 正在使用全局 Python!")
        print("                请检查 VS Code 右下角是否选的是 .venv")
    print()

    ok = True

    # ---------- 2. OpenCV ----------
    print("[2] OpenCV (opencv-python)")
    try:
        import cv2
        print(f"    版本      : {cv2.__version__}")
        print(f"    安装位置  : {cv2.__file__}")
    except ImportError as e:
        print(f"    导入失败  : {e}")
        print("    解决办法  : .venv\\Scripts\\python.exe -m pip install opencv-python")
        ok = False
    print()

    # ---------- 3. NumPy ----------
    print("[3] NumPy")
    try:
        import numpy as np
        print(f"    版本      : {np.__version__}")
        arr = np.array([1, 2, 3])
        print(f"    简单测试  : np.array([1,2,3]).sum() = {arr.sum()}")
    except ImportError as e:
        print(f"    导入失败  : {e}")
        print("    解决办法  : .venv\\Scripts\\python.exe -m pip install numpy")
        ok = False
    print()

    # ---------- 4. Matplotlib ----------
    print("[4] Matplotlib")
    try:
        import matplotlib
        print(f"    版本      : {matplotlib.__version__}")
    except ImportError as e:
        print(f"    导入失败  : {e}")
        print("    解决办法  : .venv\\Scripts\\python.exe -m pip install matplotlib")
        ok = False
    print()

    # ---------- 5. 摄像头检测(只探测, 不打开画面) ----------
    print("[5] 摄像头探测")
    try:
        import cv2
        # CAP_DSHOW 是 Windows 上的 DirectShow 后端, 在 Windows 上比默认后端更稳
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"    检测到摄像头, 分辨率 {w} x {h}")
            print("    提示: 想看实时画面, 请运行 src/camera_test.py")
        else:
            print("    没有检测到 0 号摄像头 (或已被其他程序占用)")
            print("    这属于硬件条件, 不影响环境本身的正确性")
        cap.release()
    except Exception as e:
        print(f"    探测时出错: {e}")
        print("    这属于硬件条件, 不影响环境本身的正确性")
    print()

    # ---------- 总结 ----------
    print("=" * 58)
    if ok:
        print(" 结果: 环境自检通过, 可以开始开发了")
    else:
        print(" 结果: 有组件导入失败, 请按上面的提示处理")
    print("=" * 58)

    return ok


def main() -> int:
    """程序入口。返回 0 表示成功, 1 表示失败。"""
    try:
        success = check_environment()
        return 0 if success else 1
    except Exception as e:
        print(f"程序运行出错: {e}")
        return 1


if __name__ == "__main__":
    # sys.exit 会把返回值当作"退出码"传给操作系统
    # 0 = 成功, 非 0 = 失败。VS Code 调试时能看到这个退出码。
    sys.exit(main())
