# v8.2 旧测试口径变更说明（先说明，后修改）

v8.1 原文件不动。以下仅修改独立 v8.2 副本的测试预期；不修改 baseline 的 22 项测试。

| 原测试 | 冲突原因 | v8.2 调整 |
|---|---|---|
| DiagnosticTests.test_full_function_does_not_prove_chain_or_authorize_strong_claim | 原测试要求 R3 删除全文，与只由 R2/异常全回退冲突；明确假设中的 root cause 也不应视为确认 | 保留正文；root cause 假设无 R3，明确确认/无需修改仍列 R3 披露；不宣称调用链完整 |
| DiagnosticTests.test_no_evidence_fallback_preserves_unknown_candidates | 无阅读证据导致 R1/R4，现在应披露而非回退 | 保留原 files/entities/正文，附未知实体及未覆盖引用；全回退仍由独立 R2 测试覆盖 |
| V81Tests.test_fallback_is_fixed_and_never_revalidated | 原来用 R3 与 R2 比较相同回退，现 R3 应软门控 | 固定回退对比改用 R2；单次调用不复验断言不变，R3 另加软门控测试 |
| V81Tests.test_real_sympy_21379_finish_delivers_sdk_packet | 原真实回答+合成覆盖夹具会因 R1/R4 全回退，现应披露 | 仍验证可交付、原候选不变、无异常；改为正文原样保留且附披露。不是本次真实24题重放成绩 |

装饰器/重复定义旧测试保留：调查调度仍使用严格完整性，以保持提示、补读优先级不变；另加终答校验接受 def 起点的测试。原 R2 结构错误仍全回退，因此相关 SDK 旧测试无需修改。

测试使用固定 ScriptedTransport 响应、临时合成仓库，并封锁网络/子进程；包含历史 SDK 协议回归测试，不运行 dev24 Coding Agent 或 harness、不重新调用模型、不重新运行24题定位调查。
