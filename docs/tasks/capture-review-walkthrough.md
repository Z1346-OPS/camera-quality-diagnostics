# 采集结果复核：三种情况的操作演示

日期：2026-10-15。使用现有 `src/review_capture.py`，不增加产品功能。

先运行下面的合成演示，再按需要使用真实摄像头。合成演示不依赖本机未入库的 `trial-003/004`、实拍图片或仓库外测试文件；只需要已有项目环境。

## 1. 运行可重复的合成演示

在项目根目录的 PowerShell 中执行。每次新建一个系统临时目录，保留输入与结果，不覆盖旧文件。三份输入都是演示夹具，不是真实摄像头采集记录。

```powershell
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'
$env:PYTHONDONTWRITEBYTECODE = '1'
@'
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

project = Path.cwd()
assert (project / "src/review_capture.py").is_file(), "请在项目根目录运行"
assert sys.prefix != sys.base_prefix, "请使用项目 .venv"
sys.path.insert(0, str(project))
from src.report import append_color_record, append_quality_record

output = Path(tempfile.mkdtemp(prefix="capture-review-demo-"))
frame = np.full((4, 5, 3), 100, dtype=np.uint8)
ok, encoded = cv2.imencode(".png", frame)
assert ok
png = encoded.tobytes()

def snapshot(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.iterdir() if p.is_file()}

cases = [("normal", 0, []),
         ("missing-image", 1, ["frame_unverifiable"]),
         ("changed-metric", 1, ["metric_mismatch"])]
for name, expected_exit, expected_issues in cases:
    folder = output / name
    folder.mkdir()
    run_id = uuid4().hex
    image_name = f"camera_frame_{run_id}_1.png"
    if name != "missing-image":
        (folder / image_name).write_bytes(png)
    # 常量100图：均值100，曝光比例、拉普拉斯方差、标准差均为0。
    brightness = 101.0 if name == "changed-metric" else 100.0
    append_quality_record(1, brightness, 0, 0, 0, 0,
                          folder / "camera_quality_runs.csv", run_id=run_id)
    append_color_record(1, 100, 100, 100, folder / "camera_colors_runs.csv",
                        scene_label="unspecified", run_id=run_id)
    task = {"schema_version": 1, "report_type": "camera_timed_capture",
            "run_id": run_id, "status": "completed",
            "counts": {"samples_completed": 1}, "samples": [{
                "frame_count": 1, "image_file": image_name,
                "image_sha256": hashlib.sha256(png).hexdigest(),
                "quality_status": "written", "color_status": "written",
                "image_status": "written"}]}
    (folder / "capture_task.json").write_text(json.dumps(task), encoding="utf-8")
    before = snapshot(folder)
    command = [sys.executable, "-B", "-X", "utf8",
               str(project / "src/review_capture.py"), str(folder)]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if process.stderr:
        print(process.stderr, file=sys.stderr, end="")
    assert process.returncode == expected_exit, (name, process.returncode, process.stdout)
    result = json.loads(process.stdout)
    assert [issue["code"] for issue in result["issues"]] == expected_issues
    assert result["verification_status"] == ("consistent" if expected_exit == 0 else "inconsistent")
    assert result["counts"]["verified_frames"] == (1 if name == "normal" else 0)
    assert snapshot(folder) == before, "复核不应修改输入"
    with (output / f"{name}.review.json").open("x", encoding="utf-8") as saved:
        saved.write(process.stdout)
    print(name, "exit=", process.returncode,
          "status=", result["verification_status"], "issues=", expected_issues)
print("演示数据与完整JSON：", output)
'@ | .\.venv\Scripts\python.exe -B -X utf8 -
```

示例脚本把 CLI 的 stdout 保存为新 JSON；复核入口本身不提供 `--output`，也不创建报告文件。结果文件在临时根目录，三个输入子目录在检查前后保持不变。

## 2. 读懂三种结果

| 情况 | 退出码 | 状态 | 应关注的字段 |
| --- | --- | --- | --- |
| 正常图片与记录 | 0 | `consistent` | 三个计数均为1，`issues=[]` |
| JSON声明图片已保存，但文件缺失 | 1 | `inconsistent` | `frame_unverifiable`，帧号1，`verified_frames=0` |
| CSV亮度记为101.0，图片实际均值100.0 | 1 | `inconsistent` | `metric_mismatch`，`metrics.brightness=["101.0", "100.0"]`，摘要仍匹配 |

合成夹具故意没有采集时的运行库、阈值与源码摘要，三份结果均包含 `measurement_context_unavailable` 提示。这不阻断按当前算法的检查，也不表示相机故障。

退出码1是已完成检查后发现不一致，结果JSON可用于定位；退出码2表示无法复核或输入错误，需结合 stderr 和 `task_status` 判断。`verified_frames` 只计摘要匹配且五项指标一致的帧。

## 3. 有真实摄像头时的采集与复核

以下命令会访问摄像头并保存图片；合成演示没有执行它们。使用唯一的新目录，完成采集后再离线复核：

```powershell
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'
$taskDir = Join-Path 'data\reports\timed-capture' ('demo-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -X utf8 src\run_capture.py --camera-index 0 --duration 10 --interval 5 --output-dir $taskDir
if ($LASTEXITCODE -ne 0) { throw '采集未成功结束；请查看错误及任务状态，不按completed任务处理。' }
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py $taskDir
```

首版采用同步读取和保存，不保证严格10秒退出。采样可能跳过区间，不能把理论点数直接当作实际样本数；以任务记录为准。失败或中断任务返回 `not_reviewed`，不恢复部分数据。

每个任务目录包含任务JSON、质量CSV、颜色CSV，以及按批次ID和帧号命名的PNG。复核结果指出记录与文件的差异，只证明检查范围内的一致性，不证明画面来源真实、相机合格或故障原因。

## 4. 展示时可说明什么

可以展示：输入一个目录如何代替手动填写多处路径；缺图与指标差异如何定位到具体帧；正常结果与异常结果如何分别解释。

本演示不新增质量评分、QR流程、网络传输或数据库。算法定义、测试数量与各环境验证记录仍以[能力矩阵](../stage-34-project-capability-matrix.md)和[Phase 4.5验收记录](phase-4.5-capture-review.md)为准。
