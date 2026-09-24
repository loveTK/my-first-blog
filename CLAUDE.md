# 규칙

기획문서(`docs/*.md`, 새로 만드는 것 포함)에는 항상 "가입/관리 서비스 계정" 섹션을 넣는다. 내용은 아래 표 기준, 새로 알게 된 서비스가 생기면 표에 추가.

# 가입/관리 서비스 계정 (내가 아는 것만)

| 서비스 | 역할(초등학생 설명) | 아는 정보 |
|---|---|---|
| GitHub (loveTK/my-first-blog) | 코드를 저장하고, 코드가 바뀌면 자동으로 배포도 해주는 곳. 이 저장소 자체. | repo 이름만 앎, 비번 모름 |
| GitHub Actions | 코드 올리면 자동으로 "서버에 새 버전 올리기"를 실행해주는 로봇. `.github/workflows/deploy-notalo.yml` | 워크플로 파일 위치만 앎 |
| AWS Lightsail | Notalo 웹사이트가 실제로 켜져서 돌아가는 컴퓨터(서버). 월 10~13불짜리 작은 컴퓨터. | 존재만 앎, 접속정보 모름 |
| Cloudflare | notalo.xyz 주소를 진짜 서버로 연결해주는 곳(DNS). 이메일 받기(Email Routing)도 시도했는데 무료 요금제엔 없어서 못 씀. | notalo.xyz 도메인이 여기 연결된 것만 앎 |
| Google Analytics (GA4) | 사이트에 사람이 몇 명 왔는지 세어주는 도구. 추적 ID `G-YKTS1ZLM3G`. | 추적 ID만 앎(코드에 박혀있음) |
| Google AdSense | 사이트에 광고 붙여서 돈 버는 도구. 광고주 ID `ca-pub-1044528124208901`. | ID만 앎, 승인 여부 모름 |
| Google OAuth (Sign in with Google) | "구글로 로그인" 버튼 눌렀을 때 진짜 구글 계정인지 확인해주는 열쇠. | client_id는 서버가 `/auth/config`로 줌, 값 자체는 모름 |
| Gmail (xorud386@gmail.com) | 사용자 문의 메일 받는 곳. Terms/Privacy 페이지의 연락처로 씀. | 이메일 주소만 앎 |
| PWA Builder (pwabuilder.com) | 웹사이트를 안드로이드 앱 파일(APK/AAB)로 바꿔주는 도구. Play Store에 올릴 파일 여기서 만듦. | 만들어준 파일(keystore, aab)만 받아서 씀 |
| Google Play Console | 만든 안드로이드 앱을 스토어에 올리는 곳. 아직 사용자가 직접 등록 안 함(예정). | 존재만 앎, 계정 정보 모름 |
| Zenodo / DeepScoresV2 | 계이름 붙이는 AI가 공부한 악보 데이터셋. 계정이 아니라 자료 출처(footer에 표기). | 링크만 앎 |

- 표에 없는 서비스(도메인 구매처 등)는 내가 모름 — 알려주면 추가.
