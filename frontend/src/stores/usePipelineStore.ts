import { create } from 'zustand'
import type { PipelineInstance, PipelineDefinitions } from '../api/types'
import { fetchPipelines, fetchPipelineDefinitions } from '../api/pipelines'

interface PipelineStore {
  pipelines: PipelineInstance[]
  definitions: PipelineDefinitions | null
  loading: boolean
  error: string | null
  fetch: () => Promise<void>
  fetchDefs: () => Promise<void>
}

export const usePipelineStore = create<PipelineStore>((set) => ({
  pipelines: [],
  definitions: null,
  loading: false,
  error: null,
  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const res = await fetchPipelines()
      set({ pipelines: res.all || [], loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },
  fetchDefs: async () => {
    try {
      const defs = await fetchPipelineDefinitions()
      set({ definitions: defs })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },
}))
