"""YOLOv8n 학습 → ONNX 내보내기. 사용: py -3 train/train.py <data.yaml> [epochs]
결과: notune/weights/notes.onnx (서빙은 onnxruntime만 씀, torch 불필요)."""
import os
import shutil
import sys

from ultralytics import YOLO

data, epochs = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30
runs = os.path.abspath("train/runs")  # 상대경로 주면 ultralytics가 runs/detect/ 밑에 또 넣어버림
m = YOLO("yolov8n.pt")
# ponytail: CPU 학습 전제(GPU 있으면 device=0). 악보는 회전/좌우반전 의미 없어서 augment 끔.
m.train(data=data, imgsz=1024, epochs=epochs, batch=8, workers=2, fliplr=0.0, mosaic=0.5,
        hsv_h=0.0, hsv_s=0.0, degrees=0.0, project=runs, name="notes", exist_ok=True)
best = os.path.join(runs, "notes", "weights", "best.pt")
assert os.path.exists(best), best
onnx = YOLO(best).export(format="onnx", imgsz=1024, opset=17, simplify=True, dynamic=False)
os.makedirs("weights", exist_ok=True)
shutil.copy(onnx, "weights/notes.onnx")
print("완료: weights/notes.onnx")
