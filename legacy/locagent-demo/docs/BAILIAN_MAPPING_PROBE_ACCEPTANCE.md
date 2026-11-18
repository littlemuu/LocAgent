# 小批量映射验证：因对照请求传输失败停止

日期：2026-10-15。批准：`Sentinel_4ced60ecff3c8191ad4bdceb94302de3`。工作区 `/home/lenovo/projects/LocAgent-rag-preview`，基线 HEAD `290c965a3321dd90d4e848dd924e3134ef10fc8c`。

## 结论

双输入请求格式和显式索引校验通过，但随后 A 单输入对照发生传输失败，未获得完整响应。依照失败即停规则，没有执行 B 对照，没有重试。**映射验证未完成，不能报告 A/B 对应关系实测通过。** 没有使用旧单输入结果替代本轮独立对照，也没有利用旧批量有损副本推断映射。

## 执行前冻结

输入来自原固定 itsdangerous commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`：A=`src/itsdangerous/encoding.py:want_bytes`，B=`src/itsdangerous/signer.py:Signer.derive_key`。两者内容不同，使用原 document 配置、原百炼北京 workspace host、`qwen3.7-text-embedding-flash`、1024 维。计划顺序是 A+B、A、B，最多 3 次新请求/4 输入项。没有查询或生成模型调用。

归一化向量比较阈值在调用前冻结：同输入 cosine >= 0.99999；最大分量绝对差 <= 0.001；同输入 cosine 比交叉输入至少高 0.01。报告 cosine、最大分量差及 L2 差。无法区分或数值偏差超限时报不确定，禁止调整阈值。

离线运行全部 `test_bailian*.py`，**75 项通过，1.649 秒**。新增测试确认正确映射通过、交换 A/B 被拒绝、相同无法区分的对照和数值不稳定被判不确定、无效向量被拒绝。离线进程禁止 socket 连接，然后才冻结 manifest。

manifest SHA256：`9c0d63376d582b7457b68ccb04d15304c47c885f8ea8839ecc990977c334b633`。manifest 绑定输入、请求 body 哈希、旧三轮证据哈希、当前引擎及新执行模块哈希、预算与比较方法。新模块每次只执行一个显式指定 step；持久 intent、外部授权锁和账本顺序防止重复。任何 unknown 会阻止后续步骤。

## 实测记录

| 请求 | 结果 | usage | 账本 |
| --- | --- | --- | --- |
| A+B | HTTP 200，2 个 1024 维有限非零向量，index 分别为整数 0、1；严格校验通过 | prompt=total=428 | settled（本地有效 usage 审计） |
| A | 传输失败；未返回 HTTP 状态、request_id 或完整 body | 未知 | unknown |
| B | 未发送 | 不适用 | 没有请求行 |

本轮传输入口调用 2 次，连同原三次累计 5 次。第二次是否已到达提供商、是否计费均未知。耗时约 15.147 秒，诊断 `raw_capture_unavailable:transport_failure`。当前代码没有保留具体失败阶段或异常类型，不能把它确定为连接、DNS、读取或代理问题，更不能据此宣称没有发送。

缺少两份独立单输入向量，因此同输入和交叉输入的 cosine、最大分量差、L2 差均为**不可计算**。没有补发请求或用其他历史数据填补对照。

## 原始响应证据

第一份完整原始 body 为 38937 字节，先保存、后解析；私有目录 0700、文件 0600。离线重新计算并验证绑定：

- request_id：`1b9025f7-5908-9785-9aba-549aa61ac890`。
- 请求 body SHA256：`9edd3cbfd96f50175b32a81366872cc9a9e88aa6e5fd3a5e4f20012dfb499344`。
- 原始响应 SHA256：`784189ff8246a17035d5d8ebae63fff29ba47a4853bdfca76249c86beece2e55`。
- binding、manifest、外部授权锁、请求记录及账本 response_hash 一致。

第二次没有完整返回 body，未生成伪造的原始响应文件。所有原始 body 只保留本机私有目录，报告不含凭据、请求头或向量全文。旧三轮所有保护文件及原学习区 README 哈希再次核对一致。

## 预算

| 项目 | CNY |
| --- | ---: |
| 原三轮 unknown 保留 | 0.540672 |
| 本轮双输入保守预留（校验通过后仍保留） | 0.032768 |
| 本轮 A 对照 unknown 保留 | 0.016384 |
| 本轮实际已预留合计 | 0.049152 |
| 累计保守占用 | **0.589824** |
| 其中 unknown 合计 | 0.557056 |
| 此次批准累计最高上限 | 0.606208 |

有效 428 tokens 按冻结标价计算估计 CNY 0.0000535；这不是已查询到的提供商扣费。失败请求 usage 和扣费未知，保留完整预留。未使用的 B 步骤预留没有入账；不会自动继续使用剩余额度。

## 交付与后续条件

新增 `locagent_service/bailian_mapping_probe.py`、`tests/test_bailian_mapping_probe.py`。实际命令使用原项目虚拟环境：冻结后分别执行 `python -m locagent_service.bailian_mapping_probe step 0`、`step 1`；没有执行 step 2。

证据位于 `outputs/bailian-mapping-probe-20261015/`：manifest、authority、ledger、两个 intent/report、第一份 body/binding/audit，以及 `offline-final.json`。后处理进程禁止网络，只核对本地证据。Windows 交付目录含预检日志、只含元数据的 findings 和代码 diff。

后续宜先离线增强传输诊断，只保留阶段与固定异常分类，不记录密钥或任意异常原文。若要再次获得独立对照，需重新明确一次性请求范围和累计预算，继续保留现有 unknown，并绑定新的 manifest/代码。当前 run 已 halted，本次授权不能用于自动重试或续跑。没有启动服务、迁移、commit、push、运行完整 32 块/10 题检索对照。
