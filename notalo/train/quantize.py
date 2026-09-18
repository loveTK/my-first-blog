"""fp32 ONNX → 정적 int8(QDQ). 사용: py -3 train/quantize.py [입력 onnx] [출력 onnx]
기본: weights/notes.onnx 를 제자리에서 int8로 바꿈(train.py 직후 실행). CPU 추론 1.9배 빠름(Xeon VNNI 기준), 정확도 게이트 동일(99.4/0.1/0.4).
캘리브레이션은 tests/fixtures 8장의 모서리 타일 32개. 검출 헤드의 디코드 부분(/model.22/ 중 cv2·cv3 제외)은 양자화 제외 —
박스(0~1024)와 신뢰도(0~1)가 한 텐서에 합쳐져 같은 스케일로 양자화되면 신뢰도가 전부 0이 됨."""
import glob
import os
import sys

import cv2
import numpy as np
import onnx
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")


class Tiles(CalibrationDataReader):
    def __init__(self):
        tiles = []
        for f in sorted(glob.glob(os.path.join(FIX, "*.png")))[:8]:
            gray = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            ss = float(np.median([s["space"] for s in core.detect_staves(core.binarize(gray))]))
            img = cv2.resize(cv2.cvtColor(core.flatten(gray), cv2.COLOR_GRAY2RGB), None, fx=core.TRAIN_SS / ss, fy=core.TRAIN_SS / ss)
            H, W = img.shape[:2]
            for ty in (0, H - core.TILE):
                for tx in (0, W - core.TILE):
                    tiles.append(img[ty:ty + core.TILE, tx:tx + core.TILE].transpose(2, 0, 1)[None].astype(np.float32) / 255)
        assert tiles
        self.it = iter(tiles)

    def get_next(self):
        t = next(self.it, None)
        return None if t is None else {"images": t}


def main(src, dst):
    pre, tmp = dst + ".pre", dst + ".tmp"
    quant_pre_process(src, pre)
    skip = [n.name for n in onnx.load(pre).graph.node if "/model.22/" in n.name and "/cv2." not in n.name and "/cv3." not in n.name]
    quantize_static(pre, tmp, Tiles(), quant_format=QuantFormat.QDQ, activation_type=QuantType.QUInt8,
                    weight_type=QuantType.QInt8, per_channel=True, nodes_to_exclude=skip)
    os.remove(pre)
    os.replace(tmp, dst)
    print(f"완료: {dst} ({os.path.getsize(dst) // 1024} KB). 이제 tests/test_accuracy.py 로 게이트 확인")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "weights/notes.onnx", a[1] if len(a) > 1 else (a[0] if a else "weights/notes.onnx"))
