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
  developer_name: string | null
  tester_name: string | null
  expert_name: string | null
  pm_name: string | null
}

/** 获取当前用户的待办列表 */
export function getMyTodo(): Promise<MyTaskItem[]> {
  return request.get('/my-tasks/todo')
}

/** 获取当前用户的已办列表 */
export function getMyDone(): Promise<MyTaskItem[]> {
  return request.get('/my-tasks/done')
}
