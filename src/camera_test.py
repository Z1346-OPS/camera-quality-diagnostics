"""
camera_test.py —— USB 摄像头连通性测试

作用: 打开 0 号摄像头, 显示实时画面, 用来确认摄像头能不能正常工作。

运行方式:
    在 VS Code 里按 F5 后选 "调试摄像头测试 (src/camera_test.py)"
    或者终端执行:  .venv\\Scripts\\python.exe src\\camera_test.py

退出方式:
    画面窗口出现后, 按键盘上的 q 键即可正常退出。
    (不要直接点窗口右上角的 X —— 那样虽然也能关, 但优雅退出更规范)
"""

import sys
import time
from uuid import uuid4

import cv2

if __package__:
    from .metrics import (
        calculate_bgr_means,
        calculate_contrast,
        calculate_exposure_ratios,
        calculate_grayscale_histogram,
        calculate_mean_brightness,
        calculate_sharpness,
    )
    from .report import append_camera_event, append_color_record, append_quality_record
else:
    from metrics import (
        calculate_bgr_means,
        calculate_contrast,
        calculate_exposure_ratios,
        calculate_grayscale_histogram,
        calculate_mean_brightness,
        calculate_sharpness,
    )
    from report import append_camera_event, append_color_record, append_quality_record

# ---------------- 可调参数 ----------------
CAMERA_INDEX = 0        # 0 号摄像头。如果有多个摄像头, 可以试 1、2
WINDOW_NAME = "Camera Test - press s to save, q to quit"
DARK_THRESHOLD = 30     # 灰度值小于等于它, 暂时视为欠曝像素
BRIGHT_THRESHOLD = 225  # 灰度值大于等于它, 暂时视为过曝像素
SCENE_KEYS = {
    ord("0"): "unspecified",
    ord("1"): "white_paper",
    ord("2"): "colored_object",
    ord("3"): "white_restored",
}

# 最多尝试打开几次。设成 3 而不是"一直重试",
# 是为了在摄像头有问题时快速失败, 而不是卡死在这里。
MAX_OPEN_ATTEMPTS = 3

# 两次尝试之间等待多少秒
RETRY_DELAY_SECONDS = 1.0


def open_camera():
    """
    尝试打开摄像头。

    返回: 打开成功的 VideoCapture 对象; 全部失败则返回 None。

    为什么优先用 CAP_DSHOW?
        Windows 上 OpenCV 默认的摄像头后端有时打开很慢或直接失败。
        CAP_DSHOW 是 Windows 自带的 DirectShow, 通常更稳定、更快。
    """
    # 优先用 DSHOW 后端 (Windows 推荐)
    backends = [
        (cv2.CAP_DSHOW, "CAP_DSHOW (Windows DirectShow, 推荐)"),
        (cv2.CAP_ANY, "CAP_ANY (OpenCV 自动选择, 备用)"),
    ]

    for backend, backend_name in backends:
        for attempt in range(1, MAX_OPEN_ATTEMPTS + 1):
            print(f"  尝试用 {backend_name} 打开 {CAMERA_INDEX} 号摄像头"
                  f" (第 {attempt}/{MAX_OPEN_ATTEMPTS} 次) ...")

            cap = cv2.VideoCapture(CAMERA_INDEX, backend)

            if cap.isOpened():
                # 再多读一帧, 确认是真的能出画面, 而不只是"打开了"
                ok, frame = cap.read()
                if ok and frame is not None:
                    print(f"  成功! 画面尺寸: {frame.shape[1]} x {frame.shape[0]}")
                    return cap
                print("    摄像头打开了, 但读不到画面, 换一种方式再试")
                cap.release()
            else:
                print("    打不开")
                cap.release()

            if attempt < MAX_OPEN_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    return None


def main() -> int:
    print("=" * 58)
    print(" 摄像头测试")
    print("=" * 58)
    print()

    cap = None
    try:
        cap = open_camera()

        if cap is None:
            # 打不开就给出清晰提示, 然后正常退出。
            # 注意: 这里返回 2, 表示"环境没问题, 但没有摄像头"。
            print()
            print("-" * 58)
            print(" 没有成功打开摄像头。可能的原因:")
            print("   1. 电脑没有接摄像头")
            print("   2. 摄像头被别的程序占用了")
            print("      (常见占用者: 相机应用、腾讯会议、钉钉、Zoom、浏览器网页)")
            print("   3. 摄像头编号不是 0")
            print("      可以把这个文件里的 CAMERA_INDEX 改成 1 或 2 再试")
            print("   4. 摄像头驱动没装好 (去设备管理器看看有没有黄色感叹号)")
            print()
            print(" 这属于硬件条件问题, 不代表 Python 环境有问题。")
            print("-" * 58)
            return 2

        print()
        print("-" * 58)
        print(" 画面窗口已打开。按 s 保存当前指标，按 q 退出。")
        print(" 场景标签：0 未指定，1 白纸，2 彩色物体，3 恢复白纸。")
        print("-" * 58)
        print()

        # ---------- 主循环: 不断读帧并显示 ----------
        frame_count = 0
        scene_label = "unspecified"
        run_id = uuid4().hex
        print(f"本次运行批次 run_id: {run_id}")
        while True:
            ok, frame = cap.read()
            if not ok:
                message = "读取画面失败，可能是摄像头被拔掉了。"
                print(message)
                event_path = append_camera_event(
                    frame_count,
                    "read_failed",
                    message,
                )
                print(f"失败事件已记录: {event_path}")
                break

            frame_count += 1
            blue_mean, green_mean, red_mean = calculate_bgr_means(frame)
            channel_spread = max(blue_mean, green_mean, red_mean) - min(
                blue_mean, green_mean, red_mean
            )
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = calculate_mean_brightness(gray_frame)
            contrast = calculate_contrast(gray_frame)
            histogram = calculate_grayscale_histogram(gray_frame)
            histogram_peak = int(histogram.argmax())
            histogram_peak_count = int(histogram[histogram_peak])
            sharpness = calculate_sharpness(gray_frame)
            dark_ratio, bright_ratio = calculate_exposure_ratios(
                gray_frame,
                DARK_THRESHOLD,
                BRIGHT_THRESHOLD,
            )

            # 显示帧计数和平均亮度, 方便观察画面是否持续变化
            cv2.putText(
                frame,
                f"frame: {frame_count}  brightness: {brightness:.1f}",
                (10, 30),                      # 文字左下角坐标
                cv2.FONT_HERSHEY_SIMPLEX,      # 字体
                1.0,                           # 字号
                (0, 255, 0),                   # 颜色 (B, G, R) = 绿色
                2,                             # 线宽
            )
            cv2.putText(
                frame,
                f"dark: {dark_ratio:.1f}%  bright: {bright_ratio:.1f}%",
                (10, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )
            cv2.putText(
                frame,
                f"sharpness: {sharpness:.1f}",
                (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2,
            )
            cv2.putText(
                frame,
                f"contrast: {contrast:.1f}",
                (10, 135),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 0, 255),
                2,
            )
            cv2.putText(
                frame,
                f"hist peak: {histogram_peak}  count: {histogram_peak_count}",
                (10, 170),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 165, 255),
                2,
            )
            cv2.putText(
                frame,
                f"B: {blue_mean:.1f} G: {green_mean:.1f} R: {red_mean:.1f} spread: {channel_spread:.1f}",
                (10, 205),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )

            cv2.putText(
                frame, f"scene: {scene_label} (0/1/2/3)", (10, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
            )
            cv2.imshow(WINDOW_NAME, frame)

            # waitKey(1) = 等 1 毫秒, 同时读取键盘。
            # 返回的是按下键的 ASCII 码; 没按键时返回 -1。
            key = cv2.waitKey(1) & 0xFF
            if key in SCENE_KEYS:
                scene_label = SCENE_KEYS[key]
                print(f"当前场景标签: {scene_label}")

            if key == ord("s"):
                report_path = append_quality_record(
                    frame_count,
                    brightness,
                    dark_ratio,
                    bright_ratio,
                    sharpness,
                    contrast,
                )
                print(f"已保存当前帧指标: {report_path}")
                color_path = append_color_record(
                    frame_count, blue_mean, green_mean, red_mean,
                    scene_label=scene_label,
                    run_id=run_id,
                )
                print(f"已保存当前帧颜色数据 [{scene_label}]: {color_path}")

            if key == ord("q"):
                print(f"你按了 q, 正常退出。共显示 {frame_count} 帧。")
                break

            # 窗口被点了右上角的 X 时, 这个判断能防止程序卡住
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                print("窗口被关闭, 退出。")
                break

        return 0

    except KeyboardInterrupt:
        # 在终端里按了 Ctrl+C
        print("\n收到 Ctrl+C, 退出。")
        return 0

    except Exception as e:
        print(f"出错了: {e}")
        return 1

    finally:
        # ============================================================
        # finally 里的代码 "无论上面发生了什么都会执行"
        # 用它来释放摄像头和关闭窗口, 保证不会留下"被占用的摄像头"
        # ============================================================
        if cap is not None:
            cap.release()
            print("已释放摄像头。")
        cv2.destroyAllWindows()
        print("已关闭所有 OpenCV 窗口。")


if __name__ == "__main__":
    sys.exit(main())
