#!/usr/bin/env python3
"""检查数据库用户和 release 状态"""
import asyncio
import sys
sys.path.insert(0, "/opt/qloop/backend")
from app.database import async_session
from sqlalchemy import text


async def check():
    async with async_session() as db:
        # 现有用户
        r = await db.execute(text("SELECT username, system_role, full_name FROM users ORDER BY created_at"))
        users = r.fetchall()
        print("=== 现有用户 ===")
        for u in users:
            print(f"  {u[0]} | role={u[1]} | full_name={u[2]}")

        # Release 状态分布(全部大写枚举值)
        r = await db.execute(text("SELECT status, COUNT(*) FROM releases GROUP BY status ORDER BY status"))
        statuses = r.fetchall()
        print("\n=== Release 状态分布 ===")
        for s in statuses:
            print(f"  {s[0]}: {s[1]} 条")

        # 各状态 release id
        for st in ["DRAFT", "CODE_PENDING_REVIEW", "TEST_PENDING_REVIEW",
                   "EXPERT_PENDING_REVIEW", "PENDING_CONFIRM", "RELEASED", "REVIEW_FAILED"]:
            r = await db.execute(text(f"SELECT id, version_id FROM releases WHERE status='{st}' LIMIT 2"))
            rows = r.fetchall()
            print(f"\n=== {st} ({len(rows)} 条可见) ===")
            for c in rows:
                print(f"  release_id={c[0]} | version_id={c[1]}")

        # 带 test_report_path / review_report_path 的 release
        r = await db.execute(text("SELECT id, test_report_path FROM releases WHERE test_report_path IS NOT NULL LIMIT 3"))
        test_reports = r.fetchall()
        print(f"\n=== 带 test_report_path ({len(test_reports)} 条) ===")
        for c in test_reports:
            print(f"  release_id={c[0]} | path={c[1]}")

        r = await db.execute(text("SELECT id, review_report_path FROM releases WHERE review_report_path IS NOT NULL LIMIT 3"))
        review_reports = r.fetchall()
        print(f"\n=== 带 review_report_path ({len(review_reports)} 条) ===")
        for c in review_reports:
            print(f"  release_id={c[0]} | path={c[1]}")


asyncio.run(check())
