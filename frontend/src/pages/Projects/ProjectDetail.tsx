import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'
import { usePolling } from '@/hooks/usePolling'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { POLLING_INTERVAL, TEAM_MEMBERS } from '@/utils/constants'
import { PageLoader } from '@/components/ui/Spinner'
import { fetchPipelines } from '@/api/pipelines'
import { uploadFiles, sendUserMessage, submitDecision } from '@/api/pipelines'
import { fetchLogs } from '@/api/logs'
import WorkspaceLayout from '@/components/workspace/WorkspaceLayout'
import ProcessPanel from '@/components/workspace/ProcessPanel'
import ToolPanel from '@/components/workspace/ToolPanel'
import type { WorkspaceMessage, PipelineInstance } from '@/api/types'

/**
 * 项目详情 — atoms.dev 风格全屏工作空间
 *
 * 左侧：Agent 过程可视化 + 用户输入
 * 右侧：工具面板（应用查看器/项目概览/代码编辑器/项目文件）
 */
export default function ProjectDetail() {
  const { pipelineId } = useParams<{ pipelineId: string }>()
  const navigate = useNavigate()
  usePageTitle('工作空间')

  const [pipeline, setPipeline] = useState<PipelineInstance | null>(null)
  const [loading, setLoading] = useState(true)
  const { messages, setMessages, addMessage, reset, setIsUploading } = useWorkspaceStore()

  // 加载 Pipeline 数据
  const loadData = useCallback(async () => {
    try {
      const res = await fetchPipelines()
      const all = res.all || []
      const found = all.find((p: any) => p.pipeline_id === pipelineId)
      if (found) {
        setPipeline(found)
        // 将 Pipeline 阶段转换为工作空间消息流
        syncStagesToMessages(found)
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [pipelineId])

  // 将 Pipeline stages 同步到消息流
  const syncStagesToMessages = useCallback(
    (pl: PipelineInstance) => {
      const stages = Array.isArray(pl.stages) ? pl.stages : []
      const existingIds = new Set(messages.map((m) => m.id))
      const newMessages: WorkspaceMessage[] = []

      // 系统欢迎消息
      if (!existingIds.has('system-start')) {
        newMessages.push({
          id: 'system-start',
          type: 'system',
          content: `🚀 开发流程已启动 — ${pl.req_type} · ${pl.req_name || pl.req_id}`,
          timestamp: pl.created_at || new Date().toISOString(),
        })
      }

      stages.forEach((stage, i) => {
        const msgId = `stage-${i}-${stage.agent_id}`
        if (existingIds.has(msgId)) return

        const agent = TEAM_MEMBERS.find((a) => a.id === stage.agent_id)
        const isDone = stage.status === 'completed'
        const isActive = stage.status === 'active' || stage.status === 'running'
        const isFailed = stage.status === 'failed'

        // Agent 工作消息
        if (isDone || isActive || isFailed) {
          newMessages.push({
            id: msgId,
            type: 'agent',
            agent_id: stage.agent_id,
            content: isDone
              ? `${stage.name} 阶段已完成。${agent?.name} 完成了相关工作任务。`
              : isActive
                ? `正在处理 ${stage.name} 阶段...`
                : `${stage.name} 阶段执行出错，需要检查。`,
            thinking: isDone
              ? [
                  { id: `${msgId}-t1`, content: `分析 ${stage.name} 阶段需求和约束`, timestamp: pl.created_at || '' },
                  { id: `${msgId}-t2`, content: `制定执行方案并开始工作`, timestamp: pl.created_at || '' },
                  { id: `${msgId}-t3`, content: `完成输出并验证结果`, timestamp: pl.created_at || '' },
                ]
              : isActive
                ? [
                    { id: `${msgId}-t1`, content: `正在分析 ${stage.name} 阶段的任务...`, timestamp: new Date().toISOString() },
                  ]
                : undefined,
            status: isActive ? 'streaming' : 'complete',
            timestamp: pl.started_at || pl.created_at || new Date().toISOString(),
          })
        }

        // 已完成阶段后添加交付物
        if (isDone) {
          const deliverableId = `deliverable-${i}`
          if (!existingIds.has(deliverableId)) {
            newMessages.push({
              id: deliverableId,
              type: 'deliverable',
              content: '',
              deliverable: {
                id: deliverableId,
                type: stage.agent_id === '04_programmer' ? 'code'
                    : stage.agent_id === '06_qa' ? 'test'
                    : stage.agent_id === '05_artist' || stage.agent_id === '07_ux' ? 'design'
                    : 'document',
                title: `${stage.name} 交付物`,
                summary: `${agent?.name} 完成了 ${stage.name} 阶段的产出，包括相关文档和资源。`,
                files: [
                  `output/${stage.name.toLowerCase().replace(/\s+/g, '_')}/README.md`,
                  `output/${stage.name.toLowerCase().replace(/\s+/g, '_')}/main.ts`,
                ],
              },
              timestamp: pl.started_at || pl.created_at || new Date().toISOString(),
            })
          }
        }

        // 在关键阶段添加决策门禁（策划完成后、架构评审后）
        if (isDone && (stage.agent_id === '02_planner' || stage.agent_id === '03_tech_lead')) {
          const decisionId = `decision-${i}`
          if (!existingIds.has(decisionId)) {
            newMessages.push({
              id: decisionId,
              type: 'decision',
              content: '',
              decision: {
                id: decisionId,
                stage: stage.name,
                agent_id: stage.agent_id,
                title: `${stage.name} 方案确认`,
                description: `${agent?.name} 已完成 ${stage.name} 方案。请确认是否同意此方案并继续下一阶段，或提出修改意见。`,
                options: [
                  { key: 'approve', label: '确认通过', icon: '✅' },
                  { key: 'reject', label: '需要修改', icon: '🔄' },
                  { key: 'skip', label: '跳过', icon: '⏭️' },
                ],
                status: 'approved', // 模拟已通过
                responded_at: pl.started_at || undefined,
              },
              timestamp: pl.started_at || pl.created_at || new Date().toISOString(),
            })
          }
        }
      })

      if (newMessages.length > 0) {
        setMessages([...messages, ...newMessages])
      }
    },
    [messages, setMessages]
  )

  useEffect(() => {
    reset()
    loadData()
    return () => {
      // 组件卸载时不重置，保留消息
    }
  }, [pipelineId])

  usePolling(loadData, POLLING_INTERVAL)

  // ━━━ 事件处理 ━━━
  const handleSendMessage = useCallback(
    async (text: string) => {
      const msg: WorkspaceMessage = {
        id: `user-${Date.now()}`,
        type: 'user',
        content: text,
        timestamp: new Date().toISOString(),
        status: 'complete',
      }
      addMessage(msg)
      // 投递到后端消息队列
      if (pipelineId) {
        try {
          await sendUserMessage(pipelineId, text)
        } catch (e) {
          console.warn('消息投递失败:', e)
        }
      }
    },
    [addMessage, pipelineId]
  )

  const handleDecisionResponse = useCallback(
    async (decisionId: string, response: string) => {
      // 提交决策到后端
      if (pipelineId) {
        try {
          await submitDecision(pipelineId, decisionId, response)
          addMessage({
            id: `decision-resp-${Date.now()}`,
            type: 'system',
            content: `✅ 决策已提交：${response === 'approve' ? '确认通过' : response === 'reject' ? '需要修改' : '跳过'}`,
            timestamp: new Date().toISOString(),
          })
        } catch (e) {
          console.warn('决策提交失败:', e)
        }
      }
    },
    [addMessage, pipelineId]
  )

  const handleFileUpload = useCallback(
    async (files: FileList) => {
      const fileArray = Array.from(files)
      const names = fileArray.map((f) => f.name).join(', ')

      // 显示上传中状态
      setIsUploading(true)
      addMessage({
        id: `upload-start-${Date.now()}`,
        type: 'system',
        content: `📎 正在上传文件：${names}`,
        timestamp: new Date().toISOString(),
      })

      try {
        const result = await uploadFiles(fileArray)
        addMessage({
          id: `upload-done-${Date.now()}`,
          type: 'system',
          content: `✅ 文件上传成功：${names}（共提取 ${result.total_text_length} 字符内容）`,
          timestamp: new Date().toISOString(),
        })

        // 如果文件中有文本内容，作为消息发送给 Agent
        if (result.combined_text.trim()) {
          const uploadMsg: WorkspaceMessage = {
            id: `user-upload-${Date.now()}`,
            type: 'user',
            content: `[上传文件内容]\n${result.combined_text.slice(0, 2000)}${result.combined_text.length > 2000 ? '\n...(内容已截断)' : ''}`,
            timestamp: new Date().toISOString(),
            status: 'complete',
          }
          addMessage(uploadMsg)
        }
      } catch (e) {
        addMessage({
          id: `upload-error-${Date.now()}`,
          type: 'system',
          content: `❌ 文件上传失败：${(e as Error).message}`,
          timestamp: new Date().toISOString(),
        })
      } finally {
        setIsUploading(false)
      }
    },
    [addMessage, setIsUploading]
  )

  const handleGitHubUrl = useCallback(
    (url: string) => {
      // TODO: 通过 API 发起 GitHub clone
      addMessage({
        id: `github-${Date.now()}`,
        type: 'system',
        content: `🔗 正在克隆 GitHub 仓库：${url}`,
        timestamp: new Date().toISOString(),
      })
    },
    [addMessage]
  )

  // ━━━ Loading / Not Found ━━━
  if (loading) return <PageLoader text="加载工作空间..." />

  if (!pipeline) {
    return (
      <div className="flex h-[calc(100vh-57px)] flex-col items-center justify-center">
        <div className="text-center">
          <div className="mb-4 flex h-16 w-16 mx-auto items-center justify-center rounded-2xl bg-gray-50 text-3xl">🔍</div>
          <h3 className="text-lg font-semibold text-gray-900">未找到该项目</h3>
          <p className="mt-1.5 text-sm text-gray-400">项目可能已被删除或 ID 不正确</p>
          <button
            onClick={() => navigate('/dashboard')}
            className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark transition-colors"
          >
            返回首页
          </button>
        </div>
      </div>
    )
  }

  // ━━━ 计算进度 ━━━
  const stages = Array.isArray(pipeline.stages) ? pipeline.stages : []
  const completedStages = stages.filter((s) => s.status === 'completed').length
  const progress = stages.length > 0 ? Math.round((completedStages / stages.length) * 100) : 0
  const pipelineName = pipeline.req_name || `需求 ${pipeline.req_id || ''}`

  // ━━━ 渲染工作空间 ━━━
  return (
    <div className="h-[calc(100vh-57px)]">
      <WorkspaceLayout
        left={
          <ProcessPanel
            messages={messages}
            pipelineName={pipelineName}
            pipelineStatus={pipeline.status}
            onSendMessage={handleSendMessage}
            onDecisionResponse={handleDecisionResponse}
            onFileUpload={handleFileUpload}
            onGitHubUrl={handleGitHubUrl}
          />
        }
        right={
          <ToolPanel
            pipelineId={pipeline.pipeline_id}
            stages={stages.map((s) => ({ name: s.name, status: s.status, agent_id: s.agent_id }))}
            progress={pipeline.status === 'completed' ? 100 : progress}
          />
        }
      />
    </div>
  )
}
