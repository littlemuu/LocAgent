# LocAgent 未被自主选择：离线分析与最小改进

后续真实验证已完成：[工具说明版试跑](ENV_REBOUND_LIVE_RESULT.md) 中出现一次自主 LocAgent 调用，证据传递与终答链核验通过。单次观察不证明描述修改的因果效果或检索收益。以下为此前离线分析记录。

状态更新：用户已批准文末试跑方案，一次性授权已登记，等待本机隐藏输入 Key；尚未启动。详见 [授权启动检查](verification/RETRIEVAL_DESCRIPTION_APPROVED_PREFLIGHT.json)。以下“未授权”描述为离线分析完成时的历史状态。

2026-11-12 北京时间。本阶段真实模型调用 0 次，未读取密钥、未创建授权。分析对象是已完成的跨文件试跑 `487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35`；保留其原始回包、请求、账本和终答。

## 真实轨迹可以证明什么

| 检索可用组响应 | 模型实际选择 | 已获得的信息 |
| --- | --- | --- |
| 1 | search_text("webhook") + list_files | 搜索命中 api.py 的说明文字；完整列出 10 个路径 |
| 2 | read_file × 4 | retry.py、worker.py、identity.py、receipts.py |
| 3 | read_file × 3 | api.py、backoff.py、http.py |
| 4 | finish | 正常结构化终答；明确 cleanup/metrics/reports 未读 |

前三次原始请求均提供 locagent_retrieve，tool_choice=auto；没有拒绝检索或执行检索失败的记录。第四次正常关闭调查，仅提供 finish。调查工具总使用 9/16 次、源码结果 3094/14336 字节，未触发调查工具或源码额度耗尽；但响应额度确实限制了调查轮次为三轮。源码总共 10 文件、2710 字节，文件名直接呈现 retry、identity、receipts 等任务线索；基础工具允许批量读文件。

模型第一条公开回复仅说开始定位 webhook delivery/retry，没有给出比较工具或放弃 LocAgent 的理由；后两轮公开 content 为空。不能从这些记录推导出模型内部偏好、训练习惯或认知原因。`tools` 列表列出了开放工具，不等于实际调用清单。

原 LocAgent 描述只有：

> Search LocAgent graph entities and source snippets. Use next_offset with the same query to continue.

它没有解释索引范围、查询形式、排名或与 search_text 的区别。代码事实是：精确 ID 可直接取实体；其他查询由 BM25 对图节点标识符进行词法排名，再返回源码片段。当前适配器未启用源码正文语义检索或调用关系遍历。

## 机制探针：人工选查询，零模型调用

通过现有独立子进程接口调用已审阅 LocAgent，静态解析同一源码快照；不执行样例代码，网络保护开启。完整输出见 [查询探针](verification/retrieval-choice-query-probes.json)。

| 查询 | 普通正文搜索 | LocAgent 当前输出 |
| --- | --- | --- |
| webhook | api.py 文档字符串命中 | No locations found. |
| retry | 定义、调用及 metrics 注释等文本命中 | retry.py 整文件与其中两个函数，第一页 1642 字节 |
| delivery_key | 定义、导入和调用命中 | identity.py 中 delivery_key 函数，487 字节 |
| dispatch/retry.py:schedule_retry | 无字面命中 | 精确函数源码，542 字节 |
| zzzxqv_nonexistent_92831 | 无命中 | No locations found. |

这些是人工选择查询的工具行为验证，不是模型自主选择，也不是质量评测。`webhook` 的空结果不能作为此次未选择的直接原因，因为真实模型没有看过它。`retry` 同时返回文件和函数，存在重复源码；这是输出特征，尚未量化其对选择或效果的影响。

## 推测与尚未排除的解释

- **基础工具已足够**：小样例、语义明确的路径和批量读取，使普通工具完成任务的成本较低。真实轨迹与此相容，但没有对照足以证明它是未选择的原因。
- **工具描述不够明确**：模型看不到适用查询与限制，可能难以判断额外工具价值。这是可单独改变的变量，不是已证实的归因。
- **三轮调查限制、工具排列或模型选择习惯**：也可能影响选择；本次没有分别操纵它们，不能归因。
- 未调用不代表检索失效，也不代表检索有益。真实自主检索证据链仍未验证；两组均成功终答只说明此次收尾和基础工具链可用。

## 已实施的最小改进

仅修改 `readonly_agent/core.py` 中 RETRIEVE 的描述，说明：路径/符号词法索引、最多五个实体候选、精确 path:QualifiedName 查询、返回带位置源码、可跨文件、无语义或调用图遍历，以及与正文搜索/已知文件读取的区别。使用通用术语，无 webhook/retry 等题目专属示例，没有要求优先或必须调用。

未修改题面、源码、工具名称和顺序、参数、模型、系统提示、逐轮控制、预算或检索算法。对比真实运行首个检索组请求与新离线请求，除 `tools[3].function.description` 外完全相同。冻结 plan 仅 runtime_hash 改变；旧授权不可复用。

验证结果：

- 原 SDK 工具/隔离/预算/收尾测试 **7/7** 通过：[日志](verification/retrieval-description-sdk-tests.log)。
- 双组 SDK → 模拟 HTTP → 持久账本回放各 3 次，均 completed；真实模型调用 0。
- 离线脚本指定一次 LocAgent 查询，真实检索返回的 1642 字节观察结果原样进入下一次模拟请求，并正常 finish；审计分类为 **scripted_fixture**，不是自主选择。
- 五个工具查询探针完成，网络尝试 0；原四个真实账本 SHA256 全部未变。
- 这些检查验证描述的实际出站内容、接口可用性和证据传输，不验证描述能否改变真实模型行为。

[机器核验汇总](verification/RETRIEVAL_CHOICE_OFFLINE_REVIEW.json) · [新冻结方案](verification/retrieval-description-v1/proposal.json)

## 下一次真实试跑提案（未授权、未执行）

方案 hash：`fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f`。

为只改变工具说明，继续使用同一 10 文件样例和原题目；deepseek-flash、非思考、每次最多 1024 输出 tokens；基础组和检索可用组各最多 4 次，总计最多 8 次，预算上限 **17 元**。发送原提示/题面、工具定义、源码证据、控制消息；检索组工具描述为本次修订。价格仍按此前核实的输入 2/输出 8 元每百万 tokens 保守计算，八次完整预留 16.842752 元；启动前重新核对当时账户价格。

判定预先固定：记录是否自主调用、参数、工具成功与否、证据是否进入紧接的下一次请求，以及正常终答；没有调用则仍记 not_selected，不补跑、不强制、不增加额度。异常立即停止。单次历史前后比较不能隔离供应商波动或证明因果/收益，只能提供一个新的自主选择观察。

本轮不改大样例或工具顺序，避免同时改变多个因素。若之后单独做强制调用，仅可称“真实传输连通性检查”，须另立方案和授权，不能计入自主选择成功。本次没有新增这种运行入口。
