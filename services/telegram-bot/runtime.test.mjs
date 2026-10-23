import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';

test('SQLite Durable Object and real alarms perform preview then approved publication', {timeout:20000},async()=>{
  const source=await readFile(new URL('./worker.mjs',import.meta.url),'utf8');
  const entry=`import handler,{PriceBot} from './worker.mjs';export default handler;
  export class RuntimeBot extends PriceBot {
    constructor(state,env){super(state,env);this.api={
      say:async()=>{},telegram:async()=>{},image:async()=> 'synthetic',
      ocr:async()=>({currency:null,list_date:null,warranty:null,warnings:[],listings:[{source_section:'Test',listing_text:'Phone PM Mix',price_usd:100,confident:true,kind:'phone'}]}),
      preview:async()=>{},publish:async()=>({sha:'fixture-sha',dispatched:true})};}
    async fetch(req){if(new URL(req.url).pathname==='/inspect')return Response.json(await this.state.storage.get('pending') || null);return super.fetch(req);}
  }`;
  const mf=new Miniflare(convertV4MiniflareOptions({workers:[{name:'testbot',compatibilityDate:'2026-10-01',modules:[{type:'ESModule',path:'entry.mjs',contents:entry},{type:'ESModule',path:'worker.mjs',contents:source}],durableObjects:{PRICE_BOT:{className:'RuntimeBot',useSQLite:true}},bindings:{TELEGRAM_BOT_TOKEN:'fixture',TELEGRAM_WEBHOOK_SECRET:'fixture-secret',TELEGRAM_OWNER_ID:'42',OPENAI_API_KEY:'fixture',GITHUB_TOKEN:'fixture',GITHUB_REPOSITORY:'owner/repo',GITHUB_BRANCH:'main',GITHUB_WORKFLOW:'pages.yml',OPENAI_MODEL:'fixture'}}]}));
  try {
    assert.equal((await mf.dispatchFetch('https://bot/telegram',{method:'POST',body:'{}'})).status,403);
    const ns=await mf.getDurableObjectNamespace('PRICE_BOT');const stub=ns.get(ns.idFromName('owner'));
    const send=update=>mf.dispatchFetch('https://bot/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'fixture-secret'},body:JSON.stringify(update)});
    const read=async()=> (await stub.fetch('https://internal/inspect')).json();
    const until=async status=>{
      for(let n=0;n<80;n++){const p=await read();if(p?.status==='failed')assert.fail('Runtime job failed: '+p.error);if(p?.status===status)return p;await new Promise(r=>setTimeout(r,100));}
      assert.fail('Runtime alarm did not reach '+status);
    };
    const response=await send({update_id:1,message:{from:{id:42},chat:{id:42,type:'private'},photo:[{file_id:'fixture',file_size:100}],caption:'2020-01-02 USD https://example.com/list'}});
    assert.equal(response.status,200);
    const pending=await until('ready');assert.equal(pending.candidate.listings.length,1);
    assert.equal(pending.candidate.list_date,'2020-01-02');
    await send({update_id:2,callback_query:{id:'callback',from:{id:42},message:{chat:{id:42,type:'private'}},data:'approve:'+pending.id}});
    const done=await until('done');assert.equal(done.commit,'fixture-sha');assert.equal(done.candidate,undefined);
  } finally {await mf.dispose();}
});
