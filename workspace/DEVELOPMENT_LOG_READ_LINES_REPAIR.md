
## 2026-11-13｜共享按行读取修复与检索选择假说：仅离线

- read_file改为start_line/end_line包含端点，一基源码行号；续页采用当前会话/快照/路径/范围绑定的不透明cursor，已签发游标可稳定重放并计预算。拒绝旧numeric offset、伪造或跨范围游标，不静默转换；返回实际行列范围，整行优先，长行可分片，空文件/空行/Unicode/CRLF均处理。两组同一schema/执行器/系统说明；其他工具next_offset保持原协议。
- core respond与SDK均进入LineReader，内部旧字符渲染仅保留历史诊断；搜索行号同步物理CR/LF规则。完整成功JSON计页/总字节预算，超预算保留终答。LocAgent实现和描述未改。
- 153项测试通过，覆盖行边界/类型/路径/冻结快照/Unicode/长行/重复与错误游标/证据编号/预算/SDK/终答/授权账本。SQLGlot原offset5960/5969错页与原回包逐字复现；分析者仅在离线夹具中显式迁为start_line，两组SDK各4脚本请求正常finish，实际含5969～5987函数及5977关键行，正文一致。未声称真实模型学会新接口或消除显式重叠请求。
- 三条批量MockTransport路径：正常16调用完成；收尾越界8调用停机；超时5调用保留模拟预留2.113536元。不发真实请求、不读凭据、不执行目标仓库代码；旧两份授权在读Key前拦截。历史2,263文件hash不变，未新增生产授权。
- source v5 hash 6d742955688ac21b2405cfea1f0cc1807560333e61aa72053ee6ab87c1cc9b79；live v3 hash 1286c563b5825f3ff56ee1b992f0502f4152311eb1430e5e465941b5d3202bd6，只冻结未授权。若日后真实验证仍最多16请求/34元，须新批准/价格核查。
- 仅基于旧轨迹及17组离线探测整理可检验假说：已知文件默认read_file、ID索引首步发现不足、普通搜索已给出候选、调查轮数限制、大结果预算利用率；每项区分证据与推测。优先在共同读取修复后再单因素研究描述/索引/预算，不强制检索、不宣称因果或独立评测。
- 报告 READ_LINES_REPAIR.md；验收 verification/read-lines-repair-v1/acceptance.json；回归 regression.log；SQLGlot回放sqlglot-replay.json。新真实模型请求0、费用0。
