import client from './client'
import type { ApiResponse, PipelineInstance, PipelineDefinitions } from './types'

export async function fetchPipelines(): Promise<{
  active: PipelineInstance[]
  all: PipelineInstance[]
  total: number
}> {
  const { data } = await client.get<ApiResponse<{
    active: PipelineInstance[]
    all: PipelineInstance[]
    total: number
  }>>('/pipelines')
  return data.data
}

export async function fetchPipelineDefinitions(): Promise<PipelineDefinitions> {
  const { data } = await client.get<ApiResponse<PipelineDefinitions>>('/pipelines/definitions')
  return data.data
}

export async function createPipeline(params: {
  user_input: string
  req_type?: string
  req_scale?: string
}): Promise<PipelineInstance> {
  const { data } = await client.post<ApiResponse<PipelineInstance>>('/pipelines/create', params)
  return data.data
}

/**
 * 上传文件（独立上传接口，返回提取的文本内容）
 */
export async function uploadFiles(files: File[]): Promise<{
  files: Array<{ filename: string; size: number; text_length: number; status: string }>
  combined_text: string
  total_text_length: number
}> {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file, file.name)
  }
  const { data } = await client.post<ApiResponse<{
    files: Array<{ filename: string; size: number; text_length: number; status: string }>
    combined_text: string
    total_text_length: number
  }>>('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return data.data
}

/**
 * 创建 Pipeline（支持同时上传文件，multipart/form-data）
 */
export async function createPipelineWithFiles(params: {
  user_input?: string
  req_type?: string
  req_scale?: string
  files?: File[]
}): Promise<PipelineInstance & { uploaded_files?: number }> {
  const form = new FormData()
  if (params.user_input) form.append('user_input', params.user_input)
  if (params.req_type) form.append('req_type', params.req_type)
  if (params.req_scale) form.append('req_scale', params.req_scale)
  for (const file of params.files ?? []) {
    form.append('files', file, file.name)
  }
  const { data } = await client.post<ApiResponse<PipelineInstance & { uploaded_files?: number }>>(
    '/pipelines/create-with-files',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    }
  )
  return data.data
}

export async function deletePipeline(pipelineId: string): Promise<void> {
  await client.delete(`/pipelines/${pipelineId}`)
}

export async function renamePipeline(pipelineId: string, name: string): Promise<void> {
  await client.put(`/pipelines/${pipelineId}/rename`, { name })
}

/** 将用户消息投递到 Pipeline 的活跃 Agent */
export async function sendUserMessage(pipelineId: string, text: string): Promise<{ msg_id: string }> {
  const { data } = await client.post<ApiResponse<{ msg_id: string }>>(
    `/pipelines/${pipelineId}/message`,
    { user_input: text }
  )
  return data.data
}

/** 提交用户对决策门禁的响应 */
export async function submitDecision(
  pipelineId: string,
  decisionId: string,
  response: string
): Promise<void> {
  await client.post(
    `/pipelines/${pipelineId}/decision`,
    null,
    { params: { decision_id: decisionId, response } }
  )
}

/** 获取沙盒文件树（用于 FileExplorer） */
export async function fetchSandboxFiles(pipelineId: string): Promise<{
  agent_id: string
  path: string
  dirs: string[]
} | null> {
  try {
    const { data } = await client.get<ApiResponse<{
      agent_id: string
      path: string
      dirs: string[]
    }>>(`/sandboxes`)
    // 返回第一个有内容的沙盒
    const sandboxes = Array.isArray(data.data) ? data.data : []
    return sandboxes[0] ?? null
  } catch {
    return null
  }
}


