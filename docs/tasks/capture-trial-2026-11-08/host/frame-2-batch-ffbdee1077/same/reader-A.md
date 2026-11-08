**P01 可以按“帧 2 范围内不再出现”关闭。** 两份报告的 `run_id=e6f899ecd3794dccbbbbfc54a62145be`，比较口径同为 `comparison_basis=current_algorithm_one_decimal`。

- 主报告 `01.json` 的 `declared_frame_counts=[1,2]`，`verified_frame_counts=[1]`。`issues[0]` 登记帧 2 的 `frame_unverifiable`，因此即使 `task_status=completed`，复核仍是 `verification_status=inconsistent`。
- 补充报告 `review.json` 只声明帧 2，`declared_frame_counts=[2]`、`verified_frame_counts=[2]`。`frames[0]` 对应帧 2，摘要匹配且五项指标与重算一致。`reported_samples`、`csv_pairs`、`verified_frames` 均为 1，`verification_status=consistent`，无问题码。帧 1 未在这次补充复核中重验。

交接时保留主报告的失败记录，将 P01 关联到补充报告的帧 2。按 SHA-256 前 16 位定位主报告 `5fee7591205c08a6` 和补充报告 `9c76f8ccbe385b17`。说明仅整理已有报告；原始报告和原图未附，要独立复算需另行索取。帧 2 原先无法核实的原因、是否发生过磁盘写入故障、整机是否恢复或合格均为未知。
