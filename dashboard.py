"""Страница в браузере, где видно, как работает бот.

Бот сам запускает её при старте. Откройте: http://localhost:8000
Работает только на вашем компьютере, в интернет ничего не выкладывается.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BotState:
    """Общее состояние бота, которое показывает страница."""

    def __init__(self, **info):
        self._lock = threading.Lock()
        self.data = {"info": info, "price": None, "equity": None, "balance": None, "position": None,
                     "candles": [], "trades": [], "events": [], "council": None, "updated": None,
                     "status": "Запуск..."}

    def update(self, **kw):
        with self._lock:
            self.data.update(kw)

    def event(self, text: str, kind: str = "info", when: str = ""):
        with self._lock:
            self.data["events"].insert(0, {"t": when, "text": text, "kind": kind})
            del self.data["events"][100:]

    def snapshot(self) -> str:
        with self._lock:
            return json.dumps(self.data, ensure_ascii=False, default=str)


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Торговый бот</title>
<style>
:root{--bg:#07090f;--bg2:#0d1220;--card:rgba(20,26,42,.72);--card2:rgba(28,36,58,.6);--ink:#eef2ff;--mute:#8a93ad;--dim:#59617a;--line:rgba(140,160,220,.12);
--up:#22d39a;--down:#ff5d73;--accent:#6d8bff;--accent2:#b06dff;--gold:#ffc35a;--fast:#ffb547;--slow:#a78bfa}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif;
background:radial-gradient(1200px 600px at 10% -10%,rgba(109,139,255,.18),transparent 60%),radial-gradient(900px 500px at 100% 0%,rgba(176,109,255,.14),transparent 60%),radial-gradient(800px 600px at 50% 120%,rgba(34,211,154,.08),transparent 60%),var(--bg);background-attachment:fixed}
.wrap{max-width:1240px;margin:0 auto;padding:22px 18px 48px}
.num{font-variant-numeric:tabular-nums}
/* шапка */
header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:14px;margin-bottom:22px}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;font-size:24px;
background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 8px 28px rgba(109,139,255,.45)}
h1{font-size:22px;margin:0;letter-spacing:-.01em}
.sub{font-size:13px;color:var(--mute)}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;padding:7px 12px;border-radius:99px;background:var(--card2);border:1px solid var(--line);color:var(--mute);backdrop-filter:blur(10px)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--dim)}
.pill.live{color:var(--up);border-color:rgba(34,211,154,.35)}
.pill.live .dot{background:var(--up);box-shadow:0 0 0 0 rgba(34,211,154,.7);animation:pulse 1.8s infinite}
.pill.off{color:var(--down)}.pill.off .dot{background:var(--down)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,211,154,.6)}70%{box-shadow:0 0 0 9px rgba(34,211,154,0)}100%{box-shadow:0 0 0 0 rgba(34,211,154,0)}}
/* карточки */
.card{position:relative;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px 20px;backdrop-filter:blur(14px);
box-shadow:0 10px 40px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.04)}
.k{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.08em;display:flex;align-items:center;gap:8px}
.k .ic{font-size:15px}
h2{font-size:16px;margin:0;display:flex;align-items:center;gap:9px}
.headrow{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.up{color:var(--up)}.down{color:var(--down)}
.empty{color:var(--mute);font-size:14px;padding:18px 0;text-align:center}
/* верхние показатели */
.grid{display:grid;grid-template-columns:1.35fr 1fr 1fr 1fr;gap:14px}
.hero{background:linear-gradient(135deg,rgba(109,139,255,.22),rgba(176,109,255,.14) 60%,rgba(20,26,42,.7));border-color:rgba(130,150,255,.3)}
.big{font-size:38px;font-weight:700;letter-spacing:-.02em;margin-top:8px;line-height:1.1}
.v{font-size:27px;font-weight:650;margin-top:8px;letter-spacing:-.01em}
.s{font-size:13px;color:var(--mute);margin-top:6px}
.chip{display:inline-block;font-size:13px;font-weight:600;padding:3px 9px;border-radius:99px;margin-top:8px}
.chip.up{background:rgba(34,211,154,.14)}.chip.down{background:rgba(255,93,115,.14)}.chip.flat{background:var(--card2);color:var(--mute)}
.flash-up{animation:fu .9s}.flash-down{animation:fd .9s}
@keyframes fu{0%{color:var(--up);text-shadow:0 0 18px rgba(34,211,154,.8)}100%{}}
@keyframes fd{0%{color:var(--down);text-shadow:0 0 18px rgba(255,93,115,.8)}100%{}}
/* позиция: полоса стоп — тейк */
.bar{position:relative;height:8px;border-radius:99px;margin:14px 0 6px;background:linear-gradient(90deg,rgba(255,93,115,.55),rgba(140,160,220,.18) 33%,rgba(34,211,154,.55))}
.bar .m{position:absolute;top:50%;width:16px;height:16px;border-radius:50%;background:#fff;transform:translate(-50%,-50%);box-shadow:0 0 0 4px rgba(255,255,255,.15),0 2px 10px rgba(0,0,0,.5);transition:left .6s}
.bar .e{position:absolute;top:-4px;width:2px;height:16px;background:var(--mute);transform:translateX(-50%)}
.barl{display:flex;justify-content:space-between;font-size:11.5px;color:var(--mute)}
/* ряды */
.row{display:grid;grid-template-columns:1.9fr 1fr;gap:14px;margin-top:14px}
.chartbox{position:relative}
canvas{width:100%;height:340px;display:block;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:rgba(10,14,26,.92);border:1px solid var(--line);border-radius:10px;padding:7px 10px;font-size:12.5px;white-space:nowrap;opacity:0;transition:opacity .15s;box-shadow:0 6px 20px rgba(0,0,0,.4)}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--mute)}
.legend i{display:inline-block;width:16px;height:3px;vertical-align:middle;margin-right:6px;border-radius:2px}
.legend i.tri{width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-radius:0}
/* совет ИИ */
.verdict{border-radius:14px;padding:12px 14px;margin-bottom:12px;font-size:14px;border:1px solid var(--line);background:var(--card2)}
.verdict.ok{border-color:rgba(34,211,154,.35);background:rgba(34,211,154,.08)}
.verdict.no{border-color:rgba(255,93,115,.35);background:rgba(255,93,115,.08)}
.verdict .big2{font-size:17px;font-weight:700;margin-top:3px}
.votes{display:grid;gap:10px}
.vote{display:grid;grid-template-columns:40px 1fr;gap:12px;align-items:start;padding:11px;border-radius:14px;background:var(--card2);border:1px solid var(--line)}
.ava{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;font-weight:800;font-size:16px;color:#fff}
.vh{display:flex;justify-content:space-between;align-items:center;gap:8px}
.vh b{font-size:14px}
.badge{font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:99px;letter-spacing:.03em}
.badge.BUY{background:rgba(34,211,154,.16);color:var(--up)}.badge.SELL{background:rgba(255,93,115,.16);color:var(--down)}
.badge.HOLD{background:rgba(255,195,90,.15);color:var(--gold)}.badge.ERR{background:rgba(255,93,115,.1);color:var(--down)}
.why{font-size:12.5px;color:var(--mute);margin-top:4px;line-height:1.4}
.members{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:6px}
/* таблица и журнал */
.scroll{max-height:360px;overflow:auto;margin:0 -6px;padding:0 6px}
.scroll::-webkit-scrollbar{width:6px}.scroll::-webkit-scrollbar-thumb{background:var(--line);border-radius:9px}
table{width:100%;border-collapse:separate;border-spacing:0 6px;font-size:13.5px}
th{text-align:left;color:var(--dim);font-weight:500;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;padding:0 10px 2px}
td{padding:10px;background:var(--card2)}
td:first-child{border-radius:12px 0 0 12px}td:last-child{border-radius:0 12px 12px 0}
.rs{font-size:11.5px;padding:3px 8px;border-radius:99px;background:rgba(140,160,220,.12);color:var(--mute)}
.ev{display:grid;grid-template-columns:44px 14px 1fr;gap:8px;font-size:13.5px;padding:7px 0}
.ev .t{color:var(--dim);font-size:12px;padding-top:1px}
.ev .d{width:10px;height:10px;border-radius:50%;margin-top:4px;background:var(--accent);box-shadow:0 0 10px rgba(109,139,255,.6)}
.ev.buy .d{background:var(--up);box-shadow:0 0 10px rgba(34,211,154,.7)}.ev.sell .d{background:var(--down);box-shadow:0 0 10px rgba(255,93,115,.7)}
.ev.err .d{background:var(--down)}.ev.err{color:var(--down)}
.ev.buy b{color:var(--up)}.ev.sell b{color:var(--down)}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.stat{font-size:12.5px;color:var(--mute);padding:5px 10px;border-radius:10px;background:var(--card2)}
.stat b{color:var(--ink)}
footer{text-align:center;color:var(--dim);font-size:12px;margin-top:26px}
@media (max-width:1000px){.grid{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}}
@media (max-width:560px){.grid{grid-template-columns:1fr}.big{font-size:32px}canvas{height:260px}}
</style></head><body><div class="wrap">
<header>
 <div class="brand"><div class="logo">₿</div><div><h1 id="title">Торговый бот</h1><div class="sub" id="status">Запуск...</div></div></div>
 <div class="pills"><span class="pill">🧪 Симуляция — без реальных денег</span><span class="pill" id="live"><span class="dot"></span><span id="livet">нет связи</span></span></div>
</header>

<div class="grid">
 <div class="card hero"><div class="k"><span class="ic">📈</span>Цена <span id="sym"></span></div><div class="big num" id="price">—</div><div id="chg"></div></div>
 <div class="card"><div class="k"><span class="ic">💰</span>Капитал</div><div class="v num" id="equity">—</div><div id="pnl" class="s"></div></div>
 <div class="card"><div class="k"><span class="ic">🎯</span>Позиция</div><div class="v num" id="pos">—</div><div id="posbar"></div><div class="s" id="posd"></div></div>
 <div class="card"><div class="k"><span class="ic">🧾</span>Сделки</div><div class="v num" id="ntr">0</div><div class="s" id="wr"></div></div>
</div>

<div class="row">
 <div class="card">
  <div class="headrow"><h2>📊 График цены</h2>
   <div class="legend"><span><i style="background:var(--accent)"></i>цена</span><span><i style="background:var(--fast)"></i>быстрая SMA</span><span><i style="background:var(--slow)"></i>медленная SMA</span><span><i class="tri" style="border-bottom:8px solid var(--up)"></i>покупка</span><span><i class="tri" style="border-top:8px solid var(--down)"></i>продажа</span></div></div>
  <div class="chartbox"><canvas id="ch"></canvas><div class="tip" id="tip"></div></div>
 </div>
 <div class="card"><div class="headrow"><h2>🤖 Совет ИИ</h2></div><div id="council" class="empty">Голосования ещё не было</div></div>
</div>

<div class="row">
 <div class="card"><div class="headrow"><h2>💼 Сделки</h2><div class="stats" id="stats"></div></div>
  <div class="scroll"><table><thead><tr><th>Закрыта</th><th>Вход</th><th>Выход</th><th>Прибыль</th><th>Причина</th></tr></thead><tbody id="trades"></tbody></table><div id="notr" class="empty">Сделок пока нет — бот ждёт хороший момент</div></div></div>
 <div class="card"><div class="headrow"><h2>📝 Журнал</h2></div><div class="scroll" id="events"></div></div>
</div>
<footer>Страница обновляется каждые 3 секунды · работает только на вашем компьютере</footer>
</div>
<script>
const $=id=>document.getElementById(id),f=(x,d=2)=>x==null?"—":Number(x).toLocaleString("ru-RU",{minimumFractionDigits:d,maximumFractionDigits:d});
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const RS={STOP_LOSS:"🛑 стоп-лосс",TAKE_PROFIT:"✅ тейк-профит",SIGNAL:"📍 сигнал",END:"конец"};
const VR={BUY:"КУПИТЬ",SELL:"ПРОДАТЬ",HOLD:"ЖДАТЬ"};
const AV={claude:["C","linear-gradient(135deg,#d97757,#b8553a)"],chatgpt:["G","linear-gradient(135deg,#10a37f,#0b7a5f)"],openai:["G","linear-gradient(135deg,#10a37f,#0b7a5f)"],grok:["X","linear-gradient(135deg,#3a3f4b,#111318)"],gemini:["✦","linear-gradient(135deg,#4285f4,#9b72cb)"]};
const ava=m=>{const k=Object.keys(AV).find(k=>m.toLowerCase().includes(k)),a=k?AV[k]:[m[0]||"?","linear-gradient(135deg,#6d8bff,#b06dff)"];return `<div class="ava" style="background:${a[1]}">${esc(a[0])}</div>`};
const sg=v=>(v>=0?"+":"")+f(v);
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
let geo=null;
function draw(c,trades){const cv=$("ch"),dpr=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext("2d");g.scale(dpr,dpr);g.clearRect(0,0,W,H);
 if(c.length<2){g.fillStyle=css("--mute");g.font="14px -apple-system,sans-serif";g.textAlign="center";g.fillText("Ждём цены с биржи…",W/2,H/2);geo=null;return}
 const vals=c.flatMap(x=>[x.close,x.f,x.s].filter(v=>v!=null));let lo=Math.min(...vals),hi=Math.max(...vals);const pad=(hi-lo)*.1||1;lo-=pad;hi+=pad;
 const L=6,R=74,T=10,B=26,x=i=>L+i*(W-L-R)/(c.length-1),y=v=>T+(hi-v)*(H-T-B)/(hi-lo);geo={x,y,L,R,T,B,W,H,c};
 g.font="11px -apple-system,sans-serif";g.lineWidth=1;
 for(let k=0;k<=5;k++){const v=lo+(hi-lo)*k/5,yy=y(v);g.strokeStyle="rgba(140,160,220,.08)";g.setLineDash([3,5]);g.beginPath();g.moveTo(L,yy);g.lineTo(W-R,yy);g.stroke();g.setLineDash([]);g.fillStyle=css("--dim");g.fillText(f(v,0),W-R+8,yy+4)}
 g.fillStyle=css("--dim");[0,Math.floor(c.length/4),Math.floor(c.length/2),Math.floor(c.length*3/4),c.length-1].forEach(i=>{g.textAlign=i===0?"left":i===c.length-1?"right":"center";g.fillText(c[i].time.slice(11,16),x(i),H-7)});g.textAlign="left";
 // заливка под ценой
 const acc=css("--accent"),gr=g.createLinearGradient(0,T,0,H-B);gr.addColorStop(0,"rgba(109,139,255,.35)");gr.addColorStop(1,"rgba(109,139,255,0)");
 g.beginPath();c.forEach((p,i)=>i?g.lineTo(x(i),y(p.close)):g.moveTo(x(i),y(p.close)));g.lineTo(x(c.length-1),H-B);g.lineTo(x(0),H-B);g.closePath();g.fillStyle=gr;g.fill();
 const line=(k,col,w,glow)=>{g.save();g.strokeStyle=col;g.lineWidth=w;g.lineJoin="round";if(glow){g.shadowColor=col;g.shadowBlur=12}g.beginPath();let s=false;c.forEach((p,i)=>{if(p[k]==null)return;s?g.lineTo(x(i),y(p[k])):g.moveTo(x(i),y(p[k]));s=true});g.stroke();g.restore()};
 line("s",css("--slow"),1.6);line("f",css("--fast"),1.6);line("close",acc,2.4,true);
 // последняя цена
 const lp=c[c.length-1].close,ly=y(lp);g.strokeStyle="rgba(109,139,255,.5)";g.setLineDash([2,3]);g.beginPath();g.moveTo(L,ly);g.lineTo(W-R,ly);g.stroke();g.setLineDash([]);
 g.fillStyle=acc;const tw=R-6;g.beginPath();g.roundRect?g.roundRect(W-R+2,ly-10,tw,20,6):g.rect(W-R+2,ly-10,tw,20);g.fill();g.fillStyle="#fff";g.font="600 11px -apple-system,sans-serif";g.fillText(f(lp,0),W-R+8,ly+4);
 g.save();g.fillStyle=acc;g.shadowColor=acc;g.shadowBlur=16;g.beginPath();g.arc(x(c.length-1),ly,4,0,7);g.fill();g.restore();
 const idx={};c.forEach((p,i)=>idx[p.time]=i);
 const mark=(t,v,col,upw)=>{const i=idx[(t||"").slice(0,16)];if(i==null)return;const X=x(i),Y=y(v);g.save();g.fillStyle=col;g.shadowColor=col;g.shadowBlur=10;g.beginPath();if(upw){g.moveTo(X,Y+3);g.lineTo(X-7,Y+15);g.lineTo(X+7,Y+15)}else{g.moveTo(X,Y-3);g.lineTo(X-7,Y-15);g.lineTo(X+7,Y-15)}g.fill();g.restore()};
 trades.forEach(t=>{mark(t.opened_at,t.entry,css("--up"),true);mark(t.closed_at,t.exit,css("--down"),false)});
 if(last&&last.position){const q=last.position;mark(q.opened_at||q.entry_time,q.entry_price,css("--up"),true)}}
$("ch").addEventListener("mousemove",e=>{if(!geo)return;const r=e.target.getBoundingClientRect(),mx=e.clientX-r.left,{c,x,L,R,W}=geo;
 const i=Math.max(0,Math.min(c.length-1,Math.round((mx-L)/(W-L-R)*(c.length-1)))),p=c[i],tp=$("tip");
 tp.innerHTML=`<div style="color:var(--mute)">${esc(p.time.slice(5,16))}</div><b>${f(p.close)}</b>`+(p.f!=null?`<div style="color:var(--fast)">быстрая ${f(p.f)}</div>`:"")+(p.s!=null?`<div style="color:var(--slow)">медленная ${f(p.s)}</div>`:"");
 tp.style.opacity=1;tp.style.left=Math.min(x(i)+12,W-140)+"px";tp.style.top=Math.max(geo.y(p.close)-60,0)+"px"});
$("ch").addEventListener("mouseleave",()=>$("tip").style.opacity=0);
let last=null,prevPrice=null;
async function tick(){try{const d=await (await fetch("/api/state",{cache:"no-store"})).json();last=d;render(d);$("livet").textContent="бот работает";$("live").className="pill live"}catch(e){$("livet").textContent="бот остановлен";$("live").className="pill off"}}
function render(d){const i=d.info;$("title").textContent="Торговый бот · "+i.symbol;$("status").textContent=d.status+(d.updated?" · обновлено в "+d.updated.slice(11,19):"");
 const pe=$("price");pe.textContent=f(d.price)+(d.price!=null?" $":"");$("sym").textContent="· "+i.symbol+" · свечи "+i.timeframe;
 if(prevPrice!=null&&d.price!=null&&d.price!==prevPrice){pe.classList.remove("flash-up","flash-down");void pe.offsetWidth;pe.classList.add(d.price>prevPrice?"flash-up":"flash-down")}prevPrice=d.price;
 const c=d.candles;if(c.length>1&&d.price!=null){const ch=(d.price/c[0].close-1)*100;$("chg").innerHTML=`<span class="chip ${ch>=0?"up":"down"}">${ch>=0?"▲":"▼"} ${sg(ch)}%</span> <span class="s">за весь график</span>`}else $("chg").innerHTML="";
 if(d.equity==null){$("equity").textContent="—";$("pnl").textContent="ждём цены с биржи"}else{$("equity").textContent=f(d.equity)+" $";const p=d.equity-i.start;$("pnl").innerHTML=`<span class="chip ${p>0?"up":p<0?"down":"flat"}">${sg(p)} $ · ${sg(p/i.start*100)}%</span><div class="s">старт: ${f(i.start)} $</div>`}
 if(d.position){const q=d.position,ch=(d.price/q.entry_price-1)*100,span=q.take_profit-q.stop_loss,pos=v=>Math.max(0,Math.min(100,(v-q.stop_loss)/span*100));
  $("pos").innerHTML=`<span class="${ch>=0?"up":"down"}">${ch>=0?"▲":"▼"} ${sg(ch)}%</span>`;
  $("posbar").innerHTML=`<div class="bar"><div class="e" style="left:${pos(q.entry_price)}%"></div><div class="m" style="left:${pos(d.price)}%"></div></div><div class="barl"><span>стоп ${f(q.stop_loss,0)}</span><span>тейк ${f(q.take_profit,0)}</span></div>`;
  $("posd").textContent=`куплено по ${f(q.entry_price)} $`}
 else{$("pos").textContent="Нет";$("posbar").innerHTML="";$("posd").textContent="ждём сигнал на покупку"}
 const tr=d.trades,w=tr.filter(t=>t.pnl_usdt>0).length,tot=tr.reduce((a,t)=>a+t.pnl_usdt,0);$("ntr").textContent=tr.length;
 $("wr").innerHTML=tr.length?`<span class="chip ${w/tr.length>=.5?"up":"down"}">${Math.round(w/tr.length*100)}% прибыльных</span><div class="s">${w} из ${tr.length}</div>`:"пока не было";
 $("stats").innerHTML=tr.length?`<span class="stat">итого <b class="${tot>=0?"up":"down"}">${tot>=0?"+":""}${f(tot,2)} $</b></span><span class="stat">лучшая <b class="up">+${f(Math.max(...tr.map(t=>t.pnl_usdt)),2)}</b></span><span class="stat">худшая <b class="down">${f(Math.min(...tr.map(t=>t.pnl_usdt)),2)}</b></span>`:"";
 $("notr").style.display=tr.length?"none":"block";
 $("trades").innerHTML=tr.slice().reverse().map(t=>`<tr><td>${esc(t.closed_at.slice(5,16))}</td><td class="num">${f(t.entry)}</td><td class="num">${f(t.exit)}</td><td class="num ${t.pnl_usdt>=0?"up":"down"}"><b>${t.pnl_usdt>=0?"+":""}${f(t.pnl_usdt,3)} $</b></td><td><span class="rs">${RS[t.reason]||esc(t.reason)}</span></td></tr>`).join("");
 $("events").innerHTML=d.events.length?d.events.map(e=>`<div class="ev ${esc(e.kind)}"><span class="t">${esc((e.t||"").slice(11,16))}</span><span class="d"></span><span>${e.text}</span></div>`).join(""):'<div class="empty">Пока событий нет</div>';
 const co=d.council;
 if(!i.members.length){$("council").className="empty";$("council").innerHTML='🔑 Ключи ИИ не добавлены — бот торгует только по стратегии.<br><span style="font-size:12.5px">Ключи вставляются в файл .env</span>'}
 else if(co){$("council").className="";const ok=co.approved;
  $("council").innerHTML=`<div class="verdict ${ok?"ok":ok===false?"no":""}"><div class="s" style="margin:0">${esc(co.when)} · сигнал «${VR[co.proposed]||esc(co.proposed)}»</div><div class="big2 ${ok?"up":"down"}">${ok===null?"⚠️ Никто не ответил":ok?"✅ Одобрено":"⛔ Отклонено"}</div></div><div class="votes">`+
  i.members.map(m=>{const v=co.votes[m],e=co.errors[m];return `<div class="vote">${ava(m)}<div><div class="vh"><b>${esc(m)}</b>${v?`<span class="badge ${esc(v.vote)}">${VR[v.vote]||esc(v.vote)}</span>`:`<span class="badge ERR">ошибка</span>`}</div><div class="why">${v?esc(v.reason):esc((e||"").slice(0,90))}</div></div></div>`}).join("")+"</div>"}
 else{$("council").className="empty";$("council").innerHTML=`<div class="members">${i.members.map(m=>`<div style="text-align:center">${ava(m)}<div style="font-size:12px;margin-top:5px">${esc(m)}</div></div>`).join("")}</div><div style="margin-top:14px">Агенты готовы. Ждём первый сигнал…</div>`}
 draw(c,tr)}
addEventListener("resize",()=>last&&draw(last.candles,last.trades));tick();setInterval(tick,3000);
</script></body></html>"""


def start(state: BotState, port: int = 8000) -> str:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Защита от "DNS rebinding": чужой сайт не сможет читать страницу бота
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("localhost", "127.0.0.1"):
                self.send_error(403)
                return
            if self.path.startswith("/api/state"):
                body, ctype = state.snapshot().encode("utf-8"), "application/json; charset=utf-8"
            elif self.path in ("/", "/index.html"):
                body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # не засорять терминал
            pass

    last_err = None
    for p in range(port, port + 10):  # если порт занят (например, бот уже запущен) — берём следующий
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError as e:
            last_err = e
    else:
        raise last_err
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://localhost:{p}"
