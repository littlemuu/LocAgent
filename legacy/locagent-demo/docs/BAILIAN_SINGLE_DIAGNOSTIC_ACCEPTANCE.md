# 百炼单输入诊断验收

2026-10-15。授权：`Sentinel_abb0aace377c81919fa44bb0aaac6c70`。独立工作区 `/home/lenovo/projects/LocAgent-rag-preview`，分支 `work/rag-offline-preview`。没有 commit、push、启动服务或修改原学习区/原数据库。

## 执行范围与结果

仅发送一次 HTTP 请求：原冻结 `pallets/itsdangerous` commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd` 中首个公开代码块 `src/itsdangerous/encoding.py:want_bytes`。原百炼北京 workspace host、原 native embedding endpoint、模型 `qwen3.7-text-embedding-flash`、1024 维。没有查询请求、生成调用、整批运行、自动重试或旧请求重放。

HTTP 200；传输入口调用次数为 1。收到 19611 字节完整 body，先原子保存，然后解析、投影和验证。原始 body 留在 WSL 私有目录，目录 0700、文件 0600；未复制到交付目录或输出完整向量。凭据只由原加载器读取供本次传输使用，未打印或另行保存。

完整响应结构的离线检查：

- 顶层字段：`output` 对象、`usage` 对象、`request_id` 字符串。
- `output.embeddings` 数组长度 1；元素字段为 `embedding` 数组、`index` 整数、`type` 字符串。
- `embedding` 长度 1024，全部是有限数值。
- **`index` 存在且等于整数 0；`text_index` 不存在。**
- `usage.prompt_tokens` 与 `usage.total_tokens` 均为整数 84；另有 `prompt_tokens_details` 对象，含整数型 `image_tokens` 和 `text_tokens`。
- request_id：`e10c75cb-3890-92e5-bac9-68cf8b103bb0`。
- 严格验证失败位置：`output.embeddings[0].text_index`，原因为缺失。新账本行因此为 unknown，执行停止。未放宽契约、未采用数组位置映射。

## 哈希和预算

| 绑定项 | SHA256 |
| --- | --- |
| manifest | `ae640623709973b0814575ff30ae6190b0a3503d601aa265f3bf88f874daaa61` |
| 单输入请求 body | `3e77a4d9063399c62bb53065f841807c08d81c974f31c9b724a95d01fcf6ffe7` |
| 原始响应 body | `0e52e823740edb8f54a05265faf7813bceb43d90d03c6ffb51ca4f13d46ba8a2` |

离线重算原始响应哈希，与 binding.json 及 SQLite 账本一致；请求、manifest、外部一次性标记相互绑定。两轮旧目录、manifest、锁标记的保护哈希全部保持不变；原学习区 README 哈希也保持不变。

旧 unknown 预留 **CNY 0.524288**；新增 unknown 预留 **CNY 0.016384**；累计保留 **CNY 0.540672**，未超批准上限。按已冻结费率与返回 usage 算出的观察值为 CNY 0.0000105，但不是提供商账单，不用于释放预留。账本 settled usage cost 为 0，不代表实际收费为 0。

## 实现与检查

- 新增 `locagent_service/bailian_single_diagnostic.py`：固定一次性入口；校验两份旧账本、原冻结数据与当前代码；仅允许一个 document，无 query；外部标记以 O_EXCL 创建且 fsync，不支持恢复/重复调用。manifest 独立绑定本次批准及累计预算。发生中断也不自动重新发请求。
- `locagent_service/bailian_live.py`：Journal 新增可选 approval 参数，默认仍为原批准；新账本 authority 使用本次批准，不混用授权。原路径默认行为保持。
- 执行前禁止网络运行全部 `test_bailian*.py`：**63 项通过，1.504s**。同时检查新 manifest 只有一个输入、无问题、预算相符、新 authority 正确绑定批准。
- 依次运行 `python -m locagent_service.bailian_single_diagnostic prepare` 和 `python -m locagent_service.bailian_single_diagnostic run`，使用项目原虚拟环境。
- 执行后以禁止 socket 连接的脚本离线检查完整字段结构、哈希、权限和历史证据。没有再次调用 run 来“测试”防重放。
- 此次未运行旧业务全量回归、数据库集成测试或多输入模型测试。

证据目录：`outputs/bailian-single-diagnostic-20261015/`，含 `manifest.json`、`authority.json`、`ledger.sqlite`、`response-000.body.bin`、`response-000.binding.json`、派生审计文件、`completion.json` 和 `offline-inspection.json`。外部 manifest 与锁位于 outputs 根目录。交付的 findings.json 仅包含结构、类型、允许的元数据与哈希。

## 最小后续修复建议（未实施、未授权进一步请求）

为这个已观察到的 endpoint/model 响应变体增加显式索引适配器：考虑读取 `index`，继续要求严格整数、范围、唯一性、数量一致；若同时存在 `index` 和 `text_index`，不一致必须拒绝。继续保留完整原始 body、usage 和向量校验以及 engine/manifest 绑定，补充离线缺失/重复/越界/矛盾索引测试。

本次单输入证据只能证明实际字段形状，不能单独证明多输入时 `index` 的语义或顺序保证。批量启用前还需核实对应 API 契约；不能据此次结果补造旧批次缺失的映射，也不能恢复旧 raw body。旧两批仍保持 unknown，不回填、不按数组顺序拼接。任何后续真实请求均须新范围与预算批准。
