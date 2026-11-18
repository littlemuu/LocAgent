# B 组定位边界

B 明确定义为最近 v7 基线：v6 标识符 BM25 和原源码预览，加 v7 自检与原终答格式；不是早期完整混合检索。原 rank_candidates/preview/retrieve、SDK_SYSTEM、SELF_CHECK_INSTRUCTION、validate_finish 源码原字节保留；本轮不加入 dense、函数体检索或新的重排。

为让新 Verified 开发题可运行，新增仅负责基础提交源码构建的适配器：提取原 CodeAnalyzer（保留 __init__ 排除和重复限定名最后定义覆盖语义）、原 is_test_file，按源码快照建立标识符 BM25。BM25S/PyStemmer 版本、英文分词/停词与 top20 正分候选规则沿用原实现。新题没有旧索引，输入顺序固定为源码路径顺序；历史索引的文件系统遍历顺序不被声称可以逐字节复刻。

B 的定位终答原样装入 localization_packet.result，不再做新推理或改写。A 的包为 null。两组 Coding Agent 的 system prompt、tool schema、模型参数和编码预算相同，单元测试比较其哈希。B 的定位请求与费用另外记账。

Loc-Bench 37 题仍只用于定位开发；本轮 Coding Agent 与评测驱动的准入名单仅为已曝光 Verified 24 题，真实冒烟进一步只允许固定的两个 ID。
