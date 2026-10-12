"""Analyze one local JPEG/PNG without changing its original bytes."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import subprocess
from time import perf_counter
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError, __version__ as pillow_version

if __package__:
    from .analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from .metrics import (
        calculate_bgr_means, calculate_contrast, calculate_exposure_ratios,
        calculate_grayscale_histogram, calculate_mean_brightness,
        calculate_sharpness,
    )
else:
    from analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from metrics import (
        calculate_bgr_means, calculate_contrast, calculate_exposure_ratios,
        calculate_grayscale_histogram, calculate_mean_brightness,
        calculate_sharpness,
    )


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 16_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG"}
SUPPORTED_MODES = {"RGB", "RGBA", "L", "LA", "P"}


class AnalysisError(ValueError):
    """A failed analysis with a stable, machine-readable reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _provenance(source_names=None) -> dict:
    root = Path(__file__).resolve().parents[1]
    sources = {}
    for name in source_names or ("analyze_image.py", "analysis_config.py", "metrics.py"):
        try:
            sources[name] = sha256((root / "src" / name).read_bytes()).hexdigest()
        except OSError:
            sources[name] = None
    git_info = {"commit": None, "working_tree_dirty": None, "status": "unavailable"}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=2, check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=2, check=False,
        )
        if commit.returncode == 0 and status.returncode == 0:
            git_info = {"commit": commit.stdout.strip(),
                        "working_tree_dirty": bool(status.stdout.strip()),
                        "status": "available"}
    except (OSError, subprocess.TimeoutExpired) as error:
        git_info["unavailable_reason"] = type(error).__name__
    return {
        "implementation_version": "local-image-analysis-4",
        "source_sha256": sources, "git": git_info,
        "runtime": {"python": sys.version.split()[0], "opencv": cv2.__version__,
                    "numpy": np.__version__, "pillow": pillow_version},
    }


def load_normalized_image(path: Path) -> tuple[np.ndarray, dict]:
    """Read once, validate, normalize; return uint8 BGR and source metadata."""
    source = Path(path)
    try:
        with source.open("rb") as stream:
            contents = stream.read(MAX_FILE_BYTES + 1)
    except PermissionError as error:
        raise AnalysisError("input_access_denied", "没有读取图片的权限") from error
    except FileNotFoundError as error:
        raise AnalysisError("input_not_found", "图片文件不存在") from error
    except OSError as error:
        raise AnalysisError("input_read_failed", "无法读取图片文件") from error
    if len(contents) > MAX_FILE_BYTES:
        raise AnalysisError("file_limit_exceeded", f"图片文件超过 {MAX_FILE_BYTES} 字节限制")
    try:
        with Image.open(BytesIO(contents)) as image:
            image_format = image.format
            if image_format not in SUPPORTED_FORMATS:
                raise AnalysisError("unsupported_format", f"不支持的图片格式: {image_format}；仅支持 JPEG/PNG")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise AnalysisError("pixel_limit_exceeded", f"图片像素超过 {MAX_PIXELS} 限制或尺寸无效")
            if getattr(image, "n_frames", 1) != 1:
                raise AnalysisError("unsupported_animation", "不支持动画图片；请提供单帧 JPEG/PNG")
            original_mode = image.mode
            if original_mode not in SUPPORTED_MODES:
                raise AnalysisError("unsupported_mode", f"不支持的图像模式/数据类型: {original_mode}；仅支持 8 位通道")
            orientation = image.getexif().get(274, 1)
            if orientation not in range(0, 9):
                raise AnalysisError("invalid_orientation", f"无效的 EXIF 方向值: {orientation}")
            image.load()
            # Zero gives no reliable direction; preserve the stored pixel order.
            upright = image.copy() if orientation == 0 else ImageOps.exif_transpose(image)
            has_alpha = original_mode in {"RGBA", "LA"} or (
                original_mode == "P" and "transparency" in image.info
            )
            if has_alpha:
                rgba = upright.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                conversion = "alpha_over_white_then_RGB_to_BGR"
            else:
                rgb = upright.convert("RGB")
                conversion = "RGB_to_BGR" if original_mode == "RGB" else f"{original_mode}_to_RGB_to_BGR"
            bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
            rgb.close()
            upright.close()
    except Image.DecompressionBombError as error:
        raise AnalysisError("pixel_limit_exceeded", "图片像素超过解码安全限制") from error
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise AnalysisError("corrupt_image", "图片损坏或无法解码为 JPEG/PNG") from error

    return bgr, {
        "warnings": ([{
            "code": "exif_orientation_unspecified",
            "message": "EXIF 方向值为 0，未执行方向变换；请人工核对显示方向",
        }] if orientation == 0 else []),
        "source": {
            "path": str(source), "format": image_format,
            "bytes": len(contents), "sha256": sha256(contents).hexdigest(),
            "width": width, "height": height, "mode": original_mode,
        },
        "preprocessing": {
            "exif_orientation": orientation, "exif_transposed": orientation in range(2, 9),
            "exif_orientation_handling": (
                "unspecified_preserve_pixel_order" if orientation == 0
                else "apply_exif_orientation"
            ),
            "channel_conversion": conversion, "dtype": "uint8",
            "analysis_color_order": "BGR", "analysis_width": bgr.shape[1],
            "analysis_height": bgr.shape[0], "region": "full_image",
            "color_profile_conversion": "none",
        },
    }


def calculate_image_metrics(bgr: np.ndarray) -> dict:
    """Reuse the camera metrics on a normalized full image or ROI."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    histogram = calculate_grayscale_histogram(gray)
    peak = int(histogram.argmax())
    dark_ratio, bright_ratio = calculate_exposure_ratios(
        gray, DARK_THRESHOLD, BRIGHT_THRESHOLD
    )
    blue, green, red = calculate_bgr_means(bgr)
    return {
        "brightness": calculate_mean_brightness(gray),
        "dark_ratio_percent": dark_ratio,
        "bright_ratio_percent": bright_ratio,
        "sharpness": calculate_sharpness(gray),
        "contrast": calculate_contrast(gray),
        "histogram_peak": peak,
        "histogram_peak_count": int(histogram[peak]),
        "bgr_means": {"blue": blue, "green": green, "red": red},
    }


def image_analysis_config() -> dict:
    return {
        "dark_threshold_inclusive": DARK_THRESHOLD,
        "bright_threshold_inclusive": BRIGHT_THRESHOLD,
        "sharpness": "variance_of_grayscale_laplacian",
        "contrast": "grayscale_standard_deviation",
        "max_file_bytes": MAX_FILE_BYTES, "max_pixels": MAX_PIXELS,
        "supported_formats": sorted(SUPPORTED_FORMATS),
        "supported_modes": sorted(SUPPORTED_MODES),
        "alpha_background_rgb": [255, 255, 255],
        "resize": "none", "color_profile_conversion": "none",
        "exif_orientation_policy": "apply_1_to_8;zero_no_transform_with_warning;reject_other",
    }


def analyze_image(path: Path) -> dict:
    """Return JSON-compatible metrics and the exact preprocessing used."""
    started = perf_counter()
    bgr, metadata = load_normalized_image(path)
    config = image_analysis_config()
    metrics = calculate_image_metrics(bgr)
    return {
        "schema_version": 2, "status": "completed", "analysis_id": uuid4().hex,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "analysis_duration_seconds": perf_counter() - started,
        "provenance": _provenance(),
        "config_sha256": sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest(),
        **metadata, "analysis_config": config, "metrics": metrics,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="只读分析本地 JPEG/PNG 图片")
    parser.add_argument("image", type=Path, help="本地图片路径")
    parser.add_argument("--output", type=Path, help="独占新建 JSON 结果文件；已存在时拒绝覆盖")
    args = parser.parse_args(argv)
    try:
        result = analyze_image(args.image)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
    except (AnalysisError, OSError, ValueError, cv2.error, MemoryError) as error:
        if isinstance(error, AnalysisError):
            code = error.code
        elif isinstance(error, FileExistsError):
            code = "output_exists"
        elif isinstance(error, PermissionError):
            code = "output_access_denied"
        elif isinstance(error, OSError):
            code = "output_write_failed"
        elif isinstance(error, MemoryError):
            code = "resource_exhausted"
        else:
            code = "analysis_failed"
        print(f"分析失败 [{code}]: {error}", file=sys.stderr)
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
