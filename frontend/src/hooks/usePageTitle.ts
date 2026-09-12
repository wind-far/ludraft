import { useEffect } from 'react'

/**
 * 设置页面标题
 */
export function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title
    document.title = `${title} | OpenClaw`
    return () => { document.title = prev }
  }, [title])
}
