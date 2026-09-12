import { create } from 'zustand'
import type { OverviewData } from '../api/types'
import { fetchOverview } from '../api/overview'

interface OverviewStore {
  data: OverviewData | null
  loading: boolean
  error: string | null
  fetch: () => Promise<void>
}

export const useOverviewStore = create<OverviewStore>((set) => ({
  data: null,
  loading: false,
  error: null,
  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const data = await fetchOverview()
      set({ data, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },
}))
