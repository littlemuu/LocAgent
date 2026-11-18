> 历史验收快照，结论仅覆盖当时范围。后续真实案例见 [REAL_CASES](REAL_CASES.md)，当前整理验证见 [DEMO_VALIDATION](DEMO_VALIDATION.md)。

# 本地入口验收 · 2026-11-07

## 交付范围

新增 `python -m locagent_service.local demo|prepare|run`。真实路径复用现有固定 GitHub 来源、代码图、BM25、GraphLocalizer、严格 finish 和单题授权账本，去掉本地用户对数据库/API/worker 服务的依赖。不是新的向量检索实现，也不是脚本定位冒充模型输出。

`prepare` 不调用模型；`run` 要求完整计划哈希、`--allow-paid`、配置的凭据环境变量，消费独立的一次性授权。模型请求失败或中断不自动重放。返回源码存在性证据，保留模型/工具轨迹，不宣称定位正确率。

README 现在是本地安装主线；旧 README 原文保留在 `README_SERVICE.md`。`local_provider.example.json` 无任何凭据，故意保留无效占位符，必须核对当前模型、上下文与价格后才能生成计划。

## 环境与保护

- 在 Mac 的独立目录 `~/Documents/Codex/locagent-local-install-20261107` 实施。
- 基于原 `LocAgent-rag-preview` 的 a006f58 工作副本，复制 322 个 Git 管理或未忽略的源码文件，保留原有未提交修改；没有复制 `.env`、旧 outputs、旧授权或虚拟环境。
- 原 preview 的 322 个文件 SHA-256 与起始清单一致，Git status 也一致。原 `LocAgent` 仍只有原先的 `tests/run_stage5_compose.py` 修改。
- 未提交、未推送、未改动两个原 checkout，未读取真实 key，未做真实模型调用。
- Python 3.12.16。新建 `.venv-local`，从本机已有包缓存离线安装 `requirements-runtime.txt` 的 149 个包成功；随后为旧测试安装 service 依赖。不是沿用原虚拟环境冒充新安装；本次没有测试从公网包仓库重新下载依赖。

## 通过的检查

1. 新本地入口 16 项测试通过。真实 AST/图/BM25 + 合成 HTTP 响应验证三轮工具循环、源码片段、行号、hash、固定版本链接、预算结算、未知结果保留预留及禁止重放。
2. 最终代码相关三组回归共 **46 项通过**：`test_local_cli`、`test_public_authorization`、`test_public_pipeline`。包含实际 spawn 子进程的测试专用传输、重复运行拒绝，以及模拟超时、EOF、中断、启动失败清理。16 项包含在 46 项内，不能相加。
3. 在新环境执行 CLI `--help`、免费 `demo` 成功。demo 明确输出 `synthetic-demo`、零付费调用和 `demo.py:render`。
4. 最终代码执行真实 GitHub `prepare` 成功：`pallets/itsdangerous` 的 tag `2.2.0`，固定 commit 为 `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。真实下载、tree/blob 校验、静态图和 BM25 构建完成；`authorized=false`、`paid_calls=0`。使用的是合成 provider 配置，没有真实模型传输。
5. `git diff --check` 通过。只读复核提出的准备阶段监督、启动异常清理、Unicode 行分隔符证据问题已修复并回归；二次只读复核未发现本轮范围内阻塞问题。

最终相关测试命令（从项目根目录）：

```sh
TMPDIR="$(.venv-local/bin/python -c 'import pathlib,tempfile; print(pathlib.Path(tempfile.gettempdir()).resolve())')" \
PYTHONPATH="$PWD:$PWD/tests" LOCAGENT_ALLOW_PAID=0 \
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
.venv-local/bin/python -B -m unittest \
  test_local_cli test_public_authorization test_public_pipeline -v
```

## 全套结果不是全绿

全套执行 `LOCAGENT_ALLOW_PAID=0 PYTHON=.venv-local/bin/python sh scripts/check_local.sh`，发现 macOS 的 `/var` 临时目录与解析后的 `/private/var` 路径差异。初跑 **731 项，41 failures、113 errors、19 skipped**。已将测试进程 `TMPDIR` 规范化，未放松应用路径校验。

规范化后重跑 **731 项，1 failure、13 errors、19 skipped**：

- 11 个 errors（包括一个 setUpClass）来自历史 Bailian 冻结实验依赖未随 Git 分发的 outputs：protected-after、frozen manifest、ledger-audit 等；没有复制旧授权或编造这些文件。
- 2 个 errors 来自旧队列入口依赖 `torch`，本次 runtime 安装不含 torch；新本地入口不依赖该队列。
- 1 个 failure 来自要求 Linux PDEATHSIG 的父进程死亡用例，macOS 不提供这个 Linux 机制。

这些失败位置的业务/测试文件不是本轮改动项。保留失败证据，没有改断言、删除测试或把失败伪装成通过。全套之后只做了静默输出流退出时关闭的小修正，随后重新跑过上述最终 46 项与真实 GitHub prepare。

另一次把测试从 stdin 启动的临时检查中，macOS spawn 无法重载 `<stdin>`，造成一项测试失败；改为可导入的 `python -m unittest` 入口后 46 项通过。README 使用模块方式，不使用 stdin 测试入口。

详细日志保存在本地 `outputs/local-install-validation/`，不进入源码包。未运行 PostgreSQL、Compose、Linux 原生或真实模型付费验收。

## 仍需完成什么

- **真实模型端到端验收尚未完成。** 当前代码确实连通真实 provider 执行路径，但本次只能证明传输替身下的完整流程，不能据此宣称真实模型兼容性或定位质量。
- 下一次验收先确定一个问题/仓库/commit、具体接收方 endpoint 和模型，再核实该账户当前上下文上限及全包最高价格。使用自备 key，并明确批准生成计划中的总金额；不沿用历史价格、计划哈希或剩余额度。
- 预算依据：单次预留 = `(完整 context × 输入最高单价 + 输出 token 上限 × 输出最高单价) / 1,000,000`；三次调用最保守预算为单次预留 × 3。未核实当前价格前不提供虚假的确定报价。此次模型费用为零。
- 本地实现尚未发布；外部用户应使用包含这些新增文件的源码版本，不能假定旧远程分支已有该入口。
- macOS 没有本入口可靠的地址空间内存限额，子进程仍不是完整沙箱。完整旧实验套件的历史夹具/可选依赖/平台覆盖还需分别整理，不影响已验证的本地入口测试，但不能宣称所有仓库功能均已验收。
