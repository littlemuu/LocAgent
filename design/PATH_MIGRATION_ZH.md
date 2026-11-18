# 新目录独立运行与旧路径处理

日常入口为项目根的 `./dev`。`project_config.json` 是唯一主机路径配置文件。运行代码依据配置与自身位置解析相对路径，不再导入旧工作区。命令：首次 `./dev bootstrap`，然后 `./dev test`、`./dev regression`、`./dev verify`。每次验证输出必须是新目录；已有同名输出时将其归档再运行，避免覆盖证据。`./dev encode` 只在 37 题回归通过后创建新编码输入锁，不调用服务；冻结目录存在时拒绝覆盖。

| 原依赖 | 处理 | 当前用途 |
|---|---|---|
| 历史主工作区（完整地址在配置 `original_workspace`） | 活跃运行时代码另存 `runtime`；原实验代码和记录保留原字节 | 只读历史档案，不参与日常测试 |
| 历史 SDK 虚拟环境，经 `workspace/.venv-openhands` 间接访问 | 根目录新建真实 `.venv`，从本地哈希锁轮包断网安装 | 旧 symlink 留作历史，不用于 `./dev` |
| 旧 legacy 环境与检索库，经 `legacy/locagent-demo/.venv` 间接访问 | 固定 bm25s/PyStemmer/numpy/scipy 到新依赖锁；纯算法参考放入 `vendor/legacy` | 只通过 AST 提取指定纯函数作等价回归，不执行旧入口 |
| 历史 benchmark snapshot、plan 中的绝对路径 | 将允许的 5,356 个源码文件成员复制到 `data/dev37/snapshots`，保留哈希；注册表使用项目相对路径 | 37 题源码来源，不需要原 snapshot 目录 |
| Linux 向量资产的旧地址 | 原样保留在已恢复的只读资产与 manifest；不是运行依赖 | 追溯已验证旧向量，不假装能复用到新文档 |
| `vendor/legacy` 参考脚本内原 `/home/...` 字面值 | 原字节保留；不执行该历史入口，测试仅抽取 rrf/entity_ranking 纯函数 | 例外清单：历史参考，不是活跃本机配置 |
| Python 基础解释器 | 唯一外部主机依赖写入配置 `host.bootstrap_python` | 已安装 CPython 3.12.16；不位于旧工作区；换机时只改此配置 |
| uv/pip 在线缓存 | 整理成 `vendor/wheels` 与 `requirements-offline.lock` | 离线安装用 `--no-index --require-hashes`，不依赖旧环境或用户缓存 |

依赖轮包共 138 个，来自现有安装的 dist-info/RECORD 校验后重新封装，保留包版本并固定重封装文件 SHA-256。它们不是原始 PyPI 下载文件，不声称具有上游原包签名验证。当前轮包用于 macOS arm64 / Python 3.12；云端 x86 Linux 环境须另行构建并固定依赖，不能拿 macOS 轮包直接部署云端。

离线主进程和检索子进程都安装 Python 级网络拒绝及旧路径 I/O 拒绝；清空服务凭据与观测导出环境变量，子进程用 `-I -B` 启动。守卫是针对已审查 Python 依赖的验证措施，不冒充 OS 网络沙箱。现有历史记录完整性另用迁移清单与 v7 原锁检查，不修改旧记录中的路径。

新代码允许同一实体有多个定义，definition_id 绑定快照、实体和行范围；排序仍按实体聚合，预览按检索匹配选定义并提示其他位置。长查询保持原始 Unicode 内容，限制改为 16,000 UTF-8 字节，所有检索边界共用验证器；普通字面文本搜索仍保留自己的 256 字符限制。
