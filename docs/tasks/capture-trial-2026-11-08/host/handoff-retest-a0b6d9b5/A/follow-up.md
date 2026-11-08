| 材料核对项 | 答案与直接依据 |
| --- | --- |
| 01.json 原始 frames 数组的元素总数 | 未知。两份说明在主报告技术详情中均只列出通过核实的条目 frames[0] → 帧 1。说明未附原始报告，也未给出数组长度。reported_samples=2 是声明样本数，verified_frames=1 是通过核实的帧数。 |
| 01.json 通过核实的帧 | 只有帧 1。verified_frame_counts=[1]，逐帧依据位于 frames[0]，对应摘要匹配且五项指标一致的帧 1。 |
| 01.json 原始 frames 数组里是否有帧 2 的记录 | 未知。declared_frame_counts=[1, 2] 且 E03 / issues[0] 记载帧 2 无法核实。这些字段说明帧 2 在声明范围内、未通过核实，但没有给出帧 2 在原始 frames 数组里是否存在条目。 |
| 02.json 通过核实的帧与定位 | 只有帧 1。补充记录 1 技术详情给出 verified_frame_counts=[1] 及 frames[0] → 帧 1。 |
| 03.json 通过核实的帧与定位 | 帧 1、帧 2。第二份说明的补充记录 2 技术详情给出 verified_frame_counts=[1, 2]，对应 frames[0] → 帧 1、frames[1] → 帧 2。 |