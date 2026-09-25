# Notalo 홈 리디자인 계획 — "1800년대 책상 위 오선지"

참고: masseriacorsano.com 의 **구조·여백·타이포 톤**만 참고(풀블리드·얇은 세리프·대문자 소형 내비·넉넉한 여백). 사진·문구·코드는 가져오지 않음.
목업: `docs/mockup-vintage.html` (아티팩트로 게시).

## 1. 방향
- 고급스럽지만 단순. 장식 대신 종이·잉크·괘선.
- **사진 없음** — CSS 종이 질감(SVG 노이즈) + 손으로 그린 오선 SVG. 저작권 리스크 0.
  실사진 원하면: 직접 찍은 사진 또는 CC0(Wikimedia PD 스캔 등)만. 진행 전 사용자 확인.
- 다크모드 = 촛불 아래 책상(짙은 갈색 종이, 밝은 잉크).

## 2. 토큰
| 역할 | 라이트 | 다크 |
|---|---|---|
| 종이 | `#EBE1CC` | `#1E1813` |
| 종이(패널) | `#E2D6BD` | `#262019` |
| 잉크 | `#2A2118` | `#E9DEC6` |
| 잉크(연함) | `#6B5B49` | `#A89A82` |
| 괘선 | `#B9A784` | `#4E4232` |
| 오른손(빨강 잉크) | `#8E3B2D` | `#C9705C` |
| 왼손(남색 잉크) | `#34435E` | `#8FA3C9` |
| 코드(초록) | `#4E5F3C` | `#9CB07E` |
| 금박 포인트 | `#9B7B3A` | `#C9A65C` |

폰트: 제목 **Cormorant Garamond** 300/400 + 이탤릭, 본문 **IBM Plex Sans KR** 300/400(기존 유지, 한국어 대응). 둘 다 Google Fonts(OFL).
버튼·내비: 11–12px 대문자, 자간 .2em, 사각(라운드 0), 1px 잉크 테두리.
라운드·그림자·배지·아이콘 전부 제거. 구분은 1px 괘선만.

## 3. 섹션(위→아래)
1. 내비: 브랜드 세리프 대문자 자간, 링크 대문자 소형, 하단 1px 괘선.
2. 히어로: 중앙 정렬, 3줄 큰 세리프 제목(핵심어만 빨강 이탤릭), 부제, 버튼 1개. 아래 **오선 SVG 카드**(음표 + 빨간 글자 + 초록 코드) — 실제 결과물 대신 "손글씨 느낌" 시그니처.
3. How: 3열, 로마숫자 I·II·III, 세로 괘선으로만 구분.
4. Tool: 이중 괘선 드롭존, 언더라인 셀렉트 3개, 버튼 1개.
5. Compare: 표. 헤더 대문자, 괘선만.
6. FAQ: 세리프 질문, +/– 토글.
7. 푸터: 한 줄 크레딧 + 링크 행.

## 4. 적용 순서(실서비스)
1. `style.css` 토큰 교체 + 폰트 링크 교체(Bricolage → Cormorant). 1커밋.
2. `index.html` 히어로: 뱃지·아이콘 제거, 오선 SVG 삽입. hero PNG는 그대로 두되 종이 프레임으로.
3. 버튼/셀렉트/드롭존/표/FAQ 클래스 스타일만 교체(HTML 구조 유지 → i18n·JS 무변경).
4. 하위 페이지(song/guide/processing)는 같은 css 쓰므로 자동 반영. 확인만.
5. liquid-glass 헤더는 방향과 안 맞음 → 제거(스크립트 2줄, #glass-bg).
6. Playwright 로컬 스크린샷으로 라이트/다크/모바일 확인 → 커밋 → 배포.

## 5. 안 하는 것
- 사진·일러스트 외부 소스, three.js/shadergradient(설치돼 있으나 이 방향엔 불필요 — 제거 권장).
- 애니메이션(스크롤 효과 등). 버튼 hover 색 반전만.

## 가입/관리 서비스 계정 (초등학생 설명)
| 서비스 | 역할 | 아는 정보 |
|---|---|---|
| GitHub (loveTK/my-first-blog) | 코드 저장소. 코드 바뀌면 자동 배포. | repo 이름만 |
| GitHub Actions | 코드 올리면 서버에 새 버전 올려주는 로봇. `.github/workflows/deploy-notalo.yml` | 파일 위치만 |
| AWS Lightsail | 사이트가 실제로 돌아가는 작은 컴퓨터. | 존재만 |
| Cloudflare | notalo.xyz 주소를 서버에 연결(DNS). Email Routing은 무료 요금제에 없음. | 도메인 연결만 |
| Google Analytics | 방문자 수 세는 도구. `G-YKTS1ZLM3G` | ID만 |
| Google AdSense | 광고로 돈 버는 도구. `ca-pub-1044528124208901`. 심사 중. | ID만 |
| Google Search Console | 구글이 우리 사이트를 어떻게 보는지. www/non-www 2개. | sitemap "가져올 수 없음"이나 검색엔 뜸 |
| Google Ads Keyword Planner | 키워드 월 검색량 조회. | `docs/keywords-en-2026-09.csv` |
| Google OAuth | "구글로 로그인" 열쇠. | client_id는 서버가 줌 |
| Gmail (xorud386@gmail.com) | 문의 메일. Terms/Privacy 연락처. | 주소만 |
| PWA Builder | 사이트를 안드로이드 앱 파일로. | 만들어준 파일만 |
| Google Play Console | 앱 올리는 곳. 미등록(예정). | 존재만 |
| Zenodo / DeepScoresV2 | AI 학습 데이터 출처. footer 표기. | 링크만 |
| Google Fonts | 글꼴 무료 제공(OFL). Cormorant Garamond·IBM Plex Sans KR 여기서 로드. | 계정 불필요 |
