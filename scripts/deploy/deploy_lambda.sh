#!/usr/bin/env bash
# FastAPI를 Lambda(Function URL)로 배포. 재실행하면 코드/환경변수만 갱신된다.
#   DATABASE_URL=postgresql://... ALLOWED_ORIGINS=https://... bash scripts/deploy/deploy_lambda.sh
# 리전: 계정 SCP가 ap-southeast-2만 허용 (Neon은 싱가포르, DB 왕복 ~90ms). API Gateway 없이 Function URL만 써서 Always Free 범위 안.
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION=${AWS_REGION:-ap-southeast-2}
FN=dining-maps-api
ROLE=dining-maps-lambda
BUILD=build/lambda
: "${DATABASE_URL:?}" "${ALLOWED_ORIGINS:?}"

# 1. 패키지: 런타임(py3.12, x86_64)용 휠만 받는다. pandas/lxml 등 크롤러 의존성은 제외.
rm -rf "$BUILD" && mkdir -p "$BUILD"
pip install -q --target "$BUILD" --platform manylinux2014_x86_64 --python-version 3.12 \
  --only-binary=:all: fastapi pydantic "psycopg[binary]" mangum
cp -r app "$BUILD/"
(cd "$BUILD" && rm -rf app/__pycache__ && python -c "import shutil; shutil.make_archive('../lambda', 'zip', '.')")

# 2. 실행 역할 (CloudWatch 로그 권한만)
ROLE_ARN=$(aws iam get-role --role-name $ROLE --query Role.Arn --output text 2>/dev/null || {
  aws iam create-role --role-name $ROLE --query Role.Arn --output text --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
  aws iam attach-role-policy --role-name $ROLE \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10  # IAM 전파
})

# 3. 함수 생성 또는 갱신
# 값에 쉼표가 있어 shorthand 대신 JSON으로 넘긴다
ENV=$(python -c 'import json,os; print(json.dumps({"Variables": {k: os.environ[k] for k in ("DATABASE_URL","ALLOWED_ORIGINS")}}))')
if aws lambda get-function --function-name $FN --region $REGION >/dev/null 2>&1; then
  aws lambda update-function-code --function-name $FN --region $REGION --zip-file fileb://build/lambda.zip >/dev/null
  aws lambda wait function-updated --function-name $FN --region $REGION
  aws lambda update-function-configuration --function-name $FN --region $REGION --environment "$ENV" >/dev/null
else
  aws lambda create-function --function-name $FN --region $REGION --runtime python3.12 \
    --handler app.lambda_handler.handler --role "$ROLE_ARN" --zip-file fileb://build/lambda.zip \
    --memory-size 512 --timeout 30 --environment "$ENV" >/dev/null
  aws lambda wait function-active --function-name $FN --region $REGION
  aws lambda add-permission --function-name $FN --region $REGION --statement-id public-url \
    --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE >/dev/null
  # 최근 생성 계정은 Function URL 퍼블릭 차단이 기본값이라 InvokeFunction(*)도 없으면 403
  aws lambda add-permission --function-name $FN --region $REGION --statement-id public-invoke \
    --action lambda:InvokeFunction --principal '*' >/dev/null
  aws lambda create-function-url-config --function-name $FN --region $REGION --auth-type NONE >/dev/null
fi
aws lambda wait function-updated --function-name $FN --region $REGION
echo "API URL: $(aws lambda get-function-url-config --function-name $FN --region $REGION --query FunctionUrl --output text)"
