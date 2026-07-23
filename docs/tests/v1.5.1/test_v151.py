#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.5.1 特批放行状态机测试

使用 httpx (同步) + subprocess psql 进行测试,无需安装新依赖。

测试目标:
1. 数据库枚举包含 released_forced
2. llm_reviews 表已添加 force_passed/force_passed_by/force_passed_at 字段
3. /api/search/releases 支持 status=released_forced 过滤
4. ReleaseListResponse 包含 force_passed_count 字段
5. LLMReviewResponse 包含 force_passed_* 字段
6. 对 pending_confirm release 特批放行 -> status=released_forced (并回滚)
7. 对 code_pending_review release 特批放行 -> 标记 force_passed=True (并回滚)
8. 已释放的 release 不允许再次特批放行 (返回 400)

破坏性测试均会:
  - 测试前记录原状态/字段
  - 测试后通过 SQL 回滚到原状态
"""

import os
import json
import sys
import subprocess
import httpx

BASE_URL = "http://localhost:8000/api"
USERNAME = "admin"
PASSWORD = "Admin@123456"

# 数据库连接配置(通过 psql 命令行)
PSQL_CMD = [
    "sudo", "-u", "postgres", "psql", "-d", "qloop",
    "-t", "-A",  # 不显示表头,不格式化对齐
    "-F", "|",   # 字段分隔符
    "-c",
]

results = []

ADMIN_TOKEN = None
PENDING_RELEASE = None
CODE_REVIEW_RELEASE = None
RELEASED_RELEASE = None

# 记录原始状态用于回滚
ORIG_FORCE_PASSED_STATE = {}  # {review_id: (force_passed, force_passed_by, force_passed_at)}


def record(tc_id, passed, actual, notes=""):
    results.append({
        "tc_id": tc_id,
        "passed": passed,
        "actual": actual,
        "notes": notes,
    })
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {tc_id} -- {actual}")


def login(username, password):
    """登录获取 token"""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{BASE_URL}/auth/login",
                json={"username": username, "password": password},
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
            return None
    except Exception as e:
        print(f"登录失败: {e}")
        return None


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


def db_query(sql, params=None):
    """通过 psql 子进程执行 SQL,返回结果行列表
    
    Args:
        sql: SQL 字符串(用 %s 占位符)
        params: 参数列表(用于替换 %s)
    
    Returns:
        list of tuples
    """
    # 替换参数
    if params:
        # 简单的参数替换(注意:仅用于测试,生产环境要用真正的参数化查询)
        final_sql = sql
        for p in params:
            if p is None:
                replacement = "NULL"
            elif isinstance(p, bool):
                replacement = "TRUE" if p else "FALSE"
            elif isinstance(p, (int, float)):
                replacement = str(p)
            else:
                # 字符串:转义单引号
                escaped = str(p).replace("'", "''")
                replacement = f"'{escaped}'"
            final_sql = final_sql.replace("%s", replacement, 1)
    else:
        final_sql = sql

    try:
        result = subprocess.run(
            PSQL_CMD + [final_sql],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql failed: {result.stderr}")
        # 解析输出
        lines = [l for l in result.stdout.strip().split("\n") if l]
        rows = []
        for line in lines:
            fields = line.split("|")
            rows.append(tuple(fields))
        return rows
    except Exception as e:
        print(f"db_query 失败: {e}")
        return []


def db_execute(sql, params=None):
    """执行无返回 SQL(UPDATE/INSERT/DELETE)"""
    if params:
        final_sql = sql
        for p in params:
            if p is None:
                replacement = "NULL"
            elif isinstance(p, bool):
                replacement = "TRUE" if p else "FALSE"
            elif isinstance(p, (int, float)):
                replacement = str(p)
            else:
                escaped = str(p).replace("'", "''")
                replacement = f"'{escaped}'"
            final_sql = final_sql.replace("%s", replacement, 1)
    else:
        final_sql = sql

    try:
        result = subprocess.run(
            PSQL_CMD + [final_sql],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql failed: {result.stderr}")
        return True
    except Exception as e:
        print(f"db_execute 失败: {e}")
        return False


def search_releases_by_status(token, status_value):
    """通过 /api/search/releases 查找指定状态的 release"""
    headers = get_headers(token)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BASE_URL}/search/releases",
                params={"status": status_value, "page": 1, "page_size": 20},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", []) if isinstance(data, dict) else data
                return items
            else:
                print(f"  search_releases_by_status HTTP={resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"查询失败: {e}")
    return []


# ============== 测试用例 ==============

def test_health():
    """TC-V151-01: 健康检查"""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                record("TC-V151-01", True, f"健康检查通过,status={data.get('status')}")
            else:
                record("TC-V151-01", False, f"健康检查失败 HTTP={resp.status_code}")
    except Exception as e:
        record("TC-V151-01", False, f"健康检查异常: {e}")


def test_login_admin():
    """TC-V151-02: admin 登录"""
    global ADMIN_TOKEN
    ADMIN_TOKEN = login(USERNAME, PASSWORD)
    record("TC-V151-02", ADMIN_TOKEN is not None,
           f"admin 登录 {'成功' if ADMIN_TOKEN else '失败'}")


def test_db_enum_released_forced():
    """TC-V151-03: 数据库枚举包含 RELEASED_FORCED(SQLAlchemy 用 .name 大写存储)"""
    try:
        rows = db_query(
            "SELECT enumlabel FROM pg_enum WHERE enumtypid = "
            "(SELECT oid FROM pg_type WHERE typname = 'release_status') "
            "ORDER BY enumsortorder;"
        )
        labels = [r[0] for r in rows]
        # 接受大小写两种形式(数据库已统一为大写 RELEASED_FORCED)
        if "RELEASED_FORCED" in labels or "released_forced" in labels:
            record("TC-V151-03", True,
                   f"数据库枚举包含 RELEASED_FORCED (共 {len(labels)} 个: {labels})")
        else:
            record("TC-V151-03", False, f"数据库枚举未包含 RELEASED_FORCED: {labels}")
    except Exception as e:
        record("TC-V151-03", False, f"数据库查询失败: {e}")


def test_db_llm_reviews_columns():
    """TC-V151-04: llm_reviews 表已添加 force_passed/force_passed_by/force_passed_at 字段"""
    try:
        rows = db_query(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='llm_reviews' AND column_name IN "
            "('force_passed','force_passed_by','force_passed_at') "
            "ORDER BY column_name;"
        )
        cols = {r[0]: r[1] for r in rows}
        required = {"force_passed", "force_passed_by", "force_passed_at"}
        missing = required - set(cols.keys())
        if not missing:
            record("TC-V151-04", True,
                   f"llm_reviews 表已包含全部 3 个新字段: {cols}")
        else:
            record("TC-V151-04", False, f"缺失字段: {missing},实际: {cols}")
    except Exception as e:
        record("TC-V151-04", False, f"数据库查询失败: {e}")


def test_search_released_forced_filter():
    """TC-V151-05: /api/search/releases 支持 status=released_forced 过滤"""
    if not ADMIN_TOKEN:
        record("TC-V151-05", False, "无 token")
        return
    headers = get_headers(ADMIN_TOKEN)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BASE_URL}/search/releases",
                params={"status": "released_forced", "page": 1, "page_size": 5},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", []) if isinstance(data, dict) else data
                record("TC-V151-05", True,
                       f"status=released_forced 过滤成功,返回 {len(items)} 条")
            else:
                record("TC-V151-05", False,
                       f"HTTP={resp.status_code},body={resp.text[:200]}")
    except Exception as e:
        record("TC-V151-05", False, f"异常: {e}")


def test_release_response_has_force_passed_count():
    """TC-V151-06: ReleaseListResponse 包含 force_passed_count 字段"""
    if not ADMIN_TOKEN:
        record("TC-V151-06", False, "无 token")
        return
    headers = get_headers(ADMIN_TOKEN)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BASE_URL}/search/releases",
                params={"status": "released", "page": 1, "page_size": 1},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", []) if isinstance(data, dict) else data
                if items:
                    first = items[0]
                    if "force_passed_count" in first:
                        record("TC-V151-06", True,
                               f"force_passed_count={first['force_passed_count']}")
                    else:
                        record("TC-V151-06", False,
                               f"未返回 force_passed_count 字段,字段: {list(first.keys())[:10]}")
                else:
                    record("TC-V151-06", False, "无 released release")
            else:
                record("TC-V151-06", False, f"HTTP={resp.status_code}")
    except Exception as e:
        record("TC-V151-06", False, f"异常: {e}")


def test_find_pending_confirm_release():
    """TC-V151-07: 查找 pending_confirm 状态的 release"""
    global PENDING_RELEASE
    if not ADMIN_TOKEN:
        record("TC-V151-07", False, "无 token")
        return
    items = search_releases_by_status(ADMIN_TOKEN, "pending_confirm")
    if items:
        PENDING_RELEASE = items[0]
        record("TC-V151-07", True,
               f"找到 pending_confirm release: {PENDING_RELEASE['id'][:8]}")
    else:
        record("TC-V151-07", False, "未找到 pending_confirm release")


def test_force_advance_pending_confirm_rollback():
    """TC-V151-08: 对 pending_confirm release 特批放行 -> released_forced,然后回滚"""
    if not PENDING_RELEASE:
        record("TC-V151-08", False, "无 pending_confirm release 可测")
        return
    headers = get_headers(ADMIN_TOKEN)
    release_id = PENDING_RELEASE["id"]
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BASE_URL}/releases/{release_id}/force-advance",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                if status == "released_forced":
                    record("TC-V151-08", True,
                           "特批放行成功,status=released_forced")
                else:
                    record("TC-V151-08", False,
                           f"特批放行返回 status={status},期望 released_forced")
            else:
                record("TC-V151-08", False,
                       f"特批放行 HTTP={resp.status_code},body={resp.text[:200]}")
    except Exception as e:
        record("TC-V151-08", False, f"特批放行异常: {e}")
    finally:
        # 回滚:恢复为 PENDING_CONFIRM 状态(数据库枚举值大写),清理 confirmed_by/confirmed_at/force_advanced_*
        db_execute(
            "UPDATE releases SET status='PENDING_CONFIRM', "
            "confirmed_by=NULL, confirmed_at=NULL, "
            "force_advanced_by=NULL, force_advanced_at=NULL WHERE id=%s;",
            (release_id,)
        )
        # 删除可能创建的占位 review(force_passed=True 且 conclusion 包含"特批放行-该阶段")
        db_execute(
            "DELETE FROM llm_reviews WHERE release_id=%s "
            "AND force_passed=TRUE AND conclusion LIKE '特批放行-该阶段%';",
            (release_id,)
        )


def test_find_code_pending_review_release():
    """TC-V151-09: 查找 code_pending_review 状态的 release"""
    global CODE_REVIEW_RELEASE
    if not ADMIN_TOKEN:
        record("TC-V151-09", False, "无 token")
        return
    items = search_releases_by_status(ADMIN_TOKEN, "code_pending_review")
    if items:
        CODE_REVIEW_RELEASE = items[0]
        record("TC-V151-09", True,
               f"找到 code_pending_review release: {CODE_REVIEW_RELEASE['id'][:8]}")
    else:
        record("TC-V151-09", False, "未找到 code_pending_review release")


def test_force_advance_code_review_with_force_passed_rollback():
    """TC-V151-10: code_pending_review 特批放行 -> test_pending_review + force_passed=True,然后回滚"""
    global ORIG_FORCE_PASSED_STATE
    if not CODE_REVIEW_RELEASE:
        record("TC-V151-10", False, "无 code_pending_review release 可测")
        return
    headers = get_headers(ADMIN_TOKEN)
    release_id = CODE_REVIEW_RELEASE["id"]

    # 记录此 release 现有的所有 code_review 评审的 force_passed 原值(枚举值大写)
    orig_rows = db_query(
        "SELECT id::text, force_passed, force_passed_by::text, force_passed_at::text "
        "FROM llm_reviews WHERE release_id=%s AND review_type='CODE_REVIEW';",
        (release_id,)
    )
    for r in orig_rows:
        # force_passed 是 't'/'f' 字符串,转换成 bool
        fp = r[1] in ("t", "True", "true")
        fp_by = None if r[2] in ("", "NULL") else r[2]
        fp_at = None if r[3] in ("", "NULL") else r[3]
        ORIG_FORCE_PASSED_STATE[r[0]] = (fp, fp_by, fp_at)

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BASE_URL}/releases/{release_id}/force-advance",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                new_status = data.get("status")
                if new_status == "test_pending_review":
                    # 查询 reviews,验证 force_passed 标记
                    rev_resp = client.get(
                        f"{BASE_URL}/reviews/release/{release_id}",
                        headers=headers,
                    )
                    if rev_resp.status_code == 200:
                        reviews = rev_resp.json()
                        code_reviews = [r for r in reviews if r.get("review_type") == "code_review"]
                        force_passed_reviews = [r for r in code_reviews if r.get("force_passed") is True]
                        if force_passed_reviews:
                            fp = force_passed_reviews[0]
                            by_name = fp.get("force_passed_by_name") or "(未知)"
                            record("TC-V151-10", True,
                                   f"代码评审特批放行成功,force_passed=True,放行人={by_name}")
                        else:
                            record("TC-V151-10", False,
                                   "未找到 force_passed=True 的 code_review")
                    else:
                        record("TC-V151-10", False,
                               f"查询 reviews HTTP={rev_resp.status_code}")
                else:
                    record("TC-V151-10", False,
                           f"new_status={new_status},期望 test_pending_review")
            else:
                record("TC-V151-10", False,
                       f"HTTP={resp.status_code},body={resp.text[:200]}")
    except Exception as e:
        record("TC-V151-10", False, f"异常: {e}")
    finally:
        # 回滚:恢复 release 状态为 CODE_PENDING_REVIEW(枚举值大写)
        db_execute(
            "UPDATE releases SET status='CODE_PENDING_REVIEW', "
            "force_advanced_by=NULL, force_advanced_at=NULL WHERE id=%s;",
            (release_id,)
        )
        # 删除可能创建的占位 review(force_passed=True 且 conclusion 包含"特批放行-该阶段")
        db_execute(
            "DELETE FROM llm_reviews WHERE release_id=%s "
            "AND force_passed=TRUE AND conclusion LIKE '特批放行-该阶段%';",
            (release_id,)
        )
        # 恢复所有 CODE_REVIEW 的 force_passed 字段
        for review_id, (fp, fp_by, fp_at) in ORIG_FORCE_PASSED_STATE.items():
            db_execute(
                "UPDATE llm_reviews SET force_passed=%s, "
                "force_passed_by=%s, force_passed_at=%s WHERE id=%s;",
                (fp, fp_by, fp_at, review_id)
            )


def test_find_released_release():
    """TC-V151-11: 查找 released 状态的 release(用于已释放检测)"""
    global RELEASED_RELEASE
    if not ADMIN_TOKEN:
        record("TC-V151-11", False, "无 token")
        return
    items = search_releases_by_status(ADMIN_TOKEN, "released")
    if items:
        RELEASED_RELEASE = items[0]
        record("TC-V151-11", True,
               f"找到 released release: {RELEASED_RELEASE['id'][:8]}")
    else:
        record("TC-V151-11", False, "未找到 released release")


def test_released_release_cannot_force_advance():
    """TC-V151-12: 已 released 的 release 不允许再次特批放行(返回 400)"""
    if not RELEASED_RELEASE:
        record("TC-V151-12", False, "无 released release 可测")
        return
    headers = get_headers(ADMIN_TOKEN)
    release_id = RELEASED_RELEASE["id"]
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BASE_URL}/releases/{release_id}/force-advance",
                headers=headers,
            )
            if resp.status_code == 400:
                record("TC-V151-12", True,
                       f"已释放 release 特批放行返回 400(符合预期),body={resp.text[:100]}")
            else:
                record("TC-V151-12", False,
                       f"HTTP={resp.status_code},期望 400,body={resp.text[:200]}")
    except Exception as e:
        record("TC-V151-12", False, f"异常: {e}")


def test_release_detail_force_passed_count():
    """TC-V151-13: /api/releases/{id} 详情接口返回 force_passed_count"""
    if not RELEASED_RELEASE:
        record("TC-V151-13", False, "无 released release 可测")
        return
    headers = get_headers(ADMIN_TOKEN)
    release_id = RELEASED_RELEASE["id"]
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BASE_URL}/releases/{release_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                if "force_passed_count" in data:
                    count = data["force_passed_count"]
                    record("TC-V151-13", True,
                           f"详情接口返回 force_passed_count={count}")
                else:
                    record("TC-V151-13", False,
                           f"详情接口未返回 force_passed_count 字段")
            else:
                record("TC-V151-13", False, f"HTTP={resp.status_code}")
    except Exception as e:
        record("TC-V151-13", False, f"异常: {e}")


def test_review_response_has_force_passed_fields():
    """TC-V151-14: LLMReviewResponse 包含 force_passed_* 字段"""
    if not ADMIN_TOKEN:
        record("TC-V151-14", False, "无 token")
        return
    headers = get_headers(ADMIN_TOKEN)
    # 优先用 RELEASED_RELEASE,否则用 PENDING_RELEASE 或 CODE_REVIEW_RELEASE
    target_release = RELEASED_RELEASE or PENDING_RELEASE or CODE_REVIEW_RELEASE
    if not target_release:
        # 查询任意 release
        items = search_releases_by_status(ADMIN_TOKEN, "released") or \
                search_releases_by_status(ADMIN_TOKEN, "test_pending_review")
        if items:
            target_release = items[0]
    if not target_release:
        record("TC-V151-14", False, "无 release 可查 reviews")
        return
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BASE_URL}/reviews/release/{target_release['id']}",
                headers=headers,
            )
            if resp.status_code == 200:
                reviews = resp.json()
                if reviews:
                    first = reviews[0]
                    required = ["force_passed", "force_passed_by",
                                "force_passed_by_name", "force_passed_at"]
                    missing = [f for f in required if f not in first]
                    if not missing:
                        record("TC-V151-14", True,
                               f"LLMReviewResponse 包含全部 4 个新字段 "
                               f"(force_passed={first.get('force_passed')})")
                    else:
                        record("TC-V151-14", False,
                               f"缺失字段: {missing},实际字段: {list(first.keys())}")
                else:
                    record("TC-V151-14", False, "无评审记录")
            else:
                record("TC-V151-14", False, f"HTTP={resp.status_code}")
    except Exception as e:
        record("TC-V151-14", False, f"异常: {e}")


def main():
    print("=" * 70)
    print("v1.5.1 特批放行状态机测试")
    print("=" * 70)

    test_health()
    test_login_admin()
    test_db_enum_released_forced()
    test_db_llm_reviews_columns()
    test_search_released_forced_filter()
    test_release_response_has_force_passed_count()
    test_find_pending_confirm_release()
    test_force_advance_pending_confirm_rollback()
    test_find_code_pending_review_release()
    test_force_advance_code_review_with_force_passed_rollback()
    test_find_released_release()
    test_released_release_cannot_force_advance()
    test_release_detail_force_passed_count()
    test_review_response_has_force_passed_fields()

    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"测试结果: {passed} 通过 / {failed} 失败 / 共 {len(results)} 项")
    print("=" * 70)

    # 保存结果
    out_path = "/mnt/c/Users/tiany/Documents/Trae solo my data/v151_test_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"结果已保存: {out_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
