import csv
import asyncio
import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import uuid

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile as FastAPIUploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile
from .inference import Classifier, ROOT

DATA = Path(os.getenv('CIGYOLO_DATA_DIR', str(ROOT / 'db'))).resolve()
UPLOADS = DATA / 'uploads'
DB = DATA / 'cigyolo.sqlite3'
MAX_FILE = 20 * 1024 * 1024
MAX_BATCH_BYTES = 200 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 24_000_000
engine = Classifier()
gate = threading.Lock()
pool = None


class LineConfigUpdate(BaseModel):
    enabled: bool
    line_name: str = Field(min_length=1, max_length=60)
    device_code: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9._-]+$')
    new_api_key: Optional[str] = Field(default=None, min_length=16, max_length=128)


def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def line_config_payload(row):
    return {
        'enabled': bool(row['enabled']),
        'line_name': row['line_name'],
        'device_code': row['device_code'],
        'api_key_configured': bool(row['api_key_hash']),
        'updated_at': row['updated_at'],
        'endpoint': '/api/line/image',
        'method': 'POST',
        'auth_header': 'X-CigYOLO-Key',
    }


def normalize_image(data: bytes, filename: str, destination: Path):
    if len(data) > MAX_FILE:
        raise HTTPException(413, '单张图片不能超过 20 MB')
    if Path(filename).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.bmp'}:
        raise HTTPException(400, '仅支持 JPG、PNG、BMP 图片')
    try:
        with Image.open(io.BytesIO(data)) as check:
            if check.format not in {'JPEG', 'PNG', 'BMP'}:
                raise ValueError('图片内容格式不支持')
            if check.width * check.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('图片不能超过 2400 万像素')
            check.verify()
        with Image.open(io.BytesIO(data)) as source:
            normalized = ImageOps.exif_transpose(source).convert('RGB')
            width, height = normalized.size
            normalized.save(destination, format='PNG')
        return width, height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, f'图片损坏或无法读取（{exc}）')


@asynccontextmanager
async def lifespan(app):
    global pool
    UPLOADS.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript((ROOT / 'webapp/schema.sql').read_text(encoding='utf-8'))
        db.execute("UPDATE images SET status='error',error='服务重启，请重新检测' WHERE status='running'")
        db.execute("UPDATE batches SET status='interrupted' WHERE status='running'")
    engine.load()
    pool = ThreadPoolExecutor(max_workers=1)
    yield
    pool.shutdown(wait=True)


app = FastAPI(title='基于YOLO图像分类的卷烟盒外观质量智能检测平台', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'webapp/static'), name='static')


@app.get('/')
def index():
    static = ROOT / 'webapp/static'
    html = (static / 'index.html').read_text(encoding='utf-8')
    # Keep the HTML and its assets in sync even when a browser cached older CSS.
    for asset in ('style.css', 'app.js'):
        version = hashlib.sha256((static / asset).read_bytes()).hexdigest()[:12]
        html = html.replace(f'/static/{asset}', f'/static/{asset}?v={version}')
    return Response(html, media_type='text/html; charset=utf-8',
                    headers={'Cache-Control': 'no-store'})


@app.get('/api/model')
def model_status():
    return engine.info


@app.post('/api/model/reload')
def reload_model():
    with gate:
        with connect() as db:
            if db.execute("SELECT 1 FROM batches WHERE status='running'").fetchone():
                raise HTTPException(409, '检测运行中，请完成后重新加载模型')
        return engine.load()


@app.get('/api/line/config')
def get_line_config():
    with connect() as db:
        row = db.execute('SELECT * FROM line_interface_config WHERE id=1').fetchone()
    return line_config_payload(row)


@app.put('/api/line/config')
def update_line_config(config: LineConfigUpdate):
    line_name = config.line_name.strip()
    device_code = config.device_code.strip()
    if not line_name or not device_code:
        raise HTTPException(400, '产线名称和设备编号不能为空')
    with connect() as db:
        current = db.execute('SELECT * FROM line_interface_config WHERE id=1').fetchone()
        key_hash = current['api_key_hash']
        if config.new_api_key:
            key_hash = hashlib.sha256(config.new_api_key.encode('utf-8')).hexdigest()
        if config.enabled and not key_hash:
            raise HTTPException(400, '启用接口前必须设置访问密钥')
        db.execute(
            'UPDATE line_interface_config SET enabled=?,line_name=?,device_code=?,api_key_hash=?,updated_at=? WHERE id=1',
            (int(config.enabled), line_name, device_code, key_hash, utc_now()),
        )
        row = db.execute('SELECT * FROM line_interface_config WHERE id=1').fetchone()
    return line_config_payload(row)


@app.post('/api/line/image')
async def receive_line_image(
    image: FastAPIUploadFile = File(...),
    api_key: Optional[str] = Header(default=None, alias='X-CigYOLO-Key'),
    client_image_id: Optional[str] = Header(default=None, alias='X-Image-ID'),
):
    with connect() as db:
        config = db.execute('SELECT * FROM line_interface_config WHERE id=1').fetchone()
        if not config['enabled']:
            raise HTTPException(503, '流水线实时接口未启用')
        supplied_hash = hashlib.sha256((api_key or '').encode('utf-8')).hexdigest()
        if not config['api_key_hash'] or not hmac.compare_digest(supplied_hash, config['api_key_hash']):
            raise HTTPException(401, '访问密钥无效')
        if client_image_id and db.execute(
            'SELECT 1 FROM line_events WHERE device_code=? AND client_image_id=?',
            (config['device_code'], client_image_id[:100]),
        ).fetchone():
            raise HTTPException(409, '该图片编号已经接收')
    if not engine.info['ready']:
        raise HTTPException(503, engine.info['message'])

    filename = (image.filename or 'line-image.jpg').replace('\\', '/').rsplit('/', 1)[-1][:240]
    data = await image.read(MAX_FILE + 1)
    batch_id = uuid.uuid4().hex
    image_id = uuid.uuid4().hex
    event_id = uuid.uuid4().hex
    folder = UPLOADS / batch_id
    storage = batch_id + '/' + image_id + '.png'
    folder.mkdir()
    try:
        width, height = normalize_image(data, filename, UPLOADS / storage)
        received_at = utc_now()
        with connect() as db:
            db.execute(
                'INSERT INTO batches(id,created_at,status,model_name,model_sha256,device) VALUES (?,?,?,?,?,?)',
                (batch_id, received_at, 'running', engine.info['model_name'], engine.info['model_sha256'], engine.info['device']),
            )
            db.execute(
                "INSERT INTO images(id,batch_id,ordinal,filename,storage_name,width,height,size_bytes,status) VALUES (?,?,?,?,?,?,?,?, 'running')",
                (image_id, batch_id, 1, filename, storage, width, height, len(data)),
            )
            db.execute(
                'INSERT INTO line_events(id,batch_id,device_code,client_image_id,received_at) VALUES (?,?,?,?,?)',
                (event_id, batch_id, config['device_code'], client_image_id[:100] if client_image_id else None, received_at),
            )
    except sqlite3.IntegrityError:
        shutil.rmtree(folder)
        raise HTTPException(409, '该图片编号已经接收')
    except Exception:
        if folder.exists():
            shutil.rmtree(folder)
        raise

    try:
        class_name, confidence, elapsed_ms = await asyncio.get_running_loop().run_in_executor(
            pool, engine.predict, UPLOADS / storage
        )
        with connect() as db:
            db.execute(
                "UPDATE images SET status='done',class_name=?,confidence=?,elapsed_ms=? WHERE id=?",
                (class_name, confidence, elapsed_ms, image_id),
            )
            db.execute("UPDATE batches SET status='completed' WHERE id=?", (batch_id,))
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE images SET status='error',error=? WHERE id=?", (str(exc), image_id))
            db.execute("UPDATE batches SET status='partial' WHERE id=?", (batch_id,))
        raise HTTPException(500, f'模型推理失败：{exc}')

    return {
        'accepted': True,
        'batch_id': batch_id,
        'image_id': image_id,
        'client_image_id': client_image_id,
        'line_name': config['line_name'],
        'device_code': config['device_code'],
        'class_name': class_name,
        'result': '良好' if class_name == 'Right' else '缺陷',
        'confidence': confidence,
        'elapsed_ms': elapsed_ms,
        'received_at': received_at,
    }


@app.post('/api/batches', status_code=201)
async def upload(request: Request):
    # Bound multipart file count and request size before parsing to disk.
    try:
        length = int(request.headers.get('content-length', '0'))
    except ValueError:
        raise HTTPException(400, '无效请求长度')
    if length > MAX_BATCH_BYTES + 1024 * 1024:
        raise HTTPException(413, '每批图片总大小不能超过 200 MB')
    batch_id = uuid.uuid4().hex
    folder = UPLOADS / batch_id
    records = []
    total = 0
    try:
        async with request.form(max_files=100, max_fields=2) as form:
            files = form.getlist('files')
            if not 1 <= len(files) <= 100 or not all(isinstance(f, UploadFile) for f in files):
                raise HTTPException(400, '请选择 1–100 张图片')
            folder.mkdir()
            for ordinal, file in enumerate(files, 1):
                filename = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1][:240]
                if Path(filename).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.bmp'}:
                    raise HTTPException(400, f'{filename}：仅支持 JPG、PNG、BMP')
                data = await file.read(MAX_FILE + 1)
                total += len(data)
                if len(data) > MAX_FILE or total > MAX_BATCH_BYTES:
                    raise HTTPException(413, '单张不能超过 20 MB，每批不能超过 200 MB')
                image_id = uuid.uuid4().hex
                storage = batch_id + '/' + image_id + '.png'
                try:
                    with Image.open(io.BytesIO(data)) as check:
                        if check.format not in {'JPEG', 'PNG', 'BMP'}:
                            raise ValueError('图片内容格式不支持')
                        if check.width * check.height > Image.MAX_IMAGE_PIXELS:
                            raise ValueError('图片不能超过 2400 万像素')
                        check.verify()
                    with Image.open(io.BytesIO(data)) as im:
                        normalized = ImageOps.exif_transpose(im).convert('RGB')
                        width, height = normalized.size
                        normalized.save(UPLOADS / storage, format='PNG')
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                    raise HTTPException(400, f'{filename}：图片损坏或无法读取（{exc}）')
                records.append((image_id, batch_id, ordinal, filename, storage, width, height, len(data)))
        with connect() as db:
            db.execute('INSERT INTO batches(id,created_at) VALUES (?,?)', (batch_id, datetime.now(timezone.utc).isoformat()))
            db.executemany('INSERT INTO images(id,batch_id,ordinal,filename,storage_name,width,height,size_bytes) VALUES (?,?,?,?,?,?,?,?)', records)
    except Exception:
        if folder.exists():
            shutil.rmtree(folder)  # Only the newly generated UUID upload directory.
        raise
    return batch(batch_id)


@app.get('/api/batches')
def history():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM batch_summary ORDER BY created_at DESC LIMIT 100')]


@app.get('/api/batches/{batch_id}')
def batch(batch_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM batch_summary WHERE id=?', (batch_id,)).fetchone()
        if row is None:
            raise HTTPException(404, '检测批次不存在')
        result = dict(row)
        result['images'] = [dict(r) for r in db.execute('SELECT * FROM images WHERE batch_id=? ORDER BY ordinal', (batch_id,))]
    return result


def run_batch(batch_id):
    try:
        for item in batch(batch_id)['images']:
            if item['status'] == 'done':
                continue
            with connect() as db:
                db.execute("UPDATE images SET status='running',error=NULL WHERE id=?", (item['id'],))
            try:
                name, confidence, ms = engine.predict(UPLOADS / item['storage_name'])
                with connect() as db:
                    db.execute("UPDATE images SET status='done',class_name=?,confidence=?,elapsed_ms=? WHERE id=?", (name, confidence, ms, item['id']))
            except Exception as exc:
                with connect() as db:
                    db.execute("UPDATE images SET status='error',error=? WHERE id=?", (str(exc), item['id']))
        with connect() as db:
            failed = db.execute("SELECT count(*) FROM images WHERE batch_id=? AND status='error'", (batch_id,)).fetchone()[0]
            db.execute('UPDATE batches SET status=? WHERE id=?', ('partial' if failed else 'completed', batch_id))
    except Exception:
        with connect() as db:
            db.execute("UPDATE batches SET status='interrupted' WHERE id=?", (batch_id,))


@app.post('/api/batches/{batch_id}/run', status_code=202)
def start(batch_id: str):
    with gate:
        current = batch(batch_id)
        if not engine.info['ready']:
            raise HTTPException(409, engine.info['message'])
        with connect() as db:
            if db.execute("SELECT 1 FROM batches WHERE status='running'").fetchone():
                raise HTTPException(409, '已有批次正在检测，请等待完成')
            if current['status'] == 'completed':
                raise HTTPException(409, '该批次已完成检测')
            db.execute("UPDATE batches SET status='running',model_name=?,model_sha256=?,device=? WHERE id=?",
                       (engine.info['model_name'], engine.info['model_sha256'], engine.info['device'], batch_id))
            # Retry entire failed/interrupted batch so model provenance stays consistent.
            db.execute("UPDATE images SET status='pending',class_name=NULL,confidence=NULL,elapsed_ms=NULL,error=NULL WHERE batch_id=?", (batch_id,))
        pool.submit(run_batch, batch_id)
    return {'id': batch_id, 'status': 'running'}


@app.get('/api/images/{image_id}')
def image_file(image_id: str):
    with connect() as db:
        row = db.execute('SELECT storage_name FROM images WHERE id=?', (image_id,)).fetchone()
    if row is None:
        raise HTTPException(404, '图片不存在')
    return FileResponse(UPLOADS / row['storage_name'], media_type='image/png')


@app.get('/api/batches/{batch_id}/csv')
def export(batch_id: str):
    data = batch(batch_id)
    buf = io.StringIO(newline='')
    writer = csv.writer(buf)
    writer.writerow(['图片名称', '状态', '判定', '置信度', '耗时(ms)', '错误信息', '模型', '模型SHA256'])
    for item in data['images']:
        filename = item['filename']
        if filename.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            filename = "'" + filename
        writer.writerow([filename, item['status'], {'Right':'良好', 'Wrong':'缺陷'}.get(item['class_name'], ''),
                         '' if item['confidence'] is None else f"{item['confidence']:.6f}", item['elapsed_ms'],
                         item['error'], data['model_name'], data['model_sha256']])
    return Response(buf.getvalue().encode('utf-8-sig'), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="cigvision-{batch_id[:8]}.csv"'})
