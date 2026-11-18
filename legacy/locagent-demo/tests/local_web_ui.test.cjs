// Pure JS unit tests: a tiny DOM harness, no browser and no real network/model calls.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {randomUUID}=require('node:crypto');
const html=fs.readFileSync('locagent_service/local_web_assets/index.html','utf8');
const script=fs.readFileSync('locagent_service/local_web_assets/app.js','utf8');
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.events={};this.hidden=false;this.disabled=false;this.checked=false;this.open=false;this.textContent='';this.value='';}
  focus(){this.focused=true;}
  setAttribute(name,value){this[name]=value;}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  addEventListener(name,fn){this.events[name]=fn;}
  set innerHTML(_){throw Error('Unsafe HTML rendering');}
}
const ready={session:'test-only',provider_configured:true,paid_enabled:true,credential_ready:true};
const idA='a'.repeat(32),idB='b'.repeat(32),sha='c'.repeat(64);
function prepared(id=idA){return {id,state:'prepared',can_run:true,preview:{plan_sha256:sha,repository_url:'https://github.com/example/demo',commit:'d'.repeat(40),problem_statement:'Find sign_payload.',endpoint:'https://provider.example/api',model:'fixture',currency:'CNY',budget:'2.20',maximum_calls:3,reservation_per_call:'2.101248',full_reservation_all_calls:'6.303744',provider:{input_per_million:'2',output_per_million:'8'}}};}
async function harness(handler=()=>null){
  const nodes={};for(const match of html.matchAll(/id="([^"]+)"/g)){assert(!nodes[match[1]],'unique ids');nodes[match[1]]=new Element();}
  nodes.source.value='prepare';const brand=new Element('a'),calls=[],stored=new Map(),location={href:'http://127.0.0.1:8766/#new',hash:'#new'};
  const navigate=url=>{const u=new URL(url,location.href);location.href=u.href;location.hash=u.hash;};
  const context=vm.createContext({document:{getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelector:selector=>{assert.equal(selector,'.brand');return brand;}},location,history:{replaceState:(_,__,url)=>navigate(url),pushState:(_,__,url)=>navigate(url)},localStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)},window:{addEventListener(){}},URL,crypto:{randomUUID},setTimeout:()=>1,clearTimeout(){},console,
    fetch:async(path,options)=>{calls.push({path,...options});const value=path==='/api/session'?ready:await handler(path,options);return{ok:true,json:async()=>value};}
  });
  vm.runInContext(script,context);await tick();return{nodes,calls,context,stored,location,run:code=>vm.runInContext(code,context)};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('core form is accessible; consent and paid button start disabled',()=>{
 assert.match(html,/<label for="repository">GitHub 仓库链接/);assert.match(html,/<label for="issue">你的问题/);
 assert.match(html,/<input type="checkbox" id="consent">/);assert.match(html,/<button id="run"[^>]*disabled/);
 assert.doesNotMatch(html,/<details[^>]*\bopen\b/);assert.doesNotMatch(html,/<script(?! src=)[^>]*>\s*\S/);
 assert.match(html,/href="\/#new"/);assert.doesNotMatch(html,/\?new=/);
});
test('prepared plan shows budget, recipient and question; changed plan resets consent',async()=>{
 const h=await harness();h.run(`render(${JSON.stringify(prepared())})`);
 assert.equal(h.nodes['budget-value'].textContent,'CNY 2.20');assert.equal(h.nodes['plan-card'].open,true);
 const text=h.nodes.plan.children.map(e=>e.textContent).join(' ');assert.match(text,/provider.example/);assert.match(text,/Find sign_payload/);
 assert.equal(h.nodes.run.disabled,true);h.nodes.consent.checked=true;h.nodes.consent.events.change();assert.equal(h.nodes.run.disabled,false);
 const changed=prepared();changed.preview.plan_sha256='e'.repeat(64);h.run(`render(${JSON.stringify(changed)})`);assert.equal(h.nodes.consent.checked,false);assert.equal(h.nodes.run.disabled,true);
 h.run(`render(${JSON.stringify({...prepared(),state:'needs_review',can_run:false,code:'execution_stopped'})})`);assert.equal(h.nodes.approval.hidden,true);assert.equal(h.nodes['plan-card'].open,false);assert.equal(h.nodes.run.disabled,true);assert.match(h.nodes['error-message'].textContent,/不要重试/);
});
test('double click sends one exact paid request only after consent',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);const h=await harness(async(path,options)=>options.method==='POST'?pending:{...prepared(),state:'running',can_run:false});
 h.run(`render(${JSON.stringify(prepared())})`);await h.nodes.run.events.click();assert.equal(h.calls.filter(x=>x.method==='POST').length,0);
 h.nodes.consent.checked=true;h.nodes.consent.events.change();const first=h.nodes.run.events.click();await h.nodes.run.events.click();
 const posts=h.calls.filter(x=>x.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].path,`/api/jobs/${idA}/run`);assert.deepEqual(JSON.parse(posts[0].body),{plan_sha256:sha,consent:true});
 release({id:idA,state:'running'});await first;await tick();assert.equal(h.nodes.run.disabled,true);
});
test('uncertain paid response cannot be retried, even after refresh',async()=>{
 const h=await harness(async(_,options)=>{if(options.method==='POST')throw Error('Failed to fetch');return prepared();});
 h.run(`render(${JSON.stringify(prepared())})`);h.nodes.consent.checked=true;h.nodes.consent.events.change();await h.nodes.run.events.click();await tick();
 assert.equal(h.nodes.run.disabled,true);assert.equal(h.nodes.consent.disabled,true);h.run(`follow('${idA}')`);await tick();await h.nodes.run.events.click();assert.equal(h.calls.filter(x=>x.method==='POST').length,1);
});
test('stale status responses cannot replace a newer task',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);const h=await harness(path=>path.endsWith(idA)?pending:prepared(idB));
 h.run(`follow('${idA}');follow('${idB}')`);await tick();release(prepared(idA));await tick();assert.equal(h.run('current'),idB);assert.equal(h.run('job.id'),idB);assert.equal(h.calls.filter(x=>x.method==='POST').length,0);
});
test('new-question view clears consent, uses supported root route, and sends nothing',async()=>{
 const h=await harness();h.run(`render(${JSON.stringify(prepared())})`);h.nodes.consent.checked=true;h.run('showNew()');assert.equal(h.location.href,'http://127.0.0.1:8766/#new');assert.equal(h.nodes.consent.checked,false);assert.equal(h.nodes['plan-card'].hidden,true);assert.equal(h.calls.filter(x=>x.method==='POST').length,0);
});
test('source results stay text-only and reject unsafe URLs; demo avoids duplicate files',async()=>{
 const h=await harness();const result={result:{status:'success'},evidence:{items:[{id:'file.py:<script>alert(1)</script>',start_line:1,end_line:2,snippet:'<script>bad()</script>',url:'javascript:alert(1)'},{id:'ok.py:sign',start_line:3,end_line:4,snippet:'def sign(): pass',url:'https://github.com/example/demo/blob/abc/ok.py#L3'}]}};
 h.run(`resultView(${JSON.stringify(result)})`);assert.equal(h.nodes.locations.children[0].children.filter(e=>e.tagName==='a').length,0);assert.equal(h.nodes.locations.children[1].children.filter(e=>e.tagName==='a').length,1);
 h.run(`resultView(${JSON.stringify({demo:{result:{found_entities:['demo.py:render'],found_files:['demo.py']}}})})`);assert.equal(h.nodes.locations.children.length,1);assert.equal(h.nodes.locations.children[0].children[0].textContent,'render');
});

test('key guide repeated open and close preserves task, URL and sends no request',async()=>{
 const h=await harness();h.run(`render(${JSON.stringify(prepared())})`);
 const before=h.calls.length,url=h.location.href;
 h.nodes['configure-key'].events.click();h.nodes['configure-key'].events.click();
 assert.equal(h.nodes['key-setup'].hidden,false);
 assert.equal(h.nodes['configure-key']['aria-expanded'],'true');
 assert.match(h.nodes['key-command'].textContent,/--port 8766$/);
 assert.match(h.nodes['key-status'].textContent,/已有密钥/);
 h.nodes['close-key-setup'].events.click();
 assert.equal(h.nodes['key-setup'].hidden,true);
 assert.equal(h.nodes['configure-key'].focused,true);
 assert.equal(h.location.href,url);assert.equal(h.calls.length,before);
 assert.equal(h.run('current'),idA);
});
test('key guide separates provider, key and paid-switch prerequisites',async()=>{
 const h=await harness();
 for(const [value,message] of [[null,/未连接/],[{provider_configured:false},/尚未配置供应商/],[{provider_configured:true,credential_ready:false},/尚无密钥/],[{provider_configured:true,credential_ready:true,paid_enabled:false},/付费入口未启用/]]){
 h.run(`session=${JSON.stringify(value)};keySetup(true)`);assert.match(h.nodes['key-status'].textContent,message);
 }
 await h.nodes['copy-key-command'].events.click();assert.match(h.nodes['key-copy-status'].textContent,/手动复制/);
 h.context.navigator={clipboard:{writeText:async text=>{assert.match(text,/^\.\/start-local-web.command /);}}};
 await h.nodes['copy-key-command'].events.click();assert.match(h.nodes['key-copy-status'].textContent,/已复制/);
 assert.doesNotMatch(html,/<input[^>]*type="password"/);
});

const textOf=e=>[e.textContent,...e.children.map(textOf)].join(' ');
test('per-call tokens and exact ledger cost visible without a result, including while running',async()=>{
 const h=await harness();const value={...prepared(),state:'running',can_run:false,accounting:{spent:'0.000003',reserved:'0',calls:[{status:'settled',usage:{prompt_tokens:1200,completion_tokens:15},cost:'0.000003'}]}};
 h.run(`render(${JSON.stringify(value)})`);
 assert.equal(h.nodes['result-card'].hidden,true);assert.equal(h.nodes['usage-card'].hidden,false);
 assert.match(textOf(h.nodes['usage-calls']),/第 1 次调用.*输入 1,200 token · 输出 15 token.*CNY 0.000003/);
 assert.match(h.nodes['usage-summary'].textContent,/已记录合计.*输入 1,200 token/);
 assert.match(h.nodes['usage-note'].textContent,/未单独抵扣缓存/);
 h.run(`render(${JSON.stringify(value)})`);assert.equal(h.nodes['usage-calls'].children.length,1);
 assert.equal(h.calls.filter(x=>x.method==='POST').length,0);
});
test('pending and failed calls stay unknown and separate from partial totals and reservations',async()=>{
 const h=await harness();const calls=[{status:'settled',usage:{prompt_tokens:0,completion_tokens:0},cost:'0'},...['reserved','raw_received','outcome_unknown'].map(status=>({status,usage:{prompt_tokens:999,completion_tokens:999},cost:'99'}))];
 h.run(`render(${JSON.stringify({...prepared(),state:'needs_review',accounting:{calls,spent:'0',reserved:'6.30'}})})`);
 assert.equal(h.nodes['usage-calls'].children.length,4);
 assert.match(textOf(h.nodes['usage-calls'].children[0]),/输入 0 token/);
 for(const node of h.nodes['usage-calls'].children.slice(1)){assert.match(textOf(node),/输入 未知 token.*费用：未知/);assert.doesNotMatch(textOf(node),/999|99/);}
 assert.match(h.nodes['usage-summary'].textContent,/已知部分合计.*输入 0 token.*待核对预留：CNY 6.30（非扣费）.*不含未知部分/);
});
test('legacy, missing, invalid and demo usage never fabricate data or retain previous task usage',async()=>{
 const h=await harness();
 h.run(`render(${JSON.stringify({...prepared(),state:'completed'})})`);assert.match(h.nodes['usage-summary'].textContent,/暂无逐次用量记录/);
 h.run(`usageView({state:'completed',accounting:{spent:'1'}})`);assert.match(h.nodes['usage-summary'].textContent,/暂无逐次用量记录/);
 h.run(`usageView(${JSON.stringify({state:'completed',accounting:{calls:[{status:'settled',usage:{prompt_tokens:-1,completion_tokens:'3'},cost:'<script>'}]}})})`);
 assert.match(textOf(h.nodes['usage-calls']),/输入 未知 token · 输出 未知 token.*费用：未知/);
 h.run(`usageView({state:'demo_completed',demo:{},accounting:{calls:[{}]}})`);assert.match(h.nodes['usage-summary'].textContent,/真实模型调用 0 次 · 费用 0/);assert.equal(h.nodes['usage-calls'].children.length,0);
 h.run(`render(${JSON.stringify(prepared())})`);assert.equal(h.nodes['usage-summary'].textContent,'尚未调用模型。');
 h.run('showNew()');assert.equal(h.nodes['usage-card'].hidden,true);
});

test('saved model replies show requested tools and id-matched results without model calls',async()=>{
 const h=await harness();const result={status:'success',iterations:3,messages:[{role:'system',content:'PRIVATE PROMPT'},{role:'user',content:'PRIVATE QUESTION'},
 {role:'assistant',tool_calls:[{id:'a',function:{name:'search_code_snippets',arguments:'{"search_terms":["BM25"]}'}},{id:'b',function:{name:'explore_tree_structure',arguments:'{}'}}]},
 {role:'tool',name:'explore_tree_structure',tool_call_id:'b',content:'TREE RESULT'},{role:'tool',name:'search_code_snippets',tool_call_id:'a',content:'SEARCH RESULT'},
 {role:'assistant',tool_calls:[{id:'end',function:{name:'finish',arguments:'{"files":["index.py"]}'}}]}]};
 h.run(`resultView(${JSON.stringify({result})})`);
 assert.equal(h.nodes['process-steps'].children.length,2);
 const first=h.nodes['process-steps'].children[0];assert.match(textOf(first.children[1]),/搜索代码[\s\S]*BM25[\s\S]*SEARCH RESULT/);assert.doesNotMatch(textOf(first.children[1]),/TREE RESULT/);
 assert.match(textOf(h.nodes['process-steps'].children[1]),/结束声明/);
 assert.doesNotMatch(h.nodes['raw-result'].textContent,/PRIVATE PROMPT|PRIVATE QUESTION/);
 assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('missing, repeated and late ids are not guessed, no stale records on legacy results',async()=>{
 const h=await harness();const reply={role:'assistant',tool_calls:[{id:'dup',function:{name:'search_code_snippets',arguments:'bad JSON'}}]};
 h.run(`resultView(${JSON.stringify({result:{messages:[reply,reply,{role:'tool',tool_call_id:'dup',content:'UNTRUSTED MATCH'}]}})})`);
 assert.match(textOf(h.nodes['process-steps']),/匹配不唯一/);assert.doesNotMatch(textOf(h.nodes['process-steps']),/UNTRUSTED MATCH/);
 h.run(`resultView({result:{messages:[{role:'assistant',tool_calls:[{id:'missing',function:{name:'unknown'}}]}]}})`);
 assert.match(textOf(h.nodes['process-steps']),/执行结果未知/);
 h.run(`resultView({result:{return_records:{legacy:[{content:'old'}]}}})`);
 assert.equal(h.nodes['process-steps'].children.length,0);assert.match(h.nodes['process-summary'].textContent,/无法还原/);assert.match(h.nodes.trace.textContent,/legacy/);
});
test('trace is text only, excludes secret fields and redacts common sensitive values in both viewers',async()=>{
 const h=await harness();const result={status:'success',diagnostics:{secret:'NEVER SHOW'},messages:[{role:'assistant',reasoning_content:'PRIVATE REASONING',content:'<script>not executed</script> contact me@example.com',tool_calls:[{id:'a',function:{name:'search_code_snippets',arguments:JSON.stringify({api_key:'TOPSECRET',search_terms:['Bearer a-secret-token']})}}]},{role:'tool',tool_call_id:'a',content:'password=HIDDENPASSWORD\n/home/alice/file.py'}]};
 h.run(`resultView(${JSON.stringify({result})})`);
 for(const text of [textOf(h.nodes['process-steps']),h.nodes.trace.textContent,h.nodes['raw-result'].textContent]){assert.doesNotMatch(text,/TOPSECRET|a-secret-token|HIDDENPASSWORD|me@example.com|PRIVATE REASONING|NEVER SHOW|home\/alice/);}
 assert.match(textOf(h.nodes['process-steps']),/<script>not executed<\/script>/);
 h.run(`resultView({demo:{result:{messages:[{role:'assistant',content:'synthetic'}]}}})`);assert.match(h.nodes['process-note'].textContent,/合成示例/);
});
