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
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--mute:#6e6e73;--line:#e3e1dc;--up:#1a7f4b;--down:#c4372b;--accent:#2f5bd3;--fast:#d98a1c;--slow:#7b4fc9}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e21;--ink:#f2f2f4;--mute:#9a9aa1;--line:#2e2e33;--up:#3fc07f;--down:#ff6b5e;--accent:#7d9dff;--fast:#f0a944;--slow:#a98bf0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px 40px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:16px}
h1{font-size:22px;margin:0}.tag{font-size:12px;padding:3px 8px;border-radius:99px;background:var(--line);color:var(--mute)}
.tag.live{background:var(--up);color:#fff}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.k{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}.v{font-size:24px;font-weight:600;margin-top:4px;font-variant-numeric:tabular-nums}
.s{font-size:13px;color:var(--mute);margin-top:2px}.up{color:var(--up)}.down{color:var(--down)}
.row{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-top:12px}
h2{font-size:15px;margin:0 0 10px}canvas{width:100%;height:280px;display:block}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mute);margin-top:6px}.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line)}th{color:var(--mute);font-weight:500}
.ev{font-size:13px;padding:6px 0;border-bottom:1px solid var(--line)}.ev .t{color:var(--mute);margin-right:6px}
.ev.buy b{color:var(--up)}.ev.sell b{color:var(--down)}.ev.err{color:var(--down)}
.votes{display:grid;grid-template-columns:1fr 1fr;gap:8px}.vote{border:1px solid var(--line);border-radius:8px;padding:8px}.vote b{display:block}
.scroll{max-height:320px;overflow:auto}.empty{color:var(--mute);font-size:13px}
@media (max-width:800px){.grid{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<header><h1 id="title">Торговый бот</h1><span class="tag">симуляция — без реальных денег</span><span class="tag" id="live">нет связи</span><span class="s" id="status"></span></header>
<div class="grid">
 <div class="card"><div class="k">Цена</div><div class="v" id="price">—</div><div class="s" id="sym"></div></div>
 <div class="card"><div class="k">Капитал</div><div class="v" id="equity">—</div><div class="s" id="pnl"></div></div>
 <div class="card"><div class="k">Позиция</div><div class="v" id="pos">—</div><div class="s" id="posd"></div></div>
 <div class="card"><div class="k">Сделок</div><div class="v" id="ntr">0</div><div class="s" id="wr"></div></div>
</div>
<div class="row">
 <div class="card"><h2>График цены</h2><canvas id="ch"></canvas>
  <div class="legend"><span><i style="background:var(--ink)"></i>цена</span><span><i style="background:var(--fast)"></i>быстрая SMA</span><span><i style="background:var(--slow)"></i>медленная SMA</span><span><i style="background:var(--up)"></i>покупка</span><span><i style="background:var(--down)"></i>продажа</span></div></div>
 <div class="card"><h2>Совет ИИ</h2><div id="council" class="empty">Голосования ещё не было</div></div>
</div>
<div class="row">
 <div class="card"><h2>Сделки</h2><div class="scroll"><table><thead><tr><th>Закрыта</th><th>Вход</th><th>Выход</th><th>Прибыль</th><th>Причина</th></tr></thead><tbody id="trades"></tbody></table><div id="notr" class="empty">Сделок пока нет</div></div></div>
 <div class="card"><h2>Журнал</h2><div class="scroll" id="events"></div></div>
</div></div>
<script>
const $=id=>document.getElementById(id),f=(x,d=2)=>x==null?"—":Number(x).toLocaleString("ru-RU",{minimumFractionDigits:d,maximumFractionDigits:d});
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const RS={STOP_LOSS:"стоп-лосс",TAKE_PROFIT:"тейк-профит",SIGNAL:"сигнал",END:"конец"};
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
function draw(c,trades){const cv=$("ch"),dpr=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext("2d");g.scale(dpr,dpr);g.clearRect(0,0,W,H);
 if(c.length<2)return;const vals=c.flatMap(x=>[x.close,x.f,x.s].filter(v=>v!=null));let lo=Math.min(...vals),hi=Math.max(...vals);const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;
 const L=8,R=70,T=8,B=22,x=i=>L+i*(W-L-R)/(c.length-1),y=v=>T+(hi-v)*(H-T-B)/(hi-lo);
 g.strokeStyle=css("--line");g.fillStyle=css("--mute");g.font="11px -apple-system,sans-serif";g.lineWidth=1;
 for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,yy=y(v);g.beginPath();g.moveTo(L,yy);g.lineTo(W-R,yy);g.stroke();g.fillText(f(v,0),W-R+6,yy+4)}
 [0,Math.floor(c.length/2),c.length-1].forEach(i=>g.fillText(c[i].time.slice(11),Math.min(x(i),W-R-30),H-6));
 const line=(k,col,w)=>{g.strokeStyle=col;g.lineWidth=w;g.beginPath();let s=false;c.forEach((p,i)=>{if(p[k]==null)return;s?g.lineTo(x(i),y(p[k])):g.moveTo(x(i),y(p[k]));s=true});g.stroke()};
 line("s",css("--slow"),1.5);line("f",css("--fast"),1.5);line("close",css("--ink"),2);
 const idx={};c.forEach((p,i)=>idx[p.time]=i);
 const mark=(t,v,col,upw)=>{const i=idx[(t||"").slice(0,16)];if(i==null)return;const X=x(i),Y=y(v);g.fillStyle=col;g.beginPath();if(upw){g.moveTo(X,Y+2);g.lineTo(X-6,Y+12);g.lineTo(X+6,Y+12)}else{g.moveTo(X,Y-2);g.lineTo(X-6,Y-12);g.lineTo(X+6,Y-12)}g.fill()};
 trades.forEach(t=>{mark(t.opened_at,t.entry,css("--up"),true);mark(t.closed_at,t.exit,css("--down"),false)});}
let last=null;
async function tick(){try{const d=await (await fetch("/api/state",{cache:"no-store"})).json();last=d;render(d);$("live").textContent="в работе";$("live").className="tag live"}catch(e){$("live").textContent="бот остановлен";$("live").className="tag"}}
function render(d){const i=d.info;$("title").textContent="Торговый бот · "+i.symbol;$("status").textContent=d.status+(d.updated?" · обновлено "+d.updated.slice(11):"");
 $("price").textContent=f(d.price);$("sym").textContent=i.symbol+", свечи "+i.timeframe;
 if(d.equity==null){$("equity").textContent="—";$("pnl").textContent="ждём цены с биржи"}else{$("equity").textContent=f(d.equity)+" $";const p=d.equity-i.start;$("pnl").innerHTML=`<span class="${p>=0?"up":"down"}">${p>=0?"+":""}${f(p)} $ (${f(p/i.start*100)}%)</span> от ${f(i.start)} $`}
 if(d.position){const q=d.position,ch=(d.price/q.entry_price-1)*100;$("pos").innerHTML=`<span class="${ch>=0?"up":"down"}">${ch>=0?"+":""}${f(ch)}%</span>`;$("posd").textContent=`куплено по ${f(q.entry_price)} · стоп ${f(q.stop_loss)} · тейк ${f(q.take_profit)}`}else{$("pos").textContent="нет";$("posd").textContent="ждём сигнал на покупку"}
 const tr=d.trades;$("ntr").textContent=tr.length;const w=tr.filter(t=>t.pnl_usdt>0).length;$("wr").textContent=tr.length?`прибыльных ${w} из ${tr.length}`:"";
 $("notr").style.display=tr.length?"none":"block";$("trades").innerHTML=tr.slice().reverse().map(t=>`<tr><td>${t.closed_at.slice(5,16)}</td><td>${f(t.entry)}</td><td>${f(t.exit)}</td><td class="${t.pnl_usdt>=0?"up":"down"}">${t.pnl_usdt>=0?"+":""}${f(t.pnl_usdt,3)}</td><td>${RS[t.reason]||t.reason}</td></tr>`).join("");
 $("events").innerHTML=d.events.length?d.events.map(e=>`<div class="ev ${e.kind}"><span class="t">${(e.t||"").slice(11,16)}</span>${e.text}</div>`).join(""):'<div class="empty">Пока событий нет</div>';
 const c=d.council;if(!i.members.length){$("council").innerHTML='<div class="empty">Ключи ИИ не добавлены — бот торгует только по стратегии. Ключи вставляются в файл .env</div>'}
 else if(c){const VR={BUY:"купить",SELL:"продать",HOLD:"ждать"};$("council").className="";$("council").innerHTML=`<div class="s" style="margin-bottom:8px">${c.when} · сигнал <b>${VR[c.proposed]}</b> → <b class="${c.approved?"up":"down"}">${c.approved===null?"никто не ответил":c.approved?"одобрено":"отклонено"}</b></div><div class="votes">`+
  i.members.map(m=>{const v=c.votes[m],e=c.errors[m];return `<div class="vote"><b>${esc(m)}</b>${v?`<span class="${v.vote==="BUY"?"up":v.vote==="SELL"?"down":""}">${VR[v.vote]}</span><div class="s">${esc(v.reason)}</div>`:`<span class="down">ошибка</span><div class="s">${esc((e||"").slice(0,80))}</div>`}</div>`}).join("")+"</div>"}
 else $("council").innerHTML=`<div class="empty">Участники: ${i.members.join(", ")}. Ждём первый сигнал.</div>`;
 draw(d.candles,tr)}
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
