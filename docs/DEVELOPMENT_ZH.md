# 开发与复现

在项目根目录运行：

```sh
python3 scripts/check_integrity.py
./scripts/test_offline.sh
```

完整性检查核对复制清单及 v7 原始/最终锁；离线测试只运行自检 v7 的26项回归。工作目录是 workspace，解释器是 workspace/.venv-openhands/bin/python，默认用现有 Python 3.12 / OpenHands 1.62.0 环境，无安装和模型请求。测试产生临时夹具，不重跑真实验证。

源码可从 workspace/readonly_agent 和 workspace/experiments 继续开发，但被冻结代码的修改会使对应历史启动计划校验失败，这是预期行为；不要改写旧锁来让旧授权通过。新实验应使用新版本/输出目录并重新冻结。

## 本机依赖

- SDK环境：workspace/.venv-openhands → /Users/xiaomu/Documents/Codex/2026-11-12/task/.venv-openhands。
- LocAgent环境：legacy/locagent-demo/.venv → /Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv。
- 精确文件来源见 migration/copied-files.json；旧根到新根见 migration/path-map.json；源码快照收集见 benchmarks/sources。
- 原计划、索引证明和部分代码引用旧绝对路径；当前离线测试仍会读取这些原位置。不得删除原目录后声称可直接复现。
- .env未复制；旧代码的凭据选择逻辑保留原状，可能回退到旧LocAgent私有配置。本次操作及提供的离线命令不读取凭据。
- requirements-openhands.lock 和原 requirements 文件已保存。复制虚拟环境不能保证可移植，因此这里只提供本机链接；换机器时需按锁重建环境、重绑数据并产生新计划。

README和报告描述历史时点，不应直接执行旧文档中的付费启动、追加日志或构建命令。当前v7真实任务已经完成，既有授权已经消费。

## 本次整理验收

45,690个复制文件已逐文件SHA-256核对，v7原始/最终锁通过，130份源码快照已收集；26项关键离线测试通过（23.217秒）。新增导航的本地链接均存在。详见 migration/prepublish-validation.json 和 migration/offline-tests.txt。
