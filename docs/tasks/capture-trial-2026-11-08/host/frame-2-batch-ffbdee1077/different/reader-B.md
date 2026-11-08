**P01 不能关闭。** 主报告 `01.json` 的 `run_id=e6f899ecd3794dccbbbbfc54a62145be`，`task_status=completed`，但 `verification_status=inconsistent`。声明帧号 `[1, 2]`，CSV 配对 2 项，`verified_frame_counts=[1]`。原批次的帧 2 仍有 `issues[0]=frame_unverifiable`。

补充报告 `review.json` 核实了另一批次（`run_id=2c72d699761043b89be433524834ace0`）的帧 2。`declared_frame_counts=[2]`、`verified_frame_counts=[2]`，样本、CSV 配对、已核实帧数各为 1。`frames[0]` 对应帧 2，图像摘要匹配，五项指标与重算结果一致，故该报告为 `consistent`。两份报告的 `comparison_basis` 均为 `current_algorithm_one_decimal`；同一帧号和口径不能抵消批次差异。

交接时保留 P01 为“未解决”，并列保存两份报告的文件名、run_id 和 SHA-256。向原采集任务索取帧 2 的原图、CSV 和原报告，核对对象、图像摘要与比较口径，再复核该帧。若取不到可比证据，记录“不可比较”。原帧无法核实的根因、是否已恢复及相机是否合格均未知。
