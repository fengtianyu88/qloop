/**
 * 站点信息 Store
 *
 * 持有动态的 site_name / site_short_name。
 * - 首次加载从 /api/system-settings/public 拉取（无需登录）
 * - 当 super_admin 修改后，通过 localStorage 信号 + 自定义事件触发刷新
 * - 任何组件都可订阅 siteInfo.siteName / siteShortName 实现动态绑定
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getPublicSiteInfo } from '@/api/systemSettings'
import { APP_TITLE, APP_SHORT_NAME } from '@/config'

const CACHE_KEY = 'qloop_site_info'
const EVENT_NAME = 'qloop:site-info-updated'

interface CachedSiteInfo {
  site_name: string
  site_short_name: string
  ts: number
}

function loadFromCache(): CachedSiteInfo | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as CachedSiteInfo
  } catch {
    return null
  }
}

export const useSiteInfoStore = defineStore('siteInfo', () => {
  const cache = loadFromCache()
  const siteName = ref<string>(cache?.site_name || APP_TITLE)
  const siteShortName = ref<string>(cache?.site_short_name || APP_SHORT_NAME)
  const loaded = ref<boolean>(false)

  async function refresh(): Promise<void> {
    try {
      const info = await getPublicSiteInfo()
      siteName.value = info.site_name
      siteShortName.value = info.site_short_name
      loaded.value = true
      localStorage.setItem(
        CACHE_KEY,
        JSON.stringify({
          site_name: info.site_name,
          site_short_name: info.site_short_name,
          ts: Date.now(),
        }),
      )
    } catch {
      // 拉取失败则保持当前值（默认或缓存）
    }
  }

  // 监听 super_admin 在另一标签页触发的更新事件
  if (typeof window !== 'undefined') {
    window.addEventListener(EVENT_NAME, () => {
      refresh()
    })
    // storage 事件：跨标签页同步
    window.addEventListener('storage', (e) => {
      if (e.key === CACHE_KEY) {
        refresh()
      }
    })
  }

  return {
    siteName,
    siteShortName,
    loaded,
    refresh,
  }
})
