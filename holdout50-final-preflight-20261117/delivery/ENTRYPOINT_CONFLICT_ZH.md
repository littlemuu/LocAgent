# 冻结入口冲突及待审阅方案

现有入口不能原样运行 holdout。尚未修改、替换或 monkeypatch 任何冻结函数；没有取消白名单、哈希或 evaluator 成员验证。

明确的冲突均位于 v5 共用的冻结 baseline 内：

1. `locagent_e2e/common.py` 的 rows()/manifest() 硬编码 `data/dev24`；allow() 只接受dev24题号；guard_holdout() 拒绝读取含 holdout-v1 的路径（ids.txt 例外）。
2. `locagent_e2e/checkpoint.py:Runner.image()` 调用 allow(identifier)；现有评分启动器使用 `locagent_e2e.evaluation`，只提供 development-scope 开关。
3. `locagent_e2e/evaluation.py:dataset_row()` 再次 allow，硬编码 dev24 evaluator.json 和其 receipt 哈希，强制数据条数等于24且集合与dev24完全相等。evaluate() 也调用 allow。不是换一个CLI参数就能用50题。
4. `driver.config_binding()` 把 dev24 manifest 和 receipt 纳入 a02c0341… binding。因此直接替换这些文件会破坏已有 binding；即使放入50题，evaluator仍会拒绝。
5. dev24 C 外层 run_c.py 的授权固定24题、holdout=False、C组和旧预算；不能复用这个入口。所有新运行需独立 once 状态和授权。

未发现已经冻结并通过验证的 holdout 执行入口。SDK和上游 SWE-bench harness 可以保持不变，Coding Agent、B/C定位器也可直接复用不变函数；但现有评分数据适配层不能原样复用。

供用户审阅的最小方案（未实现、未授权）：

- 新建本轮外层ABC单路调度，读取独立holdout元数据与授权；不修改57个C冻结文件或42个共用文件，逐次核验原binding。
- 新建独立 evaluator 数据适配入口，以原始 holdout名单/封存Parquet哈希/固定数据版本代替dev24的24题数据边界；只在隔离 evaluator 中读取测试patch与标签。模型侧只生成公开字段投影。
- 新入口复用同一 SWE-bench 3.0.0、commit d83e1001739f4d96add351d9ec0d56f4594a0d82，以及原 evaluate() 的评分调用、base reset与资源包装行为，包括历史上未生效的harness资源限制；不修复配置、不变测试、不变评分。
- 对数据适配差异单独生成diff、哈希与无模型离线检查；只验证名单隔离、once状态与调用契约，不试跑holdout，不重跑dev24，不用结果调试。

这会新增评分数据适配组件，不能宣称“现有冻结评分入口完全不变”。当前边界禁止擅自修改实验组件，所以此项需要用户明确允许后才能实现并另做离线核验。仅确认费用不能自动授权绕过这个冲突。若不允许新增该适配层，应维持未运行，不能开机后再临时取消验证。
