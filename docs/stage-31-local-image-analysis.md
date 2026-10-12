# 阶段 1：通用图片分析入口

本文件保留 2026-10-01 的初次实现记录。2026-10-02 按新阶段计划完成的入口核验、错误码、版本追溯与边界测试见[阶段 1 核验记录](stage-1-local-input-verification.md)；真实手机照片验收仍待用户操作。

## 目标与原理

输入本地 JPEG/PNG 文件，复用 `src/metrics.py` 的亮度、曝光比例、拉普拉斯方差、灰度对比度、直方图峰值和 BGR 通道均值。先读取原始字节并算 SHA-256，然后检查实际编码格式、字节数、像素数和模式；加载后按 EXIF 方向转正，统一为 8 位 BGR。全图参与计算；不猜测标签区域、故障原因或可读性。

允许的原始模式为 8 位 `RGB`、`RGBA`、`L`、`LA`、`P`。灰度会复制到三个颜色通道；带透明度的像素以白色背景合成；不做 ICC 色彩配置转换。16 位等其他模式明确拒绝，避免未经说明的量化。压缩 JPEG 的像素值可能因编码有损而变化。结果 JSON 记录实际方向、原始模式、转换步骤、分析尺寸、区域、阈值和指标定义。默认曝光阈值仍是 30 与 225，未经标签场景标定。

## 文件变化

- `src/analyze_image.py`：只读分析函数及命令行入口；可选独占新建 JSON 结果，拒绝覆盖已有结果。
- `src/analysis_config.py`：旧入口与新入口共用的默认曝光阈值。
- `src/camera_test.py`、`src/verify_frame_metrics.py`：改为从公共配置导入，旧常量名称及数值保持一致。
- `tests/test_analyze_image.py`：合成 JPEG/PNG、方向、通道、数据类型、资源限制、损坏文件和结果覆盖测试。
- `README.md`：运行方式及限制。

不会改写已有 CSV、JSON、原始帧或输入照片。输出文件需事先选择未使用的名称；不指定 `--output` 时仅向标准输出打印 JSON。

## 验证与局限

自动测试使用合成图片，覆盖 EXIF 方向、通道顺序和错误输入；完整旧测试用于确认本地摄像头指标与历史复核没有回归。2026-10-01 本机验证：新增测试 12 项通过；完整 `pytest` 162 项通过；不落盘编译检查通过；独立进程调用 CLI 对合成 PNG 成功生成 JSON，原图字节未变，再次使用同一结果名返回错误且旧结果未变。`compileall` 尝试写入仓库 `__pycache__` 被当前沙箱拒绝，故改用内存编译检查。项目没有配置独立的 lint、类型检查或构建命令。

真实手机照片、真实设备上的拍摄效果和跨平台兼容性仍需另行验证，不能由合成测试推断准确率。阶段 1 不接入上传、权限、数据库、条码识别或目标区域。

真实手机照片验证时，在项目根运行（替换为真实路径与新的结果名）：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_image.py 'D:\Photos\label.jpg' --output '.\data\reports\label-analysis-001.json'
```

检查 JSON 中 `source.sha256`、`source.width/height`、`preprocessing.exif_orientation`、`analysis_width/height` 和各指标；对照手机原图方向与颜色。再次分析同一张图使用 `label-analysis-002.json`，确认旧结果和原图未变。照片可能含个人信息，仅在本地保管。

## 下一步

由用户用实际手机照片核验本地图片入口。后续实施顺序已在[阶段 0 主设计](label-reading-project-design.md)调整为先做本地 ROI、QR 读码和评测，再做手机上传与服务；本阶段不启动。
