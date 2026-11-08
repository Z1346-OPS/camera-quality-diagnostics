1. 补充报告 `only-1.json` 实际只核实了帧 1。`declared_frame_counts=[1]`，`verified_frame_counts=[1]`，逐帧依据是 `frames[0] → 帧 1`，该帧摘要匹配且五项指标逐项一致。`counts` 中 `reported_samples=1`、`csv_pairs=1`、`verified_frames=1`，`verification_status=consistent` 仅适用于这一帧。

2. P01 仍未解决。主报告 `01.json` 的 `declared_frame_counts=[1, 2]`，`verified_frame_counts=[1]`，`frames[0] → 帧 1`。主报告 `issues[0]`（E03，`frame_unverifiable`）指向帧 2。两份报告的 `run_id` 相同，但补充报告没有帧 2 的逐帧核实记录，复验结论为“证据不足”。

3. 交接时保留两份报告的文件名及摘要前 16 位（主报告 `5fee7591205c08a6`，补充报告 `d81de6e365b8b1e4`），标记“P01／帧 2／未解决”。请下一位同事到原任务目录核对帧 2 原图是否存在、能否读取，再补交同一任务中明确定位到帧 2、摘要匹配且五项指标逐项一致的复核记录。说明未附原图和原始报告，帧 2 无法核实的原因未知；取不到证据时保留当前状态。
