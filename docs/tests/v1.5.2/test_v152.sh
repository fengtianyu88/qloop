#!/bin/bash
# v1.5.2: 综合测试脚本

PASS=0
FAIL=0
TOTAL=0

check() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "PASS" ]; then
        PASS=$((PASS + 1))
        echo "[PASS] $2"
    else
        FAIL=$((FAIL + 1))
        echo "[FAIL] $2 -- $3"
    fi
}

BASE_URL="http://localhost:8000/api"

# 登录
TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123456"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "FATAL: 登录失败"
    exit 1
fi
AUTH="Authorization: Bearer $TOKEN"

echo "=========================================="
echo "  v1.5.2 自定义组织类型测试"
echo "=========================================="
echo ""

# === TC-01: 健康检查 ===
RESP=$(curl -s "$BASE_URL/health")
VERSION=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null)
check "$([ "$VERSION" = "1.5.2" ] && echo PASS || echo FAIL)" "TC-01: 健康检查版本=1.5.2" "实际=$VERSION"

# === TC-02: GET /api/org-types 返回 3 个系统类型 ===
RESP=$(curl -s -w "\n%{http_code}" "$BASE_URL/org-types" -H "$AUTH")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
check "$([ "$HTTP" = "200" ] && [ "$COUNT" = "3" ] && echo PASS || echo FAIL)" "TC-02: GET /api/org-types 返回 3 个系统类型" "HTTP=$HTTP count=$COUNT"

# === TC-03: 系统类型包含 department/division/group ===
CODES=$(echo "$BODY" | python3 -c "import sys,json; data=json.load(sys.stdin); print(','.join(sorted([t['code'] for t in data])))" 2>/dev/null)
check "$([ "$CODES" = "department,division,group" ] && echo PASS || echo FAIL)" "TC-03: 系统类型为 department/division/group" "实际=$CODES"

# === TC-04: 系统类型 is_system=true ===
ALL_SYS=$(echo "$BODY" | python3 -c "import sys,json; data=json.load(sys.stdin); print(all(t['is_system'] for t in data))" 2>/dev/null)
check "$([ "$ALL_SYS" = "True" ] && echo PASS || echo FAIL)" "TC-04: 所有预设类型 is_system=true" "all_system=$ALL_SYS"

# === TC-05: 创建自定义类型 center ===
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/org-types" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"center","name":"中心","sort_order":4}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
IS_SYSTEM=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('is_system'))" 2>/dev/null)
check "$([ "$HTTP" = "201" ] && [ "$IS_SYSTEM" = "False" ] && echo PASS || echo FAIL)" "TC-05: 创建自定义类型 center" "HTTP=$HTTP is_system=$IS_SYSTEM"

CENTER_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# === TC-06: 重复 code 创建应失败 ===
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/org-types" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"center","name":"中心2","sort_order":5}')
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "400" ] && echo PASS || echo FAIL)" "TC-06: 重复 code 创建返回 400" "HTTP=$HTTP"

# === TC-07: code 大小写不敏感检查 ===
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/org-types" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"CENTER","name":"大写中心","sort_order":6}')
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "400" ] && echo PASS || echo FAIL)" "TC-07: code 大小写不敏感检查(CENTER vs center)" "HTTP=$HTTP"

# === TC-08: 创建使用自定义类型的组织 ===
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/organizations" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"测试中心_v152","org_type":"center","description":"自定义类型测试"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
ORG_TYPE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_type',''))" 2>/dev/null)
check "$([ "$HTTP" = "201" ] && [ "$ORG_TYPE" = "center" ] && echo PASS || echo FAIL)" "TC-08: 创建使用自定义类型的组织" "HTTP=$HTTP org_type=$ORG_TYPE"

TEST_ORG_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# === TC-09: 使用不存在的类型创建组织应失败 ===
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/organizations" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"非法类型测试","org_type":"nonexistent"}')
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "400" ] && echo PASS || echo FAIL)" "TC-09: 使用不存在的类型创建返回 400" "HTTP=$HTTP"

# === TC-10: 组织树包含自定义类型 ===
RESP=$(curl -s "$BASE_URL/organizations/tree" -H "$AUTH")
HAS_CENTER=$(echo "$RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = False
def check_tree(items):
    global found
    for item in items:
        if item.get('org_type') == 'center':
            found = True
        if item.get('children'):
            check_tree(item['children'])
check_tree(data)
print(found)
" 2>/dev/null)
check "$([ "$HAS_CENTER" = "True" ] && echo PASS || echo FAIL)" "TC-10: 组织树包含 center 类型" "has_center=$HAS_CENTER"

# === TC-11: 删除系统类型应失败 ===
DEPT_ID=$(curl -s "$BASE_URL/org-types" -H "$AUTH" | python3 -c "import sys,json; types=json.load(sys.stdin); print([t['id'] for t in types if t['code']=='department'][0])" 2>/dev/null)
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL/org-types/$DEPT_ID" -H "$AUTH")
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "400" ] && echo PASS || echo FAIL)" "TC-11: 删除系统类型返回 400" "HTTP=$HTTP"

# === TC-12: 删除有引用的自定义类型应失败 ===
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL/org-types/$CENTER_ID" -H "$AUTH")
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "400" ] && echo PASS || echo FAIL)" "TC-12: 删除有引用的自定义类型返回 400" "HTTP=$HTTP"

# === TC-13: 删除测试组织后再删除自定义类型 ===
# 先删除测试组织
curl -s -X DELETE "$BASE_URL/organizations/$TEST_ORG_ID" -H "$AUTH" > /dev/null 2>&1
# 再删除自定义类型
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL/org-types/$CENTER_ID" -H "$AUTH")
HTTP=$(echo "$RESP" | tail -1)
check "$([ "$HTTP" = "204" ] && echo PASS || echo FAIL)" "TC-13: 删除无引用的自定义类型返回 204" "HTTP=$HTTP"

# === TC-14: 删除后类型列表恢复 3 个 ===
COUNT=$(curl -s "$BASE_URL/org-types" -H "$AUTH" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
check "$([ "$COUNT" = "3" ] && echo PASS || echo FAIL)" "TC-14: 删除后类型列表恢复 3 个" "count=$COUNT"

# === TC-15: 数据库 org_units.org_type 列为 VARCHAR ===
COL_TYPE=$(sudo -u postgres psql -d qloop -t -c "SELECT data_type FROM information_schema.columns WHERE table_name='org_units' AND column_name='org_type';" 2>/dev/null | xargs)
check "$([ "$COL_TYPE" = "character varying" ] && echo PASS || echo FAIL)" "TC-15: org_units.org_type 列类型为 VARCHAR" "实际=$COL_TYPE"

# === TC-16: 数据库 org_units.org_type 值为小写 ===
VALUES=$(sudo -u postgres psql -d qloop -t -c "SELECT DISTINCT org_type FROM org_units ORDER BY org_type;" 2>/dev/null | xargs)
check "$([ "$VALUES" = "department division group" ] && echo PASS || echo FAIL)" "TC-16: org_units.org_type 值为小写" "实际=$VALUES"

# === TC-17: 数据库旧枚举类型已删除 ===
TYPE_EXISTS=$(sudo -u postgres psql -d qloop -t -c "SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname='org_type');" 2>/dev/null | xargs)
check "$([ "$TYPE_EXISTS" = "f" ] && echo PASS || echo FAIL)" "TC-17: 旧枚举类型 org_type 已删除" "exists=$TYPE_EXISTS"

# === TC-18: created_by_name 在列表中正确填充 ===
# 创建一个新类型
RESP=$(curl -s -X POST "$BASE_URL/org-types" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"test_by_name","name":"测试创建人","sort_order":10}')
# 获取列表验证 created_by_name
BY_NAME=$(curl -s "$BASE_URL/org-types" -H "$AUTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data:
    if t['code'] == 'test_by_name':
        print(t.get('created_by_name', ''))
        break
" 2>/dev/null)
check "$([ -n "$BY_NAME" ] && [ "$BY_NAME" != "None" ] && echo PASS || echo FAIL)" "TC-18: created_by_name 在列表中填充" "by_name=$BY_NAME"

# 清理
TEST_ID=$(curl -s "$BASE_URL/org-types" -H "$AUTH" | python3 -c "import sys,json; types=json.load(sys.stdin); ids=[t['id'] for t in types if t['code']=='test_by_name']; print(ids[0] if ids else '')" 2>/dev/null)
if [ -n "$TEST_ID" ]; then
    curl -s -X DELETE "$BASE_URL/org-types/$TEST_ID" -H "$AUTH" > /dev/null 2>&1
fi

echo ""
echo "=========================================="
echo "  测试结果: $PASS/$TOTAL 通过, $FAIL 失败"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
