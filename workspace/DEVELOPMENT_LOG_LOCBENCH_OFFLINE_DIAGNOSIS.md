
## 2026-11-13｜LocBench 两题轨迹、检索与参考映射离线诊断

- 对修复版四组原回包/工具结果/评分核对；两个检索组前三轮实际开放LocAgent且auto，调用0。无模型选择动机证据，不归因“不信任检索”。Loguru实际走测试文件路线，参考函数未读；题面强调补单测而参考补丁改实现，分开看任务建议与定位分。
- SQLGlot两组都从普通搜索获得参考函数名称，但read_file offset5960/5969是字符游标，实际完整行146～270/271，第二页3931/3940字符重复；未读到5969～5987行正文。Loguru offset100同样落到第7行。剩余工具/字节未耗尽，固定第4请求收尾。
- 固定当前实体ID BM25/精确读取，17组与普通搜索配对探测。全文题面999/1386字符均超256上限，显式拒绝，未静默截断。Loguru标题仅Logger.add约49KB，traceback/RecursionError/recursion均无候选；traceback普通搜索65行、含目标文件11行。SQLGlot标题前5无参考函数，SetItem仅表达式类；轨迹已有_parse_set_item_assignment检索目标第1，19行正文第一页1244字节。Loguru参考派生_format_list可第1/761字节，但标明oracle，不当自主发现。整文件检索Loguru耗尽14KiB也到不了目标函数。
- 原标签、base commit、old blob、AST区间及参考patch旧行匹配；四组分数精确复算。Loguru补丁实现重复帧压缩；SQLGlot明确把_parse_id_var换成_parse_column。精确实体返回源码与AST片段逐字一致。仅内存重建文本并ast.parse，不执行目标代码、不改标签。参考函数不是唯一根因/全面答案评分。
- 建议先给两组共同提供按行读取并保留独立分页游标，再验证短候选/正文索引等检索发现能力，最后研究自主选择；预先固定查询、预算和指标，oracle/强制调用单列。没有修改生产工具、提示、预算、检索或冻结方案。
- 17个检索子进程均用已审查工具与offline拒绝保护；不读取凭据，付费请求0、费用0。2,263份历史/冻结文件hash不变，未新增生产授权。报告 LOCBENCH_OFFLINE_DIAGNOSIS.md；证据 verification/locbench-offline-diagnosis-v1/acceptance.json 及轨迹、查询、静态检查JSON。已曝光开发题、知晓参考后的诊断，不是独立测试或盲评。
