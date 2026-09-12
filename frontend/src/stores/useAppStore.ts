import { create } from 'zustand'

interface AppStore {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  rightSidebarOpen: boolean
  toggleRightSidebar: () => void
  setRightSidebarOpen: (open: boolean) => void
}

export const useAppStore = create<AppStore>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  rightSidebarOpen: true,
  toggleRightSidebar: () => set((s) => ({ rightSidebarOpen: !s.rightSidebarOpen })),
  setRightSidebarOpen: (open: boolean) => set({ rightSidebarOpen: open }),
}))
