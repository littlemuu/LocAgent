# 端到端开发试跑准备包

状态：准备代码完成；真实冒烟部分完成后异常停止；云端未运行；正式试跑未运行。完整说明见 `docs/E2E_PREPARATION_REPORT_ZH.md`。

目录版本名为 e2e-preparation-v1，当前运行配置版本为 e2e-dev24-prep-v2。唯一付费运行使用的旧 2,048 输出上限版本已保存在 archive/smoke-runtime-v1；当前 4,096 版本只做过离线验证，禁止恢复旧失败账本。

在本项目目录执行离线测试（不调用模型、不读取 holdout 内容）：

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

本地环境重建用 scripts/bootstrap_local.sh（要求父项目的 project_config.json、vendor/wheels 和 requirements-offline.lock；会下载额外锁定依赖，不调用模型）。云主机用 scripts/cloud_setup.sh，在专用 Ubuntu 24.04 x86 主机安装 Docker/Python/锁定依赖并建立 .venv-cloud。云端安装未实测；脚本本身不会启动任务或模型调用。

云端后续人工操作顺序：安装环境、重新登录取得 Docker 权限、离线测试、检查资源/数据/镜像，再另行获准启动独立冒烟。不得继续原 verification/smoke-run 失败目录。`driver plan` 和 `scripts/repository_batches.py plan` 只输出计划，不运行模型。Mac 不执行整个仓库镜像批次，只允许 smoke 选定的 2 张镜像。

```bash
PYTHONPATH=. .venv-cloud/bin/python -m unittest discover -s tests -v
PYTHONPATH=. .venv-cloud/bin/python -m locagent_e2e.driver plan --output run-plan
.venv-cloud/bin/python scripts/repository_batches.py plan --output image-plan
```

驱动将完整阶段及请求落盘，正常已完成步骤可跳过；失败、未决请求、改变代码/数据/镜像的恢复会拒绝。正式 trial 入口额外要求新的显式授权文件、匹配的开发集哈希、正预算及 Linux x86 平台。`config/trial-authorization.example.json` 保持 approved=false。切勿把示例改为 true 以绕过本轮停止要求。

工具仅在隔离的题目容器内运行。密钥必须通过 CLI 显式提供的私有 dotenv 文件读取，不能放入交付包或镜像。选定开发题的 evaluator.json 只给评测器，public.json 才是模型可见题面。不要运行父项目会打开 holdout Parquet 的全量验证入口；本轮专用测试与数据白名单不需要该文件。
