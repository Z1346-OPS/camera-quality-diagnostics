"""Build the synthetic QR regression dataset for the label evaluation entry point.

The dataset is deliberately small, controlled and self-consistent:

* payloads are disjoint per split, so ``development`` and ``test`` share no ``label_id``,
  ``batch_id`` or expected-answer hash -- the evaluator rejects such leakage;
* every sample is one controlled degradation of one payload, and the degradation is recorded
  in the manifest ``source`` text.  The manifest schema is strict (unknown fields are
  rejected by ``src/label_evaluation.py``), so v1 keeps conditions in text rather than adding
  a structured field;
* image hashes are computed from the bytes actually written, so re-running this script always
  produces a self-consistent image + manifest pair.  The exact PNG bytes depend on the local
  OpenCV/zlib build: commit the generated files, and do not regenerate them inside CI.

Degradation families, and what each one is for:

===============  ==================================================================
clean            control samples that must always decode
downscale        small images; tests that shrinking alone does not break decoding
blur             softness gradient (sigma 3 passes, sigma 5 and 8 fail)
brightness       under/over exposure and low contrast
rotation         in-plane rotation (the decoder rotates internally)
jpeg             compression artefacts
occlusion        a white patch covering part of the code
noise-large      large code (24 px per module) on a wide canvas with photographic noise
                 and JPEG artefacts.  This is the only family that reproduces the real
                 capture failure mode: the plain baseline fails while the internal
                 downscale search succeeds, so the report shows a paired improvement.
                 Canvas size was measured not to affect the outcome, so the smallest
                 tested canvas is used to keep the repository small.
===============  ==================================================================

Run from the project root:

    .\\.venv\\Scripts\\python.exe -X utf8 tools\\generate_synthetic_samples.py
"""

import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "data" / "samples" / "synthetic-qr-v1"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
SCHEMA_VERSION = 1
QUIET_MODULES = 4          # QR spec requires a 4-module quiet zone; the encoder omits it
BASE_MODULE_PX = 8         # default pixel size of one QR module before degradation
PNG_COMPRESSION = 6
NOISE_SEED_BASE = 1000     # deterministic per-sample noise; keeps regeneration stable
PAYLOAD_KEYS = ("A", "B", "C", "D")
NOISE_CANVAS = (896, 1120)  # (height, width) for the noise-large family

# Operations are applied in this fixed order: build, perspective, canvas, resize,
# blur, brightness, rotation, noise, jpeg, occlusion.
MATRIX = (
    # clean: 2
    ("clean", "module8", {"module_px": 8}),
    ("clean", "module6", {"module_px": 6}),
    # downscale: 3
    ("downscale", "w160", {"resize_width": 160}),
    ("downscale", "w96", {"resize_width": 96}),
    ("downscale", "w64", {"resize_width": 64}),
    # blur: 3
    ("blur", "sigma3", {"blur": 3.0}),
    ("blur", "sigma5", {"blur": 5.0}),
    ("blur", "sigma8", {"blur": 8.0}),
    # brightness: 3
    ("brightness", "dark055", {"alpha": 0.55, "beta": 25}),
    ("brightness", "lowcontrast", {"alpha": 0.75, "beta": 40}),
    ("brightness", "bright135", {"alpha": 1.35, "beta": -30}),
    # rotation: 3
    ("rotation", "deg8", {"angle": 8.0}),
    ("rotation", "deg15", {"angle": 15.0}),
    ("rotation", "deg25", {"angle": 25.0}),
    # jpeg: 3
    ("jpeg", "q30", {"jpeg_quality": 30}),
    ("jpeg", "q15", {"jpeg_quality": 15}),
    ("jpeg", "q8", {"jpeg_quality": 8}),
    # occlusion: 3
    ("occlusion", "px12", {"occlusion_patch": 12}),
    ("occlusion", "px20", {"occlusion_patch": 20}),
    ("occlusion", "px28", {"occlusion_patch": 28}),
    # noise-large: 3
    ("noise-large", "noise25-q50", {"module_px": 24, "canvas": list(NOISE_CANVAS),
                                    "noise": 25.0, "jpeg_quality": 50}),
    ("noise-large", "noise22-q60", {"module_px": 24, "canvas": list(NOISE_CANVAS),
                                    "noise": 22.0, "jpeg_quality": 60}),
    ("noise-large", "persp-noise25-q50", {"module_px": 24, "canvas": list(NOISE_CANVAS),
                                          "perspective": 0.04, "noise": 25.0,
                                          "jpeg_quality": 50}),
)

SPLITS = ("development", "test")
SPLIT_PREFIX = {"development": "dev", "test": "test"}


def payload_text(split, key):
    """Return the fixed payload for one (split, key) pair.

    ``SYNTH-`` rather than a stage number: the data must not depend on document numbering.
    """
    return f"SYNTH-{SPLIT_PREFIX[split].upper()}-{key}"


def build_base(payload, module_px):
    """Encode ``payload`` and scale it up; the encoder returns one pixel per module."""
    code = cv2.QRCodeEncoder_create().encode(payload)
    code = cv2.copyMakeBorder(code, QUIET_MODULES, QUIET_MODULES, QUIET_MODULES, QUIET_MODULES,
                              cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(code, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)


def paste_on_canvas(code, canvas):
    """Centre ``code`` on a white canvas so the sample looks like a capture, not a crop."""
    height, width = canvas
    if code.shape[0] > height or code.shape[1] > width:
        raise RuntimeError(f"二维码 {code.shape[:2]} 放不进画布 {canvas}")
    image = np.full((height, width), 255, np.uint8)
    top, left = (height - code.shape[0]) // 2, (width - code.shape[1]) // 2
    image[top:top + code.shape[0], left:left + code.shape[1]] = code
    return image


def add_noise(image, sigma, seed):
    """Deterministic gaussian sensor noise; the seed keeps regeneration reproducible."""
    generator = np.random.default_rng(seed)
    noisy = image.astype(np.int16) + generator.normal(0.0, sigma, image.shape).astype(np.int16)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def render(payload, params, seed):
    """Apply the documented operation pipeline and return a single-channel 8-bit image."""
    image = build_base(payload, params.get("module_px", BASE_MODULE_PX))

    if "perspective" in params:
        height, width = image.shape[:2]
        shift = params["perspective"]
        source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        target = np.float32([[width * shift, height * shift], [width * (1 - shift), 0],
                             [width, height * (1 - shift)], [0, height]])
        matrix = cv2.getPerspectiveTransform(source, target)
        image = cv2.warpPerspective(image, matrix, (width, height), borderValue=255)

    if "canvas" in params:
        image = paste_on_canvas(image, params["canvas"])

    if "resize_width" in params:
        width = params["resize_width"]
        image = cv2.resize(image, (width, width), interpolation=cv2.INTER_AREA)

    if "blur" in params:
        image = cv2.GaussianBlur(image, (0, 0), params["blur"])

    if "alpha" in params:
        image = cv2.convertScaleAbs(image, alpha=params["alpha"], beta=params.get("beta", 0))

    if "angle" in params:
        height, width = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), params["angle"], 1.0)
        image = cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255)

    if "noise" in params:
        image = add_noise(image, params["noise"], seed)

    if "jpeg_quality" in params:
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), params["jpeg_quality"]])
        if not ok:
            raise RuntimeError("JPEG 编码失败")
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)

    if "occlusion_patch" in params:
        patch = params["occlusion_patch"]
        height, width = image.shape[:2]
        top, left = height // 2 - patch // 2, width // 2 - patch // 2
        image = image.copy()
        image[top:top + patch, left:left + patch] = 255

    return image


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_image(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image, [int(cv2.IMWRITE_PNG_COMPRESSION), PNG_COMPRESSION]):
        raise RuntimeError(f"写入图片失败: {path}")


def build_split(split):
    """Write one split's images and answers; returns its manifest samples and a summary."""
    split_dir = DATASET_DIR / split
    answer_dir = split_dir / "answers"
    samples, summary, image_hashes = [], [], set()

    answers = {}
    for key in PAYLOAD_KEYS:
        text = payload_text(split, key)
        path = answer_dir / f"{key}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))     # exactly the payload bytes, no newline
        answers[key] = (text, sha256_file(path))

    for index, (condition, severity, params) in enumerate(MATRIX, start=1):
        key = PAYLOAD_KEYS[(index - 1) % len(PAYLOAD_KEYS)]
        text, answer_hash = answers[key]
        seed = NOISE_SEED_BASE + index * 7 + (1000 if split == "test" else 0)
        image = render(text, params, seed)
        filename = f"{SPLIT_PREFIX[split]}-{index:02d}-{condition}-{severity}-{key}.png"
        image_path = split_dir / filename
        write_image(image_path, image)
        digest = sha256_file(image_path)
        if digest in image_hashes:
            raise RuntimeError(f"图片哈希重复（同一原图只能列一次）: {filename}")
        image_hashes.add(digest)
        height, width = image.shape[:2]
        samples.append({
            "id": f"synthetic-qr-v1-{split}-{index:02d}",
            "image": f"../samples/synthetic-qr-v1/{split}/{filename}",
            "sha256": digest,
            "label_id": f"synthetic-qr-v1-{split}-{key}",
            "batch_id": f"synthetic-qr-v1-{split}",
            "split": split,
            "source_kind": "synthetic",
            "source": (f"程序生成的合成样本；退化条件={condition}；参数="
                       f"{json.dumps(params, sort_keys=True)}；基底载荷={text}；用途=解码鲁棒性回归"),
            "expected_file": f"../samples/synthetic-qr-v1/{split}/answers/{key}.txt",
            "expected_sha256": answer_hash,
            "truth_source": "tools/generate_synthetic_samples.py 预先固定的载荷文本，与解码输出无关",
        })
        summary.append((index, condition, severity, key, width, height,
                        image_path.stat().st_size / 1024))
    return samples, summary


def main():
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    grand_total = 0
    for split in SPLITS:
        samples, summary = build_split(split)
        manifest_path = MANIFEST_DIR / f"evaluation-synthetic-{split}.json"
        manifest_path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "samples": samples},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        total = sum(entry[6] for entry in summary)
        grand_total += total
        print(f"\n=== {split}：{len(samples)} 个样本，图片合计 {total / 1024:.1f} MB ===")
        print(f"{'#':>3}  {'条件':<12}{'强度':<19}{'载荷':<3}{'尺寸':>11}  {'KB':>8}")
        for index, condition, severity, key, width, height, size in summary:
            print(f"{index:>3}  {condition:<12}{severity:<19}{key:<3}{f'{width}x{height}':>11}  {size:>8.1f}")
        print(f"清单: {manifest_path.relative_to(PROJECT_ROOT)}")

    print(f"\n两套 split 图片合计 {grand_total / 1024:.1f} MB。")
    print("完成。清单哈希由实际写出的字节计算，重新运行会得到自洽的图片+清单对。")


if __name__ == "__main__":
    main()
