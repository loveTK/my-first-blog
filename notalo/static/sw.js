// 설치 가능(PWA) 조건을 채우기 위한 최소 서비스워커. 아무것도 캐시하지 않는다 —
// ponytail: 오프라인 지원 없음(변환은 서버가 하므로 의미 없음). 캐시를 넣으면 오늘 겪은 '옛날 이미지' 문제가 재발한다.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
