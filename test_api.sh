#!/bin/bash

# Base URL der lokalen API
BASE_URL="http://127.0.0.1:5000/api"

# 1️⃣ Login als Schüler
echo "==> Logging in as student..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/student/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"api_test_student", "password":"red4power", "teacher_username":"api_test"}')

echo "Login response: $LOGIN_RESPONSE"

# Extract JWT token
TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")

if [ -z "$TOKEN" ]; then
  echo "Login failed, aborting."
  exit 1
fi

echo "Token acquired: $TOKEN"
AUTH_HEADER="Authorization: Bearer $TOKEN"

# 2️⃣ Alle Stocks abrufen
echo "==> Fetching all stocks..."
curl -s -X GET "$BASE_URL/stocks/all" -H "$AUTH_HEADER" | jq

# 3️⃣ Einzelstock abrufen (Beispiel stock_id=1)
echo "==> Fetching stock ID 1..."
curl -s -X GET "$BASE_URL/stocks/1" -H "$AUTH_HEADER" | jq

# 4️⃣ Buy 5 Aktien von stock_id=1
echo "==> Buying 5 shares of stock 1..."
curl -s -X POST "$BASE_URL/stocks/1/buy" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"amount":5}' | jq

# 5️⃣ Sell 2 Aktien von stock_id=1
echo "==> Selling 2 shares of stock 1..."
curl -s -X POST "$BASE_URL/stocks/1/sell" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"amount":2}' | jq

# 6️⃣ Portfolio abrufen
echo "==> Fetching portfolio..."
curl -s -X GET "$BASE_URL/student/portfolio-history" -H "$AUTH_HEADER" | jq

# 7️⃣ Dashboard info abrufen
echo "==> Fetching dashboard info..."
curl -s -X GET "$BASE_URL/student/dashboard" -H "$AUTH_HEADER" | jq

echo "==> Test completed successfully!"
