"use client"

import BlockedUserScreen from "@/components/BlockedUserScreen"
import { CRASH_API_BASE, TELEGRAM_AUTH_URL } from "@/lib/api"
import { useStore } from "@/lib/store"
import { init, retrieveRawInitData } from "@telegram-apps/sdk"
import { useEffect, useRef, useState } from "react"

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isBlocked, setIsBlocked] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const authAttemptedRef = useRef(false)

  useEffect(() => {
    if (typeof window === "undefined") return
    if (authAttemptedRef.current) return

    authAttemptedRef.current = true

    init()
    const initDataRaw = retrieveRawInitData()
    console.log("[AuthProvider] initDataRaw:", initDataRaw ? "received" : "missing")

    if (!initDataRaw) {
      console.warn("[AuthProvider] Нет initDataRaw — не в Telegram WebView?")
      setIsLoading(false)
      return
    }

    const { setUser, setBalance, setAuthToken, setApiBaseUrl } =
      useStore.getState()
    setApiBaseUrl(CRASH_API_BASE)

    const authenticate = async () => {
      try {
        const response = await fetch(TELEGRAM_AUTH_URL, {
          method: "POST",
          headers: {
            Authorization: `tma ${initDataRaw}`,
          },
        })

        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(
            `Auth failed (${response.status}): ${errorText || "unknown"}`
          )
        }

        const payload = await response.json()
        console.log("[AuthProvider] auth payload:", payload)

        const token =
          payload.token || payload.jwt || payload.access_token || null
        const rawUser =
          payload.user ||
          payload.profile ||
          payload.data?.user ||
          payload.data?.profile

        if (!token || !rawUser) {
          throw new Error("Missing auth token or user in response")
        }

        setAuthToken(token)
        try {
          localStorage.setItem("casino_crash_jwt", token)
        } catch (error) {
          console.warn("Unable to persist JWT:", error)
        }

        const normalizedUser = normalizeUser(rawUser)
        setUser(normalizedUser)

        const balanceValue = deriveBalance(payload, rawUser)
        setBalance(balanceValue)

        if (normalizedUser.blocked) {
          setIsBlocked(true)
        }
      } catch (error) {
        console.error("Auth error:", error)
        alert("Ошибка авторизации через Telegram. Проверь консоль и сервер.")
      } finally {
        setIsLoading(false)
      }
    }

    authenticate()
  }, [])

  // Если пользователь заблокирован, показываем экран блокировки
  if (isBlocked) {
    return <BlockedUserScreen />
  }

  // Если загрузка, показываем пустой экран
  if (isLoading) {
    return <div className="min-h-screen bg-gray-900" />
  }

  return <>{children}</>
}

function normalizeUser(user: any) {
  const telegramId =
    user?.telegram_id || user?.telegramId || user?.tg_id || user?.tgId
  const username = user?.username || user?.tg_username || user?.tgUsername
  const name = user?.name || user?.first_name || user?.firstName
  const avatarUrl = user?.avatar || user?.avatar_url || user?.photo_url
  const blocked =
    Boolean(user?.blocked) ||
    user?.status === "blocked" ||
    user?.state === "blocked"

  return {
    id: user?.id || user?.user_id,
    telegramId: telegramId ? String(telegramId) : undefined,
    username,
    name,
    firstName: user?.first_name || user?.firstName,
    avatarUrl,
    blocked,
    wallet: user?.wallet,
  }
}

function deriveBalance(payload: any, user: any) {
  const wallet =
    payload?.wallet ||
    user?.wallet ||
    payload?.data?.wallet ||
    (typeof user?.balance === "number"
      ? { coins_cash: user.balance }
      : undefined)

  const directBalance =
    payload?.balance ??
    user?.balance ??
    wallet?.balance ??
    wallet?.coins ??
    wallet?.coins_total

  const toNumber = (value: any) => {
    const num = Number(value)
    return Number.isFinite(num) ? num : 0
  }

  if (typeof directBalance !== "undefined") {
    return toNumber(directBalance)
  }

  const cash = toNumber(wallet?.coins_cash ?? wallet?.coinsCash)
  const bonus = toNumber(wallet?.coins_bonus ?? wallet?.coinsBonus)

  if (cash || bonus) {
    return cash + bonus
  }

  return 0
}
