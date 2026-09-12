import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { createPipeline } from '@/api/pipelines'
import { REQ_TYPES, REQ_SCALES, PIPELINE_PATHS } from '@/utils/constants'
import clsx from 'clsx'

export default function NewRequest() {
  usePageTitle('提交需求')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [input, setInput] = useState('')
  const [reqType, setReqType] = useState(searchParams.get('type') || '')
  const [reqScale, setReqScale] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const t = searchParams.get('type')
    if (t) setReqType(t)
  }, [searchParams])

  const handleSubmit = async () => {
    if (!input.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await createPipeline({
        user_input: input.trim(),
        req_type: reqType || undefined,
        req_scale: reqScale || undefined,
      })
      navigate('/dashboard')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const selectedType = REQ_TYPES.find((t) => t.key === reqType)
  const pipelinePath = reqType ? PIPELINE_PATHS[reqType] : null

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {/* 标题 */}
      <div>
        <h1 className="text-[28px] font-bold tracking-tight text-gray-900">提交新需求</h1>
        <p className="mt-1.5 text-[15px] text-gray-500">
          详细描述你的游戏开发需求，AI 团队将自动分析并执行
        </p>
      </div>

      {/* 需求输入 */}
      <div>
        <label className="mb-2.5 block text-[13px] font-semibold text-gray-700">需求描述</label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={"描述你想要开发的功能...\n\n提示：越详细的描述，AI 团队越能精准理解你的需求"}
          className="w-full rounded-xl border border-gray-200 bg-white p-4 text-[15px] leading-relaxed text-gray-900 placeholder-gray-400 outline-none transition-all focus:border-brand/40 focus:shadow-input resize-none"
          rows={5}
        />
      </div>

      {/* 需求类型 */}
      <div>
        <label className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-gray-700">
          需求类型
          {!reqType && <span className="font-normal text-gray-400">(可选，AI 会自动识别)</span>}
        </label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {REQ_TYPES.map((type) => {
            const selected = reqType === type.key
            return (
              <button
                key={type.key}
                onClick={() => setReqType(reqType === type.key ? '' : type.key)}
                className={clsx(
                  'group flex items-center gap-2.5 rounded-xl border p-3 text-left transition-all',
                  selected
                    ? 'border-brand/40 bg-brand-50 shadow-sm'
                    : 'border-gray-150 bg-white hover:border-gray-200 hover:bg-gray-50'
                )}
              >
                <span className={clsx(
                  'flex h-8 w-8 items-center justify-center rounded-lg text-base transition-transform',
                  selected ? 'bg-brand/10 scale-110' : 'bg-gray-50 group-hover:scale-105'
                )}>
                  {type.icon}
                </span>
                <div className="min-w-0">
                  <div className={clsx(
                    'text-[12px] font-semibold transition-colors',
                    selected ? 'text-brand' : 'text-gray-900'
                  )}>
                    {type.name}
                  </div>
                  <div className="text-[10px] text-gray-400 leading-snug">{type.desc}</div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* 规模 */}
      <div>
        <label className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-gray-700">
          预估规模
          {!reqScale && <span className="font-normal text-gray-400">(可选，AI 会自动判断)</span>}
        </label>
        <div className="flex flex-wrap gap-2.5">
          {REQ_SCALES.map((scale) => {
            const selected = reqScale === scale.key
            return (
              <button
                key={scale.key}
                onClick={() => setReqScale(reqScale === scale.key ? '' : scale.key)}
                className={clsx(
                  'rounded-xl border px-4 py-2.5 text-left transition-all',
                  selected
                    ? 'border-brand/40 bg-brand-50'
                    : 'border-gray-150 bg-white hover:border-gray-200 hover:bg-gray-50'
                )}
              >
                <div className={clsx(
                  'text-[13px] font-semibold',
                  selected ? 'text-brand' : 'text-gray-900'
                )}>
                  {scale.key} · {scale.name}
                </div>
                <div className="text-[11px] text-gray-400">{scale.desc}</div>
              </button>
            )
          })}
        </div>
      </div>

      {/* 预览流程 */}
      {pipelinePath && (
        <div className="rounded-xl border border-brand/20 bg-brand-50 p-5">
          <div className="mb-3 flex items-center gap-2.5">
            <svg className="h-4 w-4 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
            <span className="text-[13px] font-semibold text-gray-900">预计执行流程</span>
            {selectedType && <Badge color="orange" size="sm">{selectedType.name}</Badge>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {pipelinePath.map((step, i) => (
              <span key={i} className="flex items-center gap-2">
                {i > 0 && (
                  <svg className="h-3 w-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                  </svg>
                )}
                <span className="rounded-lg bg-white px-3 py-1.5 text-[12px] font-medium text-gray-600 shadow-soft">
                  {step}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-5 py-3.5 text-sm text-red-600">
          <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          提交失败: {error}
        </div>
      )}

      {/* 提交 */}
      <div className="flex items-center gap-4 pb-8">
        <Button
          variant="primary"
          size="lg"
          onClick={handleSubmit}
          disabled={!input.trim() || submitting}
          loading={submitting}
        >
          {submitting ? '提交中...' : '提交需求'}
        </Button>
        <span className="text-[13px] text-gray-400">
          提交后，AI 团队将自动开始处理
        </span>
      </div>
    </div>
  )
}
