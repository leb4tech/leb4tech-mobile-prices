import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{PriceBot,Clients,caption,candidate,csv} from './worker.mjs';
const META = {date:'2020-01-02',source:'https://example.com/list'};
const OCR = {currency:null,list_date:null,warranty:null,warnings:[],listings:[{source_section:'Example',listing_text:'Phone PM Mix 256GB',price_usd:123,confident:true,kind:'phone'}]};
const env = {TELEGRAM_BOT_TOKEN:'fixture',TELEGRAM_WEBHOOK_SECRET:'test-secret',TELEGRAM_OWNER_ID:'42',OPENAI_API_KEY:'fixture',GITHUB_TOKEN:'fixture',GITHUB_REPOSITORY:'owner/repo',GITHUB_BRANCH:'main',GITHUB_WORKFLOW:'pages.yml',OPENAI_MODEL:'fixture-model'};
const clone = x=>JSON.parse(JSON.stringify(x));
function storage() {
  const map = new Map();
  const s = {alarm:null,async get(k){return clone(map.get(k) ?? null);},async put(k,v){map.set(k,clone(v));},async deleteAlarm(){s.alarm=null;},async setAlarm(at){s.alarm=at;},async transaction(fn){return fn(s);}};
  return s;
}
function harness() {
  const state={storage:storage()}, bot=new PriceBot(state,env), events=[];
  bot.api={async say(...x){events.push(['say',...x]);},async telegram(...x){events.push(['telegram',...x]);},async image(...x){events.push(['image',...x]);return 'synthetic-image';},async ocr(){events.push(['ocr']);return clone(OCR);},async preview(...x){events.push(['preview',...x]);},async publish(...x){events.push(['publish',...x]);return {sha:'commit',dispatched:true};}};
  let id=1;
  const update = body=>bot.fetch(new Request('https://internal',{method:'POST',body:JSON.stringify({update_id:id++,...body})}));
  const message = extra=>update({message:{from:{id:42},chat:{id:42,type:'private'},photo:[{file_id:'fixture',file_size:1000}],caption:'2020-01-02 USD https://example.com/list',...extra}});
  const press = (action,token)=>update({callback_query:{id:'cb',from:{id:42},message:{chat:{id:42,type:'private'}},data:action+':'+token}});
  return {bot,state,events,update,message,press};
}
test('caption requires a real nonfuture date, explicit USD and public source',()=>{
  assert.deepEqual(caption('2020-01-02 USD https://example.com/list'),META);
  for (const input of ['', '2020-01-02 LBP https://example.com','2020-02-31 USD https://example.com','2999-01-01 USD https://example.com','2020-01-02 USD https://u:p@example.com','2020-01-02 USD https://example.com/?apiKey=hidden','2020-01-02 USD https://127.0.0.1']) assert.throws(()=>caption(input));
});
test('candidate preserves names and never invents availability or manufacturer identity',()=>{
  const result=candidate(OCR,META,'fixture-id');
  assert.equal(result.listings[0].listing_text,OCR.listings[0].listing_text);
  assert.equal(result.listings[0].availability,null);assert.equal(result.listings[0].condition,null);
  assert.equal(result.source_warranty_text,null);assert.equal(result.retailer_verified,false);
  assert.equal(result.method,'ocr_with_user_approval');
});
test('unclear prices, duplicate rows, contradictory dates/currencies block the entire candidate',()=>{
  for (const price of [null,-1,0,NaN,Infinity,'123',true]) {
    const input=clone(OCR);input.listings[0].price_usd=price;assert.throws(()=>candidate(input,META,'id'));
  }
  const variants=[];
  for (const [k,v] of [['currency','EUR'],['list_date','2020-01-03'],['warnings',['unclear']]]) {const o=clone(OCR);o[k]=v;variants.push(o);}
  const duplicate=clone(OCR);duplicate.listings.push(clone(duplicate.listings[0]));variants.push(duplicate);
  for (const [k,v] of [['confident',false],['confident','true'],['kind','unknown']]) {const o=clone(OCR);o.listings[0][k]=v;variants.push(o);}
  for (const o of variants) assert.throws(()=>candidate(o,META,'id'));
});
test('CSV quotes multiline labels and protects spreadsheet formula cells',()=>{
  const data=candidate(OCR,META,'id');data.listings[0].listing_text='=HYPERLINK("x")\nPM';
  const result=csv(data);assert.ok(result.startsWith('\ufeff'));assert.ok(result.includes('"\'=HYPERLINK(""x"")\nPM"'));
});
test('only authenticated webhook reaches durable object',async()=>{
  let calls=0;const bindings={...env,PRICE_BOT:{idFromName(){return 'id';},get(){return {async fetch(){calls++;return new Response('ok');}};}}};
  for (const secret of ['', 'wrong']) {
    const res=await worker.fetch(new Request('https://bot/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':secret},body:'{}'}),bindings);
    assert.equal(res.status,403);
  }
  assert.equal(calls,0);
  const res=await worker.fetch(new Request('https://bot/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':env.TELEGRAM_WEBHOOK_SECRET},body:'{}'}),bindings);
  assert.equal(res.status,200);assert.equal(calls,1);
});
test('other users and group chats never trigger OCR or preview',async()=>{
  const h=harness();await h.message({from:{id:7}});await h.message({chat:{id:42,type:'group'}});
  assert.equal(h.events.length,0);assert.equal(await h.state.storage.get('pending'),null);
});
test('missing caption does not start OCR',async()=>{
  const h=harness();await h.message({caption:undefined});assert.equal(h.events.filter(x=>x[0]==='ocr').length,0);
  assert.equal(h.state.storage.alarm,null);
});
test('upload -> preview only -> explicit approval -> exactly one publication',async()=>{
  const h=harness();await h.message();assert.equal(h.events.filter(x=>x[0]==='publish').length,0);
  await h.bot.alarm();let p=await h.state.storage.get('pending');assert.equal(p.status,'ready');
  assert.equal(h.events.filter(x=>x[0]==='preview').length,1);assert.equal(h.events.filter(x=>x[0]==='publish').length,0);
  await h.press('approve',p.id);await h.press('approve',p.id);await h.bot.alarm();await h.bot.alarm();
  assert.equal(h.events.filter(x=>x[0]==='publish').length,1);assert.equal((await h.state.storage.get('pending')).status,'done');
});
test('cancel and expired or superseded approvals cannot publish',async()=>{
  const h=harness();await h.message();await h.bot.alarm();const p=await h.state.storage.get('pending');
  await h.press('approve','a'.repeat(32));assert.equal((await h.state.storage.get('pending')).status,'ready');
  await h.press('cancel',p.id);await h.press('approve',p.id);await h.bot.alarm();assert.equal((await h.state.storage.get('pending')).status,'cancelled');
  await h.message();await h.bot.alarm();const next=await h.state.storage.get('pending');next.created=0;await h.state.storage.put('pending',next);
  await h.press('approve',next.id);await h.bot.alarm();assert.equal(h.events.filter(x=>x[0]==='publish').length,0);
  assert.equal((await h.state.storage.get('pending')).candidate,undefined);
});
test('OCR failure leaves no publishable state or image',async()=>{
  const h=harness();h.bot.api.ocr=async()=>({});await h.message();await h.bot.alarm();
  const p=await h.state.storage.get('pending');assert.equal(p.status,'failed');assert.equal(p.fileId,undefined);assert.equal(p.candidate,undefined);
  assert.equal(h.events.filter(x=>x[0]==='publish').length,0);
});
test('duplicate webhook update cannot queue another image',async()=>{
  const h=harness();await h.message();await h.bot.alarm();const p=await h.state.storage.get('pending');
  await h.bot.fetch(new Request('https://internal',{method:'POST',body:JSON.stringify({update_id:1,message:{from:{id:42},chat:{id:42,type:'private'},photo:[{file_id:'different',file_size:1000}],caption:'2020-01-02 USD https://example.com/list'}})}));
  assert.equal((await h.state.storage.get('pending')).id,p.id);
});
test('GitHub compare-and-swap rejects conflicts and never dispatches after failed save',async()=>{
  const original=globalThis.fetch;const calls=[];
  try {
    globalThis.fetch=async(url,init)=>{
      calls.push([url,init]);
      if(init.method==='PUT')return new Response('conflict',{status:409});
      return Response.json({sha:'old-sha',encoding:'base64',content:btoa('{}')});
    };
    await assert.rejects(()=>new Clients(env).publish(candidate(OCR,META,'id')));
    assert.equal(calls.length,2);assert.equal(JSON.parse(calls[1][1].body).sha,'old-sha');
    assert.ok(calls.every(([url])=>url.includes('/contents/data/image-prices.json')));
  } finally {globalThis.fetch=original;}
});
test('successful save plus failed dispatch is reported separately',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async(url,init)=>init.method==='PUT' ? Response.json({commit:{sha:'saved-sha'}}) : init.method==='POST' ? new Response('denied',{status:403}) : Response.json({sha:'old',encoding:'base64',content:btoa('{}')});
    const r=await new Clients(env).publish(candidate(OCR,META,'id'));assert.equal(r.sha,'saved-sha');assert.equal(r.dispatched,false);
  } finally {globalThis.fetch=original;}
});
test('OCR request is fixed to official API and uses structured output and no response storage',async()=>{
  const original=globalThis.fetch;let payload;
  try {
    globalThis.fetch=async(url,init)=>{
      assert.equal(url,'https://api.openai.com/v1/responses');payload=JSON.parse(init.body);
      return Response.json({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(OCR)}]}]});
    };
    assert.deepEqual(await new Clients(env).ocr('data:image/png;base64,fixture'),OCR);
    assert.equal(payload.store,false);assert.equal(payload.text.format.strict,true);
  } finally {globalThis.fetch=original;}
});
test('/id returns only the sender ID and never grants publication rights',async()=>{
  const original=globalThis.fetch;const sent=[];
  try {
    globalThis.fetch=async(url,init)=>{sent.push(JSON.parse(init.body));return Response.json({ok:true,result:{}});};
    const res=await worker.fetch(new Request('https://bot/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':env.TELEGRAM_WEBHOOK_SECRET},body:JSON.stringify({update_id:1,message:{text:'/id',from:{id:7},chat:{type:'private',id:7}}})}),{...env,TELEGRAM_OWNER_ID:'0'});
    assert.equal(res.status,200);assert.equal(sent[0].chat_id,7);assert.ok(sent[0].text.includes('7'));
    assert.ok(!sent[0].text.includes('42'));
  } finally {globalThis.fetch=original;}
});
test('identical saved candidate avoids another GitHub commit',async()=>{
  const original=globalThis.fetch;const data=candidate(OCR,META,'id');const methods=[];
  try {
    globalThis.fetch=async(url,init)=>{
      methods.push(init.method || 'GET');
      return init.method==='POST' ? new Response(null,{status:204}) : Response.json({sha:'existing',encoding:'base64',content:Buffer.from(JSON.stringify(data)).toString('base64')});
    };
    assert.equal((await new Clients(env).publish(data)).dispatched,true);assert.deepEqual(methods,['GET','POST']);
  } finally {globalThis.fetch=original;}
});
test('preview includes readable text and exposes approval only after the complete preview',async()=>{
  const api=new Clients(env), events=[];
  api.telegram=async(method,body)=>{events.push({method,body});return {};};
  const data=candidate(OCR,META,'preview-id');await api.preview(42,data,'preview-id');
  assert.equal(events[0].method,'sendDocument');assert.equal(events[0].body.get('reply_markup'),null);
  assert.ok(events[1].body.text.includes('Phone PM Mix 256GB'));assert.ok(events[1].body.text.includes('$123'));
  assert.equal(events[1].body.reply_markup,undefined);
  assert.equal(events.at(-1).body.reply_markup.inline_keyboard[0][0].callback_data,'approve:preview-id');
});
