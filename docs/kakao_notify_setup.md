# 카카오톡 알림 설정 (크롤·파이프라인 실패 시 "나에게 보내기")

워크플로우(crawl.yml, rescore.yml)가 실패하면 `scripts/pipeline/notify_kakao.py`가
카카오톡 "나와의 채팅"으로 메시지를 보낸다. GitHub secrets 두 개만 있으면 되고,
없으면 조용히 건너뛴다 (GitHub 기본 실패 메일이 백업).

## 최초 설정 (1회, 약 5분)

1. **카카오 앱 만들기** — https://developers.kakao.com → 내 애플리케이션 → 애플리케이션 추가.
   생성 후 [앱 키]에서 **REST API 키** 복사.

2. **카카오 로그인 설정** — 앱의 [카카오 로그인] 메뉴에서
   - 활성화 ON
   - Redirect URI에 `https://localhost` 추가
   - [동의항목]에서 **카카오톡 메시지 전송(talk_message)** 을 "선택 동의"로 설정

3. **인가 코드 받기** — 브라우저에서 아래 주소를 연다 (REST_API_KEY 치환):

       https://kauth.kakao.com/oauth/authorize?client_id=REST_API_KEY&redirect_uri=https://localhost&response_type=code&scope=talk_message

   동의하면 `https://localhost/?code=XXXX` 로 이동한다(페이지는 안 떠도 됨).
   주소창의 `code=` 뒤 값을 복사.

4. **토큰 발급** — cmd에서 (REST_API_KEY, 인가코드 치환):

       curl -X POST "https://kauth.kakao.com/oauth/token" -d "grant_type=authorization_code&client_id=REST_API_KEY&redirect_uri=https://localhost&code=인가코드"

   응답 JSON의 **refresh_token** 값을 복사. (인가 코드는 1회용·10분 유효 --
   실패하면 3번부터 다시)

5. **GitHub secrets 등록** — 프로젝트 폴더 cmd에서:

       gh secret set KAKAO_REST_API_KEY
       gh secret set KAKAO_REFRESH_TOKEN

   앱 [보안]에서 Client Secret을 "사용함"으로 켰다면 토큰 발급 curl에
   `&client_secret=...`을 붙이고, `gh secret set KAKAO_CLIENT_SECRET`도 등록.

   (각각 실행하면 값 입력 프롬프트가 뜬다 -- 복사해 둔 값 붙여넣기)

6. **테스트** — Actions 탭에서 crawl 워크플로우를 수동 실행(workflow_dispatch)하거나,
   로컬에서:

       set KAKAO_REST_API_KEY=... && set KAKAO_REFRESH_TOKEN=... && python scripts\pipeline\notify_kakao.py "테스트"

## 유지보수

- refresh token 유효기간은 **2개월**. 만료 1개월 전부터는 알림이 나갈 때 Actions
  로그에 `NEW_REFRESH_TOKEN=...` 경고가 찍힌다 → 그 값으로
  `gh secret set KAKAO_REFRESH_TOKEN` 만 다시 실행하면 연장된다.
- 갱신을 놓쳐 만료되면 **카톡 알림만** 죽는다 (크롤·파이프라인은 무관).
  3~5번을 다시 하면 복구.
