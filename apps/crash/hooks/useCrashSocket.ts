import { useCallback, useEffect, useRef, useState } from 'react';
import { useStore } from '@/lib/store';
import { CrashStateSnapshot, resolveBalanceValue, crashBalanceFromPayload } from '@/lib/crash';

const DEFAULT_WS_URL = process.env.NEXT_PUBLIC_WS_URL || "wss://crash.gnezdoai.ru/ws";

interface UseCrashSocketParams {
    token?: string | null;
}

export interface CrashGameState {
    phase: 'betting' | 'flying' | 'crashed';
    startTime: number;
    betEndTime: number;
    crashTime: number;
    crashPoint: number | null;
    sessionId: string;
}

export function useCrashSocket({ token }: UseCrashSocketParams) {
    const wsRef = useRef<WebSocket | null>(null);
    const [connected, setConnected] = useState(false);
    const [gameState, setGameState] = useState<CrashGameState>({
        phase: 'betting',
        startTime: 0,
        betEndTime: 0,
        crashTime: 0,
        crashPoint: null,
        sessionId: '',
    });
    const [history, setHistory] = useState<any[]>([]);
    const [activeBet, setActiveBet] = useState<any>(null);
    const setBalance = useStore((state) => state.setBalance);

    const updateBalance = useCallback((payload: any) => {
        const normalized = crashBalanceFromPayload(payload);
        const total = resolveBalanceValue(normalized);
        if (typeof total === 'number') {
            setBalance(total);
        }
    }, [setBalance]);

    useEffect(() => {
        if (!token) return;

        if (wsRef.current) {
            wsRef.current.close();
        }

        // Construct WS URL (assuming /ws/crash endpoint based on backend code)
        // The backend router is @router.websocket("/ws/crash")
        // If DEFAULT_WS_URL is "wss://host/ws", we might need to adjust.
        // But let's assume the env var or default points to the base or we construct it.
        // Backend `apps/bot/ws/crash.py` is mounted.
        // If the main app mounts api at /api, maybe ws is at /ws/crash?
        // Let's try to use the same base but replace path if needed, or just append if base is root.
        // For now, I'll assume the default URL needs to be adjusted to point to /ws/crash
        // If DEFAULT_WS_URL is "wss://crash.gnezdoai.ru/ws", maybe it's just "wss://crash.gnezdoai.ru/ws/crash"?
        // Let's try to be smart.
        let url = DEFAULT_WS_URL;
        if (url.endsWith('/ws')) {
            url = url + '/crash';
        } else if (!url.endsWith('/crash')) {
            url = url.replace(/\/+$/, '') + '/ws/crash';
        }

        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            setConnected(true);
            ws.send(JSON.stringify({ type: 'auth', token }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                const type = data.type;

                if (type === 'auth-success') {
                    // Initial state might be sent here or separately?
                    // Backend sends: auth-success, sync, balance-update, session-history
                } else if (type === 'sync') {
                    setGameState({
                        phase: data.phase,
                        startTime: data.startTime,
                        betEndTime: data.betEndTime,
                        crashTime: data.crashTime,
                        crashPoint: data.crashPoint,
                        sessionId: data.id,
                    });
                } else if (type === 'balance-update') {
                    updateBalance(data);
                } else if (type === 'session-history') {
                    setHistory(data.history);
                } else if (type === 'game-start') {
                    setGameState(prev => ({
                        ...prev,
                        phase: 'betting',
                        sessionId: data.id,
                        startTime: data.startTime,
                        betEndTime: data.betEndTime,
                        crashTime: data.crashTime,
                        crashPoint: null,
                    }));
                    setActiveBet(null); // Reset bet on new round
                } else if (type === 'game-flying') {
                    setGameState(prev => ({
                        ...prev,
                        phase: 'flying',
                    }));
                } else if (type === 'game-crash') {
                    setGameState(prev => ({
                        ...prev,
                        phase: 'crashed',
                        crashPoint: data.crashPoint,
                    }));
                } else if (type === 'bet-accepted') {
                    setActiveBet(data.bet);
                } else if (type === 'cashout-processed') {
                    setActiveBet((prev: any) => prev ? { ...prev, status: 'cashed_out', ...data.cashout } : null);
                }

            } catch (e) {
                console.error("WS Parse error", e);
            }
        };

        ws.onclose = () => {
            setConnected(false);
        };

        return () => {
            ws.close();
        };
    }, [token, updateBalance]);

    const sendPing = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'ping' }));
        }
    }, []);

    // Keep alive
    useEffect(() => {
        const interval = setInterval(sendPing, 10000);
        return () => clearInterval(interval);
    }, [sendPing]);

    return {
        connected,
        gameState,
        history,
        activeBet,
    };
}
