import { create } from 'zustand'
import type { InventoryData } from '../api/types'
import { fetchInventory } from '../api/inventory'

interface InventoryStore {
  data: InventoryData | null
  loading: boolean
  error: string | null
  fetch: () => Promise<void>
}

export const useInventoryStore = create<InventoryStore>((set) => ({
  data: null,
  loading: false,
  error: null,
  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const data = await fetchInventory()
      set({ data, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },
}))
