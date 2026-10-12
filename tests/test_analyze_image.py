"""Local image input and preprocessing tests use generated files only."""

from hashlib import sha256
import json

import numpy as np
from PIL import Image
import pytest

from src import analyze_image as module


def test_rgb_png_uses_existing_bgr_metrics_and_preserves_original(tmp_path):
    source = tmp_path / "color.png"
    Image.new("RGB", (3, 2), (30, 20, 10)).save(source)
    original = source.read_bytes()

    result = module.analyze_image(source)

    assert source.read_bytes() == original
    assert result["source"]["sha256"] == sha256(original).hexdigest()
    assert result["source"]["format"] == "PNG"
    assert result["preprocessing"]["dtype"] == "uint8"
    assert result["preprocessing"]["channel_conversion"] == "RGB_to_BGR"
    assert result["metrics"]["bgr_means"] == {
        "blue": 10.0, "green": 20.0, "red": 30.0,
    }
    assert result["metrics"]["histogram_peak_count"] == 6
    assert result["analysis_config"]["dark_threshold_inclusive"] == 30
    assert result["analysis_config"]["bright_threshold_inclusive"] == 225


def test_jpeg_exif_orientation_is_applied_before_analysis(tmp_path, monkeypatch):
    source = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (4, 2), (255, 0, 0))
    for x in (2, 3):
        for y in (0, 1):
            image.putpixel((x, y), (0, 0, 255))
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif, quality=100, subsampling=0)

    actual_means = module.calculate_bgr_means
    seen = {}

    def capture_pixels(frame):
        seen["top_left"] = frame[0, 0].tolist()
        seen["bottom_left"] = frame[-1, 0].tolist()
        return actual_means(frame)

    monkeypatch.setattr(module, "calculate_bgr_means", capture_pixels)

    result = module.analyze_image(source)

    assert result["source"]["width"] == 4
    assert result["source"]["height"] == 2
    assert result["preprocessing"]["exif_orientation"] == 6
    assert result["preprocessing"]["exif_transposed"] is True
    assert (result["preprocessing"]["analysis_width"],
            result["preprocessing"]["analysis_height"]) == (2, 4)
    assert seen["top_left"][2] > 240  # red half moved to top
    assert seen["bottom_left"][0] > 240  # blue half moved to bottom


@pytest.mark.parametrize("mode", ["L", "LA", "P", "RGBA"])
def test_eight_bit_modes_are_normalized_to_three_channels(tmp_path, mode):
    source = tmp_path / f"{mode}.png"
    if mode == "P":
        image = Image.new("P", (2, 2), 1)
        palette = [0, 0, 0] * 256
        palette[3:6] = [30, 20, 10]
        image.putpalette(palette)
    elif mode == "L":
        image = Image.new(mode, (2, 2), 60)
    elif mode == "LA":
        image = Image.new(mode, (2, 2), (60, 255))
    else:
        image = Image.new(mode, (2, 2), (30, 20, 10, 255))
    image.save(source)

    result = module.analyze_image(source)
    assert result["source"]["mode"] == mode
    assert result["preprocessing"]["analysis_color_order"] == "BGR"
    assert result["preprocessing"]["dtype"] == "uint8"


def test_transparent_pixel_is_composited_on_white(tmp_path):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(source)
    result = module.analyze_image(source)
    assert result["metrics"]["bgr_means"] == {
        "blue": 255.0, "green": 255.0, "red": 255.0,
    }
    assert result["preprocessing"]["channel_conversion"] == "alpha_over_white_then_RGB_to_BGR"


def test_rejects_unsupported_format_and_high_bit_depth(tmp_path):
    gif = tmp_path / "image.gif"
    Image.new("RGB", (2, 2)).save(gif)
    with pytest.raises(ValueError, match="不支持的图片格式"):
        module.analyze_image(gif)

    high_depth = tmp_path / "high.png"
    Image.fromarray(np.full((2, 2), 1000, dtype=np.uint16)).save(high_depth)
    with pytest.raises(ValueError, match="模式/数据类型"):
        module.analyze_image(high_depth)


@pytest.mark.parametrize("contents", [b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_corrupt_files_have_clear_error(tmp_path, contents):
    source = tmp_path / "broken.png"
    source.write_bytes(contents)
    with pytest.raises(ValueError, match="损坏或无法解码"):
        module.analyze_image(source)


def test_file_and_pixel_limits(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    Image.new("RGB", (3, 2)).save(source)
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="文件超过"):
        module.analyze_image(source)
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 25 * 1024 * 1024)
    monkeypatch.setattr(module, "MAX_PIXELS", 5)
    with pytest.raises(ValueError, match="像素超过"):
        module.analyze_image(source)


def test_cli_writes_new_json_only_and_keeps_old_result(tmp_path, capsys):
    source = tmp_path / "image.png"
    target = tmp_path / "result.json"
    Image.new("RGB", (2, 2), (10, 20, 30)).save(source)
    assert module.main([str(source), "--output", str(target)]) == 0
    first = target.read_bytes()
    assert json.loads(first)["source"]["format"] == "PNG"
    capsys.readouterr()

    assert module.main([str(source), "--output", str(target)]) == 2
    assert target.read_bytes() == first
    assert "[output_exists]" in capsys.readouterr().err


@pytest.mark.parametrize("orientation", range(1, 9))
def test_all_exif_orientations_move_pixels_correctly(tmp_path, monkeypatch, orientation):
    pixels = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    image = Image.fromarray(pixels)
    exif = Image.Exif()
    exif[274] = orientation
    source = tmp_path / "orientation.png"
    image.save(source, exif=exif)
    expected = {
        1: pixels, 2: np.fliplr(pixels), 3: np.rot90(pixels, 2),
        4: np.flipud(pixels), 5: pixels.transpose(1, 0, 2),
        6: np.rot90(pixels, -1), 7: pixels.transpose(1, 0, 2)[::-1, ::-1],
        8: np.rot90(pixels),
    }[orientation]
    original_means = module.calculate_bgr_means

    def check_pixels(bgr):
        np.testing.assert_array_equal(bgr, expected[:, :, ::-1])
        return original_means(bgr)

    monkeypatch.setattr(module, "calculate_bgr_means", check_pixels)
    result = module.analyze_image(source)
    assert result["preprocessing"]["exif_transposed"] == (orientation != 1)


def test_format_is_content_based_and_rejects_disguised_gif(tmp_path):
    source = tmp_path / "wrong-extension.bin"
    Image.new("RGB", (2, 2)).save(source, format="JPEG")
    assert module.analyze_image(source)["source"]["format"] == "JPEG"
    Image.new("RGB", (2, 2)).save(source, format="GIF")
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(source)
    assert captured.value.code == "unsupported_format"


def test_palette_transparency_and_grayscale_values(tmp_path):
    source = tmp_path / "palette.png"
    image = Image.new("P", (1, 1), 0)
    image.putpalette([0, 0, 0] * 256)
    image.save(source, transparency=0)
    result = module.analyze_image(source)
    assert result["metrics"]["brightness"] == 255
    assert result["preprocessing"]["channel_conversion"] == "alpha_over_white_then_RGB_to_BGR"
    Image.new("L", (1, 1), 60).save(source)
    result = module.analyze_image(source)
    assert list(result["metrics"]["bgr_means"].values()) == [60, 60, 60]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_byte_limit_boundary(tmp_path, monkeypatch, offset):
    source = tmp_path / "boundary.png"
    Image.new("RGB", (2, 2)).save(source)
    contents = source.read_bytes()
    limit = len(contents) + 10
    monkeypatch.setattr(module, "MAX_FILE_BYTES", limit)
    source.write_bytes(contents + b"\x00" * (10 + offset))
    if offset > 0:
        with pytest.raises(module.AnalysisError) as captured:
            module.analyze_image(source)
        assert captured.value.code == "file_limit_exceeded"
    else:
        assert module.analyze_image(source)["source"]["bytes"] == limit + offset


@pytest.mark.parametrize("pixels", [5, 6, 7])
def test_pixel_limit_boundary(tmp_path, monkeypatch, pixels):
    source = tmp_path / "pixels.png"
    Image.new("RGB", (pixels, 1)).save(source)
    monkeypatch.setattr(module, "MAX_PIXELS", 6)
    if pixels > 6:
        with pytest.raises(module.AnalysisError) as captured:
            module.analyze_image(source)
        assert captured.value.code == "pixel_limit_exceeded"
    else:
        assert module.analyze_image(source)["source"]["width"] == pixels


def test_real_pixel_limit_rejects_small_compressed_image_before_load(tmp_path, monkeypatch):
    source = tmp_path / "large.png"
    Image.new("RGB", (4001, 4000)).save(source)
    assert source.stat().st_size < module.MAX_FILE_BYTES

    def unexpected_load(*args, **kwargs):
        pytest.fail("over-limit image must not allocate decoded pixels")

    monkeypatch.setattr(Image.Image, "load", unexpected_load)
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(source)
    assert captured.value.code == "pixel_limit_exceeded"


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_truncated_valid_header_is_decode_error(tmp_path, image_format):
    source = tmp_path / "truncated"
    Image.new("RGB", (10, 10)).save(source, format=image_format)
    contents = source.read_bytes()
    source.write_bytes(contents[:len(contents) // 2])
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(source)
    assert captured.value.code == "corrupt_image"


def test_animation_is_explicitly_rejected(tmp_path):
    source = tmp_path / "animated.png"
    Image.new("RGB", (2, 2)).save(
        source, save_all=True, append_images=[Image.new("RGB", (2, 2), "white")],
        duration=100, loop=0,
    )
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(source)
    assert captured.value.code == "unsupported_animation"


def test_missing_file_has_stable_cli_error(tmp_path, capsys):
    assert module.main([str(tmp_path / "missing.png")]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "[input_not_found]" in output.err


def test_permission_error_is_distinct_from_corruption(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(module.Path, "open", denied)
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(tmp_path / "private.png")
    assert captured.value.code == "input_access_denied"


def test_provenance_config_and_reanalysis_are_traceable(tmp_path):
    source = tmp_path / "trace.png"
    Image.new("RGB", (2, 2)).save(source)
    first, second = module.analyze_image(source), module.analyze_image(source)
    assert first["schema_version"] == 2
    assert first["analysis_id"] != second["analysis_id"]
    assert first["source"]["sha256"] == second["source"]["sha256"]
    assert first["config_sha256"] == sha256(
        json.dumps(first["analysis_config"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    root = module.Path(module.__file__).resolve().parent
    for name, digest in first["provenance"]["source_sha256"].items():
        assert digest == sha256((root / name).read_bytes()).hexdigest()
    assert first["analysis_duration_seconds"] >= 0
    assert first["provenance"]["runtime"]["opencv"]


def test_git_unavailable_is_unknown_not_clean(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git unavailable")

    monkeypatch.setattr(module.subprocess, "run", unavailable)
    git_info = module._provenance()["git"]
    assert git_info["status"] == "unavailable"
    assert git_info["commit"] is None
    assert git_info["working_tree_dirty"] is None


@pytest.mark.parametrize("exception,code", [
    (PermissionError("denied"), "output_access_denied"),
    (OSError("disk failure"), "output_write_failed"),
])
def test_output_failure_is_distinct_and_does_not_print_success(tmp_path, monkeypatch, capsys, exception, code):
    source = tmp_path / "input.png"
    target = tmp_path / "output.json"
    Image.new("RGB", (2, 2)).save(source)
    real_open = module.Path.open

    def fail_output(path, *args, **kwargs):
        if path == target:
            raise exception
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(module.Path, "open", fail_output)
    assert module.main([str(source), "--output", str(target)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert f"[{code}]" in output.err


@pytest.mark.parametrize("orientation", [9, 65535])
def test_invalid_exif_is_explicitly_rejected(tmp_path, orientation):
    source = tmp_path / "bad-exif.png"
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (2, 2)).save(source, exif=exif)
    with pytest.raises(module.AnalysisError) as captured:
        module.analyze_image(source)
    assert captured.value.code == "invalid_orientation"


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_zero_exif_preserves_decoded_pixels_and_warns(tmp_path, monkeypatch, image_format):
    source = tmp_path / "zero-exif"
    pixels = np.arange(18, dtype=np.uint8).reshape(2, 3, 3) * 10
    exif = Image.Exif()
    exif[274] = 0
    Image.fromarray(pixels).save(source, format=image_format, exif=exif)
    original = source.read_bytes()
    with Image.open(source) as image:
        expected = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
    original_means = module.calculate_bgr_means

    def check_pixels(bgr):
        np.testing.assert_array_equal(bgr, expected)
        return original_means(bgr)

    monkeypatch.setattr(module, "calculate_bgr_means", check_pixels)
    result = module.analyze_image(source)
    assert source.read_bytes() == original
    assert result["preprocessing"]["exif_orientation"] == 0
    assert result["preprocessing"]["exif_transposed"] is False
    assert result["preprocessing"]["exif_orientation_handling"] == "unspecified_preserve_pixel_order"
    assert (result["preprocessing"]["analysis_width"], result["preprocessing"]["analysis_height"]) == (3, 2)
    assert result["warnings"][0]["code"] == "exif_orientation_unspecified"
    assert result["analysis_config"]["exif_orientation_policy"] == "apply_1_to_8;zero_no_transform_with_warning;reject_other"


def test_missing_orientation_has_no_warning(tmp_path):
    source = tmp_path / "plain.png"
    Image.new("RGB", (3, 2)).save(source)
    result = module.analyze_image(source)
    assert result["preprocessing"]["exif_orientation"] == 1
    assert result["preprocessing"]["exif_transposed"] is False
    assert result["warnings"] == []


@pytest.mark.parametrize("size", [(3072, 4096), (4000, 4000)])
def test_sixteen_megapixel_limit_accepts_old_rejection_and_exact_boundary(tmp_path, size):
    assert module.MAX_PIXELS == 16_000_000
    source = tmp_path / "accepted.png"
    Image.new("RGB", size, (10, 20, 30)).save(source)
    result = module.analyze_image(source)
    assert (result["preprocessing"]["analysis_width"], result["preprocessing"]["analysis_height"]) == size
    assert result["analysis_config"]["max_pixels"] == 16_000_000
    assert result["metrics"]["bgr_means"] == {"blue": 30.0, "green": 20.0, "red": 10.0}
