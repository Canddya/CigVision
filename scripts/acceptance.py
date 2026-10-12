"""Isolated integration tests. Test model is random/untrained, never production."""
import io
import json
import os
from pathlib import Path
import sys
import time
import statistics

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'docs/acceptance'
DATA = OUT / 'test-data' / str(time.time_ns())
DATA.mkdir(parents=True)
os.environ['CIGYOLO_DATA_DIR'] = str(DATA)
os.environ['CIGYOLO_MODEL'] = str(DATA / 'missing.pt')
os.environ['YOLO_CONFIG_DIR'] = str(ROOT / 'db/yolo-config')
from fastapi.testclient import TestClient
from PIL import Image
from webapp import main

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name)

def img(fmt='PNG'):
    b = io.BytesIO()
    Image.new('RGB', (80, 60), (180, 180, 180)).save(b, format=fmt)
    return b.getvalue()

with TestClient(main.app) as c:
    check('首页 UTF-8', '卷烟盒外观质量检测' in c.get('/').text)
    check('缺失模型明确显示未就绪', not c.get('/api/model').json()['ready'])
    check('空上传拒绝', c.post('/api/batches', files=[]).status_code == 400)
    check('101 张服务端拒绝', c.post('/api/batches', files=[('files', (f'{i}.png', img())) for i in range(101)]).status_code == 400)
    check('损坏图片拒绝', c.post('/api/batches', files=[('files', ('bad.png', b'bad'))]).status_code == 400)
    check('伪造扩展名拒绝', c.post('/api/batches', files=[('files', ('bad.bmp', img('GIF')))]).status_code == 400)
    check('超大单文件拒绝', c.post('/api/batches', files=[('files', ('large.png', b'0'*(20*1024*1024+1)))]).status_code == 413)
    check('无效批次 404', c.get('/api/batches/not-exist').status_code == 404)
    r = c.post('/api/batches', files=[('files', (f'中文_{i}.{ext}', img(fmt))) for i,(ext,fmt) in enumerate([('jpg','JPEG'),('png','PNG'),('BMP','BMP')])])
    check('JPG PNG BMP 中文文件名上传', r.status_code == 201 and r.json()['total'] == 3)
    batch = r.json(); bid = batch['id']
    check('缺失模型禁止产生预测', c.post(f'/api/batches/{bid}/run').status_code == 409)
    check('原图预览', c.get('/api/images/'+batch['images'][0]['id']).status_code == 200)
    check('CSV 中文 BOM', c.get(f'/api/batches/{bid}/csv').content.startswith(b'\xef\xbb\xbf'))
    many = c.post('/api/batches', files=[('files', ('same.png', img())) for _ in range(100)])
    check('100 张上传与重名隔离', many.status_code == 201 and len({i['storage_name'] for i in many.json()['images']}) == 100)
    # Real YOLO architecture, random parameters. Proves execution only, not accuracy.
    from ultralytics import YOLO
    from ultralytics.nn.tasks import ClassificationModel
    from ultralytics.data.augment import classify_transforms
    model = YOLO('yolo11n-cls.yaml')
    model.model = ClassificationModel('yolo11n-cls.yaml', nc=2, verbose=False)
    model.model.names = {0:'Right',1:'Wrong'}
    model.model.transforms = classify_transforms(800)
    model.model.args = {'task':'classify', 'imgsz':800}
    model.ckpt = {'train_args': {'task':'classify', 'imgsz':800}}
    weights = DATA / 'UNTRAINED-integration-only.pt'
    model.save(str(weights))
    os.environ['CIGYOLO_MODEL'] = str(weights)
    check('真实 YOLO 引擎加载隔离的未训练测试权重', c.post('/api/model/reload').json()['ready'])
    check('异步推理启动', c.post(f'/api/batches/{bid}/run').status_code == 202)
    check('运行中拒绝重复启动', c.post(f'/api/batches/{bid}/run').status_code == 409)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        batch=c.get(f'/api/batches/{bid}').json()
        if batch['status']!='running': break
        time.sleep(.2)
    check('真实 YOLO 前向推理完成（仅链路验收）', batch['status']=='completed' and batch['completed']==3)
    check('分类概率范围和耗时', all(i['class_name'] in {'Right','Wrong'} and 0<=i['confidence']<=1 and i['elapsed_ms']>0 for i in batch['images']))
    check('模型溯源持久化', len(batch['model_sha256'])==64)
    check('已完成批次不可重复启动', c.post(f'/api/batches/{bid}/run').status_code==409)
    # Error handling and progress are tested explicitly, separately from actual YOLO.
    original_predict=main.engine.predict
    def failing(path): raise RuntimeError('验收：模拟推理失败')
    main.engine.predict=failing
    c.post(f"/api/batches/{many.json()['id']}/run")
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        failed=c.get(f"/api/batches/{many.json()['id']}").json()
        if failed['status']!='running': break
        time.sleep(.1)
    check('逐张失败持久化且任务结束', failed['status']=='partial' and failed['failed']==100)
    main.engine.predict=original_predict
    perf={}
    for route in ['/', '/api/model', '/api/batches', f'/api/batches/{bid}', f'/api/batches/{bid}/csv']:
        values=[]
        for _ in range(6):
            t=time.perf_counter(); response=c.get(route); values.append((time.perf_counter()-t)*1000)
            assert response.status_code==200
        perf[route]={'mean_ms':round(statistics.mean(values),2),'max_ms':round(max(values),2)}
    check('核心读取 API 平均响应小于 2 秒',all(p['mean_ms']<2000 for p in perf.values()))

with TestClient(main.app) as c:
    check('服务重启后结果保留',c.get(f'/api/batches/{bid}').json()['completed']==3)

report={'checks':checks,'performance':perf,'inference':batch,'production_model_acceptance':'BLOCKED: trained CigYOLO weights not provided','test_data':str(DATA)}
(OUT/'functional.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved',OUT/'functional.json')
