#!/usr/bin/env python3
"""为三个上传函数添加空文件检查(在文件类型校验之前)"""
import re

FILES = [
    "/opt/qloop/backend/app/services/release_service.py",
    "/home/tiany/qloop/backend/app/services/release_service.py",
]

# 匹配模式: "    # 校验文件类型(白名单,P1-2)\n    if not validate_file_type("
# 在其前插入空文件检查
PATTERN = "    # 校验文件类型(白名单,"
REPLACEMENT = """    # 空文件检查(P1-4)
    if not file_data:
        raise ValueError("文件内容为空,请上传有效的文件")

    # 校验文件类型(白名单,"""

for path in FILES:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 计算替换前的出现次数
    count = content.count(PATTERN)
    print(f"{path}: 找到 {count} 处需要修改")

    # 执行替换
    new_content = content.replace(PATTERN, REPLACEMENT)

    # 写回
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # 验证
    with open(path, "r", encoding="utf-8") as f:
        verify = f.read()
    verify_count = verify.count("空文件检查")
    print(f"  写入完成,验证: 现在有 {verify_count} 处 '空文件检查'")

print("\n修复完成")
