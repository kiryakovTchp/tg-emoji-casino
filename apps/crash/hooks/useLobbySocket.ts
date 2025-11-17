import { crashBalanceFromPayload, resolveBalanceValue } from '@/lib/crash';
import { useStore } from '@/lib/store';
import { useCallback, useEffect, useRef, useState } from 'react';

export interface LobbyEvent {
  type: string;
  [key: string]: any;
}

export interface ChatMessage {
  userId: string;
  username: string;
  avatarUrl?: string;
  message: string;
  createdAt: number;
}

const DEFAULT_WS_URL = "wss://crash.gnezdoai.ru/ws"

interface UseLobbySocketParams {
  initData?: string
  token?: string | null
}

export function useLobbySocket({ initData, token }: UseLobbySocketParams) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [lobbyEvents, setLobbyEvents] = useState<LobbyEvent[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [sessionHistory, setSessionHistory] = useState<Array<{ multiplier: number; timestamp: number }>>([]);
  const [error, setError] = useState<string | null>(null);
  const setBalance = useStore((state) => state.setBalance);

  const normalizeType = (value: any) => {
    if (!value && value !== 0) return "";
    return String(value).trim().toLowerCase().replace(/[:\s]+/g, "-");
  };

  const updateBalanceFromPayload = (payload: any) => {
    if (typeof payload === "number" && Number.isFinite(payload)) {
      setBalance(payload);
      return;
    }
    const normalized = crashBalanceFromPayload(payload);
    const total = resolveBalanceValue(normalized);
    if (typeof total === "number") {
      setBalance(total);
    }
  };

  useEffect(() => {
    if (!initData && !token) return;
    // Закрываем старый ws если был
    if (wsRef.current) {
      wsRef.current.close();
    }
    const targetUrl =
      process.env.NEXT_PUBLIC_WS_URL || DEFAULT_WS_URL;
    const ws = new WebSocket(targetUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      const payload: Record<string, any> = { type: "auth" }
      if (token) {
        payload.token = token
      }
      if (initData) {
        payload.initData = initData
      }
      ws.send(JSON.stringify(payload));
    };

    ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data);
        const normalizedType = normalizeType(raw.type);
        const data = { ...raw, type: normalizedType, rawType: raw.type };

        if (normalizedType === 'auth-success' || normalizedType === 'auth:success') {
          setUser(data.user);
          setConnected(true);
          setError(null);
          updateBalanceFromPayload(data.balance ?? data.user?.balance ?? data.wallet);
          return;
        }

        if (normalizedType === 'session-history' || normalizedType === 'game-history') {
          setSessionHistory(data.history || []);
          return;
        }

        if (normalizedType === 'chat-message') {
          setChatMessages((prev) => [...prev.slice(-99), data]);
          return;
        }

        if (data.error) {
          setError(data.error);
          return;
        }

        if (
          normalizedType === 'balance-update' ||
          normalizedType === 'balance-updated' ||
          normalizedType === 'bet-accepted' ||
          normalizedType === 'cashout-processed'
        ) {
          updateBalanceFromPayload(
            data.balance ??
              data.wallet ??
              data.user?.balance ??
              data.data?.balance
          );
        }

        setLobbyEvents((prev) => [...prev.slice(-99), data]);
      } catch (e) {
        setError('Ошибка парсинга сообщения');
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setUser(null);
    };

    ws.onerror = (e) => {
      setConnected(false);
      setError('WebSocket error');
    };

    return () => {
      ws.close();
    };
  }, [initData, token]);

  // Отправка сообщения в чат
  const sendChat = useCallback((message: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'chat-message', message }));
  }, []);

  // Отправка ставки
  const sendBet = useCallback((bet: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'bet', bet }));
  }, []);

  // Отправка cashout
  const sendCashout = useCallback((betAmount: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'cashout', betAmount }));
  }, []);

  // Прочие события (старт, краш и т.д.)
  const sendGameEvent = useCallback((event: LobbyEvent) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify(event));
  }, []);

  return {
    connected,
    error,
    user,
    lobbyEvents,
    chatMessages,
    sessionHistory,
    sendChat,
    sendBet,
    sendCashout,
    sendGameEvent,
  };
} 
