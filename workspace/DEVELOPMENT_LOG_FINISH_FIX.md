
## 2026-11-12 北京时间｜首次真实试跑终答协议诊断与离线修复

- 用户报告 `Stopped: RuntimeError. No automatic retry.`。只读检查真实账本：基础组 3 次 DeepSeek HTTP 200，均 settled；模型成功 list_files/read_file 并找到 greeting 函数；检索组未启动。
- 结算费用上界 ¥0.008236，未知预留 ¥0；不是供应商实扣核验金额。保留原始失败结果、轨迹、授权和账本，未续跑、未消费剩余次数、未读取密钥。
- 根因：原生 SDK FinishTool 的 message schema/描述是自由文本，而本地适配器额外要求内嵌 JSON。模型返回自然语言终答，JSON 解析失败；正向脚本测试预先构造 JSON，漏掉协议矛盾。
- 修复：模型端显式 object schema（files/entities/answer），校验后转换为 SDK 原生字符串；原始回包不改写。保留第一个停机原因，终端输出可读原因和预算状态，不输出原始异常文本。
- 新增 6 项真实回包回归；SDK/预算等 46/46，核心/真实 LocAgent 26/26，总计 72/72。新双组完整离线回放各 2 次模拟 HTTP 均完成；没有新增真实模型请求。
- 修复方案 hash `6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd`，未授权。原授权限定一次试跑、出错即停；不自动新建 grant 或重试。
- 交付 `FIRST_LIVE_FAILURE.md`、`verification/FIRST_LIVE_INCIDENT.json`、`tests_sdk/fixtures/first_live_finish_incident.json`、`verification/deepseek-preparation-v3-finish`。原终答不自动改判成功，不作两组效果比较。
