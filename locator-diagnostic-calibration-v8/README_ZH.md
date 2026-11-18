# C 组定位诊断校准 v8

这是独立的 `locator-diagnostic-calibration-v8`，不是项目已有的 `runtime/experiments/sdk_hybrid_v8`。历史 B/v7、历史冻结记录、Coding Agent 与 harness 均保持原样。当前仅完成离线验收；没有开机、SSH、付费 API 或 C 组评测授权。

- `calibration/locator.py`：C 定位器入口 `run()` 和与 B 相同的 `build_packet()` 外层封装。
- `calibration/policy.py`：仅定位器的证据覆盖、剩余预算阅读优先级、三段诊断与保守回退。
- `baseline/`：从 v5 交付所附 `unchanged-core-runtime-v4.zip` 精确提取的 42 个冻结依赖。原始 B 入口仍为 `locagent_e2e.agent.run`；这里的历史授权文件只用于原有测试，不构成新 C 授权。
- `delivery/REPORT_ZH.md`：按要求顺序的中文验收报告。
- `delivery/OLD_ANSWER_AUDIT_ZH.md`：五题旧终答共 50 句完整审计。
- `FREEZE.json`：独立配置和代码绑定。`delivery/SHA256SUMS.json`：交付文档与证据校验和。

从项目根目录复核（全部离线；不执行目标仓库代码）：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python locator-diagnostic-calibration-v8/scripts/run_offline.py baseline
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python locator-diagnostic-calibration-v8/scripts/run_offline.py new
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python locator-diagnostic-calibration-v8/scripts/verify_frozen.py
```

测试入口禁止网络连接、DNS、启动外部进程及 holdout 路径访问；原有虚构 holdout 路径拒绝测试照常保留。`audit_history.py` 仅解析十个明确列出的历史开发题定位文件，不执行响应中的命令；`build_delivery.py` 只生成新的独立冻结与估算文件。重建报告后应重新生成交付校验和。

未来获得 C 运行授权后，在隔离的单路进程内将本目录与 `baseline/` 加入 Python 模块路径，使用 `calibration.locator.run` 完成定位，调用 `build_packet(result, instance_id=..., base_commit=...)` 取得版本 1 定位包，再传给字节不变的 `locagent_e2e.agent.run(..., packet=packet)`。本轮没有增加会启动容器或调用 API 的 C 批量入口；不得把旧 A/B 授权用于 C，也不得直接运行历史 checkpoint 驱动来冒充 C。

校准是一种保守证据约束，不是根因正确性证明。完整行、函数体范围可机械检查，行为和关键调用链穷尽性不能据此证明；本版始终将推断标为待验证假设。自然语言同义表达的语义审核仍有局限。违规诊断会整体替换成保守内容，可能丢失有帮助的推断，因此需要未来获授权的真实 C 运行评价，不能用合成测试或旧回答回放证明效果。
