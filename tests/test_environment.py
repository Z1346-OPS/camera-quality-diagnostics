"""
test_environment.py —— 环境测试

作用: 用 pytest 自动检查 Python / OpenCV / NumPy 能否正常导入和工作。

这些测试的意义:
    "能导入" 是最基本的要求。以后你每次改动环境(比如装了新包),
    跑一遍这个文件, 就能立刻知道环境有没有被搞坏。

运行方式:
    方法一: 在 VS Code 左侧点 "测试" 图标 (烧瓶形状), 然后点运行
    方法二: 终端里执行 (在项目根目录):
            .venv\\Scripts\\python.exe -m pytest
"""

import sys

import numpy as np
import pytest


# ============================================================
#  Python 本身
# ============================================================

def test_python_version():
    """确认 Python 是 3.12.x"""
    major, minor = sys.version_info[:2]
    assert major == 3, f"主版本应该是 3, 实际是 {major}"
    assert minor == 12, f"次版本应该是 12, 实际是 {minor}"


def test_running_in_virtual_environment():
    """
    确认测试跑在项目 .venv 里, 而不是全局 Python。
    如果这条失败, 说明 VS Code 或终端选错了解释器。
    """
    assert sys.prefix != sys.base_prefix, (
        "当前不在虚拟环境里! 请确认用的是 "
        ".venv\\Scripts\\python.exe 而不是全局 Python"
    )


# ============================================================
#  NumPy
# ============================================================

def test_numpy_importable():
    """NumPy 能导入, 且版本合理"""
    assert np.__version__ is not None
    # 版本号形如 "2.5.3", 至少要有两段
    assert len(np.__version__.split(".")) >= 2


def test_numpy_basic_math():
    """NumPy 的加法确实是对的 (防止装了个假包)"""
    a = np.array([1, 2, 3])
    b = np.array([10, 20, 30])
    result = a + b
    assert list(result) == [11, 22, 33]


def test_numpy_uint8_image_dtype():
    """
    图像在 OpenCV 里就是 uint8 的数组。
    这里确认 uint8 的溢出行为符合预期 (255 + 1 会绕回 0),
    这是理解图像处理的一个关键点 —— 也是初学者最常踩的坑:
    两张图直接相加, 很可能因为溢出而"变黑"而不是"变亮"。
    """
    # 用 dtype=np.uint8 构造数组来演示溢出, 而不是对标量做加法。
    # 原因: NumPy 2.x 对标量 uint8 溢出会发 RuntimeWarning,
    #       而数组运算不会 —— 行为一样, 但不刷警告。
    v = np.array([255], dtype=np.uint8)
    assert (v + 1)[0] == 0, "uint8 数组的 255 + 1 应该绕回 0"


# ============================================================
#  OpenCV
# ============================================================

def test_opencv_importable():
    """OpenCV 能导入, 且版本非空"""
    cv2 = pytest.importorskip("cv2", reason="opencv-python 未安装")
    assert cv2.__version__


def test_opencv_can_create_image():
    """能创建一张图像 (黑图)"""
    cv2 = pytest.importorskip("cv2")
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    assert img.shape == (100, 200, 3)
    assert img.sum() == 0, "全黑图的像素和应该是 0"


def test_opencv_grayscale_conversion():
    """
    彩色图转灰度图应该得到单通道图, 且尺寸不变。
    这是图像质量检测最基础的操作之一。
    """
    cv2 = pytest.importorskip("cv2")

    # 造一张 50x80 的纯蓝色图 (BGR 里蓝色在第一个通道)
    color = np.zeros((50, 80, 3), dtype=np.uint8)
    color[:, :, 0] = 255

    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)

    assert gray.shape == (50, 80), f"灰度图应该是 2 维, 实际 {gray.shape}"
    # 纯蓝 (0,0,255) 转灰度约等于 29
    assert 20 < gray[0, 0] < 40, f"纯蓝的灰度值应该是 29 左右, 实际 {gray[0, 0]}"


def test_opencv_blur_reduces_noise():
    """高斯模糊应该让图像的"变化剧烈程度"下降"""
    cv2 = pytest.importorskip("cv2")

    # 造一张黑白棋盘格 = 高频噪声
    checker = np.zeros((60, 60), dtype=np.uint8)
    checker[::2, ::2] = 255
    checker[1::2, 1::2] = 255

    blurred = cv2.GaussianBlur(checker, (7, 7), 0)

    # 用标准差衡量"变化剧烈程度"
    assert blurred.std() < checker.std(), "模糊之后标准差应该变小"


# ============================================================
#  Matplotlib
# ============================================================

def test_matplotlib_importable():
    """Matplotlib 能导入"""
    matplotlib = pytest.importorskip("matplotlib", reason="matplotlib 未安装")
    assert matplotlib.__version__


def test_matplotlib_has_backend():
    """
    确认 Matplotlib 有可用的绘图后端。
    没有后端的话, 画图时会直接报错。
    """
    matplotlib = pytest.importorskip("matplotlib")
    # Agg 是无需界面的后端, 一定能用; 这里只是确认后端机制正常
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    fig = plt.figure()
    assert fig is not None
    plt.close(fig)
