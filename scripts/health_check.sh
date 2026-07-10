#!/bin/bash

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "============================================================"
echo "Python Debug Assistant Health Check"
echo "BASE_URL: $BASE_URL"
echo "============================================================"


# /health 확인


echo
echo "1. /health 확인"

HEALTH_RESPONSE="$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$BASE_URL/health" || true)"
HEALTH_BODY="$(echo "$HEALTH_RESPONSE" | sed -n '1,/HTTP_STATUS:/p' | sed '$d')"
HEALTH_STATUS="$(echo "$HEALTH_RESPONSE" | grep 'HTTP_STATUS:' | cut -d':' -f2)"

echo "HTTP STATUS: $HEALTH_STATUS"
echo "$HEALTH_BODY"

if [ "$HEALTH_STATUS" != "200" ]; then
    echo "ERROR: /health 요청 실패"
    exit 1
fi


# 일반 대화 테스트


echo
echo "2. /chat 일반 대화 테스트"

CHAT_RESPONSE="$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "health-check-session",
        "message": "안녕. 너는 어떤 기능을 할 수 있어?"
    }' || true)"

CHAT_BODY="$(echo "$CHAT_RESPONSE" | sed -n '1,/HTTP_STATUS:/p' | sed '$d')"
CHAT_STATUS="$(echo "$CHAT_RESPONSE" | grep 'HTTP_STATUS:' | cut -d':' -f2)"

echo "HTTP STATUS: $CHAT_STATUS"
echo "$CHAT_BODY"

if [ "$CHAT_STATUS" != "200" ]; then
    echo "ERROR: /chat 일반 대화 테스트 실패"
    exit 1
fi


# 마스킹 테스트


echo
echo "3. 개인정보 / 욕설 마스킹 테스트"

MASK_RESPONSE="$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "health-check-mask-session",
        "message": "내 이메일은 test@example.com이고 전화번호는 010-1234-5678이야. 시발 이 에러 왜 나?"
    }' || true)"

MASK_BODY="$(echo "$MASK_RESPONSE" | sed -n '1,/HTTP_STATUS:/p' | sed '$d')"
MASK_STATUS="$(echo "$MASK_RESPONSE" | grep 'HTTP_STATUS:' | cut -d':' -f2)"

echo "HTTP STATUS: $MASK_STATUS"
echo "$MASK_BODY"

if [ "$MASK_STATUS" != "200" ]; then
    echo "ERROR: /chat 마스킹 테스트 실패"
    exit 1
fi


# Python 에러 테스트


echo
echo "4. Python 에러 질문 테스트"

ERROR_RESPONSE="$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "health-check-error-session",
        "message": "TypeError: int object is not iterable 에러가 발생했어. 원인과 해결 방법을 알려줘."
    }' || true)"

ERROR_BODY="$(echo "$ERROR_RESPONSE" | sed -n '1,/HTTP_STATUS:/p' | sed '$d')"
ERROR_STATUS="$(echo "$ERROR_RESPONSE" | grep 'HTTP_STATUS:' | cut -d':' -f2)"

echo "HTTP STATUS: $ERROR_STATUS"
echo "$ERROR_BODY"

if [ "$ERROR_STATUS" != "200" ]; then
    echo "ERROR: /chat Python 에러 테스트 실패"
    exit 1
fi

echo
echo "============================================================"
echo "Health Check 완료"
echo "============================================================"