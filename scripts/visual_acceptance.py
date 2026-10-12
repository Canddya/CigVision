"""Browser acceptance with local Chrome; no downloaded browser required."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance'
errors=[]
checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.get_by_text('未配置可用模型',exact=False).wait_for()
    page.screenshot(path=str(OUT/'desktop-empty.png'),full_page=True)
    files=list((ROOT/'CigYOLO/data').glob('*/*.BMP'))[:3]
    page.locator('#fileInput').set_input_files([str(f) for f in files])
    assert page.locator('#fileCount').inner_text()=='已选择 3 / 100'
    page.locator('#uploadButton').click()
    page.wait_for_function("document.querySelector('#total').textContent === '3'")
    page.wait_for_function("document.querySelector('#previewImage').complete && document.querySelector('#previewImage').naturalWidth > 0")
    assert page.locator('#runButton').is_disabled()
    checks.append('真实浏览器选择文件、上传三张 BMP、预览成功；缺模型禁用检测')
    page.screenshot(path=str(OUT/'desktop-uploaded.png'),full_page=True)
    with page.expect_download() as info:
        page.locator('#exportButton').click()
    info.value.save_as(str(OUT/'browser-export.csv'))
    checks.append('真实浏览器 CSV 下载')
    page.get_by_role('button',name='检测记录',exact=True).click()
    page.get_by_role('button',name='打开',exact=True).first.wait_for()
    page.screenshot(path=str(OUT/'desktop-history.png'),full_page=True)
    page.get_by_role('button',name='打开',exact=True).first.click()
    page.reload(wait_until='networkidle')
    page.wait_for_function("document.querySelector('#total').textContent === '3'")
    checks.append('历史记录打开与刷新恢复')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    checks.append('390px 手机视口无页面横向溢出（表格内部滚动）')
    page.get_by_role('button',name='使用说明',exact=True).click()
    page.screenshot(path=str(OUT/'mobile-help.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert '\ufffd' not in page.locator('body').inner_text()
    assert not errors,errors
    checks.append('无浏览器 JavaScript 异常或替换字符')
    browser.close()
(OUT/'visual.json').write_text(json.dumps({'checks':checks,'console_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False))
