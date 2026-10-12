const $=id=>document.getElementById(id);
let files=[], current=null, model={ready:false}, lineConfig=null, selected=null, busy=false, polling=false;
const states={uploaded:'待检测',running:'检测中',completed:'已完成',partial:'部分失败',interrupted:'已中断',pending:'待检测',error:'失败',done:'已完成'};
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
async function api(url,options={}){const r=await fetch(url,options);if(!r.ok){let msg='请求失败';try{const x=await r.json();msg=typeof x.detail==='string'?x.detail:JSON.stringify(x.detail);}catch{}throw Error(msg);}return r.json();}
function label(item){return item.class_name==='Right'?'良好':item.class_name==='Wrong'?'缺陷':states[item.status]||item.status;}
function badge(item){const el=document.createElement('span');el.className='badge '+(item.class_name==='Right'?'good':item.class_name==='Wrong'?'defect':item.status);el.textContent=label(item);return el;}
function displayFiles(){ $('fileCount').textContent=`已选择 ${files.length} / 100`;$('fileList').replaceChildren();files.forEach((file,i)=>{const li=document.createElement('li'),name=document.createElement('span'),remove=document.createElement('button');name.textContent=file.name;name.title=file.name;remove.textContent='×';remove.setAttribute('aria-label','移除 '+file.name);remove.disabled=busy;remove.onclick=()=>{files.splice(i,1);displayFiles();};li.append(name,remove);$('fileList').append(li);});if(!files.length){const li=document.createElement('li');li.textContent='尚未选择图片';li.className='muted';$('fileList').append(li);}$('uploadButton').disabled=!files.length||busy;$('fileInput').disabled=busy;$('clearFiles').disabled=busy;$('uploadButton').textContent=busy?'正在上传…':model.ready?'上传并开始检测':'上传图片';}
function addFiles(incoming){if(busy)return;const next=[...files,...incoming];if(next.length>100)return notice('每批最多上传 100 张图片，请减少数量后重试。');if(next.some(f=>!(/\.(jpe?g|png|bmp)$/i.test(f.name))))return notice('仅支持 JPG、PNG、BMP 图片。');if(next.some(f=>f.size>20*1024*1024))return notice('单张图片不能超过 20 MB。');if(next.reduce((n,f)=>n+f.size,0)>200*1024*1024)return notice('每批图片总大小不能超过 200 MB。');files=next;notice('');displayFiles();}
$('fileInput').onchange=e=>{addFiles(Array.from(e.target.files));e.target.value='';};$('clearFiles').onclick=()=>{files=[];displayFiles();};
for(const event of ['dragover','dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.toggle('dragover',event==='dragover');if(event==='drop')addFiles(Array.from(e.dataTransfer.files));});
async function getModel(){model=await api('/api/model');$('modelMessage').textContent=model.message;$('modelMessage').classList.toggle('ready',model.ready);$('modelName').textContent=model.model_name||'待接入训练权重';$('device').textContent=model.device||'加载模型后显示';displayFiles();if(current)render();}
function setInterfaceState(element, enabled){element.textContent=enabled?'已启用':'未启用';element.classList.toggle('on',enabled);element.classList.toggle('off',!enabled);}
function renderLineConfig(config){
  lineConfig=config;
  setInterfaceState($('lineEntryStatus'),config.enabled);
  setInterfaceState($('lineConfigState'),config.enabled);
  $('lineEnabled').checked=config.enabled;
  $('lineName').value=config.line_name;
  $('deviceCode').value=config.device_code;
  $('lineKeyState').textContent=config.api_key_configured?'已配置访问密钥；留空保存将继续使用原密钥。':'尚未配置访问密钥';
  $('lineEndpoint').textContent=location.origin+config.endpoint;
  $('lineCurlExample').textContent=`curl -X POST "${location.origin}${config.endpoint}" \\\n  -H "X-CigYOLO-Key: <访问密钥>" \\\n  -H "X-Image-ID: <图片唯一编号>" \\\n  -F "image=@camera.jpg"`;
}
async function getLineConfig(){const config=await api('/api/line/config');renderLineConfig(config);return config;}
$('reloadModel').onclick=async()=>{const b=$('reloadModel');b.disabled=true;try{notice('正在加载模型…');await api('/api/model/reload',{method:'POST'});await getModel();notice(model.ready?'模型加载成功，可以开始检测。':model.message);}catch(e){notice(e.message);}finally{b.disabled=false;}};
$('uploadButton').onclick=async()=>{busy=true;displayFiles();notice('正在上传图片，请稍候…');try{const data=new FormData();files.forEach(f=>data.append('files',f));current=await api('/api/batches',{method:'POST',body:data});selected=null;files=[];localStorage.setItem('cigyoloBatch',current.id);render();notice(model.ready?'':'图片上传成功。接入训练模型后，可点击“开始检测”。');if(model.ready)await run();}catch(e){notice(e.message);}finally{busy=false;displayFiles();}};
async function run(){if(!current)return;const id=current.id;$('runButton').disabled=true;try{await api(`/api/batches/${id}/run`,{method:'POST'});current=await api(`/api/batches/${id}`);notice('');render();}catch(e){notice(e.message);}finally{$('runButton').disabled=false;}}
$('runButton').onclick=run;
function render(){const b=current;$('total').textContent=b.total;$('good').textContent=b.good;$('defect').textContent=b.defect;$('progressText').textContent=states[b.status]+(b.failed?` · ${b.failed} 张失败`:'');$('progressNumber').textContent=`${b.completed+b.failed} / ${b.total}`;$('progress').value=(b.completed+b.failed)/b.total*100;$('runButton').hidden=b.status==='completed'||b.status==='running';$('runButton').disabled=!model.ready;$('runButton').textContent=['partial','interrupted'].includes(b.status)?'重新检测':'开始检测';$('exportButton').href=`/api/batches/${b.id}/csv`;$('exportButton').classList.remove('disabled');$('exportButton').setAttribute('aria-disabled','false');$('results').replaceChildren();for(const item of b.images){const row=document.createElement('tr');row.classList.toggle('selected',selected===item.id);const values=[item.ordinal,item.filename,null,item.confidence===null?'—':(item.confidence*100).toFixed(2)+'%',item.elapsed_ms===null?'—':item.elapsed_ms.toFixed(0)+' ms'];for(let i=0;i<values.length;i++){const td=document.createElement('td');if(i===2)td.append(badge(item));else td.textContent=values[i];if(i===1)td.title=item.filename;row.append(td);}const td=document.createElement('td'),btn=document.createElement('button');btn.textContent='查看';btn.onclick=()=>{selected=item.id;render();};td.append(btn);row.append(td);$('results').append(row);}if(!selected&&b.images.length)selected=b.images[0].id;preview(b.images.find(i=>i.id===selected));}
function preview(item){if(!item)return;$('previewEmpty').hidden=true;$('preview').hidden=false;const src=`/api/images/${item.id}`;if($('previewImage').getAttribute('src')!==src)$('previewImage').src=src;$('previewImage').alt=item.filename;$('previewName').textContent=item.filename;$('previewMeta').replaceChildren();for(const [name,value] of [['图片尺寸',`${item.width} × ${item.height}`],['文件大小',`${(item.size_bytes/1024).toFixed(1)} KB`],['判定结果',label(item)],['置信度',item.confidence===null?'—':(item.confidence*100).toFixed(2)+'%'],['推理耗时',item.elapsed_ms===null?'—':item.elapsed_ms+' ms'],...(item.error?[['失败原因',item.error]]:[])]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;$('previewMeta').append(dt,dd);}}
async function showHistory(){const rows=await api('/api/batches');$('historyRows').replaceChildren();if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=6;td.className='empty';td.textContent='暂无检测记录，上传图片后会自动保存。';tr.append(td);$('historyRows').append(tr);}for(const b of rows){const tr=document.createElement('tr');for(const value of [new Date(b.created_at).toLocaleString('zh-CN'),b.id.slice(0,8),b.total,`${b.good} / ${b.defect}`,states[b.status]]){const td=document.createElement('td');td.textContent=value;tr.append(td);}const td=document.createElement('td'),button=document.createElement('button');button.textContent='打开';button.onclick=async()=>{try{current=await api(`/api/batches/${b.id}`);selected=null;localStorage.setItem('cigyoloBatch',b.id);render();switchPage('workbench');}catch(e){notice(e.message);}};td.append(button);tr.append(td);$('historyRows').append(tr);}}
function switchPage(id){$('locationCurrent').textContent={workbench:'烟盒包装破损检测',history:'检测记录',help:'使用说明',lineConfig:'流水线实时接口配置'}[id];document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!==id);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===id));if(id==='history')showHistory().catch(e=>notice(e.message));}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>switchPage(b.dataset.page));$('refreshHistory').onclick=()=>showHistory().catch(e=>notice(e.message));
setInterval(async()=>{if(!current||current.status!=='running'||polling)return;polling=true;const id=current.id;try{const b=await api(`/api/batches/${id}`);if(current.id===id){current=b;render();}}catch(e){notice('连接暂时中断，正在自动重试：'+e.message);}finally{polling=false;}},600);
(async()=>{try{await Promise.all([getModel(),getLineConfig()]);const id=localStorage.getItem('cigyoloBatch');if(id){try{current=await api(`/api/batches/${id}`);render();}catch{localStorage.removeItem('cigyoloBatch');}}}catch(e){notice(e.message);}})();

$('openLineConfig').onclick=async()=>{try{await getLineConfig();switchPage('lineConfig');scrollToSection(document.querySelector('main'));}catch(e){notice(e.message);}};
$('backToWorkbench').onclick=()=>switchPage('workbench');
$('toggleLineKey').onclick=()=>{const input=$('lineApiKey'),show=input.type==='password';input.type=show?'text':'password';$('toggleLineKey').textContent=show?'隐藏':'显示';};
$('generateLineKey').onclick=()=>{const bytes=new Uint8Array(24);crypto.getRandomValues(bytes);$('lineApiKey').value=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');$('lineApiKey').type='text';$('toggleLineKey').textContent='隐藏';$('lineSaveMessage').textContent='已生成新密钥，请复制并保存配置。';};
$('copyLineKey').onclick=async()=>{const value=$('lineApiKey').value;if(!value){$('lineSaveMessage').textContent='请先输入或生成新密钥。';return;}try{await navigator.clipboard.writeText(value);$('lineSaveMessage').textContent='密钥已复制。';}catch{$('lineApiKey').select();document.execCommand('copy');$('lineSaveMessage').textContent='密钥已复制。';}};
$('lineConfigForm').onsubmit=async event=>{event.preventDefault();const button=$('saveLineConfig');button.disabled=true;$('lineSaveMessage').textContent='正在保存…';try{const newKey=$('lineApiKey').value.trim();const config=await api('/api/line/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('lineEnabled').checked,line_name:$('lineName').value.trim(),device_code:$('deviceCode').value.trim(),new_api_key:newKey||null})});$('lineApiKey').value='';$('lineApiKey').type='password';$('toggleLineKey').textContent='显示';renderLineConfig(config);$('lineSaveMessage').textContent='配置已保存并立即生效。';}catch(e){$('lineSaveMessage').textContent=e.message;}finally{button.disabled=false;}};

function scrollToSection(target) {
  const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
  target.scrollIntoView({ behavior, block: 'start' });
}
document.querySelectorAll('[data-footer-page]').forEach(button => {
  button.onclick = () => { switchPage(button.dataset.footerPage); scrollToSection(document.querySelector('main')); };
});
document.querySelectorAll('[data-footer-target]').forEach(button => {
  button.onclick = () => {
    switchPage('workbench');
    const target = button.dataset.footerTarget === 'model-panel' ? document.querySelector('.model-panel') : $('dropzone');
    scrollToSection(target);
  };
});
$('backToTop').onclick = () => scrollToSection(document.body);
