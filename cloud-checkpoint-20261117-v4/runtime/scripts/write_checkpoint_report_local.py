from pathlib import Path
import json,datetime
out=Path('outputs/e2e-checkpoint-v4');s=json.loads((out/'round-summary.json').read_text());sm=s['smoke_acceptance'];rows=s['trial_rows'];decision=s['checkpoint']
def yn(x):return '是' if x is True else '否' if x is False else '未运行'
def edit(row):return str(row['first_source_edit_request']) if row.get('first_source_edit_request') is not None else ('未编辑' if row.get('status')=='completed' else '未运行/未确认')
lines=['# LocAgent 四组冒烟与前8题试跑报告','', '日期：2026-11-17。只使用已曝光的dev24；holdout 50题内容未读取。','', '## 四组验收结果','']
if sm:
 lines += ['四组在新适配器下均完成编码流程与官方harness，无技术异常。Astropy A为本轮新跑；其他三组为原始响应离线回放（零新增模型调用），补丁与历史记录逐字节一致，并重新评测。回放是兼容性验收，不能当作新的模型性能样本。旧失败记录原样保留。','', '| 题号 | 组别 | 验收方式 | 空补丁 | 首次源码编辑请求 | resolved | 耗时/秒 |','|---|---|---|---|---:|---|---:|']
 for r in sorted(sm['episodes'],key=lambda r:(r['instance_id'],r['arm'])):
  lines.append(f"| {r['instance_id']} | {r['arm']} | {'新跑' if r['execution_mode']=='live' else '原响应离线回放'} | {yn(r['empty_patch'])} | {edit(r)} | {yn(r['resolved'])} | {r['wall_seconds']:.2f} |")
else:lines+=['四组验收未全部通过；未完成项见原始状态记录。']
lines+=['','## 前8题表格','', '按冻结selection_order前8题，每题A→B，单路执行；没有按历史结果挑题。下表B组的token、费用和时间包含该题定位，A组无定位输入。费用是响应usage按缓存命中和调用时段的计量估算，不是账单实扣。时间含定位（仅B）、编码与评测，镜像下载和环境准备另外计入总墙钟。','', '| 序号 | 题号 | 组别 | 空补丁 | 首次编辑请求 | resolved | 输入/输出token | 费用估算/元 | 耗时/秒 |','|---:|---|---|---|---:|---|---:|---:|---:|']
for r in rows:
 ran=r['status']!='未运行';c=r['total_cost'];tokens=f"{c['input_tokens']:,} / {c['output_tokens']:,}" if ran else '未运行';fee=f"{c['metered_cny']:.6f}" if ran else '未运行';elapsed=f"{r['total_seconds']:.2f}" if r.get('total_seconds') is not None else '未运行/未完成'
 lines.append(f"| {r['number']} | {r['instance_id']} | {r['arm']} | {yn(r.get('empty_patch'))} | {edit(r)} | {yn(r.get('resolved'))} | {tokens} | {fee} | {elapsed} |")
completed=[r for r in rows if r['status']=='completed'];trial=s['trial_cost'];total=s['round_cost'];smc=s['smoke_live_cost'];byarm={arm:[r for r in completed if r['arm']==arm] for arm in ['A','B']}
lines+=['','## 是否满足继续条件','']
if len(completed)==16:
 empty=sum(r['empty_patch'] for r in completed);resolved=sum(r['resolved'] is True for r in completed)
 lines += [f"前8题16次编码/评测全部完成：空补丁 **{empty}/16（{empty/16:.1%}）**，resolved **{resolved}/16**。"]
 if empty>8:lines+=['**触发止损：空补丁率>50%，不继续后16题。**']
 else:lines+=['**空补丁率≤50%，满足本次空补丁阈值，但已按要求在8题检查点暂停；后16题未运行，不自动继续。**']
 for arm,rr in byarm.items():lines.append(f"- {arm}组：空补丁{sum(r['empty_patch'] for r in rr)}/{len(rr)}，resolved {sum(r['resolved'] is True for r in rr)}/{len(rr)}。")
else:lines += [f"只完成{len(completed)}/16次编码与评测；检查点未完整到达，不能判定继续条件。失败位置：{s['failed_step'] or '无，仍需检查运行状态'}。后续未运行，不自动重试。"]
lines += ['',f"前8题实际发起{trial['requests']}次模型请求，输入{trial['input_tokens']:,}、输出{trial['output_tokens']:,} tokens；API计量估算{trial['metered_cny']:.6f}元，保守上界{trial['upper_cny']:.6f}元。",f"本轮总计（含新增Astropy A冒烟；回放不收费）{total['requests']}次请求，输入{total['input_tokens']:,}、输出{total['output_tokens']:,} tokens；API计量估算 **{total['metered_cny']:.6f}元**，保守上界 **{total['upper_cny']:.6f}元**，预算50元。未决请求{total['uncertain_requests']}次。",f"本轮驱动从开始至最后完成步骤的墙钟约{(s['last_completed_at']-s['started_at'])/60:.2f}分钟，包含冒烟回放、镜像准备和执行；不含开机前本地开发、回传和关机操作。服务端实际模型标识：{', '.join(s['models'])}。",'', '计价依据：[DeepSeek官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。峰时每百万token：缓存命中0.04元、未命中2元、输出8元；空闲时段半价。本轮按北京时间各请求开始时间归档计价，跨时段边界的最终账单可能有小幅差异。云主机/磁盘/公网流量不包含在API金额中，云账单实扣未读取。','', '## 修改、验收和统计口径','', '- Coding Agent仅增加非空纯文本、assistant角色、finish_reason=stop、无工具调用/拒绝标记的终答兼容；使用SDK原生内容响应结束流程，不伪造finish工具调用。截断、拒绝、混合或空响应仍拒绝。定位器终答校验保持原样。','- 模型、提示、检索、工具schema和40次编码请求预算保持不变。B沿用v7自检+v6标识符BM25/源码预览及原终答，未加入dense或检索改进。','- 本地与云端22项离线测试通过；两题容器实际写入、撤销源码的统计验证通过。源码哈希/配置绑定和回归日志随证据包保存。','- 实际环境核验发现：harness容器为Docker bridge网络、未设置容器级CPU/内存上限（Memory=0、NanoCpus=0）；旧评测包装器中的限制未生效。本轮所有评测仍在同一16核/64GB主机单路进行，未中途更改。Coding Agent工具使用独立的无网络容器配置。后续需决定沿用本轮实际评测配置，还是修复限制后另行冻结配置；本轮没有中途改动，不能把评测容器描述为已限制6CPU/6GB。','- 首次源码编辑按工具执行前后实际内容变化计算，记录所属编码请求序号（从1开始），包含生产和测试代码、终端修改和编辑工具修改；未编辑为null。文档/配置、未跟踪且被忽略的生成物及/tmp不计；单个工具调用内写入后立即还原的瞬时变化不在观测范围。','- 空补丁按最终完整git diff是否为空判断，与首次编辑独立：曾编辑后撤回可同时有首次编辑序号且空补丁。','- 冒烟新跑与试跑共享50元账本，发请求前预留最大上下文峰时费用；失败/未决请求不自动重试。旧全量trial入口在本配置中被禁用，专用入口最多前8题。','', '## 结束状态和未运行项','']
shutdown=out/'shutdown-receipt.json'
if shutdown.exists():
 sh=json.loads(shutdown.read_text());lines+=[f"实例{sh['instance_id']}：{sh['state']}，{sh['mode']}；云端API密钥已删除，日志与补丁已备份。CPU/内存停止计费，云盘保留并继续计费；普通公网IP释放，下次开机应重新读取地址。"]
else:lines+=['关机状态尚待控制台核验，不能声称已关机。']
lines+=['','- dev24后16题×A/B：未运行。','- holdout50执行与内容读取：未运行。','- 完整混合检索改进组：未运行。','- 本轮不据8题开发试跑得出定位能提升端到端修复率的最终结论。','', '证据：round-summary.json、云端原始请求/响应账本、prediction.jsonl、patch.diff、harness日志、22项测试、配置冻结清单、关机截图。历史冻结记录未改写。']
(out/'REPORT_ZH.md').write_text('\n'.join(lines)+'\n')
print('Report written; complete trial episodes:',len(completed))
