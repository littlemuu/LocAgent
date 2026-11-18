> CLI 操作手册。当前演示版入口与验证边界请先看 [README](README.md)；后续两次真实案例见 [实测摘要](docs/REAL_CASES.md)。

# LocAgent：本地安装，定位公开 Python 仓库

**本隔离副本新增浏览器工作台：** 启动、配置与安全说明见 [本地前端 README](README_LOCAL_WEB.md)，验收见 [LOCAL_WEB_ACCEPTANCE](docs/LOCAL_WEB_ACCEPTANCE.md)。页面直连下述 local prepare/run，默认禁止付费。

输入公开 GitHub Python 仓库链接和一个问题，准备固定版本的代码图与 BM25 索引，再用**你自己的模型 API key**运行 LocAgent，输出文件、函数/类、源码行号、片段、固定 commit 链接和工具轨迹。只定位，不自动修复或运行目标仓库代码。

本项目基于 [gersteinlab/LocAgent](https://github.com/gersteinlab/LocAgent) 改造，不是从零实现论文方法。原异步服务、评估和历史实验仍在；说明移到 [服务与实验 README](README_SERVICE.md)。许可证保持 [Apache-2.0](LICENSE)，上游贡献与论文引用见 [上游说明](docs/UPSTREAM_README.md)。

**本次是未发布的本地交付代码。** 这些新增文件尚未提交/推送，别人需要收到此交付版本，或等包含它的版本发布后再安装。不能把旧远程分支的 clone 当成本版已交付。

## 先区分三件事

- `local demo`：两节点合成夹具和脚本响应，免费、离线，只检查安装和接口。不是任意仓库定位。
- `local prepare`：真实下载公开仓库、固定 commit、静态建图/BM25、生成待确认计划。**不调用模型，不产生模型费用。**
- `local run`：真实 GraphLocalizer 工具循环，调用你确认的模型供应商。必须自备 key、核实价格并明确确认计划。不是 BM25 排名冒充模型答案。

本入口只执行 **BM25**，不提供 dense/hybrid，不下载 embedding 模型。本地入口已有无付费回归和两次后续真实案例，详见 [实测摘要](docs/REAL_CASES.md)。**两次案例不是系统定位准确率评估，也不代表本次整理重新调用了模型。**

## 1. 本地安装

支持目标为 macOS、Linux、WSL2；本次仅验证 macOS。推荐 **Python 3.12**。原生 Windows 暂不支持（使用 Unix 文件锁/进程资源限制）。本入口不需要 Docker、PostgreSQL、API server 或 GitHub token。

在收到的项目根目录运行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python -B -m locagent_service.local --help
.venv/bin/python -B -m locagent_service.local demo
```

首次安装会从包仓库下载依赖。当前复用完整 LocAgent runtime，包含一些本入口未使用的旧依赖，尚未做最小依赖裁剪。`demo` 应返回 `mode=synthetic-demo`、`paid_calls=0` 和 `demo.py:render`；它不需要模型 key。

## 2. 配置自己的供应商和费用上限

```sh
cp locagent_service/local_provider.example.json provider.local.json
```

用本地编辑器填写 `provider.local.json`。示例**故意不能执行**：必须替换所有 `REPLACE...`，并把 `context_tokens=0` 改为供应商公布的真实上下文上限。

- 示例 endpoint 指向 DeepSeek 官方 chat completions，但**当前模型名称、允许的响应 model、上下文上限及价格必须由你核实**。价格参考 [DeepSeek 官方文档](https://api-docs.deepseek.com/quick_start/pricing/)，不沿用历史实验价格。
- `input_per_million` / `output_per_million`：同一币种、每百万 token 的最高全包单价，包含账户相关加价；不要以缓存优惠扩大额度。
- `budget`：你允许本题消费的总金额；`currency` 是该金额与价格的币种。所有金额用十进制字符串。
- `max_calls=3`：最多三次模型请求，不是保证三次就能命中；每次最多输出 512 token。请求过大、预算不足或模型未按协议完成会停止。
- `pricing_confirmation`：记录核实日期、来源和适用模型/账户。不需要写账号、余额或任何密钥。
- 当前包装层仅接受 `full-context` 预留，不使用 token 启发式估计、过期的实验输入界限或历史授权。

**每次发送前预留：** `(context_tokens × input_per_million + output_tokens × output_per_million) / 1,000,000`。它可能远大于实际费用。总预算至少覆盖下一次完整预留才会发出请求；计划显示单次预留和最多调用次数的合计。账本按原始 usage 和你提供的最高单价结算，不是供应商账单，也不能弥补填错价格/上下文上限。

## 3. 输入仓库和问题，先生成计划

```sh
.venv/bin/python -B -m locagent_service.local prepare \
  https://github.com/pallets/itsdangerous \
  "Where is a URL-safe timed value serialized and signed?" \
  --ref 2.2.0 \
  --provider-config provider.local.json \
  --run-dir runs/itsdangerous-001
```

`--ref` 可省略，默认解析仓库默认分支；输出始终绑定完整 40 位 commit。每次使用**新的目录**，不覆盖原结果、索引或授权。输出的 `preview.json` / `plan.json` 应显示正确问题、仓库版本、接收方 endpoint、模型、金额上限及 `plan_sha256`。**先审阅它们，再运行下一步。**

`prepare` 只联系 GitHub；问题此时保存在本机，不发送给模型。它最多运行 300 秒，可用 `--timeout-seconds` 调整为 1–900 秒。失败留下的目录不会自动重用。

## 4. 自备 key，明确确认后运行真实模型

只在自己的终端输入 key，不发到聊天、不写进配置/命令参数/版本库。下面通过隐藏输入把 key 放进当前 shell 环境；不持久保存，程序不自动读取 `.env`：

```sh
export DEEPSEEK_API_KEY="$(.venv/bin/python -c 'import getpass; print(getpass.getpass("DeepSeek API key: "))')"

# 把下面的 SHA 替换成你审阅过的 preview.json 里的 plan_sha256。
.venv/bin/python -B -m locagent_service.local run \
  --run-dir runs/itsdangerous-001 \
  --approve-plan REPLACE_WITH_REVIEWED_PLAN_SHA256 \
  --allow-paid

unset DEEPSEEK_API_KEY
```

如果配置了另一个 `credential_env`，使用对应的环境变量。不要把未经核实的 endpoint 填入配置：key 会作为认证头发给该接收方。

执行意味着同意将**问题、代码片段、图/工具返回及对话轨迹**发送给计划中的模型供应商，并按所填价格和预算调用。仓库内容和问题可能包含敏感信息，请先检查。只想试安装时停在 `demo`；只想查看计划时停在 `prepare`。

`run` 不重新下载、切换版本或自动改用其他模型。它采用一次性授权、发送前持久化预留、原始响应留存和严格 `finish(files, entities)` 校验。最多运行 300 秒（可调 1–900 秒），没有自动重试或断点续跑。

## 5. 查看结果与证据

运行目录包含：

- `run.json`：进程结束状态。`completed` 仅说明流程结束，还要看 `status`。
- `result.json`：模型选定的文件、函数/类、token usage、原始输出、消息及实际工具返回轨迹。
- `evidence.json`：从固定源码重新提取的位置、原始片段、文件 SHA-256 和 GitHub commit 行链接。片段最多 40 行/12,000 字节，截断会标记；它证明位置存在，**不独立证明答案正确**。
- `authority/.../ledger.json` 及响应文件：单次请求的预留、结算、未知状态与审计证据。包含问题/代码/模型响应的文件都应留在可信本机，不要整个目录上传。

```sh
.venv/bin/python -m json.tool runs/itsdangerous-001/evidence.json
```

`status=success` 表示提交了合法位置，不等于定位命中；`empty` 表示没有最终位置；`iteration_limit` 表示未在额度内完成。退出码：0 为正常完成/计划/demo，2 为输入或准备失败，3 为需要人工检查，4 为 `empty` 或 `iteration_limit`。

## 出错时怎么处理

- `github_http_403` / `github_http_429`：匿名 GitHub 限流，稍后新建准备目录重试；不会偷读 GitHub token。
- `download_failed`：检查 GitHub 直连、DNS、TLS。下载不继承代理、不跟重定向，不提供降级绕过。
- `tree_limit` / `file_limit` / `links_or_submodules_unsupported` / `unsupported_python`：仓库超出支持边界；不要通过放宽校验强行运行。
- `preparation_failed` / `dependency_missing`：先核对 Python 3.12、完整 runtime 依赖及源目录。运行免费 demo/测试；不要用付费调用排查安装。
- `credential_environment_missing`：只检查配置的环境变量名和是否在当前终端导出，不把 key 打印出来。
- `plan_confirmation_mismatch` / 源码、索引或 engine 哈希变化：重新审阅当前代码并准备新计划，不能复用旧 SHA。
- `needs_review` / `execution_stopped` / `deadline_exceeded` / `interrupted`：保留整个目录，查看账本与供应商账单。**超时/取消/断连/非 200/无效 usage 不代表未计费。** 未知请求保留完整预留；同目录再次运行会被拒绝。不要清空账本或换目录自动重放。

配置、来源或索引检查失败会在模型请求前停止；运行中的失败可能已经消耗调用。进程被强制结束时 `run.json` 可能尚未写出，`run-started.json` 和授权记录仍阻止再次执行。需要新实验时必须重新审核、另行批准。

## 支持范围与安全边界

仅公开 `https://github.com/owner/repo` Python 仓库；不支持私有仓库、SSH URL、本地任意路径或上传 pickle。下载限制为 8 MiB、展开 32 MiB、最多 3,000 项、单文件 1 MiB。拒绝符号链接、子模块、LFS、路径穿越和无法解析的 Python。只读取 Python 源码，不安装或执行目标仓库依赖、测试、setup、hooks。

模型协议为非流式 OpenAI-compatible chat completions + function calling；不是对任意供应商的兼容保证。函数边界沿用原图解析器，动态生成对象、赋值别名及部分构造函数不一定能独立定位。BM25 对问题用词敏感，跨语言问句与代码词汇不匹配可能检索差。

本机目录需可信且仅当前用户访问；索引是本程序创建并校验哈希的 pickle，不接受别人给的 pickle。进程有墙钟监督及 CPU/文件/描述符限制；**macOS 不提供本入口的可靠地址空间内存限额**。没有完整 OS 沙箱、总磁盘配额或公网鉴权，不适合不可信多用户/公开部署。不得把子进程等同于安全沙箱。

## 无付费测试

```sh
LOCAGENT_ALLOW_PAID=0 .venv/bin/python -B -m unittest discover \
  -s tests -p 'test_local_cli.py' -v
```

测试使用真实解析/图/BM25与合成 HTTP 响应，验证入口和安全边界，不测真实模型质量。全套旧服务测试另需 `requirements-service.txt`，参见 [tests/README.md](tests/README.md)。早期验证记录见 [本地入口验收](docs/LOCAL_INSTALL_ACCEPTANCE.md)；本次整理验证见 [当前验证](docs/DEMO_VALIDATION.md)。
