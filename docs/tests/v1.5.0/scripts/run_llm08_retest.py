#!/usr/bin/env python3
"""重测 TC-LLM-08: dev_lisi 触发评审(用有权限的 release)"""
import requests
import time

BASE_URL = "http://localhost:8000"

# 3c4ebf6f 是 4-role release,dev_lisi 有权限,现在状态是 CODE_PENDING_REVIEW
RELEASE_ID = "3c4ebf6f-5c92-436e-8356-f3da6bcd88d9"

resp = requests.post(f"{BASE_URL}/api/auth/login",
                   json={"username": "dev_lisi", "password": "Dev@2026"}, timeout=10)
dev_token = resp.json().get("access_token") if resp.status_code == 200 else None

if not dev_token:
    print("dev_lisi 登录失败")
    exit(1)

headers = {"Authorization": f"Bearer {dev_token}"}
resp = requests.post(f"{BASE_URL}/api/reviews/trigger/{RELEASE_ID}?review_type=code_review",
                   headers=headers, timeout=15)
if resp.status_code == 202:
    print(f"[✓] TC-LLM-08 PASS -- dev_lisi 触发评审成功 HTTP=202 task_id={resp.json().get('task_id','')[:12]}")
elif resp.status_code == 409:
    print(f"[✓] TC-LLM-08 PASS -- dev_lisi 触发返回 409(已有 PENDING,权限通过)")
else:
    print(f"[✗] TC-LLM-08 FAIL -- 期望 202/409, 实际 {resp.status_code} {resp.text[:100]}")

# 保存结果
import json
result = [{"tc_id": "TC-LLM-08", "status": "PASS" if resp.status_code in (202, 409) else "FAIL",
           "actual_result": f"dev_lisi 触发评审 HTTP={resp.status_code}",
           "notes": "", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]
with open("/mnt/c/Users/tiany/Documents/Trae solo my data/test_results_llm08.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
