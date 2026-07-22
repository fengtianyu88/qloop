#!/usr/bin/env python3
"""从测试输出日志中解析测试结果"""
import re
import json
import os

LOG_FILES = [
    "/tmp/test_output.log",      # 第一轮(先加载,会被覆盖)
    "/tmp/test_output2.log",     # 第二轮(覆盖第一轮)
    "/tmp/test_output3.log",     # 第三轮(最终结果,覆盖前两轮)
]

# 解析模式: [✓] TC-XXX PASS -- actual_result
# 或: [✗] TC-XXX FAIL -- actual_result
# 或: [⊘] TC-XXX SKIP -- actual_result
PATTERN = re.compile(r"^\[([✓✗⊘])\]\s+(TC-[A-Z0-9-]+)\s+(PASS|FAIL|SKIP)\s+--\s+(.*)$")

results = {}

for log_file in LOG_FILES:
    if not os.path.exists(log_file):
        continue
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            m = PATTERN.match(line.strip())
            if m:
                symbol, tc_id, status, actual = m.groups()
                results[tc_id] = {
                    "tc_id": tc_id,
                    "status": status,
                    "actual_result": actual,
                    "notes": "",
                    "timestamp": "2026-07-22",
                    "source": log_file,
                }

# 保存
out_path = "/mnt/c/Users/tiany/Documents/Trae solo my data/test_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(list(results.values()), f, ensure_ascii=False, indent=2)

print(f"从日志解析了 {len(results)} 个测试结果")
by_status = {}
for r in results.values():
    s = r["status"]
    by_status.setdefault(s, []).append(r["tc_id"])
for s, ids in sorted(by_status.items()):
    print(f"  {s}: {len(ids)}")
print(f"\n结果已保存: {out_path}")
