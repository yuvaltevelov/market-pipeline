"use strict";
const $=id=>document.getElementById(id),el=(tag,text,cls)=>{
 const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(cls)n.className=cls;return n;
},replace=(id,...children)=>$(id).replaceChildren(...children);
let report=null,category="all",selection=null;
const num=(v,d=2)=>typeof v==="number"&&Number.isFinite(v)?new Intl.NumberFormat("en-US",{maximumFractionDigits:d}).format(v):"אין נתון";
const fmtTime=unix=>typeof unix==="number"?new Date(unix*1000).toLocaleString("he-IL",{dateStyle:"short",timeStyle:"short",timeZone:"Asia/Jerusalem"}):"לא ידוע";
const statusOk=a=>{
 if(a.status!=="reported"||!Number.isFinite(a.as_of))return false;
 const sec=Date.now()/1000-a.as_of;
 const max=a.timeframe==="60m"?
    (a.category==="crypto"?2*3600:["stock","etf","futures"].includes(a.category)?72*3600:4*3600):
    (a.category==="crypto"?2*86400:5*86400);
 return sec>=-300&&sec<=max;
};
const active=()=>report?.assets.filter(a=>a.timeframe===$("period").value)||[];
function badge(text,css){return el("span",text,"pill "+(css||""))}
function link(url,label){
 try{const u=new URL(url);if(u.protocol!=="https:"||!["finance.yahoo.com","docs.kraken.com"].includes(u.hostname))throw Error("untrusted source");const a=el("a",label);a.href=u.href;a.target="_blank";a.rel="noopener noreferrer";return a}
 catch{return el("span","מקור לא מאושר")}
}
function scoreLabel(a){return !statusOk(a)?"חסר":typeof a.score==="number"?a.score+"/100":"—"}
function bias(a){return !statusOk(a)?"unavailable":a.bias||"unavailable"}
function list(){
 const q=$("query").value.trim().toLowerCase();
 let assets=active().filter(a=>(category==="all"||a.category===category)&&(a.id+" "+a.name).toLowerCase().includes(q));
 const sort=$("sort").value;
 assets.sort((a,b)=>{
  if(sort==="symbol")return a.id.localeCompare(b.id);
  const va=statusOk(a)?sort==="rvol"?a.indicators?.rvol:a.score:null;
  const vb=statusOk(b)?sort==="rvol"?b.indicators?.rvol:b.score:null;
  return (typeof vb==="number"?vb:-999)-(typeof va==="number"?va:-999);
 });
 $("shown").textContent=assets.length+" נכסים";
 const area=$("assetlist");area.replaceChildren();
 if(!assets.length){area.append(el("p","אין נתונים המתאימים לסינון.","small"));replace("detail",el("p","בחר נכס זמין.","small"));return;}
 for(const a of assets){
  const btn=el("button",null,"asset"+(a.id===selection?.id&&a.timeframe===selection?.timeframe?" selected":""));
  btn.type="button";btn.setAttribute("aria-label","בחר "+a.name);
  const info=el("div");info.append(el("div",a.id,"ticker"),el("div",a.name,"name"));
  btn.append(info,el("div",statusOk(a)?num(a.price,4):"אין מחיר","price"),
   el("div",scoreLabel(a),"score "+bias(a)));
  btn.addEventListener("click",()=>{selection=a;detail();listHighlights();});
  area.append(btn);
 }
 if(!selection||!assets.some(a=>a.id===selection.id)){selection=assets[0];detail();}
 listHighlights();
}
function listHighlights(){
 for(const b of $("assetlist").children){
  if(b.tagName!=="BUTTON")continue;
  b.classList.toggle("selected",b.getAttribute("aria-label")==="בחר "+selection?.name);
 }
}
function metric(title,value,hint){
 const wrap=el("div",null,"indicator");wrap.append(el("span",title,"label"),el("span",value,"value"));
 if(hint)wrap.append(el("div",hint,"small"));return wrap;
}
function plot(container,chart){
 if(!Array.isArray(chart)||chart.length<2)return;
 const values=chart.map(x=>x.close).filter(x=>Number.isFinite(x));if(values.length<2)return;
 const lo=Math.min(...values),hi=Math.max(...values),span=hi-lo||1;
 const points=values.map((v,i)=>(15+i*770/(values.length-1)).toFixed(2)+","+(150-(v-lo)*132/span).toFixed(2)).join(" ");
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
 svg.setAttribute("viewBox","0 0 800 180");svg.setAttribute("role","img");svg.setAttribute("aria-label","התפתחות מחיר היסטורית ב-"+values.length+" נרות; אינו כולל תחזית");svg.setAttribute("class","plot");
 const line=document.createElementNS(svg.namespaceURI,"polyline");line.setAttribute("points",points);line.setAttribute("fill","none");line.setAttribute("stroke","#7be5c0");line.setAttribute("stroke-width","2.4");line.setAttribute("stroke-linejoin","round");svg.append(line);container.append(svg);
}
function detail(){
 const a=selection;if(!a)return;
 const target=$("detail");target.replaceChildren();
 const header=el("div",null,"detailtop"),title=el("div");
 const marketAge=(Date.now()/1000-a.as_of)/3600;
 const marketLabel=statusOk(a)&&a.timeframe==="60m"&&marketAge>4?
  "נר מהמסחר האחרון; השוק עשוי להיות סגור — לא נתון תוך-יומי עדכני":
  statusOk(a)?"נתון היסטורי תקף":"לא זמין/התיישן";
 title.append(el("h2",a.name),badge(a.category.toUpperCase()+" · "+a.timeframe),badge(marketLabel,statusOk(a)?"bullish":"bearish"));
 header.append(title,el("div",statusOk(a)?num(a.price,5):"—","detailprice"));target.append(header);
 const info=el("p",null,"small");
 info.append("מקור: ",link(a.source_url,a.source)," | הנר האחרון: "+fmtTime(a.as_of)+" | כמות נרות: "+(a.bars||0));
 target.append(info);
 if(!statusOk(a)){target.append(el("div","הספק לא החזיר סדרת OHLCV מלאה וטרייה. לכן אין ניקוד, תחזית או איתותי כסף חכם.","notice danger"));return;}
 const desc=a.bias==="bullish"?"נטייה טכנית שורית":a.bias==="bearish"?"נטייה טכנית דובית":"תמונה טכנית מעורבת";
 target.append(el("div","ניקוד כללים: "+scoreLabel(a)+" · "+desc,"notice"));
 plot(target,a.chart);
 const f=a.indicators||{},grid=el("div",null,"indicatorgrid");
 const fields=[
  ["EMA 20",num(f.ema20,4),"ממוצע מעריכי קצר"],
  ["EMA 50",num(f.ema50,4),"ממוצע מעריכי ארוך"],
  ["RSI 14",num(f.rsi14,1),"מומנטום יחסי"],
  ["RVOL",f.rvol===null?"חסר":num(f.rvol,2)+"×","נפח לעומת 20 נרות קודמים"],
  ["CMF 20",num(f.cmf20,3),"לחץ כסף משוער מנרות"],
  ["MFI 14",num(f.mfi14,1),"מחיר × נפח"],
  ["ATR 14",num(f.atr14,4),"תנודתיות ביחידות מחיר"],
  ["תזוזה 20 נרות",num(f.momentum20_pct,2)+"%","מומנטום, לא צפי"],
  ["Rolling VWAP 20",num(f.rolling_vwap20,4),"אינו VWAP של יום המסחר"]
 ];
 for(const [label,value,hint] of fields)grid.append(metric(label,value,hint));
 target.append(grid);
 const structure=el("div",null,"risks");
 structure.append(el("h3","מבנה שוק · סימני אזהרה"));
 for(const field of [["sweep","Liquidity Sweep"],["breakout","Breakout"],["fvg","FVG"]]){
  structure.append(el("div",field[1]+": "+(f[field[0]]==="bullish"?"דפוס שורי":f[field[0]]==="bearish"?"דפוס דובי":"לא אותר"),"small"));
 }target.append(structure);
 const bt=a.backtest||{};
 const section=el("div",null,"risks");section.append(el("h3","בדיקת אסטרטגיה: תקופת מבחן שלא שימשה לקביעת הכללים"));
 if(bt.status==="measured"){
  const win=el("div",null,"indicatorgrid");win.append(metric("עסקאות",bt.trades),metric("אחוז חיוביות",num(bt.win_rate_pct)+"%"),metric("תשואה מצטברת",num(bt.total_return_pct)+"%"),
  metric("ירידה מרבית",num(bt.max_drawdown_pct)+"%"),metric("קנייה והחזקה",num(bt.buy_hold_same_window_pct)+"%"));
  section.append(win,el("p",bt.method,"small"));
 }else section.append(el("p","אין די עסקאות/היסטוריה לבדיקת ביצועים בעלת משמעות. מספר תצפיות: "+(bt.trades||0)+".","small"));
 target.append(section);
 const reasons=el("div",null,"risks");reasons.append(el("h3","אינדיקציות ומה חסר כדי לאמת"));
 for(const line of [...(a.reasons||[]),...(a.flags||[])])reasons.append(el("div","• "+line,"bullet"));
 reasons.append(el("div","נתוני צד יוזם עסקה / Level 2 / עסקאות אופציות / זיהוי מוסדיים: אינם זמינים במקורות הללו.","bullet"));
 target.append(reasons);
}
function returnsMap(a){
 const map=new Map();const bars=a.chart||[];for(let i=1;i<bars.length;i++){
  const prev=bars[i-1].close,cur=bars[i].close;if(!Number.isFinite(prev)||!Number.isFinite(cur)||prev<=0)continue;
  const d=new Date(bars[i].time*1000);
  const key=a.timeframe==="1d"?d.toISOString().slice(0,10):Math.floor(bars[i].time/3600);
  map.set(key,cur/prev-1);
 }return map;
}
function compare(){
 if(!report)return;
 const rows=active().filter(statusOk);
 for(const id of ["compareA","compareB"]){
  const sel=$(id),old=sel.value;sel.replaceChildren();
  for(const a of rows){const opt=el("option",a.id+" · "+a.name);opt.value=a.id;sel.append(opt);}
  if(rows.some(a=>a.id===old))sel.value=old;
 }
 if(rows.length<2){replace("comparison",el("p","אין לפחות שני נכסים עם סדרות היסטוריות תקפות.","small"));return;}
 if(!$("compareB").value||$("compareA").value===$("compareB").value)$("compareB").value=rows[1].id;
 calculate();
}
function calculate(){
 const a=active().find(x=>x.id===$("compareA").value),b=active().find(x=>x.id===$("compareB").value);
 if(!a||!b||a.id===b.id){replace("comparison",el("p","בחר שני נכסים שונים.","small"));return}
 const ma=returnsMap(a),mb=returnsMap(b);const aa=[],bb=[];
 for(const [key,val] of ma){if(mb.has(key)){aa.push(val);bb.push(mb.get(key))}}
 if(aa.length<20){replace("comparison",el("p","רק "+aa.length+" תצפיות משותפות; לא ניתן לחשב מתאם שימושי.","small"));return;}
 const avg=x=>x.reduce((a,b)=>a+b,0)/x.length;
 const avga=avg(aa),avgb=avg(bb);
 const xy=aa.reduce((acc,x,i)=>acc+(x-avga)*(bb[i]-avgb),0);
 const ax=aa.reduce((acc,x)=>acc+(x-avga)**2,0);
 const bx=bb.reduce((acc,x)=>acc+(x-avgb)**2,0);
 const coefficient=ax>0&&bx>0?xy/Math.sqrt(ax*bx):null;
 replace("comparison",el("strong","מתאם תשואות ("+aa.length+" מדידות): "+num(coefficient,3)),
 el("p","מדגם היסטורי בלבד. "+(coefficient===null?"אין שונות מספקת למדידה.":"הקשר עשוי להשתנות בחדות; נתונים לא מסונכרנים במלואם בין בורסות."),"small"));
}
async function load(){
 $("status").textContent="טוען נתוני מחקר שנאספו על ידי GitHub Actions…";
 try{
  const response=await fetch("./data/pro.json?t="+Date.now(),{cache:"no-store"});
  if(!response.ok)throw Error("response "+response.status);
  const next=await response.json();
  if(next.schema_version!==3||!Array.isArray(next.assets)||!next.coverage)throw Error("schema mismatch");
  report=next;const age=next.generated_at?(Date.now()-Date.parse(next.generated_at))/3600000:Infinity;
  const total=next.assets.length,valid=next.assets.filter(statusOk).length;
  const stats=[["נכסים וטווחים",total],["סדרות תקפות כעת",valid],["סדרות לא תקפות",total-valid],["אימות צולב",next.coverage.cross_verified]];
  replace("summary",...stats.map(([title,value])=>{const box=el("div",null,"stat");box.append(el("span",title),el("strong",value));return box;}));
  $("status").classList.toggle("danger",valid===0||age>6);
  $("status").textContent="דוח אחרון: "+(next.generated_at?new Date(next.generated_at).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem"}):"טרם בוצע איסוף")+
   " · גיל: "+(Number.isFinite(age)?num(age,1)+" שעות":"לא זמין")+" · "+
   (valid===0?"אין סדרות נתונים שימושיות כרגע.":age>6?"האיסוף ישן; נבדקת טריות כל סדרה.":"ניתוח כללים, לא תחזית או נתוני זמן אמת.");
  selection=null;list();compare();
 }catch(err){
  report=null;$("status").classList.add("danger");$("status").textContent="אי אפשר לאמת נתוני מחקר: "+err.message;
  replace("assetlist",el("div","אין נתונים מאומתים","loading"));replace("detail",el("div","לא מוצגים איתותים ללא נתונים","loading"));
 }
}
$("query").addEventListener("input",list);
$("sort").addEventListener("change",list);
$("period").addEventListener("change",()=>{selection=null;list();compare()});
$("filters").addEventListener("click",event=>{
 const b=event.target.closest("button[data-category]");if(!b)return;
 category=b.dataset.category;
 for(const btn of $("filters").querySelectorAll("button"))btn.classList.toggle("active",btn===b);
 list();
});
$("reload").addEventListener("click",load);
$("compareA").addEventListener("change",calculate);$("compareB").addEventListener("change",calculate);
load();
