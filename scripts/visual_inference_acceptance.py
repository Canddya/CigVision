"""Isolated browser test with UNTRAINED weights; never modifies production data."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance'
report=json.loads((OUT/'functional.json').read_text(encoding='utf-8'))
data=Path(report['test_data'])
env=os.environ.copy()
env.update(CIGYOLO_DATA_DIR=str(data),CIGYOLO_MODEL=str(data/'UNTRAINED-integration-only.pt'),CIGYOLO_PORT='8001')
log=(OUT/'isolated-server.log').open('w',encoding='utf-8')
server=subprocess.Popen([sys.executable,str(ROOT/'scripts/start.py')],cwd=str(ROOT),env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
try:
    for _ in range(90):
        try:
            if httpx.get('http://127.0.0.1:8001/api/model').json()['ready']:break
        except httpx.HTTPError:pass
        time.sleep(.5)
    else:raise RuntimeError('Isolated server failed')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8001',wait_until='networkidle')
        files=list((ROOT/'CigYOLO/data').glob('*/*.BMP'))
        page.locator('#fileInput').set_input_files([str(f) for f in files])
        page.locator('#uploadButton').click()
        page.wait_for_function("document.querySelector('#progressText').textContent === '已完成'",timeout=180000)
        assert page.locator('#results .badge.good, #results .badge.defect').count()==len(files)
        assert '—' not in page.locator('#results').inner_text()
        page.locator('#notice').evaluate("e=>{e.hidden=false;e.textContent='验收专用：本页使用未训练测试权重，仅验证推理与展示链路；不代表正式检测结果。'}")
        page.screenshot(path=str(OUT/'desktop-inference-TEST-ONLY.png'),full_page=True)
        assert not errors,errors
        browser.close()
    # Test full 100-image real forward execution in isolated data directory.
    client=httpx.Client(base_url='http://127.0.0.1:8001',timeout=120)
    content=files[0].read_bytes()
    batch=client.post('/api/batches',files=[('files',(f'{i}.BMP',content)) for i in range(100)]).json()
    started=time.perf_counter()
    assert client.post(f"/api/batches/{batch['id']}/run").status_code==202
    for _ in range(600):
        batch=client.get(f"/api/batches/{batch['id']}").json()
        if batch['status']!='running':break
        time.sleep(.2)
    assert batch['completed']==100 and batch['status']=='completed',batch
    result={'browser_real_inference_images':len(files),'browser_errors':errors,'batch_100_completed':batch['completed'],'batch_100_elapsed_seconds':round(time.perf_counter()-started,2),'warning':'UNTRAINED weights: pipeline acceptance only; production acceptance remains blocked'}
    (OUT/'inference-browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result)
finally:
    server.terminate()
    server.wait(timeout=30)
    log.close()
