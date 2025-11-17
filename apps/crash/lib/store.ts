import { create } from "zustand"

const DEFAULT_CRASH_API_BASE =
  process.env.NEXT_PUBLIC_CRASH_API_BASE || "https://casino.gnezdoai.ru/api/crash"

interface User {
  id?: string | number
  telegramId?: string
  username?: string
  firstName?: string
  avatarUrl?: string
  name?: string
  blocked?: boolean
  [key: string]: any
}

interface StoreState {
  user: User | null
  balance: number
  demoBalance: number
  authToken: string | null
  apiBaseUrl: string
  setUser: (user: User) => void
  setBalance: (balance: number) => void
  setDemoBalance: (demoBalance: number) => void
  setAuthToken: (token: string | null) => void
  setApiBaseUrl: (url: string) => void
  adjustBalance: (amount: number) => void
  adjustDemoBalance: (amount: number) => void
}

export const useStore = create<StoreState>((set) => ({
  user: null,
  balance: 0,
  demoBalance: 500,
  authToken: null,
  apiBaseUrl: DEFAULT_CRASH_API_BASE,
  setUser: (user) => set({ user }),
  setBalance: (balance) => set({ balance }),
  setDemoBalance: (demoBalance) => set({ demoBalance }),
  setAuthToken: (authToken) => set({ authToken }),
  setApiBaseUrl: (apiBaseUrl) => set({ apiBaseUrl }),
  adjustBalance: (amount) =>
    set((state) => ({ balance: state.balance + amount })),
  adjustDemoBalance: (amount) =>
    set((state) => ({ demoBalance: state.demoBalance + amount })),
}))
