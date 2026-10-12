"""Run with conda run --no-capture-output -n pytorch python scripts/start.py."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'db' / 'yolo-config'))
(ROOT / 'db' / 'yolo-config').mkdir(parents=True, exist_ok=True)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('webapp.main:app', host='127.0.0.1', port=int(os.getenv('CIGYOLO_PORT', '8000')), workers=1)
