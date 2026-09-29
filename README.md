# camera-quality-diagnostics

面向工业视觉场景的**图像质量检测与故障分析工具**。

---

## 1. 项目名称

`camera-quality-diagnostics` —— 摄像头图像质量诊断工具

---

## 2. 项目目标

在工业视觉场景里，摄像头拍出来的图**质量会变差**，但原因往往不好判断：

- 镜头脏了 → 画面整体发雾
- 对焦跑了 → 边缘模糊
- 光源老化 → 整体偏暗或偏色
- 传输丢包 → 画面出现马赛克、条纹
- 相机过热 → 噪点变多

本项目的目标是做一个**能自动判断"这张图哪里不对劲"的工具**，
把上面这些问题从"靠人眼感觉"变成"有数字、有依据"。

**当前阶段（v0.3，进行中）**：v0.2 基础质量指标和读帧失败事件记录已经完成，正在为基础故障模式识别补充颜色通道数据。

目前还没有完成场景阈值标定和自动故障模式识别，因此这些指标只能用于观察和对照，不能直接判定工业相机是否合格。

---

## 3. 环境安装方式

### 已经装好了，这里是记录

| 项目 | 值 |
|---|---|
| Python | **3.12.10**（官方 CPython，64 位） |
| Python 安装位置 | `D:\DevTools\Python312` |
| 虚拟环境 | `D:\Projects\Python\camera-quality-diagnostics\.venv` |
| pip 缓存 | `D:\DevCache\pip` |

> Python 3.12.10 是 **3.12 系列最后一个提供官方 Windows 安装包的版本**。
> 3.12.11 及以后进入 security-only 阶段，只发源码包，没有 `.exe` 安装器。

### 如果要在别的电脑上重建

```powershell
# 1. 安装官方 Python 3.12（从 python.org 下载 python-3.12.10-amd64.exe）

# 2. 建虚拟环境
D:\DevTools\Python312\python.exe -m venv .venv

# 3. 按清单装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 4. 如何运行

### 方式一：在 VS Code 里（推荐）

1. 用 VS Code 打开本文件夹
2. 按 **F5** → 选择「调试主程序 (src/main.py)」
3. 下方终端会打印环境自检结果

**F5 之前不需要手动敲任何命令。** VS Code 会自动用 `.venv` 里的 Python。

### 方式二：在终端里

```powershell
# 环境自检
.venv\Scripts\python.exe src\main.py

# 摄像头质量测试（按 s 保存当前指标，按 q 退出）
.venv\Scripts\python.exe src\camera_test.py

# 只读汇总带标签颜色报告（不打开摄像头，不修改 CSV）
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_colors.py

# 新批次报告产生后，按 run_id 和场景分别汇总（旧报告保持不变）
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_colors.py .\data\reports\camera_colors_runs.csv

# 同次按 s 的质量指标写入 camera_quality_runs.csv，与颜色批次报告共享 run_id 和 frame_count

# 只读检查两份批次报告是否存在单侧记录；有未配对记录时退出码为 1
.\.venv\Scripts\python.exe -X utf8 .\src\check_reports.py

# 只显示指定批次的配对情况；仍校验完整 CSV，不修改旧记录
.\.venv\Scripts\python.exe -X utf8 .\src\check_reports.py --run-id 7bfd31a24dc64d96aa22311a78bf7200

# 首次记录一个新批次时使用；此示例批次已创建备注，再运行会报“文件已存在”
.\.venv\Scripts\python.exe -X utf8 .\src\record_conditions.py 7bfd31a24dc64d96aa22311a78bf7200 --note '采集后回忆：按2时换上了彩色物体，其他条件基本没变。光照、位置和纸张距离未量化；自动曝光状态未核实。'

# 摄像头退出后，按批次导出完整配对的 JSON；替换成实际 run_id
.\.venv\Scripts\python.exe -X utf8 .\src\export_pairs.py f1c6d22b952147bf91a2b3ac7c0cbc9b

# 只读汇总一个批次 JSON 中各场景的样本数与指标范围
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_pairs.py .\data\reports\camera_pair_f1c6d22b952147bf91a2b3ac7c0cbc9b.json

# 只读核对三场景标签是否按白纸→彩色物体→恢复白纸各保存一次
.\.venv\Scripts\python.exe -X utf8 .\src\validate_capture.py .\data\reports\camera_pair_7bfd31a24dc64d96aa22311a78bf7200.json

# 只读比较同一批次的白纸与恢复白纸标签，显示后者减前者的均值差
.\.venv\Scripts\python.exe -X utf8 .\src\compare_white.py .\data\reports\camera_pair_e5125e7c90fb4cfda143f2252b596fa0.json

# 跨批次汇总白纸差值；有更多批次时在命令末尾追加其 JSON 路径
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_white_runs.py .\data\reports\camera_pair_e5125e7c90fb4cfda143f2252b596fa0.json

# 跑测试
.venv\Scripts\python.exe -m pytest
```

JSON 导出只处理指定批次；该批次若有未配对记录会失败。历史其他批次的单侧记录不会混入导出。结果保存为 `data/reports/camera_pair_<run_id>.json`，已存在时不会覆盖。JSON 只是结构化指标，不包含故障判断。
JSON 汇总也只是描述性统计；单次或少量采样不能据此设定设备合格阈值。
白纸标签差值也不能证明相机故障或恢复效果；场景标签由操作者手动选择，需结合拍摄条件解释。
跨批次汇总会拒绝重复的 `run_id`；只有一个完整批次时不显示跨批次范围。多个批次也仍不足以自动设定合格阈值。

> ⚠️ **不要用全局 Python 跑这个项目。** 一律用 `.venv\Scripts\python.exe`，
> 否则会出现"明明装了包却 import 不到"的问题。

---

## 5. 如何调试

在 VS Code 里按 **F5**，`launch.json` 已经准备好三套配置：

| 配置名 | 用途 |
|---|---|
| **调试主程序 (src/main.py)** | 默认，按 F5 直接走这个 |
| **调试当前文件 (当前打开的 .py)** | 换文件不用改配置，通用 |
| **调试摄像头测试 (src/camera_test.py)** | 专门调摄像头那个程序 |

### 打断点

在行号左边点一下，出现红点就是断点。按 F5 后程序会停在那里。

| 按键 | 作用 |
|---|---|
| <kbd>F5</kbd> | 启动 / 继续 |
| <kbd>F10</kbd> | 单步跳过（不进入函数） |
| <kbd>F11</kbd> | 单步进入（进入函数内部） |
| <kbd>Shift</kbd>+<kbd>F5</kbd> | 停止调试 |

**看变量值**：停住时鼠标悬停在变量上，或看左侧「变量」面板。

> 💡 **建议先练一次**：打开 `src/main.py`，在 `in_venv = sys.prefix != sys.base_prefix`
> 这一行打断点，按 F5，然后悬停看 `sys.prefix` 和 `sys.base_prefix` 的区别 ——
> 这能帮你直观理解「虚拟环境」到底是什么。

---

## 6. 当前阶段功能

**v0.1 —— 环境验证阶段，已完成：**

- ✅ Python 3.12.10 安装并配置好 PATH
- ✅ 项目虚拟环境 `.venv` 建好
- ✅ OpenCV / NumPy / Matplotlib / pytest 装好
- ✅ VS Code 配置好（F5 可调试，自动用 `.venv`）
- ✅ 环境自检程序 `src/main.py`
- ✅ 摄像头测试程序 `src/camera_test.py`
- ✅ 自动化测试 `tests/test_environment.py`

**v0.2 —— 基础质量指标阶段，已完成：**

- ✅ 平均亮度、欠曝比例和过曝比例
- ✅ 拉普拉斯方差清晰度分数
- ✅ 灰度标准差对比度分数
- ✅ 256级灰度直方图、峰值灰度和峰值像素数量
- ✅ 实时画面叠加显示
- ✅ 按 `s` 追加保存单帧 CSV 报告
- ✅ 指标和报告自动化测试

> 当前结果依赖画面内容、光照和相机自动曝光。默认阈值尚未完成具体工业场景标定，不应把单个分数直接解释为“合格”或“故障”。

**v0.2.1 —— 采集事件记录，已完成：**

- ✅ 已打开摄像头发生读帧失败时记录 `read_failed`
- ✅ 独立保存到 `data/reports/camera_events.csv`
- ✅ 记录毫秒时间、最后成功帧数、事件类型和说明
- ✅ 软件模拟验证终端提示、事件写入和资源释放

> 当前电脑使用内置摄像头，因此没有进行真实硬件断连测试；集成流程通过安全的软件模拟验证。

---

## 7. 后续计划

按难度递进，逐步把"判断图像哪里不对"做出来：

**v0.2 —— 基础质量指标**
- [x] 平均亮度计算与实时显示
- [x] 过曝/欠曝像素比例（默认阈值用于观察，尚未完成场景标定）
- [x] 清晰度分数：拉普拉斯方差（模糊阈值尚未标定）
- [x] 对比度分数：灰度标准差（低对比度阈值尚未标定）
- [x] 灰度直方图及峰值显示
- [x] 按 `s` 输出单帧质量报告（CSV）

**v0.3 —— 故障模式识别**
- [ ] 脏污检测：通过局部对比度异常定位镜头脏点
- [ ] 条纹/马赛克检测：基于频域分析
- [ ] 噪点估计：估计噪声水平
- [ ] 偏色检测：BGR 通道均值已完成，基准和阈值未完成

**v0.4 —— 工程化**
- [ ] 实时监控模式（连续检测并画趋势曲线）
- [ ] 阈值可配置（不同场景不同标准）
- [ ] 报告可视化（Matplotlib 出图）
- [ ] 批量分析历史图片

**v1.0 —— 可用工具**
- [ ] 打包成可执行文件，不装 Python 也能用
- [ ] 图形界面

---

## 8. 目录结构

```
camera-quality-diagnostics\
├── .venv\                  ← 虚拟环境（不要提交到 Git）
├── .vscode\
│   ├── settings.json       ← 让 VS Code 用 .venv
│   └── launch.json         ← F5 调试配置
├── src\
│   ├── __init__.py
│   ├── main.py             ← 主程序 / 环境自检
│   ├── camera_test.py      ← 摄像头采集、实时显示和按键流程
│   ├── metrics.py          ← 图像质量指标计算
│   └── report.py           ← CSV 报告保存
├── tests\
│   ├── test_environment.py ← 环境测试
│   ├── test_metrics.py     ← 图像质量指标测试
│   └── test_report.py      ← CSV 报告测试
├── data\
│   ├── samples\            ← 样本图片（会提交）
│   └── reports\            ← 生成的报告（不提交）
├── docs\                   ← 分阶段学习记录和 v0.2 总结
├── .gitignore
├── README.md               ← 本文件
└── requirements.txt        ← 依赖清单
```

---

## 9. 常见问题

### 按 F5 报 `ModuleNotFoundError: No module named 'cv2'`

说明用的是全局 Python，不是 `.venv`。
点 VS Code 右下角的 Python 版本号，选 `.venv\Scripts\python.exe`。

### 摄像头打不开

常见原因（程序里也会提示）：
1. 被相机应用 / 腾讯会议 / 钉钉 / Zoom 占用
2. 编号不是 0，把 `camera_test.py` 里的 `CAMERA_INDEX` 改成 1 或 2
3. 驱动问题，去设备管理器看有没有黄色感叹号

这属于硬件条件，不代表 Python 环境有问题。

### 装了包但 import 不到

确认命令用的是 `.venv\Scripts\python.exe -m pip install xxx`。
如果直接敲 `pip install xxx`，可能装到了全局 Python。
