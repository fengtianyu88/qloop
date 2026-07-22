#!/usr/bin/env python3
"""重置测试用户的密码为已知值,以便执行跳过的测试用例"""
import asyncio
import sys
sys.path.insert(0, "/opt/qloop/backend")
from app.database import async_session
from app.utils.security import pwd_context
from sqlalchemy import text


# 用户名 -> 新密码
RESETS = {
    "pm_zhangwei": "Pm@2026",
    "dev_lisi": "Dev@2026",
    "tester_wangwu": "Test@2026",
    "expert_zhaoliu": "Expert@2026",
}


async def reset():
    async with async_session() as db:
        for username, password in RESETS.items():
            hashed = pwd_context.hash(password)
            r = await db.execute(
                text("UPDATE users SET hashed_password = :hp WHERE username = :u"),
                {"hp": hashed, "u": username},
            )
            print(f"  {username}: 重置密码 -> {password} (affected={r.rowcount})")
        await db.commit()
        print("密码重置完成")


asyncio.run(reset())
