# QLoop v1.5.2 测试报告

## 测试概述

- **版本**: v1.5.2
- **测试日期**: 2026-07-23
- **测试范围**: 自定义组织类型功能
- **测试用例数**: 18
- **通过率**: 100% (18/18)

## 测试环境

- 后端: FastAPI + SQLAlchemy 2.0 async + PostgreSQL
- 前端: Vue 3 + Element Plus + TypeScript
- 运行环境: WSL Ubuntu-24.04

## 测试结果

| TC ID | 测试内容 | 结果 |
|-------|---------|------|
| TC-01 | 健康检查版本=1.5.2 | PASS |
| TC-02 | GET /api/org-types 返回 3 个系统类型 | PASS |
| TC-03 | 系统类型为 department/division/group | PASS |
| TC-04 | 所有预设类型 is_system=true | PASS |
| TC-05 | 创建自定义类型 center | PASS |
| TC-06 | 重复 code 创建返回 400 | PASS |
| TC-07 | code 大小写不敏感检查 | PASS |
| TC-08 | 创建使用自定义类型的组织 | PASS |
| TC-09 | 使用不存在的类型创建返回 400 | PASS |
| TC-10 | 组织树包含 center 类型 | PASS |
| TC-11 | 删除系统类型返回 400 | PASS |
| TC-12 | 删除有引用的自定义类型返回 400 | PASS |
| TC-13 | 删除无引用的自定义类型返回 204 | PASS |
| TC-14 | 删除后类型列表恢复 3 个 | PASS |
| TC-15 | org_units.org_type 列类型为 VARCHAR | PASS |
| TC-16 | org_units.org_type 值为小写 | PASS |
| TC-17 | 旧枚举类型 org_type 已删除 | PASS |
| TC-18 | created_by_name 在列表中填充 | PASS |

## 结论

v1.5.2 自定义组织类型功能全部测试通过,包括:
- 系统预设类型保护(不可删除)
- 自定义类型 CRUD 完整流程
- 类型引用检查(有引用不可删除)
- code 唯一性检查(大小写不敏感)
- 组织创建/更新类型校验
- 数据库迁移正确性(enum -> varchar, 大写 -> 小写)
