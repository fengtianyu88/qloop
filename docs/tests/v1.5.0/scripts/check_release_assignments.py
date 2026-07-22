#!/usr/bin/env python3
"""查询 release 与 PM/dev/test/expert 的分配关系"""
import asyncio
import sys
sys.path.insert(0, "/opt/qloop/backend")
from app.database import async_session
from sqlalchemy import text


async def check():
    async with async_session() as db:
        sql = """
        SELECT r.id AS release_id, r.status, r.version_id,
               v.version_number, v.project_id,
               v.developer_id, v.tester_id, v.expert_id,
               p.name AS project_name, p.pm_user_id,
               pm.username AS pm_username,
               dev.username AS dev_username,
               tester.username AS tester_username,
               expert.username AS expert_username
        FROM releases r
        JOIN versions v ON r.version_id = v.id
        JOIN projects p ON v.project_id = p.id
        LEFT JOIN users pm ON p.pm_user_id = pm.id
        LEFT JOIN users dev ON v.developer_id = dev.id
        LEFT JOIN users tester ON v.tester_id = tester.id
        LEFT JOIN users expert ON v.expert_id = expert.id
        WHERE v.is_deleted = false
        ORDER BY r.created_at DESC
        LIMIT 15
        """
        r = await db.execute(text(sql))
        rows = r.fetchall()
        print("=== Release 分配关系 ===")
        for row in rows:
            print(f"  release={row[0]}")
            print(f"    status={row[1]} | ver={row[3]} | project={row[4]}")
            print(f"    PM={row[10]} | dev={row[11]} | tester={row[12]} | expert={row[13]}")


asyncio.run(check())
