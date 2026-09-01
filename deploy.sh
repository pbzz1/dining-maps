#!/usr/bin/env bash
# 커밋 + 배포를 한 번에.   bash deploy.sh "커밋 메시지"
# 변경된 파일을 보고 프론트(frontend-react/)·백엔드(app/)를 필요한 쪽만 배포한다.
#   --front / --back   판별 무시하고 강제
#   --no-commit        배포만 (커밋·push 생략)
set -euo pipefail
cd "$(dirname "$0")"

MSG=""; FRONT=""; BACK=""; COMMIT=1
for a in "$@"; do
  case "$a" in
    --front) FRONT=1 ;;
    --back) BACK=1 ;;
    --no-commit) COMMIT=0 ;;
    *) MSG="$a" ;;
  esac
done

[ -f .env.deploy ] || { echo ".env.deploy 없음 (DATABASE_URL/ALLOWED_ORIGINS/VITE_API_BASE)"; exit 1; }
set -a; source .env.deploy; set +a

# 어느 쪽이 바뀌었는지: 미커밋 변경 + 아직 push 안 된 커밋 둘 다 본다.
CHANGED=$( { git diff --name-only HEAD; git diff --name-only origin/master..HEAD 2>/dev/null; } | sort -u)
if [ -z "$FRONT$BACK" ]; then
  grep -q '^frontend-react/' <<<"$CHANGED" && FRONT=1
  grep -q '^app/' <<<"$CHANGED" && BACK=1
fi
[ -n "$FRONT$BACK" ] || { echo "배포할 변경 없음 (frontend-react/, app/ 둘 다 그대로)"; exit 0; }

if [ "$COMMIT" = 1 ] && [ -n "$(git status --porcelain)" ]; then
  [ -n "$MSG" ] || { echo "커밋 메시지가 필요합니다:  bash deploy.sh \"메시지\""; exit 1; }
  git add -A
  git commit -q -m "$MSG"
  echo "커밋: $(git log --oneline -1)"
fi

[ -n "$BACK" ]  && { echo "== 백엔드 배포 =="; bash scripts/deploy/deploy_lambda.sh | tail -1; }
[ -n "$FRONT" ] && { echo "== 프론트 배포 =="; bash scripts/deploy/deploy_frontend.sh | grep "SITE URL"; }

[ "$COMMIT" = 1 ] && git push -q && echo "push 완료"
echo "끝. 브라우저에서 Ctrl+Shift+R"
