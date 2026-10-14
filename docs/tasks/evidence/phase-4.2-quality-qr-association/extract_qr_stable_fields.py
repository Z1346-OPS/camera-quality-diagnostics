r"""证据工具（**不是产品代码**）：用**改动前**的 `analyze_label` 提取 QR 稳定业务字段。

用途：为 Phase 4.2「QR 结果与图像质量测量关联」提供**外部 oracle**。
后续实现完成后，用同一脚本重跑并逐字段比较，证明既有 QR 稳定业务字段未被改变。

边界：
- 本脚本**只读**：调用 `analyze_label`（不传 output），不写任何项目文件，只写它自己的 stdout 到指定路径。
- 本脚本**不导入**待实现的 `src/quality_qr_analysis.py`，因此 oracle 与后续实现无关。
- `src/` 与 `tests/` **不得**依赖本脚本；它位于证据目录，不是产品入口、不是 `tools/`。

运行（项目根执行）：
    .\.venv\Scripts\python.exe -B -X utf8 \
        docs\tasks\evidence\phase-4.2-quality-qr-association\extract_qr_stable_fields.py
"""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

# --- 定位项目根（向上找到含 src/ 与 .git/ 的目录），不依赖 CWD -------------------
ROOT = Path(__file__).resolve()
while ROOT.parent != ROOT and not (ROOT / "src" / "analyze_label.py").exists():
    ROOT = ROOT.parent
if not (ROOT / "src" / "analyze_label.py").exists():
    raise SystemExit("无法定位项目根：找不到 src/analyze_label.py")
sys.path.insert(0, str(ROOT))

from src import analyze_label as label_cli  # noqa: E402

# --- 允许变化的字段（逐路径列出，禁止笼统忽略差异）---------------------------
VOLATILE_PATHS = [
    ("analysis_id", "每次调用生成的随机 ID（uuid4），必然变化"),
    ("analyzed_at", "墙上时间戳，必然变化"),
    ("analysis_duration_seconds", "耗时，必然变化"),
    ("provenance.git", "commit / working_tree_dirty / status 随提交与工作区状态变化；"
                       "Phase 4.1 若先提交，commit 会变，故整体排除"),
    ("attempts[].decode.duration_seconds", "单次解码耗时，必然变化"),
]

# --- 固定夹具（全部为 git 已跟踪的入库文件）----------------------------------
SAMPLE = "data/samples"
SYN = "data/samples/synthetic-qr-v1/development"
SYN_TEST = "data/samples/synthetic-qr-v1/test"

FIXTURES = [
    {
        "name": "stage2_full_no_downscale",
        "note": "真实 PNG；Phase 4.1 A16 冒烟样本；有独立答案；单 profile",
        "image": f"{SAMPLE}/stage2-known-qr.png",
        "roi": None,
        "expected_file": f"{SAMPLE}/stage2-known-qr.expected.txt",
        "truth_source": "stage2 入库独立答案文件（非解码器输出）",
        "try_downscale": False,
    },
    {
        "name": "stage2_roi_with_downscale",
        "note": "同一原图 + ROI；两个 region × 两个 profile；验证 ROI 不串配",
        "image": f"{SAMPLE}/stage2-known-qr.png",
        "roi": (66, 66, 132, 132),
        "expected_file": f"{SAMPLE}/stage2-known-qr.expected.txt",
        "truth_source": "stage2 入库独立答案文件（非解码器输出）",
        "try_downscale": True,
    },
    {
        "name": "dev01_clean_decoded",
        "note": "清晰样本；decoded + correct",
        "image": f"{SYN}/dev-01-clean-module8-A.png",
        "roi": None,
        "expected_file": f"{SYN}/answers/A.txt",
        "truth_source": "合成数据集独立答案 A.txt（编码器输入，早于解码）",
        "try_downscale": False,
    },
    {
        "name": "dev07_blur5_decode_error",
        "note": "模糊 sigma5；decode_error 状态",
        "image": f"{SYN}/dev-07-blur-sigma5-C.png",
        "roi": None,
        "expected_file": f"{SYN}/answers/C.txt",
        "truth_source": "合成数据集独立答案 C.txt（编码器输入，早于解码）",
        "try_downscale": True,
    },
    {
        "name": "dev08_blur8_not_decoded",
        "note": "模糊 sigma8；not_decoded 状态",
        "image": f"{SYN}/dev-08-blur-sigma8-D.png",
        "roi": None,
        "expected_file": f"{SYN}/answers/D.txt",
        "truth_source": "合成数据集独立答案 D.txt（编码器输入，早于解码）",
        "try_downscale": True,
    },
    {
        "name": "test07_blur5_ambiguous",
        "note": "test split；ambiguous 状态",
        "image": f"{SYN_TEST}/test-07-blur-sigma5-C.png",
        "roi": None,
        "expected_file": f"{SYN_TEST}/answers/C.txt",
        "truth_source": "合成数据集独立答案 C.txt（编码器输入，早于解码）",
        "try_downscale": True,
    },
    {
        "name": "dev01_clean_no_truth",
        "note": "无独立答案；truth_check 必须为 not_provided，不得称正确",
        "image": f"{SYN}/dev-01-clean-module8-A.png",
        "roi": None,
        "expected_file": None,
        "truth_source": None,
        "try_downscale": False,
    },
]


def project_stable(report):
    """深拷贝后逐路径删除允许变化的字段；其余全部保留。"""
    stable = deepcopy(report)
    stable.pop("analysis_id", None)
    stable.pop("analyzed_at", None)
    stable.pop("analysis_duration_seconds", None)
    provenance = stable.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("git", None)
    for attempt in stable.get("attempts", []):
        decode = attempt.get("decode")
        if isinstance(decode, dict):
            decode.pop("duration_seconds", None)
    return stable


def main():
    records = []
    for fixture in FIXTURES:
        image = ROOT / fixture["image"]
        expected = (ROOT / fixture["expected_file"]) if fixture["expected_file"] else None
        report = label_cli.analyze_label(
            image, fixture["roi"], expected, fixture["truth_source"],
            try_downscale=fixture["try_downscale"],
        )
        records.append({
            "name": fixture["name"],
            "note": fixture["note"],
            "image": fixture["image"],
            "image_sha256": sha256(image.read_bytes()).hexdigest(),
            "roi": list(fixture["roi"]) if fixture["roi"] else None,
            "expected_file": fixture["expected_file"],
            "try_downscale": fixture["try_downscale"],
            "stable": project_stable(report),
        })

    document = {
        "kind": "qr_stable_fields_oracle",
        "phase": "4.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py",
        "generator_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "code_baseline": "用改动前的 src/analyze_label.py + src/label_analysis.py 生成；未导入待实现模块",
        "volatile_paths": [{"path": path, "reason": reason} for path, reason in VOLATILE_PATHS],
        "comparison_rule": "逐 fixture、逐路径比较 stable 子树；volatile_paths 中的路径不比较。"
                           "任何其他路径的差异都算回归。",
        "records": records,
    }
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
