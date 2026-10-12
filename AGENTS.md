# camera-quality-diagnostics — 项目规则

> 项目专属规则。跨项目通用约束见 `C:\Users\zex\.codex\AGENTS.md`。
> 下面的路径与命令均已在本机实测（2026-10-12，pytest 收集 283 项，exit 0）。

## 项目定位

基于 Python + OpenCV 的**摄像头采集、图像质量指标记录与证据核对**项目。
目前是练习与流程验证项目，**不是**已标定的工业相机诊断产品。

**已实现**：摄像头采集；亮度/曝光比例/清晰度/对比度等指标；颜色通道均值；
读帧失败事件记录；按批次保存 CSV/JSON；可选原始帧 PNG 留证与数值复核；
本地 JPEG/PNG 图片分析；QR 基线解码与人工 ROI。

**尚未实现**：脏污/条纹/噪点/偏色等故障的自动识别；场景阈值标定；
手机上传、数据库、服务化；标签可读性的合格判定。

## 环境与命令（实测）

- Python **3.12.10**，虚拟环境在项目根的 `.venv`。一律使用 `.venv`，不要用系统 Python。
- 项目根：`D:\Projects\Python\camera-quality-diagnostics`
  **会话 cwd 必须 = 项目根**（见全局规则中的沙箱说明）。

```powershell
# 测试（283 项）
.\.venv\Scripts\python.exe -m pytest -q

# 摄像头采集
.\.venv\Scripts\python.exe src\main.py
.\.venv\Scripts\python.exe src\camera_test.py

# 本地图片质量分析
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_image.py <图片> --output <新JSON>

# QR 解码 / 人工 ROI
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py <图片> [--roi x y w h] --output <新JSON>
```

## 目录约定

- `src/` — 入口与实现（`analyze_image.py`、`analyze_label.py`、`camera_test.py`、`main.py` …）
- `tests/` — pytest 用例，与 `src/` 模块同名对应
- `docs/` — 分阶段记录 `stage-XX-*.md`，编号递增
- `data/reports/` — 生成的 JSON / CSV；`data/samples/` — 合成样例
- `photo/` — 实拍原图

## 不可违反的约束

1. **原图只读**：不覆盖、不修改 `photo/` 与 `data/samples/` 下的任何图片。
2. **输出仅新建**：`--output` 指定的 JSON 路径必须是**新文件**；重新分析换新文件名，
   不覆盖历史报告。
3. **旧报告不改写**：可以新增字段，但不要改变历史 JSON 的既有格式与字段含义。
4. **不夸大结论**：文档必须区分「已实现」与「规划」。未读出的 QR 只能说
   "读出/未读出"，**不能称为"正确"**；无真值时 `truth_check.status` 为 `not_provided`；
   仅单一有效码与独立已知答案逐字节相同才为 `correct`。
5. **区分业务结果与程序异常**：未读出、歧义、答案不匹配**不是**执行异常；
   只有候选解码失败/执行错误才返回退出码 2。不要把业务结果包装成异常。
6. **不自动打开 QR 内的链接。**
7. 不为了让测试通过而删除、跳过或弱化测试。

## 修改流程

1. 先读相关 `src/` 与 `tests/`，确认现有行为；
2. 说明要改哪些文件、为什么、预期效果、风险、回滚方式；
3. 改完运行 `.\.venv\Scripts\python.exe -m pytest -q`；
4. 行为变更同步更新 `docs/` 与 `README.md`；
5. 报告如实写测试结果：失败就贴输出，跳过的步骤就说明跳过。
