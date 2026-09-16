# 음표머리 모델 재학습 (스캔 열화 증강 포함)

서비스 컨테이너엔 GPU도 데이터셋도 없다. 학습은 **DeepScoresV2를 내려받은 PC(가능하면 GPU)** 에서 돌리고,
결과 `weights/notes.onnx`만 커밋한다.

## 왜 다시 학습하나
현재 모델은 깨끗한 렌더링(DeepScoresV2)만 봤다. 복사기 스캔·책 사진처럼 번지고 얼룩진 악보에선
빽빽한 16분음표 빔 속 머리를 놓친다(엘리제 2페이지 아래 시스템 등). 학습 타일의 절반에
'나쁜 스캔' 효과를 입혀 섞으면 모델이 그 차이에 둔감해진다. 검증(val)은 깨끗한 원본 그대로 두어
기존 정확도가 떨어지지 않는지 같은 잣대로 본다.

## 순서
```bash
pip install -r train/requirements-train.txt          # ultralytics (torch 포함)

# 1) DeepScoresV2 dense → 1024 타일 (300페이지 기준 수천 타일)
python train/prep_ds2.py <ds2_dense 폴더> train/ds --max-images 300

# 1b) MUSCIMA++ (손글씨 실제 스캔 140장) 를 같은 폴더에 섞음
#     받기: https://github.com/OMR-Research/muscima-pp/releases (MUSCIMA-pp_v2.0.zip, 이미지 포함)
python train/prep_muscima.py <MUSCIMA-pp_v2.0 폴더> train/ds

# 1c) 라벨 없는 실제 스캔(AudioLabs v2 = IMSLP 940장, 마디 박스만 있음) → 현재 모델 검출을 라벨로(의사라벨)
#     받기: https://www.audiolabs-erlangen.de/resources/MIR/2019-ISMIR-LBD-Measures
#     preview/*.jpg 를 눈으로 검토, 틀린 페이지 타일은 지운 뒤 진행. 검토 없이 쓰면 놓친 음표가 굳는다
python train/pseudo_label.py <AudioLabs 이미지 폴더> train/ds --conf 0.6

# 2) 학습 타일 50%에 열화본 1장씩 추가 (원본은 그대로, val은 손대지 않음)
python train/degrade.py train/ds --ratio 0.5 --copies 1

# 3) 학습 (GPU면 train.py의 m.train(...)에 device=0 추가). 중간에 죽으면 끝에 resume
python train/train.py train/ds/data.yaml 12

# 4) 정확도 게이트 — 반드시 통과해야 배포 (기준: 음높이 ≥98%, 누락 ≤1%, 오탐 ≤0.5%)
python tests/test_accuracy.py

# 5) 엘리제 같은 실제 스캔으로 눈 검사 후 weights/notes.onnx 커밋 → 자동 배포
```

## degrade.py가 하는 것
| 효과 | 흉내내는 것 |
|---|---|
| 가우시안 번짐 / 저해상도 재확대 | 초점 안 맞음, 낮은 dpi 스캔 |
| 기울기 조명 + 비네팅 | 책 펼쳐 찍은 그림자, 폰 카메라 |
| 종이색·대비 저하 | 누런 종이, 옅은 복사본 |
| 침식/팽창 | 옅게 인쇄 / 잉크 번짐 |
| 가우시안·점 노이즈 | 토너 얼룩, 먼지 |
| JPEG 압축 | 메신저로 받은 사진 |
| 뒷면 비침 | 얇은 종이 양면 인쇄 |

박스는 안 건드린다(기하 변형 없음). 기울기·휨은 추론 쪽 `core.deskew` / `_track_lines`가 처리.

## 데이터 섞는 비율 (권장)
| 출처 | 페이지 | 역할 |
|---|---|---|
| DeepScoresV2 | 300 | 기본. 인쇄 서체·기호 다양성 |
| MUSCIMA++ | 140 | 진짜 종이 스캔 질감·손글씨 굵기 편차 |
| AudioLabs v2 (의사라벨) | 검토 통과분만 | 진짜 IMSLP 스캔. 마디 박스만 있어 음표 라벨은 모델 검출 |
| degrade.py | 위 전체의 50% | 번짐·얼룩·JPEG |

## 확인된 한계
- CPU 4코어에선 타일 40%·12에폭에 ≈4시간. 열화본을 섞으면 타일 수가 1.5배라 그만큼 더 걸린다.
- 열화가 너무 세면 깨끗한 악보 정확도가 떨어진다. `--ratio` 0.3~0.5부터.
