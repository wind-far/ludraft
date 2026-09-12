/**
 * 格式化日期时间
 */
export function formatTime(iso: string): string {
  if (!iso) return ''
  return iso.substring(11, 19)
}

/**
 * 格式化为完整日期
 */
export function formatDate(iso: string): string {
  if (!iso) return ''
  return iso.substring(0, 19).replace('T', ' ')
}

/**
 * 格式化数字为简写
 */
export function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

/**
 * 获取 group 对应的 TailwindCSS 颜色类
 */
export function getGroupColorClass(group: string): string {
  const map: Record<string, string> = {
    control: 'bg-accent-blue/15 text-accent-blue',
    design: 'bg-accent-green/15 text-accent-green',
    architecture: 'bg-accent-purple/15 text-accent-purple',
    implementation: 'bg-accent-orange/15 text-accent-orange',
    verification: 'bg-accent-cyan/15 text-accent-cyan',
  }
  return map[group] || 'bg-accent-blue/15 text-accent-blue'
}
