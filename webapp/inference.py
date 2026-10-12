"""CigVision classification adapter; no substitute or auto-downloaded weights."""
import hashlib
import os
from pathlib import Path
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class Classifier:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None
        self.info = dict(ready=False, message='未配置模型：请将训练权重放入 models/best.pt，然后点击重新加载。',
                         model_name=None, model_sha256=None, device=None, imgsz=800)

    def load(self):
        with self.lock:
            self.model = None
            self.info.update(ready=False, model_name=None, model_sha256=None, device=None)
            default_path = ROOT / 'params/best.pt'
            if not default_path.is_file():
                default_path = ROOT / 'models/best.pt'
            path = Path(os.getenv('CIGYOLO_MODEL', str(default_path)))
            if not path.is_file():
                self.info['message'] = '未配置模型：请将训练权重放入 models/best.pt，然后点击重新加载。'
                return self.info
            try:
                import torch
                from ultralytics import YOLO
                candidate = YOLO(str(path), task='classify')
                names = {int(k): str(v) for k, v in candidate.names.items()}
                if candidate.task != 'classify' or set(names.values()) != {'Right', 'Wrong'} or len(names) != 2:
                    raise ValueError('需要包含 Right、Wrong 两个类别的 YOLO 分类权重')
                self.device = 0 if torch.cuda.is_available() else 'cpu'
                candidate.to(self.device)
                self.model = candidate
                self.info.update(ready=True, message='模型已就绪', model_name=path.name,
                                 model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 device=torch.cuda.get_device_name(0) if self.device == 0 else 'CPU')
            except Exception as exc:
                self.info['message'] = '模型加载失败：' + str(exc)
            return self.info

    def predict(self, path):
        with self.lock:
            if self.model is None:
                raise RuntimeError(self.info['message'])
            # PIL handles Unicode paths consistently and matches CLI RGB input.
            from PIL import Image
            started = time.perf_counter()
            with Image.open(path) as im:
                result = self.model.predict(im.convert('RGB'), imgsz=800, device=self.device, verbose=False)[0]
            if result.probs is None:
                raise ValueError('模型没有返回分类概率')
            return self.model.names[int(result.probs.top1)], float(result.probs.top1conf), round((time.perf_counter()-started)*1000, 2)
