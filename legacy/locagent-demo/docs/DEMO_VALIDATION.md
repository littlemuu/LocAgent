# 当前演示版验证 · 2026-11-08

## 本轮范围

在独立的 `locagent-demo-20261108` 整理 CLI/web 入口和说明，没有合入构造函数补读/后续阅读实验。没有修改或重启旧目录的服务，没有复制旧 web-runs、key、供应商私有配置、授权、账本或历史 verification。没有提交、推送、公开部署或调用真实模型。

## 安装：通过的是什么

- Mac Apple Silicon，Python 3.12.16。
- 本目录新建空 `.venv`，使用本机 uv 缓存离线安装 `requirements-runtime.txt` 的 149 个依赖；不是引用或复制旧虚拟环境。
- 边界测试另外安装 `requirements-demo-test.txt`，增加 5 个服务测试依赖；以 Python 自带 ensurepip 补齐 pip，`pip check` 通过。
- 初次 57 项回归在 runtime-only 环境运行，55 项通过，2 项因缺少可选 FastAPI 而报错。因此明确增加独立测试依赖文件和安装步骤；没有改断言掩盖错误。

可复现本次离线环境流程（需要自己已具备对应缓存和 Python，不保证任意电脑可离线安装）：

```sh
uv venv --offline --python python3.12 .venv
uv pip install --offline --python .venv/bin/python -r requirements-runtime.txt
uv pip install --offline --python .venv/bin/python -r requirements-demo-test.txt
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip check
```

不要覆盖已有 `.venv` 来重放；在新的源码副本测试。面对没有缓存的新机器，使用主 README 的标准 venv + pip 联网流程。

**未验证：空缓存从公网下载、第二台电脑、Linux/WSL2/原生 Windows。** 依赖包含历史 runtime，尚未最小化或构建跨平台 wheel/全哈希锁。不能笼统说“干净安装和跨平台已经验证”。

## 当前通过的免费检查

- **61 项 Python 回归通过**：CLI 16、web 11、公开来源/授权等 30、可移植启动包装 4。
- **7 项前端 JS 回归通过**；Node 语法检查通过。Node 为本机 ChatGPT 所附 Node；不是主应用运行依赖。
- `sh scripts/check_demo.sh` 完整通过：CLI help、合成 demo、上述 61+7 测试及 shell 语法检查。
- 合成 demo 明确返回 `synthetic-demo`、`paid_calls=0`、`demo.py:render`。
- 实际通过新启动脚本拉起生产 web 入口，在独立临时端口与独立测试目录走完 HTTP → demo 子进程 → 结果读取；没有 provider 配置、付费关闭、0 个付费标记，最后正常停止本次服务（exit 0）。不是仅调用测试替身 Controller。
- 所有源码 Python 文件 AST 解析、修改的 shell 脚本语法和新主要文档的相对链接检查通过。
- 原四个源码目录的文件 SHA256 与 Git status 在收尾核对一致；核心代码和 UI 静态资源与原 local-web 相同。
- 新主要文档与启动脚本无开发者绝对路径；源码包排除环境、私有运行记录和继承的生成式评测输出。常见 API key/私钥模式扫描未发现候选；这不是完备秘密审计。

真实图/BM25、工具循环、子进程和 loopback HTTP 都在测试范围内，但供应商 HTTP 和 GitHub archive 使用合成数据。测试用 `paid_calls` 字段中的数字是合成响应计数，不是计费流量。

## 没有重新验证的部分

- 本轮没有请求真实模型，历史两例见 [REAL_CASES](REAL_CASES.md)，不使用它们推断当前准确率。
- 本轮没有重新下载真实 GitHub 仓库；此前真实免费 prepare 记录按历史验收保留。
- 没有重新跑全仓库历史实验聚合、PostgreSQL、Docker 或 Linux 平台专用检查。历史全套不是全绿，不能将本轮 68 项定向检查替代全套结果。
- 本轮没有新的浏览器视觉/移动实机验收。UI 资源完全未变；既有浏览器与响应式检查见 [历史 UI 验收](LOCAL_WEB_SIMPLIFIED_UI.md)，当前另做了真实启动/HTTP 功能 smoke。

## 本机验证产物

`verification/` 保存安装日志、初次缺依赖结果、最终 `check-demo.log`、`pip-check.log`、启动 smoke、前后保护清单和包装审计。它不随可搬运源码包分发，避免携带本机路径、测试运行数据或历史状态。源码清单见根目录 `SOURCE_MANIFEST.json`，清单不对自身或环境/运行文件计算哈希。
