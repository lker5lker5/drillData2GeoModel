// 分层观察 / 岩性显隐 / 钻孔显隐 面板脚本（交互式模型页共用）
//
// 原先这段脚本由 handlers/processors.py 以 f-string 逐页拼进 HTML：每生成一个页面就
// 多内嵌一份完全相同的代码，且 JS 的花括号在 f-string 里必须写成 {{ }}。
// 现改为独立文件，浏览器只需下载一次（之后各页命中缓存），JS 也不再受 f-string 转义约束。
//
// 页面通过内联的 window.LAYER_PANEL_CFG 传入参数：
//   lithOrder  : 岩性顺序（数组），决定分层展开的方向
//   sep        : 相邻岩性水平展开的最大间距（与页面 X 范围成比例）
//   lithTraces : {岩性: [trace 索引...]}，供岩性开关使用
//   drill      : 钻孔 trace 索引数组，供钻孔开关使用
// 缺失的键按“无该项”处理，与原先按需注入各分支的行为一致。

(function(){
var gdP=document.getElementById('layer-explode-model');
if(!gdP)gdP=document.querySelector('.js-plotly-plot');
if(!gdP)return;

// 参数由页面内联的 window.LAYER_PANEL_CFG 传入（岩性顺序、展开间距、trace 索引）
var CFG=window.LAYER_PANEL_CFG||{};

var LITH_ORDER=CFG.lithOrder||[];
var SEP=CFG.sep||0;
var N_LITH=LITH_ORDER.length;
var _rafId=null,_pendingFactor=null;

// 分层观察所需的 trace 列表：运行时从 gd.data 派生，不在 HTML 里重复内嵌一份坐标。
// 这里只保存对“原始数组”的引用——Plotly.restyle 是整体替换 gd.data[ix].x，不会就地改写，
// 因此原始数组始终保持初始值，本函数也就天然幂等（无累积漂移）。
var BODY=null;
function buildBody(){
 if(BODY)return BODY;
 BODY=[];
 LITH_ORDER.forEach(function(lith){
  var idxs=LITH_TRACES[lith]||[];
  for(var k=0;k<idxs.length;k++){
   var ix=idxs[k],tr=gdP.data[ix];
   if(!tr||!tr.x||!tr.z)continue;
   BODY.push({
    trace:ix,lith:lith,
    type:(tr.type==='mesh3d'?'mesh':'surface'),
    x:tr.x,z:tr.z
   });
  }
 });
 return BODY;
}

function applySpread(factor){
 _pendingFactor=factor;
 if(_rafId!==null)return;
 _rafId=requestAnimationFrame(function(){
  var f=_pendingFactor;_pendingFactor=null;_rafId=null;
  var body=buildBody();
  var xList=[],xIx=[],zList=[],zIx=[];
  var center=(N_LITH-1)/2;
  for(var i=0;i<body.length;i++){
   var m=body[i],li=LITH_ORDER.indexOf(m.lith);
   if(li<0)continue;
   var offX=(li-center)*f*SEP;
   var offZ=Math.abs(li-center)*f*SEP*0.06;
   if(m.type==='mesh'){
    xList.push(m.x.map(function(v){return v+offX;}));
    zList.push(m.z.map(function(v){return v===null?null:v+offZ;}));
   }else{
    xList.push(m.x.map(function(r){return r.map(function(v){return v+offX;});}));
    zList.push(m.z.map(function(r){return r.map(function(v){return v===null?null:v+offZ;});}));
   }
   xIx.push(m.trace);zIx.push(m.trace);
  }
  Plotly.restyle(gdP,{x:xList,z:zList},xIx);
 });
}
var sl=document.getElementById('layer-explode-slider');
if(sl){
var lb=document.getElementById('layer-explode-label');
sl.addEventListener('input',function(){var f=parseInt(this.value)/100;lb.textContent=Math.round(f*100)+'%';applySpread(f)});
document.getElementById('layer-explode-reset').addEventListener('click',function(){sl.value=0;lb.textContent='0%';applySpread(0)});
}

var LITH_TRACES=CFG.lithTraces||{};
document.querySelectorAll('.lith-toggle-cb').forEach(function(cb){
 cb.addEventListener('change',function(){
  var traces=LITH_TRACES[this.value];
  if(traces&&traces.length) Plotly.restyle(gdP,'visible',this.checked,traces);
 });
});

var DRILL=CFG.drill||[];
var dt=document.getElementById('drill-toggle');
if(dt)dt.addEventListener('change',function(){
 Plotly.restyle(gdP,'visible',this.checked,DRILL);
});

})();
