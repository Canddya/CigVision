"""Exercise the running website using the supplied trained model and repository samples."""
from pathlib import Path
import csv
import io
import json
import time
import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/acceptance'
BASE = 'http://127.0.0.1:8000'
samples = sorted((ROOT / 'CigYOLO/data').glob('*/*.BMP'))
client = httpx.Client(base_url=BASE, timeout=120)
status = client.get('/api/model').json()
assert status['ready'], status
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until='networkidle')
    page.locator('#fileInput').set_input_files([str(f) for f in samples])
    page.locator('#uploadButton').click()
    page.wait_for_function("document.querySelector('#progressText').textContent === '已完成'", timeout=180000)
    bid = page.evaluate("localStorage.getItem('cigyoloBatch')")
    batch = client.get(f'/api/batches/{bid}').json()
    assert batch['completed'] == len(samples) and batch['failed'] == 0, batch
    assert page.locator('#results .badge.good, #results .badge.defect').count() == len(samples)
    page.wait_for_function("document.querySelector('#previewImage').complete && document.querySelector('#previewImage').naturalWidth > 0")
    page.screenshot(path=str(OUT/'trained-model-desktop.png'), full_page=True)
    with page.expect_download() as download:
        page.locator('#exportButton').click()
    download.value.save_as(str(OUT/'trained-model-results.csv'))
    rows = list(csv.DictReader(io.StringIO((OUT/'trained-model-results.csv').read_text(encoding='utf-8-sig'))))
    assert len(rows) == len(samples)
    assert all(row['判定'] in {'良好','缺陷'} for row in rows)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'trained-model-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    browser.close()

comparison = []
for sample, prediction in zip(samples,batch['images']):
    expected = 'Right' if sample.parent.name == '良好' else 'Wrong'
    comparison.append(dict(filename=sample.name,folder_label=expected,prediction=prediction['class_name'],
                           confidence=prediction['confidence'],elapsed_ms=prediction['elapsed_ms'],
                           matches_folder_label=expected==prediction['class_name']))
uploads = [('files',(f"test_{i:03d}_{samples[i%len(samples)].name}",samples[i%len(samples)].read_bytes())) for i in range(100)]
response=client.post('/api/batches', files=uploads)
response.raise_for_status()
large=response.json()
t=time.perf_counter()
response=client.post(f"/api/batches/{large['id']}/run")
assert response.status_code==202,response.text
for _ in range(600):
    large=client.get(f"/api/batches/{large['id']}").json()
    if large['status']!='running':break
    time.sleep(.2)
assert large['completed']==100 and large['failed']==0,large
result=dict(model=status,sample_batch_id=bid,samples=comparison,
            sample_matches=sum(x['matches_folder_label'] for x in comparison),sample_count=len(samples),
            batch100_id=large['id'],batch100_completed=large['completed'],batch100_seconds=round(time.perf_counter()-t,2),
            browser_errors=errors,note='文件夹标签仅作样例对照，6 张样例不足以评估泛化准确率；100 张测试循环使用这 6 张图片。')
(OUT/'trained-model.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
