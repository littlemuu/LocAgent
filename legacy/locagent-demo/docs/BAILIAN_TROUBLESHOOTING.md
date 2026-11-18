# 百炼 embedding 排错记录与 RAG 验收边界

整理时间：2026-10-16（UTC）。事件发生于 2026-10-15；按阶段记录，不以文件本地 mtime 推断请求的 UTC 时刻。工作区 `/home/lenovo/projects/LocAgent-rag-preview`，HEAD `290c965a3321dd90d4e848dd924e3134ef10fc8c`；后续百炼模块和多数报告尚未提交。**本页是最新综合说明，链接的阶段报告保持当时快照，不回写旧结论。**

目前只完成有界响应契约、留存与小样本对照排错。32 代码块/10 查询的小开发集尚未完成真实 BM25/dense/hybrid 检索对照；它是读过源码后手工构造的非盲测集合，不能声称检索提升。

## 1. 首次及显式恢复：响应失败与证据缺口

- **现象**：首次 16 输入返回 HTTP 200，但 `response_invalid`；显式恢复同一 16 输入仍失败。
- **证据**：[首次诊断](BAILIAN_RESPONSE_DIAGNOSIS.md)、[恢复验收](BAILIAN_RECOVERY_ACCEPTANCE.md)。首次只留下原响应 SHA256、状态和耗时，无原 body、usage 或字段失败路径。恢复记录明确为 `output.embeddings[0].text_index` 缺失，16 个 1024 维向量，usage 1954，request_id `f3b9a7e0-054c-97b3-a8a0-fd07a5cd6a5e`。
- **已排除/未确认**：恢复的 model 未回显是允许情况，不是该次失败原因；首次具体失败原因未知，不能倒推为同一种字段问题。恢复的 safe.json 是有损投影，未保留未知字段，不能据它判断原响应是否含 index。
- **修复**：先增加固定字段审计；继而确认投影不能替代完整 body，转入原始字节留存修复。
- **验证**：诊断轮 49 项通过；恢复预检轮 53 项通过，分别见原报告，不相加。
- **遗留问题**：两轮原始 body 丢失，哈希不能还原内容；不能从投影重建原索引，更不能按数组顺序映射旧向量。两轮各保留 0.262144 元 unknown。

## 2. 原始留存与 native 索引适配

- **现象**：有损投影丢弃了可能关键的字段；后续单输入完整响应显示原生 `output.embeddings[].index=0`，没有 text_index。
- **证据**：[映射证据审计](BAILIAN_MAPPING_AUDIT.md)、[原始留存](BAILIAN_RAW_CAPTURE_ACCEPTANCE.md)、[单输入诊断](BAILIAN_SINGLE_DIAGNOSTIC_ACCEPTANCE.md)、[严格适配](BAILIAN_INDEX_ADAPTER_ACCEPTANCE.md)。完整原始响应 SHA256 `0e52e823740edb8f54a05265faf7813bceb43d90d03c6ffb51ca4f13d46ba8a2`。
- **已排除/未确认**：此前核对的[官方同步 embedding 文档](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)在 native 响应及 Flash 示例写 text_index；兼容接口是 `data[].index`。实测却是 native `output.embeddings[].index`，不是改用了兼容接口。本页整理仅离线，未重新联网检查文档。不能把这一单输入反推到旧两轮丢失的 body。
- **修复**：`bailian_raw_artifact.py` 在解析/投影/验证前写原始 body，以临时文件、fsync、同目录 hard link 原子发布且禁止覆盖，再保存请求/manifest/响应哈希绑定。body 和元数据分别原子发布，不是跨文件/SQLite 原子事务；中断仍保留 unknown。`bailian_response.py` 支持显式 index/text_index，拒绝 bool、非整数、缺失、越界、重复和不完整覆盖，双字段同时存在必须一致；只按显式索引重排。维度、有限非零向量、usage 校验保留。
- **验证**：原始留存轮 63 项通过；适配轮 124 项通过（70 Bailian + 54 RAG 相关）。已保存单输入 body 离线回放通过，仅另存结果，不改旧失败或结算旧行。
- **遗留问题**：单输入只能证实字段形状。完整 body 不可用时仍失败关闭；没有新增依据就不能恢复旧批量索引。

## 3. 双输入成功、A 对照传输失败与异常链丢失

- **现象**：A+B 双输入成功，两个向量的 index 为 0、1；随后 A 单输入约 15.147 秒失败，B 未发送，无重试。
- **证据**：[有界验证停止报告](BAILIAN_MAPPING_PROBE_ACCEPTANCE.md)。失败行 HTTP 状态、response_hash、tokens 均空，只有 `raw_capture_unavailable:transport_failure`。批量完整 body SHA256 `784189ff8246a17035d5d8ebae63fff29ba47a4853bdfca76249c86beece2e55`，usage 428。
- **已排除/未确认**：socket 配置 15 秒、整体定时器 60 秒；耗时接近 15 秒不能确定超时类别。旧 exchange 只在读完 body 后返回状态，空 HTTP 状态不证明没收到响应头，更不证明未发送。无法区分 DNS、TCP、TLS、读超时或包装内本地异常；不认定服务端故障。
- **修复**：定位到旧 `Journal.step` 的 `except BaseException`：原类型/阶段未持久化，随后 `raise ValueError(...) from None` 抑制异常链，编排层又捕获该固定异常。新增 `bailian_transport_diagnostics.py` 保存固定阶段、允许列表分类、已确认状态及布尔事实，未知归 unknown；主失败与清理异常分开。连接/socket/定时器清理不再覆盖主因。body 已完整读取但清理失败时仍先留存 body，再保持失败。超时、重试、预算策略不变。
- **验证**：小批量前 75 项通过；安全诊断最终轮 104 项通过（86 Bailian + 18 公开下载相关），见[安全诊断验收](BAILIAN_TRANSPORT_DIAGNOSTICS_ACCEPTANCE.md)。注入覆盖真实连接→exchange→Journal 链的各阶段、整体/操作超时、清理失败、响应头已读但 body 失败、敏感字符串不进入诊断。
- **遗留问题**：新诊断不能追溯恢复旧异常。`request_method_entered` 不等于字节送达；operation_timeout 不等于服务端故障。该失败继续 unknown，不能自动重试。

## 4. 补充 A/B 对照：格式通过，冻结数值标准未通过

- **现象**：新授权只补 A、B 各一次，均 HTTP 200、index=0、1024 维，usage 84/344；与保留批量比较后判定 inconclusive。
- **证据**：[对照验收](BAILIAN_MAPPING_CONTROLS_ACCEPTANCE.md)、`outputs/bailian-mapping-controls-20261015/offline-comparison.json`。冻结标准为归一化后同输入 cosine >= 0.99999、最大分量差 <= 0.001，并且同输入 cosine 比交叉输入至少高 0.01。
- **已排除/未确认**：请求重建字节 SHA256 与原绑定相同，A/B 文本、同一 host/path、模型 `qwen3.7-text-embedding-flash`、dimension=1024、text_type=document、output_type=dense 一致，均无 instruct。客户端记录中未见参数差异；响应未回显模型版本，后端不可见条件未知。不能将差异称为已获官方保证的“正常误差”或归因于版本变化。
- **修复**：本阶段没有为结果修改代码或放宽阈值；分别保存原始 body 和新账本，以旧批量做离线对照。
- **验证**：此次预检 104 项通过，属于另一次运行，不与安全诊断轮累计；两份新响应字节/请求/manifest/账本哈希绑定通过。
- **遗留问题**：同输入相似度虽然明显高于交叉输入，但两个数值等价条件未过，原实验仍不确定，不得事后改判。

| 对照（归一化后） | cosine | 最大分量绝对差 | L2 差 |
| --- | ---: | ---: | ---: |
| batch A / single A | 0.997305 | 0.009654 | 0.073413 |
| batch B / single B | 0.998302 | 0.006947 | 0.058267 |
| batch A / single B | 0.407182 | 0.118079 | 1.088869 |
| batch B / single A | 0.413964 | 0.122384 | 1.082623 |

## 5. 相同单输入已有对照：区别映射与数值复现

- **现象**：最早保留完整 body 的 A 单输入，与新 A 单输入自身也有数值差异。
- **证据**：两份 A 整请求 SHA256 均为 `3e77a4d9063399c62bb53065f841807c08d81c974f31c9b724a95d01fcf6ffe7`；A 内容 UTF-8 为 216 字节，B 为 1421 字节，对应各次内容哈希一致。只读重算 old A/new A：cosine 0.998325、最大分量差 0.006767、L2 差 0.057879。old A/batch A 为 0.997286/0.008805。
- **已排除/未确认**：五个现存向量原始范数 0.999673–1.000442，归一化后差异仍在。所有分量可精确 binary16 往返，但这只描述返回数值特征，不证明内部计算精度。双方舍入至三位小数后同输入最大差仍约 0.007–0.009，不能仅归因于末尾文本小数表示。仅凭这些样本无法确定差异根因，也不能单独归因于批处理。
- **修复**：仅澄清实验解释，不修改冻结标准、旧记录或适配代码。原阈值实际同时要求近乎数值复现，并不只是验证输入映射。
- **验证**：现存同输入 cosine 约 0.997–0.998，A/B 交叉约 0.407–0.414，对这两个样本的显式 index 对应有较强支持；这不是普遍索引契约证明，也不是检索提升证据。本页整理时重新离线核对旧/新 A 请求绑定和数值。
- **遗留问题**：此前研究未找到官方重复/批单确定性、容差、内部精度或固定版本保证；“未找到”不等于证明官方不存在说明。应先参考相应模型/接口官方说明或支持回复，缺失部分明确标注，不能编造保证。本轮未联网研究。

## 账本、证据与版本索引

最终为 **7 次传输入口调用、6 次有 HTTP 响应证据**；现存完整原始 body **4 份**，不是六份。失败请求是否到达提供商仍未知。unknown **0.557056 元**，总保守占用 **0.622592 元**，不是实际扣费。

差额 0.065536 元对应成功批量两输入及成功 A/B 单输入两项的完整预留。它们已经 settled 并按有效 usage 审计；现有 `Journal.report()` 仍将 settled 输入的完整预留计入总占用，不等于尚未记录 usage。实际提供商扣费未查询，unknown 不释放。

| 阶段（2026-10-15） | manifest SHA256 | 证据目录（outputs 下） |
| --- | --- | --- |
| 首次 | `0f7a528612306d2fa6d3047520b6c279ebdcca0e1edb6f615530dbf3c5fdd36b` | bailian-live-20261015 |
| 恢复 | `34c3c005ea86d08aaff7bb8e4c48218fea062c86c2704ad63bc83e7edcea902c` | bailian-recovery-once-20261015 |
| 单输入字段诊断 | `ae640623709973b0814575ff30ae6190b0a3503d601aa265f3bf88f874daaa61` | bailian-single-diagnostic-20261015 |
| 批量及失败 A 对照 | `9c0d63376d582b7457b68ccb04d15304c47c885f8ea8839ecc990977c334b633` | bailian-mapping-probe-20261015 |
| 补充 A/B | `1ea1d3b244615e14395d07e5dfe09b2696d64dffddebf916cc289657b0e56511` | bailian-mapping-controls-20261015 |

各 manifest 的 `engine_files` 是当轮代码版本依据；不能拿当前源码冒充历史版本，也不能修改旧 manifest 以绕过 hash 保护。当前相关实现为 `bailian_live.py`、`bailian_raw_artifact.py`、`bailian_response.py`、`bailian_transport_diagnostics.py` 和共享 `public_repo.py`。各阶段报告中的测试数量是单轮结果，包含重复执行，**不汇总相加**。

## 下一步计划（尚未执行，非付费许可）

1. **字段/索引正确性**：单独定义结构、类型、范围、唯一性、完整覆盖、双字段一致性及乱序重排验收；记录两个样本的有限映射支持，与官方契约差异分开说明。
2. **数值稳定性**：先查官方说明，分别设计重复单输入、批/单及批顺序对照，明确版本、精度信息可见性、样本量和容差依据；在新实验前冻结，不能倒改本轮失败判定。
3. **检索质量**：在独立新标准、输入清单、代码/manifest 和累计预算获批准后，再做 32 块/10 查询的 BM25/dense/hybrid 小开发集对照。保留固定标签/指标并说明非盲测；真实检索尚未完成，fake 链路通过不是质量证明。

全程保留旧响应、失败、授权和 unknown；不得凭剩余额度自动续跑。当前无新的付费执行许可。

## 后续探索性检索与独立复核（2026-10-16）

上文保留探索性检索执行前的历史状态。后续已完成原32块/10题内存检索及只读复核，见[检索验收与独立复核](BAILIAN_RETRIEVAL_ACCEPTANCE.md)。指标、全部dense/RRF排名和42项向量来源核验一致；dense在本开发集@3/@5多命中q04/q05/q08，固定RRF将其排到8/8/4。累计10入口、9次HTTP响应证据，unknown仍为0.557056元，保守占用1.277952元，并非实际扣费。旧数值实验不确定结论不变，不代表普遍契约或泛化质量已证明；未新增调用或调整参数。
