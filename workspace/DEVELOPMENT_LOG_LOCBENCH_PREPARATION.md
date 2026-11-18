
## 2026-11-13｜LocBench 两道已曝光开发题接入 OpenHands，离线验收

- 当前工作目录 `/Users/xiaomu/Documents/Codex/2026-11-12/task`。新增 `experiments/locbench_dev/`，冻结 `locbench_openhands/v3/manifest.json`，hash `45688f8a1c3a705b542d39573fcca9176d1e514edc81114de72f636fc0ddbf1c`；报告 `LOCBENCH_OPENHANDS_PREPARATION.md`。
- 旧流水线最新完整 batch101，当前引擎 strict-ready 106（development 29/test 77），历史任意引擎 113；batch102 只有目录，未见结果与验收，不声称已运行。仅检查总体元数据及选中开发题，没有打开未解封测试题内容。
- 选择 `Delgan__loguru-1239@65fe4a8db9a8f297ae3648f51b5e3050b30945a9` 与 `tobymao__sqlglot-3417@e1b6483d5e26d556f6a3dd82c6d35f475c189c2b`；既有开发曝光明确，不称独立测试。全仓 297/325 文件重新核验 SHA-256、Git blob/tree 和缓存提交证据；两组相同非隐藏 Python 投影 163/147 文件。题面逐字对齐，标签独立保存，映射到 AST 与补丁 old-blob；参考修改函数不等于唯一根因。
- 首次离线发现 LocAgent 源码校验按整行比较，误拒 AST 段末行注释：Loguru 13 节点受影响。改为 AST 类型/限定名称/起止行/精确 segment 校验，增加末行注释、Unicode、字符串空白与内容/跨度/名称伪造回归；不放宽来源检查。
- 第二次离线的 `traceback` 查询正确为空，但验收过严。保留词查询及空结果，另加文件列表首路径的显式脚本连通性查询；不修改检索算法或真实提示，不声称自主选择。v1/v2 冻结与中止记录全部保留。
- 最终四组正常 finish，16 次模拟请求，0 网络尝试、0 付费调用；检索结果均进入下一请求（包括空结果）。耗时 Loguru 基础1.88s/检索6.97s，SQLGlot 基础2.00s/检索30.74s，属离线本机开销。65 项测试通过，22 上游证据及746历史文件摘要不变。机器验收 `verification/LOCBENCH_PREPARATION_ACCEPTANCE.json`。
- 拟议真实范围：SDK1.62.0 + `deepseek-flash`（非思考），两题两组每组≤4请求，共≤16请求，每题≤17元、总≤34元，最保守预留33.816576元而非预计花费。2026-11-13 公价输入未命中2/输出8元每百万；账户未核验。发送题面、工具/系统提示、该题本组源码证据及历史，不发评分/补丁/另一组答案。
- 仍需完成两题真实批量入口、一次性授权与预算编排的离线验收，再核实账户/无重复并取得新批准。当前入口仅模拟；未读取密钥、未访问.env、未创建grant、未复用旧授权。实体ID BM25/精确取回、Python投影、小样本、曝光及图重建耗时是明确限制。

