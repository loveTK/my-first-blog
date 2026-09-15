# 홈페이지 퍼블리싱 가이드 (GitHub Pages)

이 저장소의 `index.html`을 GitHub Pages로 무료 배포하는 방법입니다. 빌드 도구 없이
정적 파일을 그대로 호스팅합니다.

## 1. GitHub Pages 활성화

1. GitHub에서 이 저장소(`loveTK/my-first-blog`)로 이동
2. 상단 탭에서 **Settings** 클릭
3. 왼쪽 메뉴에서 **Pages** 클릭
4. **Build and deployment** 섹션에서:
   - **Source**: `Deploy from a branch` 선택
   - **Branch**: `main`(또는 `master`) + `/ (root)` 선택
   - **Save** 클릭

## 2. 배포 확인

- 저장 후 1~2분 정도 기다리면 같은 페이지 상단에 다음과 같은 초록색 안내가 뜹니다:
  `Your site is live at https://lovetk.github.io/my-first-blog/`
- 이 주소가 실제 홈페이지 URL입니다.
- Actions 탭에서 `pages build and deployment` 워크플로가 성공(초록 체크)했는지 확인할 수 있습니다.

## 3. 내용 수정 후 재배포

`index.html`이나 `style.css`를 수정해서 `main` 브랜치에 push하면
GitHub Pages가 자동으로 다시 빌드합니다. 별도 배포 명령이 필요 없습니다.

```bash
git add index.html style.css
git commit -m "홈페이지 내용 수정"
git push origin main
```

## 4. 커스텀 도메인 연결 (선택)

자신의 도메인을 쓰고 싶다면:

1. 도메인 DNS 설정에서 GitHub Pages IP로 A 레코드 4개 추가
   (`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`)
   또는 서브도메인이면 CNAME을 `lovetk.github.io`로 설정
2. Settings → Pages → **Custom domain**에 도메인 입력 후 저장
3. DNS가 전파되면(수 분~수 시간) **Enforce HTTPS** 체크박스 활성화

## 5. 로컬에서 미리보기

배포 전에 로컬에서 바로 확인하려면:

```bash
python3 -m http.server 8000
```

브라우저에서 `http://localhost:8000` 접속.
