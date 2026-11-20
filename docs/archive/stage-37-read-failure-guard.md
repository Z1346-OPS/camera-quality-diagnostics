# 文档 37：默认摄像头取帧失败的传播防护（2026-10-17）

> 本文档序号 37 = `docs/` 下已有 `stage-NN-*` 的最大 NN（36）+ 1。
> 业务阶段：承接业务阶段 4.4「定时采集与间隔留证」的读取边界加固。

## 1. 一句话结论

默认摄像头读取边界已加一层薄适配，**显式传播 `grab()`/`retrieve()` 的真实成功标志**：
底层取帧失败但返回非空数组时，不再被计为成功采集。

**这修正的是「错误的成功状态」这一代码缺陷，不是历史近黑画面根因的确认。**
历史异常在本轮与上一轮实机诊断中均未复现，触发原因与因果链仍未确认。

## 2. 问题

`CaptureRunner` 通过注入的 `camera.read()` 取帧，成功与否只看返回的布尔值。
默认工厂 `_default_camera_factory` 直接返回 `cv2.VideoCapture(index, cv2.CAP_DSHOW)`，
因此默认路径用的是 `cv2.VideoCapture.read()`。

对照官方 OpenCV 5.0.0 源码（下载副本只读，未编译、未执行）：

- `VideoCapture::read()`（`cap.cpp`）**丢弃** `retrieve()` 的布尔返回值，
  最终按 `!image.empty()` 判定成功。
- `VideoCapture_DShow::grabFrame()`（`cap_dshow.cpp`）返回 `!isDeviceDisconnected()`，
  是**断开检查**，不证明有新帧。
- `VideoCapture_DShow::retrieveFrame()` 在 `getPixels()` **之前**先
  `frame.create(Size(w,h), CV_8UC3)` **预分配**出非空输出数组；`getPixels()` 等待超时
  （`WaitForSingleObject(hEvent, 1000)`）即返回 false。

由这三条可推出：上游停止供帧时，`read()` 可能阻塞约 1 秒后**仍然返回 true**，
并交出一个已分配但未取到新像素的数组。此时采集任务会把它当作有效帧测量、保存、复核，
**任务 completed**，而画面可能近黑。

## 3. 改动

只改默认工厂与其薄适配对象，不动采样循环、指标算法与报告格式。

`src/capture_task.py`：

```python
class _GrabRetrieveCamera:
    def read(self):
        if not self._capture.grab():      # grab 失败 → 不调用 retrieve
            return False, None
        retrieved, frame = self._capture.retrieve()
        if not retrieved:                 # retrieve 的真实标志为准
            return False, None            # 即使 frame 非空也不上交
        return True, frame
```

- 委托 `CaptureRunner` 实际用到的接口：`isOpened()`、`getBackendName()`、`release()`、`read()`。
- `_default_camera_factory` 改为返回该适配对象；后端仍为 `CAP_DSHOW`，编号传递不变。

### 保持的契约（未改）

- `camera.read()` 的接口与 `(ok, frame)` 返回形状不变。
- `_capture_loop` 采样循环、`_is_valid_frame`、指标算法、报告字段与格式不变。
- 异常沿用现有处理：不吞异常、不包装、首错优先（执行错误 → 释放错误 → 正常完成）不变。
- 设备生命周期（打开 / 释放 / 释放失败记录）不变。
- **不新增**自动重试、重连、补采、删首帧、亮度合格阈值或暗图过滤。
- `IMPLEMENTATION_VERSION` 保持 `timed-capture-1`：报告字段与语义未变，
  改动本身已由报告 provenance 的 `source_sha256["capture_task.py"]` 记录。

## 4. 测试

先写能暴露旧行为的用例并运行（`6 failed, 6 passed`），再实现修复并运行（`12 passed`）。
其中**核心用例在旧代码上是行为失败**（`DID NOT RAISE CaptureTaskError`），
不是导入或语法错误：

- 旧代码把 `retrieve=False` 返回的非空数组当作成功帧，任务 `completed` 并保存样本。

新增用例覆盖（`tests/test_capture_task.py`，T13 段）：

1. `grab=True / retrieve=False / 数组非空` → `failed` + `read_failed`、0 有效帧、0 样本、
   无留证、设备释放；且断言适配器**没有**走底层那个会误报成功的 `read()`。
2. `grab=False` → 不调用 `retrieve`，进入既有读取失败路径，设备释放。
3. `grab/retrieve` 都成功但画面确实全黑 → 按现有规则正常完成，**不**判为执行异常。
4. 正常图像 → 像素逐字节不变，采样 / PNG / CSV / 离线复核（`review_capture`）均一致。
5. 底层 `grab`/`retrieve` 抛异常 → 原样传播（对象同一性），设备释放。
6. 适配器委托 `release`：仅释放失败时 `release_failed`，首错优先不变；编号传递不变。

测试通过**真实默认工厂**驱动（替换 `capture_task.cv2.VideoCapture`），
而不是把一个已返回 `False` 的假 camera 直接注入 `CaptureRunner`。

## 5. 验证结果

| 项目 | 结果 |
| --- | --- |
| `pip check` | exit 0，无依赖冲突 |
| 目标回归（修复前 → 后） | exit 1（`6 failed`）→ exit 0（`12 passed`） |
| 完整 pytest（仓库外 basetemp、禁字节码与缓存） | exit 0，**493 passed**，0 失败、0 跳过 |
| `tools/check_evaluation_expectations.py`（不 `--refresh`） | exit 0，与入库期望完全一致 |
| 离线夹具自检（8 场景 51 断言） | 51/51 通过 |

用例数 493 = 上一轮 481 + 本轮新增 12。历史记录里的 `477 passed, 4 skipped`
与 `481 passed` 都是各自轮次的实测值，不作为本轮结果。

## 6. 边界与未确认

- **已修正**：失败返回值传播——`grab`/`retrieve` 的真实标志现在被显式检查并传播。
- **未确认**：历史近黑画面是否真的走过这条路径；上游为何停止供帧
  （驱动、厂商隐私/智能感知功能、设备状态、其他程序占用等）；该异常是否可复现。
- 实机正常只证明**本次正常路径回归通过**，**不能**证明历史异常已消失。
- 若某后端在成功时仍让 `retrieve()` 返回 `False`（与 DirectShow 语义不同），
  适配器会误判失败。本项目默认后端固定为 `CAP_DSHOW`，风险受限；
  注入的 `camera_factory` 不受影响。
- **不承诺完全防止复发。**

## 7. 相关记录

- 只读源码与候选机制：`data/reports/black-frame-check-20261016-184306-f5b01a96/`
- 实机诊断（未复现）：`data/reports/black-frame-live-diagnosis-20261016-191842-961aa331/`
- 本轮变更与验证：`data/reports/read-failure-guard-20261017-101037-9d36a959/`
