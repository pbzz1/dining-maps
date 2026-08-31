#!/usr/bin/env bash
# React 빌드를 S3(비공개) + CloudFront(OAC)로 배포. 재실행하면 빌드·업로드·캐시 무효화만 한다.
#   VITE_API_BASE=https://xxx.lambda-url.ap-southeast-2.on.aws bash scripts/deploy/deploy_frontend.sh
# 비용: CloudFront 1TB/월 영구 무료, S3는 수 MB라 월 $0.01 미만.
set -euo pipefail
cd "$(dirname "$0")/../.."
export MSYS_NO_PATHCONV=1  # Git Bash가 "/*" 같은 인자를 윈도 경로로 바꾸지 않게

REGION=${AWS_REGION:-ap-southeast-2}   # 계정 SCP가 이 리전만 허용
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET=dining-maps-web-$ACCOUNT
NAME=dining-maps
: "${VITE_API_BASE:?}"

# 1. S3 버킷 (퍼블릭 차단 기본값 유지, CloudFront만 읽는다)
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || \
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null

# 2. CloudFront: /brand/BHC/ 같은 디렉터리 URL에 index.html을 붙이는 함수 (S3 REST 원본은 이를 못 한다)
FN_ARN=$(aws cloudfront describe-function --name $NAME-index --query FunctionSummary.FunctionMetadata.FunctionARN --output text 2>/dev/null || {
  printf 'function handler(e){var r=e.request;if(r.uri.endsWith("/"))r.uri+="index.html";else if(!r.uri.includes("."))r.uri+="/index.html";return r}' > build/cf-fn.js
  aws cloudfront create-function --name $NAME-index --function-config Comment="dir index",Runtime=cloudfront-js-2.0 \
    --function-code fileb://build/cf-fn.js --query FunctionSummary.FunctionMetadata.FunctionARN --output text
  ETAG=$(aws cloudfront describe-function --name $NAME-index --query ETag --output text)
  aws cloudfront publish-function --name $NAME-index --if-match "$ETAG" >/dev/null
})

# 3. OAC + 배포 (Comment로 식별)
DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='$NAME'].Id | [0]" --output text)
if [ "$DIST_ID" = "None" ] || [ -z "$DIST_ID" ]; then
  OAC_ID=$(aws cloudfront list-origin-access-controls --query "OriginAccessControlList.Items[?Name=='$NAME'].Id | [0]" --output text)
  if [ "$OAC_ID" = "None" ]; then
    OAC_ID=$(aws cloudfront create-origin-access-control --origin-access-control-config \
      Name=$NAME,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3 \
      --query OriginAccessControl.Id --output text)
  fi
  cat > build/cf-dist.json <<EOF
{
  "CallerReference": "$NAME-$(date +%s)",
  "Comment": "$NAME",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "HttpVersion": "http2and3",
  "PriceClass": "PriceClass_200",
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "s3", "DomainName": "$BUCKET.s3.$REGION.amazonaws.com",
    "OriginAccessControlId": "$OAC_ID",
    "S3OriginConfig": {"OriginAccessIdentity": ""}
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3",
    "ViewerProtocolPolicy": "redirect-to-https",
    "Compress": true,
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "FunctionAssociations": {"Quantity": 1, "Items": [{"EventType": "viewer-request", "FunctionARN": "$FN_ARN"}]}
  },
  "CustomErrorResponses": {"Quantity": 2, "Items": [
    {"ErrorCode": 403, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 0},
    {"ErrorCode": 404, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 0}
  ]}
}
EOF
  DIST_ID=$(aws cloudfront create-distribution --distribution-config file://build/cf-dist.json --query Distribution.Id --output text)
  # 버킷 정책: 이 배포만 읽기 허용
  aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"cloudfront.amazonaws.com\"},\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::$BUCKET/*\",\"Condition\":{\"StringEquals\":{\"AWS:SourceArn\":\"arn:aws:cloudfront::$ACCOUNT:distribution/$DIST_ID\"}}}]}"
fi
DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query Distribution.DomainName --output text)

# 4. 빌드 (Node 24 + rolldown이 이 PC에서 크래시해서 node@22로 실행) + SEO 정적 페이지, 업로드, 캐시 무효화
(cd frontend-react && SITE_URL="https://$DOMAIN" npx -y node@22 node_modules/vite/bin/vite.js build \
  && SITE_URL="https://$DOMAIN" node scripts/build-static-pages.mjs)
aws s3 sync frontend-react/dist "s3://$BUCKET" --delete --region "$REGION" >/dev/null
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null

echo "SITE URL: https://$DOMAIN"
echo "Lambda ALLOWED_ORIGINS 에 https://$DOMAIN 이 없다면 deploy_lambda.sh 를 다시 실행할 것"
