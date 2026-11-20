# 阶段 2：人工 ROI、QR 基线与独立答案核对

日期：2026-10-02。用户在阶段 1 验收后要求继续，按现有设计进入阶段 2。状态：代码、自动测试和本地 CLI 验证已完成；真实纸质 QR 的独立已知答案验收待用户操作。本阶段不进入样本划分/正式准确率评测、增强、网页、数据库或 RAG。

## 目标与原理

复用 JPEG/PNG 校验、EXIF/通道规范化及原有质量指标，在同一份规范化图像上计算整图指标与 QR 基线。有人工 ROI 时，另计算 ROI 指标和读码，保留整图结果。ROI 从 EXIF 处理后的图像取精确数组切片：`x y width height`，右/下边界不含，零起点；负坐标、非正宽高、越界与非整数明确拒绝。无缩放、补边、Gamma、CLAHE 或自动选区。

解码仅限定 QR Code，使用 ZXing-C++ 3.1.1。显式配置：旋转搜索开；内部降采样、反色尝试关；LocalAverage 二值化；Plain 文本模式；非 pure 输入；返回候选错误。解码器内部二值化是基线配置，不能称为未做任何处理。候选四角记录 ROI 局部坐标和加上 ROI 偏移的规范化图像坐标，不声称是原始 EXIF 文件坐标。多候选即歧义，即使编码相同或某项匹配真值，也不自动挑选。

解码状态与独立答案状态分别保存：

| 解码状态 | 含义 | 已知答案提供后的核对 |
| --- | --- | --- |
| decoded | 单一有效码读出 | 原始 payload 字节相同为 correct，否则 incorrect |
| not_decoded | 没有返回候选 | not_decoded，不能判定照片没有 QR |
| ambiguous | 多个候选，包括错误候选 | ambiguous，不按答案选码 |
| decode_error | 单一候选但解码器报告校验/格式等错误 | decode_error，不将错误候选内容当真值 |
| execution_error | 解码调用异常或依赖不可用 | execution_error，保留错误类型 |

无独立答案时一律 `truth_check.status: not_provided`，读出不称正确。答案来自最多 64 KiB 的本地 UTF-8 文件，必须提供独立来源描述；不 trim、不去 BOM、不规范化 URL/Unicode。原始字节以 Base64 保存，显示文本不作为字节真值替代。来源是用户陈述，记录 `user_asserted_independent`，程序无法证明独立性；正式数据采样与真值复核仍属阶段 3。

新报告 `report_type: label_baseline`、schema 1，与旧图片报告 schema 2 区分；记录图像源哈希、预处理、分析 ID、配置哈希、ROI、解码器版本、源码哈希与 Git dirty 状态。顶层 `completed` 表示调用完成，不表示标签可读或编码正确。有候选解码错误或执行异常时 `completed_with_errors`，CLI 退出 2，仍可保存本次新结果；未读出、歧义或答案不匹配则退出 0，供调用方查看业务状态。输入/ROI/答案/输出错误返回明确错误码且不打印成功结果。

## 文件变化与兼容

- `src/analyze_image.py`：抽取 `load_normalized_image`、`calculate_image_metrics`、`image_analysis_config`，现有 `analyze_image` 与 CLI 复用这些函数。限额、EXIF 0 警告、指标、配置和原有结果字段保留；实现版本更新为 local-image-analysis-4。规范化图像仍在此模块，不重写指标核心。
- `src/label_analysis.py`：仅处理数组、ROI、QR 基线和答案比较，无文件/Web/UI 调用。解码依赖延迟导入，缺失返回明确执行错误，旧图片入口不依赖解码库。
- `src/analyze_label.py`：本地新入口，答案文件校验、整图/ROI 两次独立基线尝试、新报告与独占输出。版本 local-label-analysis-1。
- `tests/test_label_analysis.py`：33 项新测试。
- `requirements.txt`：仅增加固定依赖 zxing-cpp==3.1.1。
- `data/samples/stage2-known-qr.png`、`stage2-known-qr.expected.txt`：本项目用已安装 OpenCV 生成的样例，预先固定 payload `STAGE2-SMOKE-001`，答案文件无末尾换行。合成材料不是手机实拍或正式评测数据。
- README、本记录及设计文档进度：说明入口、状态、真实验证与下一步。

修改前检查 Git 状态，保留既有未提交工作。既有脚本、requirements 和说明文档在当前可写工作区 `camera-quality-stage2-review/YYYY-MM-DD_HH-mm/` 做文件级备份；写回仅限项目文件，不修改系统或注册表。原图只读，输出 `open('x')`，重新分析必须用新名字；无历史 CSV/JSON/图片迁移、覆写或 Git 提交。

本次输入安全核对的边界是本地用户提供图片、ROI 和答案文件：沿用解码前格式/字节/像素校验，ROI 不越界，答案限长并严格 UTF-8；文件路径不进入 shell，Git 查询为固定参数；只读原件，结果独占创建。JSON 序列化文本，不执行编码内容。保留程序与候选错误，不以无码掩盖异常。当前没有服务端认证或文件所有者隔离，也没有硬解码超时；本地 CLI 不作为安全公开上传服务。

## 解码依赖核查

已核对 [官方 PyPI 项目](https://pypi.org/project/zxing-cpp/3.1.1/)、[官方仓库](https://github.com/zxing-cpp/zxing-cpp)、[固定版本 Python 构建配置](https://github.com/zxing-cpp/zxing-cpp/blob/v3.1.1/wrappers/python/pyproject.toml)、[绑定源码](https://github.com/zxing-cpp/zxing-cpp/blob/v3.1.1/wrappers/python/zxing.cpp)和 Apache-2.0 许可证。PyPI 3.1.1 发布于 2026-07-29；匹配本机 CPython 3.12/Windows x64 的 wheel 为 `zxing_cpp-3.1.1-cp312-abi3-win_amd64.whl`，1003677 字节。

下载后计算 SHA-256，与 PyPI 元数据一致：`29f98a91148171460b47a942d137ecc90c4b8097636f23cca65263a56bb025d3`。检查 ZIP 成员、METADATA、WHEEL：无 .pth、安装脚本或路径穿越项，无额外运行时依赖声明。以 `pip install --no-index --no-deps --no-compile <已核查本地 wheel>` 仅安装到项目 .venv，未运行源码构建。源码构建 CMake 有取依赖行为，本次不采用。未安装未来阶段依赖，不关闭 TLS 校验。

wheel 包含本机原生扩展，上述检查不等于对二进制做完整安全审计；仅对本机安装与功能测试作事实报告，不根据发布平台列表宣称跨平台实测。解码无主动网络访问设计，不自动打开 payload 链接，不上传用户图片。

## 自动验证

新测试用独立 OpenCV 编码输入生成 QR，并用 ZXing 解码，真值来自编码前已固定内容。覆盖：单码、无码、多码及不按答案挑码；中文 UTF-8、末尾换行不匹配；非 QR 排除；ROI 正确切片无补边、四角偏移、EXIF 6 转正后的选区；整图/ROI 指标分别计算；原图不变；重复分析新 ID、旧结果拒绝覆写；无效数组/ROI、损坏输入、答案编码/来源/大小、依赖缺失、候选错误、执行异常、MemoryError 与输出权限/写失败。

最终运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests\test_label_analysis.py -q -p no:cacheprovider --basetemp C:\Users\zex\Documents\ChatGPT\project1\stage2-label-tests-20261002-3
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider --basetemp C:\Users\zex\Documents\ChatGPT\project1\stage2-full-20261002-3
.\.venv\Scripts\python.exe -B -X utf8 -m pip check
```

观察结果：新测试 `33 passed in 1.42s`，完整新旧回归 `228 passed in 9.62s`，依赖 `No broken requirements found.`；源码与测试内存编译通过。项目没有独立 build/lint/type-check 配置，因此未声称运行这些工具。临时目录必须换新路径，pytest 会清理指定 basetemp。

## 本机运行证据与失败保留

独立 CLI 进程运行，结果放在当前可写工作区 `camera-quality-stage2-review/runtime-smoke-2/`，保留先前结果与失败轮次：

- 合成已知 QR：整图和 ROI 均有效读出，独立答案核对 correct，退出 0。写回项目后的 stage2-known-qr.png 再次通过独立 CLI 验证，退出 0、decoded、correct，报告源码哈希均可读取。
- 越界 ROI：退出 2、invalid_roi，无结果文件生成。
- 用户手机实拍 A1.jpg：3072×4096，方向 0 保持像素排列。QR 基线返回单一无效候选，错误类型 `ErrorType.Checksum`、错误消息为空，最终状态 decode_error、退出 2，无独立已知答案。没有得到有效编码，不能声称读码成功、实物编码错误或确认图片一定包含可读 QR。
- 旧 analyze_image.py 重跑 A1：退出 0，指标、预处理、配置及配置哈希与 phone-stage1-004.json 一致；源码版本与分析 ID 按本次运行更新，路径字符串采用本轮调用形式。
- 本轮前后 A1 SHA-256 一致，data/reports 原有 29 个文件的字节哈希均未变。未覆盖旧结果。

第一轮冒烟脚本误将 A1 的预期退出码设为 0，实际为 2，导致 AssertionError；不是成功读码。调查确认是候选码校验失败，最初代码把候选错误归入 execution_error。随后新增 decode_error 区分候选错误与运行异常，保留候选原始错误和非零退出，更新测试并重跑以上全部验证。没有删除或跳过失败样例。

## 用户实拍验收步骤

先确认 PNG 显示完整四周白边，打印项目样例或使用自己能独立核实编码的纸质标签。若使用样例，拍摄内容预先已知为 `STAGE2-SMOKE-001`；把实拍存为 `photo/stage2-label.jpg`，图片仍受 25 MiB/1600 万限制。不要从此次解码输出创建答案。

```powershell
# 合成样例验证（输出名须未占用）
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py '.\data\samples\stage2-known-qr.png' --expected-file '.\data\samples\stage2-known-qr.expected.txt' --truth-source '项目样例预先指定的生成内容 STAGE2-SMOKE-001' --output '.\data\reports\qr-synthetic-001.json'

# 打印后手机实拍，先整图基线
$photo = '.\photo\stage2-label.jpg'
$before = (Get-FileHash -LiteralPath $photo -Algorithm SHA256).Hash
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py $photo --expected-file '.\data\samples\stage2-known-qr.expected.txt' --truth-source '实拍的是项目样例打印件，编码内容预先固定' --output '.\data\reports\qr-real-001.json'
$exitCode = $LASTEXITCODE
$after = (Get-FileHash -LiteralPath $photo -Algorithm SHA256).Hash
"退出码: $exitCode；原图未变: $($before -eq $after)"

# 可选 ROI：以下坐标只示范格式，必须换为照片内标签区域并保留二维码白边
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py $photo --roi 100 200 600 600 --expected-file '.\data\samples\stage2-known-qr.expected.txt' --truth-source '实拍项目样例打印件' --output '.\data\reports\qr-real-roi-001.json'
```

核对原图方向、实际 ROI 坐标与独立答案来源，反馈各 attempts 的 decode.status、truth_check.status 及退出码即可。保留未读出、错误或歧义结果，不以重新拍摄成功抹去旧失败。自有标签用自己的 UTF-8 答案文件，避免编辑器新增 BOM/换行；不需要把私人图片或编码内容发到聊天。

## 局限、学习与下一步

只有合成 QR 证明基本路径可运行；A1 实拍未读出有效码。真实纸质 QR 的已知答案验证仍待用户完成，不能计算正确率或给出曝光/硬件根因判定。只支持单张图和一个人工 ROI，未提供鼠标选区、原生 App、手机网页、自动检测标签区域、增强分支或独立评测集合。

文件/像素/答案长度限制保留，但没有生产级硬内存限制、解码硬超时或并发控制；本机冒烟脚本的 30 秒 subprocess 超时不是产品功能。两次读码及指标增加耗时，不能从小合成图推断服务容量。PNG 色彩配置仍不转换，方向 0 仍需用户目视确认。二维码可能包含任意内容，程序仅记录，不执行链接。

学习练习：解释 ROI 为什么基于转正后坐标；用含多个码的图解释为何不能靠真值选择；对比 decoded 与 correct；解释 JSON 记录 payload 字节和显示文本的区别。当前用户掌握程度未考核。

面试问答：

1. **读出是否代表读对？** 不代表，只有与独立已知答案比较后才能判正确；无答案保持未知。
2. **裁剪后位置怎么还原？** 局部四角加 ROI 左上角偏移，得到规范化图像坐标；不是原始 EXIF 坐标。
3. **为什么记录解码器内部配置？** 默认降采样、反色等会改变基线尝试范围；显式配置才能复核比较。
4. **为什么多码不能挑一个答案匹配的？** 会把真值用于选择结果，夸大实际读取能力；需要人工指定目标区域。
5. **无有效码就是软件执行失败吗？** 不一定：无码、候选校验错误、程序异常有不同状态，原始错误必须保留。

下一步先完成本阶段真实纸质 QR 验证，之后阶段 3 才建设来源/真值清单、按标签分组划分与独立评测；不自动进入阶段 3。

## 用户 A2.jpg 整图读码成功记录（2026-10-02）

用户先用旧 analyze_image.py 分析 A2.jpg，随后实际运行 analyze_label.py 并提供完整输出，结果保存为 data/reports/qr-A2-001.json，分析 ID f6b6e0005f654c5199a0fc619661f447，状态 completed。源 JPEG/RGB，1279×1706、122596 字节，EXIF 1，未旋转、缩放或增强。整图解码返回单一有效 QR Code，decode.status 为 decoded，无解码错误；输出内容为微信域名 URL，仅记录，不访问或执行链接。解码耗时约 0.0477 秒、总分析约 0.2219 秒，均为本次运行记录，不是性能保证。

只读核对保存报告的分析 ID、有效候选数及当前原图 SHA-256，与用户输出相符。known_truth 与 truth_check 均为 not_provided，故本次证明 A2 文件成功读出，不能记为独立已知答案核对 correct，也不能据此宣称准确率。A2 的手机实拍来源与方向尚未单独确认，不把此前 A1 的来源确认移用于 A2。

可用人工 ROI (320, 1080, 240, 260) 对当前报告中的 QR 四角区域做功能验证，坐标在 1279×1706 图内，并比已解码四角范围留有外侧余量；是否包含足够白边需用户目视核对。该示例参考已读出的位置，仅用于选区功能核验，不能当独立评测样本选择方法。后续独立真值必须来自制作记录或其他独立核实来源，不复制本次解码内容充当真值。

本轮仅更新证据文档，没有修改代码或重跑自动测试。阶段 2 的真实已知答案验收仍待完成；不自动进入阶段 3。

## A2 手机实拍 ROI 实际验证（2026-10-02）

用户补充确认 A2.jpg 是手机实拍、方向正确，二维码业务身份为“图灵社区”微信服务号。这是用户提供的来源与业务身份确认，并非独立完整编码字节真值；此前“来源待确认”为当时历史状态。用户随后要求进行 ROI 验证。

助手实际运行项目 CLI，以 (320,1080,240,260) 为 ROI，独占新建 data/reports/qr-A2-roi-001.json；退出码 0，分析 ID faec95b0ea844baab7bba6ac8769cf29。整图 1279×1706、ROI 240×260，两次均 decoded、各有一个有效 QR，原始 payload 字节相同。ROI 四角加偏移后与整图返回坐标一致；未旋转、缩放、补边或增强。未执行二维码链接。

| 本次指标 | 整图 | ROI |
| --- | --- | --- |
| 平均灰度 | 126.1846 | 146.0831 |
| 暗像素比例 % | 7.0980 | 0.0577 |
| 亮像素比例 % | 0.9201 | 0.0032 |
| 拉普拉斯方差 | 159.2036 | 1175.1782 |
| 解码耗时秒 | 0.01239 | 0.00343 |

ROI 指标改变源于计算区域改变，不能解释为原图被增强、实际细节变清晰或读码准确率提高。本次两者已经均可读出；耗时仅是本机一次运行，不能作为性能保证。选区参考此前解码位置，只证明此选区功能可运行，不作为独立评测选区规则。

运行前后 A2.jpg 的 SHA-256 不变；data/reports 原有 31 个文件的字节哈希不变。新结果未覆盖旧结果。本轮未改代码、未重跑自动测试，此前最新完整测试仍是 228 项通过。检查本轮文档差异，只有新增验证证据；原图及历史 CSV/JSON/原始图片未改。

结论：本张手机实拍的 ROI 功能验证通过。truth_check 仍为 not_provided，整图与 ROI 一致不等于独立验证编码正确；真实已知完整答案验收待完成，保留该状态。不进入阶段 3。

## A3 提供答案但不匹配的实际案例（2026-10-02）

用户运行 A3.jpg，使用项目样例答案文件并填写“项目样例打印件手机实拍，生成内容预先固定”的来源描述，结果保存 qr-A3-known-001.json，分析 ID 583f71fac35d4a1cbcb26bbb2649afa2。600×698 JPEG 被成功解码，decode.status 为 decoded，单一有效 QR，但读出内容为与 A2 相同的微信域名链接；样例答案仍是 STAGE2-SMOKE-001，因此 truth_check.status 为 incorrect。

只读核对保存报告、当前原图哈希、答案文件哈希和 A2 编码字节，确认该不匹配确实存在。该结果说明与所提供答案不一致，不能直接证明解码器错误：A3 是否实际拍摄项目样例打印件尚待确认，命令中的 truth-source 描述只是用户陈述，不能作为客观来源证明。完整编码真值尚未独立核实，不把微信服务号名称充当完整 payload，也不从这次输出复制答案。

保留原报告的 incorrect，不修改答案文件、不覆盖原图或旧报告。若 A3 拍的是图灵社区二维码，应在新分析中不提供项目样例答案，记录正确性未知；若验证项目样例，应打印 stage2-known-qr.png 并实际拍摄该打印件，再用新的文件和结果名分析。本例作为实拍答案比较的不匹配证据保留，不进入正确率统计。阶段 2 的实拍独立答案成功验收仍待完成。

本轮仅追加记录，未改代码、未重跑测试或访问微信链接。

## A3 来源确认与新基线记录（2026-10-02）

用户明确确认 A3 拍摄的是图灵社区二维码，而非项目生成样例，因此此前将该图与 STAGE2-SMOKE-001 比较属于输入图片与答案材料不对应。这个来源确认解释了旧报告的 incorrect，不能把它作为解码器误读证据；旧报告仍保留，不修改已保存结果或答案文件。

用户随后实际运行不带 expected-file 的 analyze_label.py，保存 qr-A3-baseline-002.json，分析 ID d76636bd463846d6b54a69e04268f46c。状态 completed，单一有效二维码 decoded，无解码错误，known_truth 与 truth_check 均为 not_provided。只读核对保存报告与当前原图哈希一致，新旧报告读出的编码字节相同，旧不匹配报告仍存在且保持 incorrect。

当前业务记录为图灵社区二维码成功读出、完整编码正确性未独立核验。A2 的整图/ROI 实拍验证已通过，A3 的新基线状态正确表达了未知真值；阶段 2 的真实独立已知编码成功核对仍待项目样例打印件实拍或其他独立编码来源。没有计算准确率或自动进入阶段 3。本轮仅补充文档，无代码修改或自动测试重跑。

## A4 已知样例读码失败与 ROI 诊断（2026-10-02）

用户首次误写 stage3-known-qr.expected.txt，返回 expected_read_failed；随后使用正确的 stage2 答案文件，已成功读入预先固定内容 STAGE2-SMOKE-001，但 qr-A4-known-001.json 的状态是 completed_with_errors，整图 decode_error、truth_check decode_error，analysis ID 808b7c33028c481b8e010a4aa61d481c。候选 valid=false、Checksum，显示文本 N 是无效候选信息，不是有效编码，不能当读出或进行正确性比较。3072×4096 JPEG、EXIF 0，不执行方向变换并保留警告。

助手只读查看原图，二维码实际在中央，报告无效候选坐标靠近底部；当前候选与可见目标位置不对应。原图可见细密纹理及边缘模糊，但不能仅凭目视确定根因，也不能确定是否拍摄屏幕。纸质打印件/屏幕来源已向用户询问，命令中的 truth-source 仍只是用户陈述，不作独立来源证明。

使用相同 CLI 和配置再次运行整图，退出 2、decode_error，失败可复现；诊断结果保存当前可写工作区 camera-quality-stage2-review/A4-repro-full.json。提出并限定验证三个假设：背景干扰候选检测、基线对当前高分辨率定位的局限、拍摄细节影响。随后只改变分析区域，以人工 ROI (600,650,1900,1900) 包含中央 QR 及外侧余量，不降采样、反色或增强。实际整图仍 decode_error，ROI 为 not_decoded、无候选，truth_check 为 not_decoded；整个 CLI 退出 2，因为保留整图的失败状态。ROI 没有解决本例失败，不能把背景干扰当作已确认根因。

ROI 新结果保留为 data/reports/qr-A4-roi-002.json；原失败报告不覆盖。诊断轮次前后 A4 SHA-256 不变、data/reports 原有 35 个文件哈希不变；没有修改源码、解码配置、答案文件或旧报告。未运行增强或尝试依据答案选择结果，未访问 QR 内链接。无代码修复，不增加只针对本图的参数或弱化测试；本次是当前基线的失败案例，完整编码有效核对尚未完成。

下一步核实拍摄来源并保留 A4 失败证据，再以纸质已知样例重新拍摄新文件验证。不能据此推断曝光或相机硬件根因；本机一次诊断不是准确率评测，不自动进入增强或阶段 3。

## A4 来源补充与 A5 已知答案匹配（2026-10-08）

用户此前明确确认 A4 是拍摄屏幕上的项目二维码，因此 A4 应记录为屏幕拍摄，旧报告中的“纸质打印件”描述不符合实际；旧 JSON 原样保留，以此补充记录来源修订。不能把 A4 失败归因于已确定的屏幕干扰。

用户本次运行 photo/A5.png，保存 qr-A5-known-001.json，分析 ID 16b0ffa8036a44ca9f617389ae0a8711。状态 completed，单一有效 QR，decode decoded，payload 与拍摄前已固定的项目样例内容 STAGE2-SMOKE-001 逐字节一致，truth_check correct。源为 402×405、7714 字节 RGBA PNG，透明通道白底合成，未旋转、缩放或外部增强，无警告。只读核对保存报告、当前输入哈希和答案文件哈希一致。已知答案核对功能成功；不据单样例计算总体准确率。

来源字段填写“项目样例纸质打印件手机实拍”，该字段由命令手工传入，程序没有自动确认采集方式。A5 的实际来源（纸质打印件实拍、屏幕拍摄、截图或导出图）仍需用户明确确认；PNG/RGBA、小文件或尺寸本身不能证明任何一种来源。不仅凭命令文本宣布纸质实拍验收完成。此前自动测试 228 项通过是历史验证，本轮未修改代码或重跑测试；只补充成功结果与来源待确认记录。

阶段 2 的已知样例本地解码与字节核对已验证成功，纸质手机实拍的最后验收取决于来源确认；不自动进入阶段 3。
