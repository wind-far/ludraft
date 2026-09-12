import { create } from 'zustand'
import type { MessageStats } from '../api/types'
import { fetchMessageStats } from '../api/messages'

interface MessageStore {
  stats: MessageStats | null
  loading: boolean
  error: string | null
  fetch: () => Promise<void>
}

export const useMessageStore = create<MessageStore>((set) => ({
  stats: null,
  loading: false,
  error: null,
  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const stats = await fetchMessageStats()
      set({ stats, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },
}))
