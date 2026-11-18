# 离线显式索引适配验收

2026-10-15，批准 `Sentinel_bb553604c8c48191bda3ba9f6efcc060`。工作区 `/home/lenovo/projects/LocAgent-rag-preview`。已检查 README、相关模块和测试；该工作区及检查的上级目录未发现 AGENTS.md 或 .agents 技能文件，本改动不涉及已有列表中的平台技能。

## 差异

- `locagent_service/bailian_response.py`：保留 `text_index`，增加实际观察到的 `index`。每个存在的索引字段都要求 `type(value) is int`，拒绝 bool、浮点数、字符串、null 等；检查范围、唯一性和完整覆盖。双字段同时存在时必须相等。按显式索引重排，绝不以数组位置推断输入映射。审计结果标记 `native-explicit-index-v1`。派生安全副本也保留这两个整数索引字段。
- `tests/test_bailian_index_adapter.py`：新增 7 项参数化/子用例测试，覆盖两种格式乱序重排、混合格式、相等双字段、错误类型、越界、冲突、缺失、重复、覆盖不足和向量/usage 保护。
- `tests/test_bailian_raw_artifact.py`：原失败样本改为索引字段冲突，继续验证失败原始 body 留存、账本哈希和 unknown 状态。

未改传输层、原始 body 先保存流程、账本结算逻辑、预算或历史 manifest。维度、有限数值、非零向量、严格 usage、重复 JSON 键等原校验保留。旧 engine manifest 与新代码不匹配，不修改旧哈希以绕过保护。

## 验证

使用原虚拟环境运行 `verify_bailian_index_adapter.py`，进程内禁止 `socket.socket.connect` 和 `socket.create_connection`。测试集合为 `test_bailian*.py` 及 `test_rag_offline.py`、`test_rag_postgres.py`、`test_rag_review_regressions.py`、`test_rag_graph_adapter.py`。

**124 项测试通过，12.360 秒，0 失败。** 其中 70 项 Bailian 测试（63 项已有、7 项新增），54 项 RAG 相关回归。原始响应留存中断/磁盘失败保护一并通过。没有运行真实数据库集成、全项目测试或真实批量模型验证。

## 单输入离线回放

读取第三次真实调用已保存的私有原始 body，SHA256：`0e52e823740edb8f54a05265faf7813bceb43d90d03c6ffb51ca4f13d46ba8a2`。重新核对 request/manifest/binding 的关联，未改写原 body 或原失败审计。

新适配结果：**通过**，1 个 1024 维向量，归一化范数检查通过，usage 为 84 tokens；使用实际存在的 `index: 0`。仅另存离线回放结果，不结算旧账本、不把历史失败改成成功。

证据目录：`outputs/bailian-index-adapter-offline/`：

- `tests.log`：完整测试日志。
- `single-input-replay.json`：原始证据绑定、新适配器哈希与离线验证结果，不含向量全文。
- `protected-before.json` / `protected-after.json`：三轮实验目录全部文件、外部 manifest/锁及原学习区 README 的 SHA256，全部一致。
- `implementation.diff`：本轮真正的增量差异，相对修改前工作区文件生成。

累计真实调用仍为 **3 次**，本轮新增网络/模型请求 **0 次**；三笔账本均保持 unknown，累计预留 **CNY 0.540672**。没有读取凭据、启动服务、迁移、commit 或 push。

## 仍未解决的真实批量条件

本次只证明已保存单输入响应可被新适配器接受，以及合成多输入索引校验/重排正确，不能声称真实批量验收通过。批量运行前仍需确认该 endpoint/model 对 `index` 的输入对应语义，并取得新的数据范围、批量请求数与预算批准，冻结包含新适配器哈希的独立 manifest，继续绑定所有旧 unknown 预留和一次性防重放约束。

旧两次批量原始字节缺失，本次不能恢复其索引；不得用数组顺序或第三次单输入结果补造旧批次映射。尚未授权后续真实请求，本轮没有执行。
