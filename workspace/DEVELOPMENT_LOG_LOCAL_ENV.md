
## 2026-11-12 北京时间｜复用本地 .env 与显式密钥加载

- 用户要求后续不反复输入 DeepSeek Key。仅检查文件元数据发现原项目已有当前用户所有、普通单链接、0600 的 `.env`；未读取或输出其内容，未复制、覆盖、改权限。当前工作区没有 `.env`，优先复用原配置。
- 当前工作区新增 `.gitignore`（忽略 .env 变体、私有授权/验收目录及依赖）和无密钥的 `.env.example`。两个目录目前均非 Git 工作树；加载器在有 Git 时额外拒绝已跟踪或未有效忽略的 .env，避免误以为 ignore 能保护已跟踪文件。
- `readonly_agent.local_env` 提供 setup/check/status：用户本机 setup 先复用有效现有配置，缺失时隐藏输入并排他创建 0600 明文文件，不接受 Key 参数、不回退可见输入、不覆盖旧配置。status 只检查元数据，本次只对真实文件运行此命令。明确 .env 是本机明文而非加密。
- 复用已有 python-dotenv 解析能力，但不使用会导入旧付费开关的旧 configure 加载器。只提取 DEEPSEEK_API_KEY，不插值/执行、不导出环境变量；拒绝重复/坏配置、链接、其他用户所有、宽权限和过大文件，错误不输出内容或 traceback。
- live_run 新增互斥 `--env-api-key`，仅在当前授权、方案、未领取状态和本机 TTY 检查通过后读文件；原隐藏输入保留。密钥继续仅经匿名管道传给 helper，不进入 SDK、源码工具、轨迹或账本。
- 新增合成 Key 配置测试 12/12；SDK 全套回归 68/68，提取安全 CLI 错误入口后配置测试再跑 12/12。无真实 Key 读取、供应商请求、软件安装或系统安全设置改动。
- 历史四个真实账本哈希不变，已有 `fb1fca68…` 授权仍未领取且未改写；运行代码哈希变化使它与新代码不匹配。此次没有创建、迁移或消费真实授权，也没有执行旧试跑命令。后续继续试跑需另行审阅绑定当前代码。
- 用户只需在工作区运行 `.venv-openhands/bin/python -B -m readonly_agent.local_env setup` 做本机就绪检查；有效旧 Key 可直接复用，无需重复输入。不要求用户在聊天提供 Key。
- 交付：工作区 `LOCAL_ENV.md`、`verification/LOCAL_ENV_SETUP.json`、`verification/local-env-tests-final.log`、`verification/local-env-sdk-regression.log`。
