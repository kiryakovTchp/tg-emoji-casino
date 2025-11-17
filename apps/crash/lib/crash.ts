import { crashApiFetch } from "./api"

export type CrashPhase = "betting" | "flying" | "crashed"

export interface CrashSessionState {
  id?: string
  phase?: CrashPhase
  seed?: string
  startTime?: number
  betEndTime?: number
  crashTime?: number
  duration?: number
  crashPoint?: number
}

export interface CrashUserState {
  betAmount?: number
  cashoutMultiplier?: number | null
  balance?: number
}

export interface CrashBalance {
  cash?: number
  bonus?: number
  total?: number
}

export interface CrashStateSnapshot {
  session?: CrashSessionState
  user?: CrashUserState
  balance?: CrashBalance
}

export interface CrashBetPayload {
  amount: number
  prefer?: "cash_first" | "bonus_first" | "auto_bonus_when_active"
  autoCashout?: number | null
  sessionId?: string
}

export interface CrashCashoutPayload {
  sessionId?: string
  betId?: string | number
}

export interface CrashActionResponse extends CrashStateSnapshot {
  bet?: {
    id?: string | number
    amount?: number
    currency?: string
    sessionId?: string
  }
  cashout?: {
    multiplier?: number
    payout?: number
    sessionId?: string
  }
  success?: boolean
  message?: string
}

const numberOrUndefined = (value: any): number | undefined => {
  const num = Number(value)
  return Number.isFinite(num) ? num : undefined
}

const timestampMs = (value: any): number | undefined => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

const normalizePhase = (value: any): CrashPhase | undefined => {
  if (!value && value !== 0) return undefined
  const normalized = String(value).toLowerCase()
  if (normalized.includes("fly")) return "flying"
  if (normalized.includes("crash") || normalized.includes("result"))
    return "crashed"
  return "betting"
}

const parseSession = (payload: any): CrashSessionState | undefined => {
  if (!payload) return undefined
  const id =
    payload.session_id ??
    payload.sessionId ??
    payload.round_id ??
    payload.roundId ??
    payload.id

  return {
    id: id ? String(id) : undefined,
    phase: normalizePhase(payload.phase ?? payload.state ?? payload.status),
    seed: payload.seed_hash ?? payload.seedHash ?? payload.seed,
    startTime:
      timestampMs(payload.start_time_ms ?? payload.start_time ?? payload.startTime) ??
      timestampMs(payload.started_at),
    betEndTime:
      timestampMs(payload.bet_end_time_ms ?? payload.bet_end_time ?? payload.betEndTime) ??
      timestampMs(payload.ends_at),
    crashTime:
      numberOrUndefined(payload.crash_time_ms ?? payload.crash_time ?? payload.crashTime) ??
      numberOrUndefined(payload.duration_ms),
    duration:
      numberOrUndefined(payload.duration_ms ?? payload.duration ?? payload.round_duration) ??
      numberOrUndefined(payload.crash_time_ms),
    crashPoint:
      numberOrUndefined(payload.crash_point ?? payload.crashPoint ?? payload.result) ??
      numberOrUndefined(payload.crash),
  }
}

const parseUserState = (payload: any): CrashUserState | undefined => {
  if (!payload) return undefined
  const betAmount =
    numberOrUndefined(payload.bet_amount ?? payload.bet ?? payload.amount) ??
    numberOrUndefined(payload.active_bet)
  const cashoutMultiplier =
    numberOrUndefined(payload.cashout_multiplier ?? payload.cashout ?? payload.multiplier) ??
    (payload.cashout === null ? null : undefined)
  const balance =
    numberOrUndefined(payload.balance) ??
    numberOrUndefined(payload.coins) ??
    numberOrUndefined(payload.wallet?.balance) ??
    numberOrUndefined(payload.wallet?.coins_total) ??
    (Number.isFinite(betAmount) ? undefined : undefined)

  return {
    betAmount,
    cashoutMultiplier:
      typeof cashoutMultiplier === "number" ? cashoutMultiplier : undefined,
    balance,
  }
}

const parseBalance = (payload: any): CrashBalance | undefined => {
  if (!payload) return undefined
  const cash =
    numberOrUndefined(payload.coins_cash ?? payload.cash ?? payload.cash_balance) ??
    numberOrUndefined(payload.real)
  const bonus =
    numberOrUndefined(payload.coins_bonus ?? payload.bonus ?? payload.bonus_balance)
  const total =
    numberOrUndefined(payload.total ?? payload.coins_total ?? payload.balance) ??
    (typeof cash === "number" || typeof bonus === "number"
      ? (cash ?? 0) + (bonus ?? 0)
      : undefined)

  if (
    typeof cash === "undefined" &&
    typeof bonus === "undefined" &&
    typeof total === "undefined"
  ) {
    return undefined
  }

  return { cash, bonus, total }
}

const normalizeState = (payload: any): CrashStateSnapshot => {
  if (!payload || typeof payload !== "object") {
    return {}
  }
  const sessionPayload =
    payload.session ?? payload.state ?? payload.game ?? payload.round ?? payload
  const userPayload = payload.user ?? payload.player ?? payload.me
  const balancePayload =
    payload.balance ?? payload.wallet ?? userPayload?.wallet ?? payload.wallet

  return {
    session: parseSession(sessionPayload),
    user: parseUserState(userPayload),
    balance: parseBalance(balancePayload),
  }
}

const parseBet = (payload: any) => {
  if (!payload) return undefined
  const amount = numberOrUndefined(payload.amount ?? payload.bet)
  const sessionId = payload.session_id ?? payload.sessionId ?? payload.round_id
  return {
    id: payload.id ?? payload.bet_id,
    amount,
    currency: payload.currency,
    sessionId: sessionId ? String(sessionId) : undefined,
  }
}

const parseCashout = (payload: any) => {
  if (!payload) return undefined
  return {
    multiplier: numberOrUndefined(payload.multiplier ?? payload.cashout),
    payout: numberOrUndefined(payload.payout ?? payload.win),
    sessionId: payload.session_id ?? payload.sessionId,
  }
}

const normalizeActionResponse = (payload: any): CrashActionResponse => {
  const snapshot = normalizeState(payload)
  return {
    ...snapshot,
    bet: parseBet(payload.bet ?? payload.data?.bet),
    cashout: parseCashout(payload.cashout ?? payload.data?.cashout),
    success: payload?.success ?? payload?.ok ?? payload?.status === "ok",
    message: payload?.message ?? payload?.error,
  }
}

export const resolveBalanceValue = (balance?: CrashBalance | null): number | undefined => {
  if (!balance) return undefined
  if (typeof balance.total === "number") {
    return balance.total
  }
  if (
    typeof balance.cash === "number" ||
    typeof balance.bonus === "number"
  ) {
    return (balance.cash ?? 0) + (balance.bonus ?? 0)
  }
  return undefined
}

export async function fetchCrashState(
  token: string,
  baseUrl?: string
): Promise<CrashStateSnapshot> {
  const payload = await crashApiFetch(
    "/state",
    { method: "GET" },
    token,
    baseUrl
  )
  return normalizeState(payload)
}

export async function postCrashBet(
  body: CrashBetPayload,
  token: string,
  baseUrl?: string
): Promise<CrashActionResponse> {
  const payload = await crashApiFetch(
    "/bet",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    token,
    baseUrl
  )
  return normalizeActionResponse(payload)
}

export async function postCrashCashout(
  body: CrashCashoutPayload,
  token: string,
  baseUrl?: string
): Promise<CrashActionResponse> {
  const payload = await crashApiFetch(
    "/cashout",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    token,
    baseUrl
  )
  return normalizeActionResponse(payload)
}

export const crashBalanceFromPayload = (payload: any): CrashBalance | undefined =>
  parseBalance(payload)

