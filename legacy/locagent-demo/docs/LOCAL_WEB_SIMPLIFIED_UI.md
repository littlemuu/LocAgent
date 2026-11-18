> 历史验收快照，结论仅覆盖当时范围。后续真实案例见 [REAL_CASES](REAL_CASES.md)，当前整理验证见 [DEMO_VALIDATION](DEMO_VALIDATION.md)。

# LocAgent 简化界面验收 · 2026-11-07

## 改动

首页只突出仓库链接、问题、免费准备与结果。改用简洁的浅色/深绿界面、中文状态与错误说明。分支版本、示例、历史任务和服务设置默认收起。结果用函数名、文件名、行号和可展开源码呈现；运行记录、账本与原始结果放入详情。

准备完成后单独展示本题费用上限、请求次数、完整问题、仓库、服务接收方、模型、配置单价与数据发送提示。付费必须单独勾选确认。源码版本、预留解释、计划校验码与完整配置仍可查看。终态任务隐藏不可用的再次授权操作，保留任务信息和历史授权摘要。

新增“换个问题”入口只切换视图，不提交请求。使用根路径 fragment `/#new`，不会增加任何后端路由。浏览器前进/后退与刷新已实测。

## 范围与安全

修改 `locagent_service/local_web_assets/` 的 HTML/CSS/JS；新增纯 JS 单元测试和此验收说明，补充 README。所有 52 个后端 Python 文件与改前 SHA256 一致，原副本、服务配置、密钥、旧任务、一次性授权及账本未改写。改前前端保存在 `verification/ui-before-simplify/`。

没有提交、推送或公网部署。没有重试旧未知任务，也没有发送真实模型请求。生产本机服务 8765 未重启或改配置；页面静态资源刷新即可生效。开始时看到的旧任务 `5075fe277b034cbd98d1b07730ef551e` 保持只读检查，页面明确提醒不可重试。

## 定向自动化验证

- `tests/test_local_web.py`：11 项通过，包含 host/origin/session/CSP、无密钥返回、精确计划同意、篡改检查、单活动任务、未知结果保留预留并拒绝重放、异常重启只读封锁。
- `tests/test_local_cli.py`：16 项通过，真实图/BM25 流程与合成模型；不联系真实供应商。
- `tests/local_web_ui.test.cjs`：7 项通过，无浏览器、无网络的 DOM 模拟测试，覆盖默认未同意、费用与接收方呈现、改计划取消同意、重复点击仅一次、未知响应后禁止重发、旧响应不覆盖新任务、根路径新问题、纯文本与安全源码链接。
- Node `--check` 通过。无新增依赖。

日志：`verification/ui-local-web.log`、`ui-local-cli.log`、`ui-javascript.log`。

## 浏览器验证

Chrome 实际操作；独立验证服务运行于 127.0.0.1:8766，付费关闭、移除 DEEPSEEK_API_KEY，使用独立 `verification/ui-free-runs`，完成后停止。未点击真实付费按钮。

- 免费示例完成：`8667c5aa5f874af698dc69c001e003bd`。
- 真实公开仓库 `pallets/itsdangerous@2.2.0` 免费准备完成：`9dcb07b26d374703b7fbc9aed7979056`。没有调用 AI；同意框和付费按钮禁用。
- 实测刷新后查看原任务、切换新问题并刷新、浏览器返回与前进、详情折叠。
- 旧未知任务使用中文说明，授权操作不可用；仅查看未重跑。
- 桌面与 390px 手机宽度目视检查，320px 窄屏 DOM 测量无横向溢出。390px 费用上限、接收方和同意区域可正常阅读。浏览器尺寸已恢复。
- 独立测试目录只有两个新任务，付费提交/运行标记均为 0。
- 截图仅保存本地验收：`verification/ui-desktop-final.jpg`、`verification/ui-mobile-consent.jpg`。

## 验证边界

这是 UI 改造的 34 项定向回归与浏览器免费流程验证，不是新的真实付费验收或模型准确率评估。没有重跑完整历史实验聚合；既有聚合缺少历史输入、torch 与 macOS/Linux 兼容问题详见 `LOCAL_WEB_ACCEPTANCE.md`，不宣称全仓库测试全绿。手机验证为桌面 Chrome 视口模拟，不是手机实机。浏览器出现的扩展警告来自扩展内容脚本，不是本地 app.js 错误。

## 重新运行前端单元测试

```sh
node --check locagent_service/local_web_assets/app.js
node --test tests/local_web_ui.test.cjs
```

此 Mac 可使用 ChatGPT 自带 Node：`/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node`。
