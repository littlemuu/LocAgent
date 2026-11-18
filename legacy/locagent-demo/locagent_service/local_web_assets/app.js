'use strict';
const $ = id => document.getElementById(id);
let session = null, current = null, job = null, busy = false, timer = null, generation = 0;
const uncertain = new Set();
const active = new Set(['preparing', 'running', 'demo_running']);
const labels = {preparing:'准备中', prepared:'等待确认', running:'分析中', completed:'已结束', needs_review:'已暂停', failed:'未完成', demo_running:'示例运行中', demo_completed:'示例完成'};
const storage = {get(){try{return localStorage.getItem('locagent.localWeb.job.v1')}catch{return null}},set(id){try{localStorage.setItem('locagent.localWeb.job.v1',id)}catch{}}};
const errors = {
  invalid_repository_or_ref:'仓库链接或版本不正确，请填写公开的 GitHub 仓库。', invalid_question:'请填写你想定位的问题，最多 8000 字。', invalid_job_id:'任务编号格式不正确。', job_not_found:'没有找到这个任务，请检查编号，或确认你打开的是原来的本机服务。', another_job_active:'已有任务正在运行，请等它结束后再开始。', provider_config_required:'本机服务还未配置 AI 服务，请先查看下方“服务设置”。', paid_disabled_or_credential_missing:'付费分析尚未启用，请查看下方“服务设置”。', plan_confirmation_mismatch:'这份计划发生了变化，不能使用旧确认开始分析。', plan_or_display_changed_needs_review:'任务信息发生了变化，已停止运行，需要先检查本机记录。', server_provider_changed_prepare_new_plan:'AI 服务配置已更改，需要重新准备并确认。', exact_plan_consent_required:'请先核实本次费用和数据接收方，再勾选确认。', execution_stopped:'分析已停止，结果尚不确定。请先核对服务商账单和本机记录，不要重试。', not_prepared_or_already_consumed:'这项任务不能再次运行。请查看已有状态。', already_consumed_needs_review:'这次请求已经提交，不能再次运行。', job_id_already_used_read_status_no_retry:'这项任务已经存在，请查看状态，不要重复提交。', interrupted_server_read_only_review_processes_and_ledger:'上次服务意外中断，目前只能查看任务。请先检查是否仍有运行中的进程和未结算费用。'
};
function humanError(code) {
  if(errors[code]) return errors[code];
  if(/interrupted|unknown|deadline|child_exited|execution_stopped|stopped_no_retry/.test(code||'')) return '运行中断，结果尚不确定。可能已经产生费用，请先核对账单与本机记录，不要重试。';
  if(/fetch|network|HTTP|session|origin|host/i.test(code||'')) return '暂时无法读取本机服务，请检查服务是否仍在运行，再查看最新状态。';
  return '这一步未能完成，请查看技术详情。系统没有自动重试。';
}
function error(message, detail='') {
  $('error').hidden=!message;$('error-message').textContent=message||'';
  $('error-details').hidden=!detail;$('technical-error').textContent=detail;
}
async function request(path, body) {
  const options={cache:'no-store',credentials:'same-origin',headers:{'X-LocAgent-Session':session?.session||''}};
  if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
  const response=await fetch(path,options),data=await response.json();
  if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
  return data;
}
function sourceChanged() {
  const demo=$('source').value==='demo';$('real-input').hidden=demo;
  for(const id of ['repository','ref','issue'])$(id).disabled=demo;
  $('source-note').textContent=demo?'用一段固定示例展示操作流程，完全免费。它不会分析你的仓库，也不代表真实 AI 的效果。':'先免费读取仓库，确认费用后才会调用 AI。';
  $('submit').textContent=demo?'查看免费示例':'准备分析 · 免费';controls();
}
function controls() {
  $('submit').disabled=!session||session.interrupted_fence||busy||active.has(job?.state)||($('source').value==='prepare'&&!session.provider_configured);
  $('run').disabled=busy||!job?.can_run||!$('consent').checked||uncertain.has(current);
  $('consent').disabled=!job?.can_run||busy||uncertain.has(current);
  $('new-task').disabled=busy||active.has(job?.state);
  $('restore').disabled=busy;
}
function remember(id) {
  current=id;storage.set(id);$('restore-id').value=id;
  const url=new URL(location.href);url.search='';url.hash='';url.searchParams.set('job',id);history.replaceState(null,'',url);$('permalink').href=url.href;
}
function pair(label,value,target='plan') {
  const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value??'未知');$(target).append(dt,dd);
}
function money(amount,currency){return `${currency||''} ${amount??'未知'}`.trim();}
// Read only the existing sanitized ledger. Never derive tokens from text or
// reinterpret budget reservations as charges; accounting remains server-owned.
function usageView(value) {
  const accounting=value.accounting, calls=Array.isArray(accounting?.calls)?accounting.calls:[];
  const currency=value.preview?.currency;
  const count=n=>Number.isSafeInteger(n)&&n>=0?n:null;
  const amount=n=>(typeof n==='string'&&/^\d+(?:\.\d+)?$/.test(n))?money(n,currency):'未知';
  const token=n=>count(n)===null?'未知':n.toLocaleString('en-US');
  const status={settled:'已收到用量',reserved:'已预留 · 等待结果',raw_received:'已收到响应 · 等待核验',outcome_unknown:'结果未知 · 需核对账单'};
  $('usage-card').hidden=false;$('usage-calls').replaceChildren();
  $('usage-note').textContent='Token 来自服务商返回并经账本核验；费用按本次计划配置单价估算，非实际账单。输入全部按配置输入价计算，未单独抵扣缓存命中优惠；以服务商账单为准。预留不是扣费。';
  if(value.demo||value.state?.startsWith('demo_')) {
    $('usage-summary').textContent='免费合成示例 · 真实模型调用 0 次 · 费用 0';
    $('usage-note').textContent='示例中的模拟用量不计入真实模型调用。';return;
  }
  if(!accounting||!Array.isArray(accounting.calls)) {
    $('usage-summary').textContent=['preparing','prepared'].includes(value.state)?'尚未调用模型。':'暂无逐次用量记录，不能据此认定费用为 0。旧任务未记录的数据无法补算。';return;
  }
  let input=0,output=0,known=0;
  calls.forEach((call,index)=>{
    const settled=call?.status==='settled',usage=settled?call.usage:null;
    const pt=count(usage?.prompt_tokens),ct=count(usage?.completion_tokens);
    if(pt!==null&&ct!==null){input+=pt;output+=ct;known++;}
    const article=document.createElement('article'),heading=document.createElement('h3'),tokens=document.createElement('p'),cost=document.createElement('p');
    article.className='usage-call';heading.textContent=`第 ${index+1} 次调用 · ${status[call?.status]||'状态未知'}`;
    tokens.textContent=`输入 ${token(pt)} token · 输出 ${token(ct)} token`;
    cost.textContent=`估算费用：${settled?amount(call.cost):'未知（可能产生费用）'}`;
    article.append(heading,tokens,cost);$('usage-calls').append(article);
  });
  const complete=known===calls.length;
  $('usage-summary').textContent=`${calls.length} 次调用记录 · ${complete?'已记录合计':'已知部分合计'}：输入 ${token(input)} token · 输出 ${token(output)} token · 已结算估算 ${amount(accounting.spent)}。待核对预留：${amount(accounting.reserved)}（非扣费）。${complete?'':'尚有调用用量未知，合计不含未知部分。'}`;
  if(!calls.length)$('usage-summary').textContent+=' 暂无逐次记录。';
}

// Render only saved, visible assistant/tool messages. Never infer private reasoning,
// replay tools, or join accounting rows to replies merely by array position.
function traceText(value) {
  return String(value??'')
    .replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/g,'[已隐藏私钥]')
    .replace(/\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_-]{16,}\b/g,'[已隐藏凭据]')
    .replace(/\bBearer\s+[^\s"',}]+/gi,'Bearer [已隐藏]')
    .replace(/((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|cookie)["']?\s*[:=]\s*)[^\r\n,}]+/gi,'$1[已隐藏]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,'[已隐藏邮箱]')
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi,'$1[已隐藏]@')
    .replace(/(https?:\/\/[^\s?]+)\?[^\s"']+/gi,'$1?[已隐藏查询参数]')
    .replace(/\/(?:Users|home)\/[^/\s]+/g,'/[用户目录]');
}
function traceSafe(value,depth=0) {
  if(depth>12)return '[内容过深，已省略]';
  if(typeof value==='string')return traceText(value);
  if(Array.isArray(value))return value.map(v=>traceSafe(v,depth+1));
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>
    [traceText(k),/key|token|secret|password|authorization|cookie|reasoning/i.test(k)?'[已隐藏]':traceSafe(v,depth+1)]));
  return value;
}
function traceDetail(parent,label,value) {
  const detail=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
  summary.textContent=label;pre.textContent=typeof value==='string'?traceText(value):JSON.stringify(traceSafe(value),null,2);
  detail.append(summary,pre);parent.append(detail);
}
function processView(value,result) {
  const target=$('process-steps');target.replaceChildren();
  const messages=Array.isArray(result.messages)?result.messages.filter(m=>m&&typeof m==='object'):[];
  const replies=messages.filter(m=>m.role==='assistant');
  const demo=!!value.demo||value.state?.startsWith('demo_');
  $('process-note').textContent=demo?'免费合成示例，不是真实模型调用。':
    '按保存的模型回复顺序展示工具请求与返回，不是模型内部思维链。回复序号不自动等同于上方计费调用序号；失败或未保存的调用可能没有回复。';
  $('process-summary').textContent=replies.length?`${replies.length} 轮已保存回复 · ${result.status==='success'?'任务合法完成，仍需核对定位是否正确':'任务状态：'+traceText(result.status||'未知')}`:
    '没有保存逐轮对话，无法还原每次模型调用。下方 JSON 仅供查看已有记录。';
  const names={explore_tree_structure:'查看目录与依赖结构',search_code_snippets:'搜索代码',read_tool_output:'继续读取工具输出',finish:'提交定位结果',search_entity:'搜索实体',get_entity_contents:'查看实体源码'};
  const idCounts=new Map();
  for(const m of replies)for(const c of Array.isArray(m.tool_calls)?m.tool_calls:[])if(c?.id)idCounts.set(c.id,(idCounts.get(c.id)||0)+1);
  replies.forEach((reply,index)=>{
    const article=document.createElement('article'),heading=document.createElement('h3');article.className='process-step';
    heading.textContent=`第 ${index+1} 轮回复${demo?' · 模拟':''}`;article.append(heading);
    if(typeof reply.content==='string'&&reply.content.trim())traceDetail(article,'模型可见回复（非内部推理）',reply.content);
    const calls=Array.isArray(reply.tool_calls)?reply.tool_calls:[];
    if(!calls.length){const p=document.createElement('p');p.textContent='这轮没有保存结构化工具请求，不能据此认定没有执行其他操作。';article.append(p);}
    calls.forEach(call=>{
      if(!call||typeof call!=='object')return;
      const name=call.function?.name,section=document.createElement('section'),title=document.createElement('h4'),state=document.createElement('p');
      title.textContent=`模型请求：${names[name]||'调用工具'}${name?' · '+traceText(name):'（工具名缺失）'}`;section.append(title);
      let args=call.function?.arguments;
      if(typeof args==='string'){try{args=JSON.parse(args)}catch{args='参数不是可解析的 JSON；未执行解析或补全。\n'+args;}}
      traceDetail(section,'查看请求参数',args??'未记录参数');
      const position=messages.indexOf(reply),next=messages.findIndex((m,i)=>i>position&&m.role==='assistant');
      const matching=typeof call.id==='string'&&idCounts.get(call.id)===1?messages.slice(position+1,next<0?undefined:next).filter(m=>m.role==='tool'&&m.tool_call_id===call.id&&(!m.name||m.name===name)):[];
      if(name==='finish')state.textContent=result.status==='success'||result.status==='empty'?'已保存完成结果；finish 是结束声明，不对应独立工具执行返回。':'已请求结束；请以任务最终状态为准，不能认定定位成功。';
      else if(matching.length===1){
        const content=matching[0].content;state.textContent='已记录匹配的工具返回（不代表内容一定正确）。';
        if(typeof content==='string'){
          const page=content.match(/output_id=([^;\n]+); offset=([^;\n]+); next_offset=([^;\n]+); output_lines=([^;\n]+); partial=(true|false)/);
          if(page)state.textContent+=` 返回第 ${traceText(page[4])} 行${page[3]!=='none'?'，还有后续内容':'，本次输出已读至末尾'}${page[5]==='true'?'；属于分页/部分输出':''}。`;
          traceDetail(section,'展开工具实际返回（已筛除常见敏感信息）',content);
        }else state.textContent+=' 返回正文缺失。';
      }else state.textContent=matching.length>1||idCounts.get(call.id)>1?'调用标识重复或匹配不唯一，未猜测对应结果。':'没有可可靠匹配的工具返回，执行结果未知。';
      section.append(state);article.append(section);
    });
    target.append(article);
  });
  // Exclude original system/user prompts, raw HTTP payloads, provider configuration,
  // hidden reasoning and diagnostics from the JSON viewer. Keep the local files intact.
  const visible={status:result.status,iterations:result.iterations,found_files:result.found_files,found_entities:result.found_entities,
    messages:messages.filter(m=>['assistant','tool'].includes(m.role)).map(m=>({role:m.role,content:m.content,tool_calls:m.tool_calls,tool_call_id:m.tool_call_id,name:m.name}))};
  $('trace').textContent=JSON.stringify(traceSafe(visible.messages.length?visible.messages:result.return_records||result.tool_trace||[]),null,2);
  $('raw-result').textContent=JSON.stringify(traceSafe(visible),null,2);
}

function resultView(value) {
  const result=value.result||value.demo?.result;$('result-card').hidden=!result;
  if(!result)return;
  const outcomes={success:'已找到以下代码位置，可展开源码核对。',empty:'这次没有找到可确认的代码位置。',iteration_limit:'已达到本次查找次数上限，尚未完成定位。',needs_review:'结果需要进一步核对。'};
  $('result-note').textContent=value.demo?'这是免费示例，不是真实 AI 的分析结果。':`${outcomes[result.status]||'分析已结束，请核对下方结果。'} 代码位置存在不代表一定能解答你的问题。`;
  $('locations').replaceChildren();const evidence=value.evidence?.items||[];
  $('result-count').textContent=evidence.length?`${evidence.length} 处位置`:'';
  if(!evidence.length){
    const entities=result.found_entities||[],files=(result.found_files||[]).filter(file=>!entities.some(id=>id.startsWith(file+':'))),found=[...entities,...files];
    if(!found.length){const p=document.createElement('p');p.className='meta';p.textContent='暂时没有可展示的代码位置。';$('locations').append(p);}
    for(const name of found){const article=document.createElement('article'),heading=document.createElement('h3'),path=document.createElement('p'),split=name.indexOf(':');article.className='location';heading.textContent=split>=0?name.slice(split+1):name.split('/').pop();path.className='file-path';path.textContent=split>=0?name.slice(0,split):name;article.append(heading,path);$('locations').append(article);}
    $('result-count').textContent=found.length?`${found.length} 处位置`:'';
  }
  for(const item of evidence){
    const article=document.createElement('article'),h=document.createElement('h3'),path=document.createElement('p'),line=document.createElement('span');
    article.className='location';const id=String(item.id||''),split=id.indexOf(':');h.textContent=split>=0?id.slice(split+1):id.split('/').pop();
    path.className='file-path';path.textContent=split>=0?id.slice(0,split):id;line.className='line-number';line.textContent=`第 ${item.start_line}–${item.end_line} 行${item.truncated?' · 仅展示部分源码':''}`;article.append(h,path,line);
    const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='展开源码';pre.textContent=item.snippet;details.append(summary,pre);article.append(details);
    // Link only to original GitHub source. Never render model content as HTML.
    try{const u=new URL(item.url);if(u.protocol==='https:'&&u.hostname==='github.com'&&!u.username&&!u.password){const a=document.createElement('a');a.href=u.href;a.rel='noopener noreferrer';a.target='_blank';a.textContent='在 GitHub 查看 ↗';article.append(a);}}catch{}
    $('locations').append(article);
  }
  processView(value,result);
}
function render(value) {
  const previous=job;job=value;$('empty').hidden=true;$('job-status').hidden=false;
  $('status').textContent=labels[value.state]||'请查看详情';$('status').className='badge '+(active.has(value.state)?'active':['needs_review','failed'].includes(value.state)?'bad':'good');
  const titles={preparing:'正在读取仓库',prepared:'准备好了，下一步由你决定',running:'正在查找相关代码',completed:'本次分析已结束',needs_review:'先暂停，避免重复计费',failed:'暂时无法准备这个仓库',demo_running:'正在生成示例',demo_completed:'可以看看结果长什么样'};
  $('status-title').textContent=titles[value.state]||'请查看任务详情';
  $('status-detail').textContent=active.has(value.state)?'可以稍后回来查看。关闭页面不会取消任务，也不会重新提交。':value.state==='prepared'?'已读取源码，还没有调用 AI 或产生模型费用。核实下方费用后再开始。':value.state==='needs_review'?'结果尚不确定。请先核对服务商账单和本机运行记录；这项任务不会自动重试。':value.state==='demo_completed'?'示例已完成，没有产生模型费用。':value.state==='completed'?'下方保留了本次找到的位置和源码，方便你继续核对。':'准备未完成，没有调用 AI。请查看提示。';
  $('task-id').textContent='任务编号：'+value.id;remember(value.id);
  if(value.error||value.code)error(humanError(value.error||value.code),value.error||value.code);else if(!uncertain.has(current))error(null);
  $('plan-card').hidden=!value.preview;
  if(value.preview){
    const p=value.preview;$('plan').replaceChildren();$('plan-details').replaceChildren();
    $('plan-summary').textContent=value.state==='prepared'?'确认费用后开始':'本次分析的费用与授权';
    if(previous?.id!==value.id||previous?.state!==value.state)$('plan-card').open=value.state==='prepared';
    $('budget-value').textContent=money(p.budget,p.currency);$('budget-note').textContent=`最多 ${p.maximum_calls} 次模型请求，预算不足时会停止。`;
    for(const [k,v] of [['仓库',p.repository_url],['问题',p.problem_statement],['AI 服务',p.endpoint],['模型',p.model]])pair(k,v);
    $('price-summary').textContent=`配置单价：每百万 token 输入 ${money(p.provider?.input_per_million,p.currency)}，输出 ${money(p.provider?.output_per_million,p.currency)}。实际费用以服务商账单为准。`;
    for(const [k,v] of [['源码版本',p.commit],['单次预留',money(p.reservation_per_call,p.currency)],['预留合计',money(p.full_reservation_all_calls,p.currency)+'（各次预留相加，不是本题费用上限）'],['计划校验码',p.plan_sha256]])pair(k,v,'plan-details');
    $('plan-provider').textContent=JSON.stringify(p.provider,null,2);
  }
  if(previous?.id!==value.id||previous?.preview?.plan_sha256!==value.preview?.plan_sha256||!value.can_run)$('consent').checked=false;
  $('approval').hidden=value.state!=='prepared';
  $('run-note').textContent=uncertain.has(current)?'尚未确认提交结果，已禁止再次发送。请只查看最新状态，并核对账单。':value.state!=='prepared'?'本次授权不可重复使用；历史、失败或未知请求都不会自动重跑。':!session?.paid_enabled?'当前只开放免费准备。请点击页首“配置 API Key”查看启动步骤。':!session?.credential_ready?'本机服务还没有可用密钥，暂时不能开始付费分析。':!value.can_run?'这项任务无法继续执行，请先检查本机记录。':'仅执行这一次，之后不会自动再次收费。';
  usageView(value);resultView(value);controls();
}
async function poll(id,token) {
  try{const value=await request('/api/jobs/'+id);if(token!==generation)return;render(value);if(active.has(value.state))timer=setTimeout(()=>poll(id,token),1200);}
  catch(e){if(token!==generation)return;error(humanError(e.message)+' 查看状态不会再次提交。',e.message);controls();}
}
function follow(id) {
  if(!/^[a-f0-9]{32}$/.test(id||'')){error('请粘贴完整的 32 位任务编号。');return;}
  clearTimeout(timer);generation++;
  if(current!==id){job=null;$('consent').checked=false;$('plan-card').hidden=true;$('result-card').hidden=true;$('usage-card').hidden=true;$('empty').hidden=true;$('job-status').hidden=false;$('status-title').textContent='正在读取任务';$('status-detail').textContent='这里只查看状态，不会重新运行。';controls();}
  remember(id);poll(id,generation);
}
function showNew(push=true) {
  if(busy||active.has(job?.state))return;
  clearTimeout(timer);generation++;job=null;current=null;$('consent').checked=false;
  for(const id of ['plan-card','result-card','usage-card','job-status'])$(id).hidden=true;
  $('empty').hidden=false;$('status').textContent='等待开始';$('status').className='badge';error(null);
  if(push)history.pushState(null,'','/#new');controls();
}
$('task-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||$('submit').disabled)return;
  const kind=$('source').value,id=crypto.randomUUID().replaceAll('-','');
  const body=kind==='demo'?{id}:{id,repository_url:$('repository').value.trim(),question:$('issue').value,ref:$('ref').value.trim()||null};
  clearTimeout(timer);generation++;busy=true;job=null;remember(id);$('consent').checked=false;
  $('plan-card').hidden=true;$('result-card').hidden=true;$('usage-card').hidden=true;$('empty').hidden=true;$('job-status').hidden=false;
  $('status').textContent='提交中';$('status').className='badge active';$('status-title').textContent='正在提交';$('status-detail').textContent='请稍候，不要重复提交。';$('task-id').textContent='任务编号：'+id;controls();error(null);
  try{await request('/api/'+kind,body);follow(id);}catch(e){$('status').textContent='请查看状态';$('status').className='badge bad';$('status-title').textContent='尚未确认提交结果';$('status-detail').textContent='任务编号已保留。请先查看最新状态，不要重复提交。';error(humanError(e.message),e.message);}finally{busy=false;controls();}
});
$('run').addEventListener('click',async()=>{
  if($('run').disabled)return;
  const id=current,sha=job.preview.plan_sha256;busy=true;uncertain.add(id);controls();
  try{await request('/api/jobs/'+id+'/run',{plan_sha256:sha,consent:true});uncertain.delete(id);follow(id);}catch(e){error('尚未确认这次付费请求的结果。请只查看状态并核对账单，不要重试。',e.message);follow(id);}finally{busy=false;controls();}
});
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();showNew();});
$('consent').addEventListener('change',controls);$('source').addEventListener('change',sourceChanged);
$('restore').addEventListener('click',()=>follow($('restore-id').value.trim()));$('refresh').addEventListener('click',()=>follow(current));$('new-task').addEventListener('click',()=>showNew());
window.addEventListener('popstate',()=>{const id=new URL(location.href).searchParams.get('job');if(id)follow(id);else showNew(false);});
function keySetup(open) {
  $('key-setup').hidden=!open;
  $('configure-key').setAttribute('aria-expanded',String(open));
  if(open) {
    const port=new URL(location.href).port;
    $('key-command').textContent='./start-local-web.command --prompt-api-key --enable-paid-run'+(/^\d{1,5}$/.test(port)?' --port '+port:'');
    $('key-status').textContent=!session?'服务未连接，仍可按以下步骤在本机设置。':!session.provider_configured?'尚未配置供应商参数：请先完成第 2 步，仅输入密钥还不能运行。':session.credential_ready?(session.paid_enabled?'本次服务已有密钥。如需更换，按下方步骤重启。':'本次服务已有密钥，但付费入口未启用。按下方步骤重启。'):'供应商已配置，本次服务尚无密钥。按下方步骤重启并输入。';
    $('key-title').focus();
  } else $('configure-key').focus();
}
$('configure-key').addEventListener('click',()=>keySetup(true));
$('close-key-setup').addEventListener('click',()=>keySetup(false));
$('copy-key-command').addEventListener('click',async()=>{
  try {
    await navigator.clipboard.writeText($('key-command').textContent);
    $('key-copy-status').textContent='已复制。确认任务已结束后，在项目目录的终端运行。';
  } catch {
    $('key-copy-status').textContent='浏览器不允许复制，请选中上方命令手动复制。命令不含密钥。';
  }
});
async function init(){
  try{
    session=await request('/api/session');$('health').textContent='本机已连接';$('health').className='badge good';$('provider').textContent=session.provider?JSON.stringify(session.provider,null,2):'尚未配置 AI 服务，可先看免费示例。';
    $('configuration').textContent=session.provider_configured?(session.paid_enabled?(session.credential_ready?'AI 服务已就绪。每一题都需要你单独确认费用后才会开始。':'付费入口已开启，但本机服务还没有可用密钥。'):'已配置 AI 服务，目前只开放免费准备。'):'尚未配置 AI 服务，请按本机 README_LOCAL_WEB.md 完成设置。';
    if(session.interrupted_fence){$('configuration').textContent='上次服务意外中断，现在只能查看任务。请先检查残留进程、服务商账单和本机记录。';error($('configuration').textContent);}
    sourceChanged();const params=new URL(location.href).searchParams,id=params.get('job')||(location.hash==='#new'?null:storage.get());if(id)follow(id);
  }catch(e){$('health').textContent='服务未连接';$('health').className='badge bad';error('无法连接本机服务。请确认 LocAgent 已启动，再刷新页面。',e.message);}
}
sourceChanged();init();
