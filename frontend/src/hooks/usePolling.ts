import { useEffect, useRef, useCallback } from 'react'

/**
 * 轮询 Hook — 按指定间隔调用 callback
 */
export function usePolling(callback: () => void, interval: number, enabled = true) {
  const savedCallback = useRef(callback)
  const timerRef = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  const start = useCallback(() => {
    savedCallback.current()
    timerRef.current = setInterval(() => savedCallback.current(), interval)
  }, [interval])

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = undefined
    }
  }, [])

  useEffect(() => {
    if (enabled) {
      start()
    }
    return stop
  }, [enabled, start, stop])

  return { start, stop }
}
