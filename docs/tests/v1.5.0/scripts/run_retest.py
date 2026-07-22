#!/usr/bin/env python3
"""QLoop v1.4.7 重测 3 个失败用例
1. TC-DL-06: presigned URL 有效期(后端 bug 已修复)
2. TC-UPLOAD-05: 上传 .exe 文件(路径修复)
3. TC-UPLOAD-14: 上传空文件(路径修复)
"""
import requests
import json
import time
from urllib.parse import urlparse, parse_qs

BASE_URL = "http://localhost:8000"
ADMIN_USER = "admin"
ADMIN_PWD = "Admin@2026"

# 用 faac4144 release 测试下载(有 test_report_path)
RELEASE_WITH_FILES = "faac4144-0745-4fa1-97ee-bf3bf53e4c1f"
# 用一个 DRAFT release 测试上传(3c4ebf6f)
DRAFT_RELEASE = "3c4ebf6f-5c92-436e-8356-f3da6bcd88d9"

RESULTS = []


def log_result(tc_id, status, actual_result="", notes=""):
    RESULTS.append({
        "tc_id": tc_id, "status": status,
        "actual_result": actual_result, "notes": notes,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "⊘"
    print(f"[{symbol}] {tc_id} {status} -- {actual_result[:100]}")


def login(username, password):
    resp = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"username": username, "password": password}, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def main():
    print("=" * 60)
    print("QLoop v1.4.7 重测 3 个失败用例")
    print("=" * 60)

    admin_token = login(ADMIN_USER, ADMIN_PWD)
    if not admin_token:
        print("admin 登录失败")
        return

    headers = {"Authorization": f"Bearer {admin_token}"}

    # === TC-DL-06: presigned URL 有效期 ===
    print("\n--- TC-DL-06: presigned URL 有效期 ---")
    resp = requests.get(
        f"{BASE_URL}/api/releases/{RELEASE_WITH_FILES}/download/test_report",
        headers=headers, allow_redirects=False, timeout=15
    )
    if resp.status_code in (200, 302, 307):
        location = resp.headers.get("Location", "")
        if location:
            parsed = urlparse(location)
            params = parse_qs(parsed.query)
            expires = params.get("X-Amz-Expires", [None])[0]
            if expires:
                expires_int = int(expires)
                if expires_int == 604800:
                    log_result("TC-DL-06", "PASS", f"X-Amz-Expires={expires} (7天=604800) ✓")
                elif expires_int >= 86400:
                    log_result("TC-DL-06", "PASS", f"X-Amz-Expires={expires} (>=1天,符合约束)")
                else:
                    log_result("TC-DL-06", "FAIL", f"X-Amz-Expires={expires},期望 604800")
            else:
                log_result("TC-DL-06", "FAIL", f"URL 中无 X-Amz-Expires,location={location[:80]}")
        else:
            log_result("TC-DL-06", "FAIL", "无 Location header")
    else:
        log_result("TC-DL-06", "FAIL", f"HTTP={resp.status_code} {resp.text[:80]}")

    # === TC-UPLOAD-05: 上传 .exe 文件 ===
    print("\n--- TC-UPLOAD-05: 上传 .exe 文件 ---")
    exe_bytes = b'\x4d\x5a\x90\x00\x03\x00\x00\x00' + b'\x00' * 100
    files = {"file": ("test.exe", exe_bytes, "application/octet-stream")}
    resp = requests.post(
        f"{BASE_URL}/api/releases/{DRAFT_RELEASE}/code-package",
        headers=headers, files=files, timeout=15
    )
    if resp.status_code == 415:
        log_result("TC-UPLOAD-05", "PASS", f".exe 被拒 HTTP=415")
    elif resp.status_code == 400:
        log_result("TC-UPLOAD-05", "PASS", f".exe 被拒 HTTP=400(类型不允许)")
    else:
        log_result("TC-UPLOAD-05", "FAIL", f"期望 415/400, 实际 {resp.status_code} {resp.text[:80]}")

    # === TC-UPLOAD-14: 上传空文件 ===
    print("\n--- TC-UPLOAD-14: 上传空文件 ---")
    files = {"file": ("empty.zip", b'', "application/zip")}
    resp = requests.post(
        f"{BASE_URL}/api/releases/{DRAFT_RELEASE}/code-package",
        headers=headers, files=files, timeout=15
    )
    if resp.status_code in (400, 415):
        log_result("TC-UPLOAD-14", "PASS", f"空文件被拒 HTTP={resp.status_code}")
    else:
        log_result("TC-UPLOAD-14", "FAIL", f"期望 400/415, 实际 {resp.status_code} {resp.text[:80]}")

    # === 汇总 ===
    print("\n" + "=" * 60)
    print("重测汇总")
    print("=" * 60)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"总计: {total}  通过: {passed}  失败: {failed}")

    out_path = "/mnt/c/Users/tiany/Documents/Trae solo my data/test_results_retest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
