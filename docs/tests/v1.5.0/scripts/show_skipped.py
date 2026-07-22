#!/usr/bin/env python3
"""读取测试结果,展示所有跳过的用例"""
import json
import os

path = "/mnt/c/Users/tiany/Documents/Trae solo my data/test_results.json"
if not os.path.exists(path):
    # Windows 路径
    path = r"c:\Users\tiany\Documents\Trae solo my data\test_results.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 按状态分类
by_status = {}
for r in data:
    s = r.get("status", "UNKNOWN")
    by_status.setdefault(s, []).append(r)

print(f"=== 测试结果汇总 ===")
print(f"总计: {len(data)}")
for s, items in by_status.items():
    print(f"  {s}: {len(items)}")

print(f"\n=== 跳过的用例 ({len(by_status.get('SKIP', []))} 个) ===")
for r in by_status.get("SKIP", []):
    tc_id = r.get("tc_id", "")
    actual = r.get("actual_result", "")
    notes = r.get("notes", "")
    print(f"  [{tc_id}] {actual[:100]} | notes: {notes[:80]}")

print(f"\n=== 失败的用例 ({len(by_status.get('FAIL', []))} 个) ===")
for r in by_status.get("FAIL", []):
    tc_id = r.get("tc_id", "")
    actual = r.get("actual_result", "")
    print(f"  [{tc_id}] {actual[:100]}")

print(f"\n=== 全部 TC ID 列表 ===")
all_ids = [r.get("tc_id", "") for r in data]
print(",".join(all_ids))
