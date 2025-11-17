'use client';

import { useLobbySocket } from '@/hooks/useLobbySocket';
import { fetchCrashState, postCrashBet, postCrashCashout, resolveBalanceValue, CrashStateSnapshot, CrashActionResponse } from '@/lib/crash';
import { useStore } from '@/lib/store';
import { init, retrieveRawInitData } from '@telegram-apps/sdk';
import { useEffect, useRef, useState } from 'react';
import CrashBetControls from './CrashBetControls';
import GameHistory from './GameHistory';
import PhaserGame from './PhaserGame';
import SessionHistory from './SessionHistory';
import TopRecords from './TopRecords';

export default function CrashGameArea() {
  const [phase, setPhase] = useState<'betting' | 'flying' | 'crashed'>('betting');
  const [startTime, setStartTime] = useState<number>(0);
  const [crashPoint, setCrashPoint] = useState<number>(2);
  const [crashTime, setCrashTime] = useState<number>(20000); // Добавляем crashTime
  const [duration, setDuration] = useState<number>(10000);
  const [betEndTime, setBetEndTime] = useState<number>(0);
  const [seed, setSeed] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>("");
  const [userBet, setUserBet] = useState<number | null>(null);
  const [userCashout, setUserCashout] = useState<number | null>(null);
  const [userBetAmount, setUserBetAmount] = useState<number>(0); // Текущая ставка пользователя
  const [initData, setInitData] = useState<string>("");
  const [isProcessingBet, setIsProcessingBet] = useState(false);
  const betTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Новый state для размеров игры
  const [gameSize, setGameSize] = useState({ width: 800, height: 450 });

  useEffect(() => {
    function updateSize() {
      const isMobile = window.innerWidth < 768;
      const maxWidth = isMobile ? window.innerWidth - 32 : 1200;
      const width = Math.max(320, Math.min(maxWidth, window.innerWidth - 32));
      const height = Math.round(width * 9 / 16); // 16:9
      setGameSize({ width, height });
    }
    if (typeof window !== 'undefined') {
      updateSize();
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }
  }, []);

  const { balance, setBalance, authToken, apiBaseUrl } = useStore();

  // Получаем initData для WebSocket авторизации
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    try {
      init();
      const initDataRaw = retrieveRawInitData();
      console.log('[CrashGameArea] initDataRaw:', initDataRaw ? 'present' : 'missing');
      
      if (initDataRaw) {
        setInitData(initDataRaw);
      } else {
        console.warn('[CrashGameArea] Нет initDataRaw — не в Telegram WebView?');
      }
    } catch (error) {
      console.error('[CrashGameArea] Ошибка получения initData:', error);
    }
  }, []);

  const { connected, user: wsUser, lobbyEvents } = useLobbySocket({ initData, token: authToken });

  // Логируем состояние подключения и initData
  useEffect(() => {
    console.log('[CrashGameArea] WebSocket connected:', connected);
    console.log('[CrashGameArea] initData length:', initData.length);
    console.log('[CrashGameArea] User:', wsUser);
  }, [connected, initData, wsUser]);

  // Cleanup timeout при размонтировании
  useEffect(() => {
    return () => {
      if (betTimeoutRef.current) {
        clearTimeout(betTimeoutRef.current);
      }
    };
  }, []);

  // Очистка при размонтировании компонента
  useEffect(() => {
    return () => {
      // Сбрасываем состояние игры при размонтировании
      setPhase('betting');
      setUserBet(null);
      setUserCashout(null);
      setUserBetAmount(0);
      setIsProcessingBet(false);
    };
  }, []);

  const applySnapshot = (snapshot?: CrashStateSnapshot | CrashActionResponse) => {
    if (!snapshot) return;
    if (snapshot.session) {
      const session = snapshot.session;
      if (session.phase) {
        setPhase(session.phase);
      }
      if (typeof session.crashPoint === 'number') {
        setCrashPoint(session.crashPoint);
      }
      if (typeof session.crashTime === 'number') {
        setCrashTime(session.crashTime);
      }
      if (typeof session.duration === 'number') {
        setDuration(session.duration);
      }
      if (session.startTime) {
        setStartTime(session.startTime);
      }
      if (session.betEndTime) {
        setBetEndTime(session.betEndTime);
      }
      if (session.seed) {
        setSeed(session.seed);
      }
      if (session.id) {
        setSessionId(session.id);
      }
    }

    if (snapshot.user) {
      const userState = snapshot.user;
      if (typeof userState.betAmount === 'number') {
        setUserBet(userState.betAmount);
        setUserBetAmount(userState.betAmount);
      } else {
        setUserBet(null);
        setUserBetAmount(0);
      }
      if (typeof userState.cashoutMultiplier === 'number') {
        setUserCashout(userState.cashoutMultiplier);
      } else if (userState.cashoutMultiplier === null) {
        setUserCashout(null);
      }
      if (typeof userState.balance === 'number') {
        setBalance(userState.balance);
      }
    }

    const balanceValue = resolveBalanceValue(snapshot.balance);
    if (typeof balanceValue === 'number') {
      setBalance(balanceValue);
    }
  };

  // Первичная загрузка состояния через REST
  useEffect(() => {
    if (!authToken) return;
    let cancelled = false;

    const syncState = async () => {
      try {
        const snapshot = await fetchCrashState(authToken, apiBaseUrl);
        if (!cancelled) {
          applySnapshot(snapshot);
        }
      } catch (error) {
        console.error('Crash state sync error:', error);
      }
    };

    syncState();

    return () => {
      cancelled = true;
    };
  }, [authToken, apiBaseUrl]);

  // Слушаем события от WebSocket
  useEffect(() => {
    // Обрабатываем только последние события, избегая дублирования
    const lastEvent = lobbyEvents[lobbyEvents.length - 1];
    if (!lastEvent) return;
    
    console.log('lobbyEvent', lastEvent);
    
    // Если sessionId изменился (новая игра) — всегда сбрасываем всё
    if (lastEvent.type === 'game-start' && lastEvent.sessionId && lastEvent.sessionId !== sessionId) {
      setPhase('betting');
      setCrashPoint(1.0);
      setCrashTime(20000); // Сброс crashTime
      setStartTime(lastEvent.startTime || 0);
      setDuration(lastEvent.duration || 20000);
      setBetEndTime(lastEvent.betEndTime || 0);
      setSeed(String(lastEvent.seed ?? ''));
      setSessionId(lastEvent.sessionId);
      setUserBet(null);
      setUserCashout(null);
      setUserBetAmount(0);
      return;
    }
    
    // Используем sessionId для предотвращения обработки старых событий
    if (lastEvent.sessionId && lastEvent.sessionId !== sessionId && sessionId !== '') {
      console.log('Skipping old event for session:', lastEvent.sessionId, 'current:', sessionId);
      return;
    }
    
    if (lastEvent.type === 'game-sync' || lastEvent.type === 'sync' || lastEvent.type === 'game-state') {
      setPhase(lastEvent.phase);
      setCrashPoint(lastEvent.crashPoint);
      setCrashTime(lastEvent.crashTime || 20000);
      setStartTime(lastEvent.startTime);
      setDuration(lastEvent.duration);
      setBetEndTime(lastEvent.betEndTime);
      setSeed(String(lastEvent.seed ?? ''));
      setSessionId(lastEvent.sessionId || '');
      // Сбрасываем ставки при синхронизации
      setUserBet(null);
      setUserCashout(null);
    } else if (lastEvent.type === 'game-start') {
      setPhase('betting');
      setCrashPoint(lastEvent.crashPoint);
      setCrashTime(20000); // По умолчанию для betting
      setStartTime(lastEvent.startTime);
      setDuration(lastEvent.duration);
      setBetEndTime(lastEvent.betEndTime);
      setSeed(String(lastEvent.seed ?? ''));
      setSessionId(lastEvent.sessionId || '');
      // Сбрасываем ставки при новой игре
      setUserBet(null);
      setUserCashout(null);
      setUserBetAmount(0);
    } else if (lastEvent.type === 'game-flying') {
      setPhase('flying');
      setCrashPoint(lastEvent.crashPoint);
      setCrashTime(lastEvent.crashTime || 20000); // Получаем crashTime от сервера
      setStartTime(lastEvent.startTime);
      setDuration(lastEvent.duration);
      setSeed(String(lastEvent.seed ?? ''));
      setSessionId(lastEvent.sessionId || '');
    } else if (lastEvent.type === 'game-crash') {
      setPhase('crashed');
      setCrashPoint(lastEvent.crashPoint);
      setCrashTime(lastEvent.crashTime || 20000);
      setStartTime(lastEvent.startTime);
      setDuration(lastEvent.duration);
      setSeed(String(lastEvent.seed ?? ''));
      setSessionId(lastEvent.sessionId || '');
      // Сбрасываем ставки при краше
      setUserBet(null);
      setUserCashout(null);
      setUserBetAmount(0);
    } else if (lastEvent.type === 'balance-update' || lastEvent.type === 'balance-updated') {
      if (typeof lastEvent.balance === 'number') {
        setBalance(lastEvent.balance);
      }
    } else if ((lastEvent.type === 'bet' || lastEvent.type === 'bet-accepted') && lastEvent.userId === wsUser?.id) {
      // Подтверждение нашей ставки - устанавливаем сумму ставки (не накапливаем)
      const betValue = typeof lastEvent.bet === 'number' ? lastEvent.bet : lastEvent.amount;
      if (typeof betValue === 'number') {
        setUserBet(betValue);
        setUserBetAmount(betValue);
      }
      // Сбрасываем состояние обработки
      setIsProcessingBet(false);
      if (betTimeoutRef.current) {
        clearTimeout(betTimeoutRef.current);
      }
    } else if ((lastEvent.type === 'cashout' || lastEvent.type === 'cashout-processed') && lastEvent.userId === wsUser?.id) {
      // Подтверждение нашего вывода
      const multiplier = typeof lastEvent.multiplier === 'number' ? lastEvent.multiplier : lastEvent.cashout;
      if (typeof multiplier === 'number') {
        setUserCashout(multiplier);
      }
      // Сбрасываем состояние обработки
      setIsProcessingBet(false);
      if (betTimeoutRef.current) {
        clearTimeout(betTimeoutRef.current);
      }
    }
  }, [lobbyEvents, setBalance, wsUser?.id, sessionId]);

  const handlePlaceBet = (amount: number) => {
    if (!authToken) {
      alert('Авторизация не выполнена. Обновите Mini App.');
      return;
    }
    if (phase !== 'betting' || balance < amount || isProcessingBet || !connected) {
      console.log('Bet blocked:', { phase, balance, amount, isProcessingBet, connected });
      return;
    }
    const place = async () => {
      try {
        setIsProcessingBet(true);
        const response = await postCrashBet({ amount, sessionId }, authToken, apiBaseUrl);
        applySnapshot(response);
        const confirmedAmount = response.bet?.amount ?? amount;
        setUserBet(confirmedAmount || amount);
        setUserBetAmount(confirmedAmount || amount);
      } catch (error) {
        console.error('Crash bet error:', error);
        alert('Не удалось сделать ставку. Попробуйте ещё раз.');
      } finally {
        setIsProcessingBet(false);
      }
    };
    place();
  };

  const handleCashout = (currentMultiplier: number) => {
    if (!authToken) {
      alert('Авторизация не выполнена. Обновите Mini App.');
      return;
    }
    if (phase !== 'flying' || userBetAmount === 0 || userCashout || isProcessingBet || !connected) return;
    
    const cashout = async () => {
      try {
        setIsProcessingBet(true);
        const response = await postCrashCashout({ sessionId }, authToken, apiBaseUrl);
        applySnapshot(response);
        const multiplier =
          response.cashout?.multiplier ??
          response.user?.cashoutMultiplier ??
          currentMultiplier;
        setUserCashout(multiplier);
      } catch (error) {
        console.error('Crash cashout error:', error);
        alert('Не удалось выполнить кэшаут. Попробуйте ещё раз.');
      } finally {
        setIsProcessingBet(false);
      }
    };

    cashout();
  };

  // Вычисляем текущий множитель для CrashBetControls
  let currentMultiplier = 1.0;
  if (phase === 'flying') {
    const elapsed = Math.max(0, Date.now() - startTime);
    const timeProgress = elapsed / crashTime;
    
    if (timeProgress >= 1) {
      // Игра уже крашнулась
      currentMultiplier = crashPoint || 1.0;
    } else {
      // Экспоненциальный рост коэффициента
      currentMultiplier = Math.pow(Math.E, timeProgress * Math.log(crashTime / 1000));
    }
  } else if (phase === 'crashed') {
    // ВСЕГДА показываем crashPoint
    currentMultiplier = crashPoint;
  }

  // Только теперь — return 'Загрузка...'
  if (!connected || !wsUser) {
    return <div className='w-full flex flex-col items-center justify-center min-h-[300px] text-gray-400'>Загрузка...</div>;
  }

  return (
    <div className="w-full flex flex-col items-center px-2 sm:px-0">
      <div className="w-full max-w-[1200px] mx-auto flex justify-center items-center" style={{ minHeight: gameSize.height }}>
        <div className="flex flex-col items-center w-full h-auto">
          <PhaserGame
            phase={phase}
            startTime={startTime}
            crashPoint={crashPoint}
            crashTime={crashTime}
            duration={duration}
            betEndTime={betEndTime}
            width={gameSize.width}
            height={gameSize.height}
            userBet={userBet}
            userCashout={userCashout}
            sessionId={sessionId}
          />

        </div>
      </div>
      <div className="max-w-[483px] w-full mx-auto mt-6">
        <CrashBetControls
          gameState={phase}
          currentMultiplier={currentMultiplier}
          onPlaceBet={handlePlaceBet}
          onCashout={() => handleCashout(currentMultiplier)}
          userBet={userBetAmount > 0 ? userBetAmount : null}
          userCashout={userCashout}
          balance={balance}
          connected={connected}
        />
      </div>
      {/* История игр */}
      <div className="max-w-[483px] w-full mx-auto mt-6">
        <GameHistory userId={wsUser?.telegramId} />
      </div>
      
      {/* История коэффициентов */}
      <div className="max-w-[483px] w-full mx-auto mt-6">
        <SessionHistory />
      </div>
      
      {/* Топ выигрышей */}
      <div className="max-w-[483px] w-full mx-auto mt-6">
        <TopRecords />
      </div>
      
      {/* Seed в самом низу */}
      {seed && (
        <div className="max-w-[483px] w-full mx-auto mt-4 p-2 bg-gray-800/30 rounded-lg text-center">
          <p className="text-gray-400 text-xs">Seed: #{seed}</p>
          {phase === 'crashed' && crashPoint && (
            <p className="text-gray-400 text-xs">Crash: {crashPoint.toFixed(4)}x</p>
          )}
        </div>
      )}

    </div>
  );
} 
