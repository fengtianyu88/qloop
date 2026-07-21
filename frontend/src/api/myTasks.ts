/** 我的待办/已办 API */
import request from './request'

export interface MyTaskItem {
  release_id: string
  project_id: string | null
  project_name: string | null
  version_id: string | null
  version_number: string | null
  release_number: number | null
  status: string
  change_notes: string | null
  created_at: string | null
  updated_at: string | null
  my_role: string | null
  // 功能7.1: 待办操作类型中文文案(如"上传代码包"、"特批放行"等)
  todo_type: string | null
  developer_name: string | null
  tester_name: string | null
  expert_name: string | null
  pm_name: string | null
}

/** 功能7.1: 待办/已办分页响应(对应后端 MyTaskPage) */
export interface MyTaskPage {
  items: MyTaskItem[]
  total: number
  page: number
  page_size: number
}

/** 获取当前用户的待办列表(分页) */
export async function getMyTodo(page: number = 1, pageSize: number = 50): Promise<MyTaskItem[]> {
  const resp = await request.get('/my-tasks/todo', { params: { page, page_size: pageSize } })
  // 后端返回 MyTaskPage { items, total, page, page_size },提取 items
  if (resp && Array.isArray((resp as any).items)) {
    return (resp as any).items as MyTaskItem[]
  }
  // 兼容:若后端直接返回数组(老版本)
  if (Array.isArray(resp)) {
    return resp as MyTaskItem[]
  }
  return []
}

/** 获取当前用户的已办列表(分页) */
export async function getMyDone(page: number = 1, pageSize: number = 50): Promise<MyTaskItem[]> {
  const resp = await request.get('/my-tasks/done', { params: { page, page_size: pageSize } })
  if (resp && Array.isArray((resp as any).items)) {
    return (resp as any).items as MyTaskItem[]
  }
  if (Array.isArray(resp)) {
    return resp as MyTaskItem[]
  }
  return []
}
