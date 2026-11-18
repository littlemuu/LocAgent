# LocAgent 本地演示版

把一个公开 Python 仓库和问题，变成带固定版本、文件/函数、行号、源码片段和工具轨迹的定位结果。

这是基于 [gersteinlab/LocAgent](https://github.com/gersteinlab/LocAgent) 的工程化改造，不是从零实现论文方法。当前主线是 **本机浏览器工作台 + CLI + 代码图/BM25 + 明确确认的模型调用**。只定位，不自动修复或执行目标仓库代码。许可证：[Apache-2.0](LICENSE)；论文与上游贡献：[上游 README](docs/UPSTREAM_README.md)。

**本目录是 2026-11-08 整理的独立本地交付，不是已经发布到 GitHub 的版本。** 没有提交、推送、覆盖旧副本，或重新调用真实模型。两个远端分支的 README 仍是其他阶段，不能用远端旧 clone 代替本目录。版本关系见 [版本地图](docs/VERSION_MAP.md)。

## 最快演示：不需要 key，不产生模型费用

推荐 Python 3.12；支持目标为 macOS、Linux、WSL2。当前实际验证为 macOS Apple Silicon + Python 3.12.16；原生 Windows 尚不支持。

拿到**这份完整源码**后，在项目根目录：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python -B -m locagent_service.local demo
./start-local-web.command
```

浏览器打开 <http://127.0.0.1:8765>，点击「免费演示」。端口占用时运行 `./start-local-web.command --port 8766`，使用对应地址。Ctrl-C 停止本次服务。

这条演示使用合成代码和脚本响应，应输出 `mode=synthetic-demo`、`paid_calls=0` 与 `demo.py:render`。**它不查询输入仓库，也不证明真实模型定位能力。** 新目录不附带任何真实 key、旧任务或已用授权；默认付费关闭。

首次安装需要包仓库网络。当前复用完整 runtime，尚未裁剪最小依赖或做跨平台锁定。本次在新的独立 venv 中从本机缓存离线安装并验证，不等于已验证空缓存公网下载或其他电脑的一次安装成功。详细记录：[当前验证](docs/DEMO_VALIDATION.md)。

## 三条路径，不要混淆

- **免费合成演示**：CLI `demo` 或网页「免费演示」。可离线运行，用于展示界面、结果结构和入口连通。
- **真实仓库免费准备**：CLI `prepare` 或网页「免费准备」。联系 GitHub，固定 40 位 commit，验证源码并建立图与 BM25；不联系模型供应商、不产生模型费用。
- **真实模型定位**：审阅计划、接收方、数据与总预算后，显式批准一次 `run`。调用自己的模型 key，可能产生费用。不会自动重试未知请求。

真实仓库准备需要先填写无密钥供应商配置，因为计划包含后续可能的接收方、模型与预算。示例配置故意不能直接执行：`locagent_service/local_provider.example.json`。不要把旧价格或历史许可当成当前授权。

操作手册：[浏览器工作台](README_LOCAL_WEB.md) · [CLI、配置、费用与安全](README_LOCAL_CLI.md)。本轮只做版本整理，不启动新的模型测试。

## 已有真实案例，以及它们没有证明什么

后续两次 web 运行保存了真实模型响应、工具调用和固定源码证据：

- `pallets/itsdangerous`：关于签名时间戳验证与过期检查的问题，返回了 `TimestampSigner.unsign`、`TimestampSigner.validate` 等位置。
- `littlemuu/nano-vllm`：关于取消功能的问题，返回 `Scheduler.cancel`（42–62 行），同时包含额外文件/实体。

它们说明真实模型路径已经完成过两次，并非只有脚本预览。但 `status=success` 只表示提交合法结果；**两例不是准确率评测，也不证明泛化、构造读取改进有效或所有工具正文都被完整读过。** 完整口径、commit 链接与限制见 [两次真实案例](docs/REAL_CASES.md)。原始响应、问题记录、授权和账本保留在旧目录，不随本源码包分发。

旧数据库 fake preview、当前合成 demo、真实模型案例是三种不同证据。历史验收文档按当时快照保留，其“尚无真实验收”不覆盖后来两次运行。

## 一次演示怎么讲

[五分钟演示顺序](docs/DEMO_GUIDE.md) 包含运行步骤、技术主线、结果解释与限制。建议先展示免费入口，再展示固定 commit 的历史案例；没有新增消费授权时，不点击真实模型执行。

工程改造重点是：免数据库的本地入口、来源固定与校验、图/BM25工具循环、一次性计划同意、费用预留/结算、未知结果防重放、可核对源码证据及本机 UI。代码图和基础定位方法来自上游，个人改造与继承部分应分开介绍。

## 免费回归

```sh
.venv/bin/python -m pip install -r requirements-demo-test.txt
PYTHON=.venv/bin/python sh scripts/check_demo.sh
```

测试只用合成供应商响应，真实执行图/BM25、工具循环、子进程及 loopback HTTP。Node 可用时另跑前端测试；不运行旧实验或真实模型评测。设置 `LOCAGENT_NODE=/path/to/node` 可指定 Node。

本地入口测试不等于全仓库全绿。旧聚合曾因历史夹具缺失、可选 `torch` 和 Linux 专用测试在 macOS 上失败，见 [历史 web 验收](docs/LOCAL_WEB_ACCEPTANCE.md)。不复制旧账本来凑测试，不删改失败断言。

## 目录导航

- [项目开发日志：排错、修复与验证](DEVELOPMENT_LOG.md)：按日期记录近期修复、真实实验结论、未解决问题和证据。

- `locagent_service/local.py`、`local_web.py`、`local_web_assets/`：当前 CLI 与网页。
- `util/`、`plugins/`、`dependency_graph/`、`repo_index/`：复用的定位与静态索引实现。
- `docs/REAL_CASES.md`、`DEMO_VALIDATION.md`、`VERSION_MAP.md`：案例、当前验证、版本关系。
- `README_SERVICE.md`、其余验收文档和旧服务代码：历史服务/实验，保留供追溯，不是首选安装入口。
- `SOURCE_MANIFEST.json`：整理版源码的校验清单，不含环境、历史运行或密钥。

## 运行边界

仅可信单用户本机、公开 GitHub Python 仓库；无私有仓库、任意本地文件、dense/hybrid 或自动代码修复。网页固定监听 127.0.0.1，不支持公网部署。模型 key 只在本人终端隐藏输入，不写入聊天、网页、配置、命令参数或仓库。`runs/`、`web-runs/`、`provider.local.json` 及授权账本不得整体分享。

源码证据证明位置存在，不独立证明答案正确。超时、取消或断线不代表未计费；保留旧记录、停止自动重放。构造函数补读和后续阅读提示仍在独立实验副本中，**未合入本演示版，也没有声称其真实收益**。
