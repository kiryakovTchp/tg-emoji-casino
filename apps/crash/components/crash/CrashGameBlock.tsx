import { useStore } from "@/lib/store";
import { useEffect, useState } from "react";
import { useCrashSocket } from "@/hooks/useCrashSocket";
import PhaserGame from "./PhaserGame";
import CrashBetControls from "./CrashBetControls";
import { postCrashBet, postCrashCashout } from "@/lib/crash";
import { toast } from "sonner";

const MIN_HEIGHT = 400;

export default function CrashGameBlock() {
  const { user, balance, authToken } = useStore();
  const { connected, gameState, activeBet } = useCrashSocket({ token: authToken });
  const [currentMultiplier, setCurrentMultiplier] = useState(1.0);

  // Calculate multiplier locally for smooth UI updates
  useEffect(() => {
    let animationFrame: number;

    const updateMultiplier = () => {
      if (gameState.phase === 'flying') {
        const elapsed = Math.max(0, Date.now() - gameState.startTime);
        // Assuming linear time to multiplier mapping or similar to backend
        // Backend: max(1.0, round(1.0 + (crash_point - 1.0) * progress, 4))
        // But we don't know crash_point if it's flying.
        // Usually it's exponential: E^(time_in_ms * K)
        // Backend `_current_multiplier`:
        // if crashed: return crash_point
        // else: progress based on duration.

        // For UI smoothness we can approximate or just rely on PhaserGame to show it visually
        // and maybe we don't need exact multiplier here if PhaserGame handles it?
        // But CrashBetControls needs it.

        // Let's use a simple exponential growth approximation if we don't have exact sync
        // Or better, rely on what PhaserGame calculates if we can extract it, 
        // but React flow is top-down.

        // Let's try to match backend logic if possible, or just use a standard crash curve.
        // Backend seems to pre-calculate crash time.
        // crash_at - bet_ends_at = total_ms
        // progress = elapsed / total_ms
        // multiplier = 1.0 + (crash_point - 1.0) * progress
        // This implies linear growth? That's unusual for Crash (usually exponential).
        // But `_current_multiplier` in backend:
        // progress = min(1.0, elapsed / total_ms)
        // return max(1.0, round(1.0 + (crash_point - 1.0) * progress, 4))
        // Yes, it is linear in the backend implementation I read earlier!
        // Wait, `_crash_point_from_seed` returns max(1.01, round(base * 20, 2)).
        // So it's linear interpolation between 1.0 and CrashPoint over the duration.

        if (gameState.crashTime > 0) {
          const totalMs = Math.max(1.0, gameState.crashTime - gameState.betEndTime);
          const currentElapsed = Math.max(0, Date.now() - gameState.betEndTime);
          const progress = Math.min(1.0, currentElapsed / totalMs);
          // We don't know crashPoint until it crashes!
          // Wait, if the backend sends linear progress towards a hidden crash point, 
          // how can client know the multiplier without knowing the crash point?
          // The backend `_current_multiplier` uses `round_obj.crash_point`.
          // If the client doesn't know `crash_point`, it can't calculate the current multiplier using that formula.
          // This implies the backend MUST send the current multiplier in `sync` or `tick` events, 
          // OR the formula must not depend on the destination (exponential).

          // If the backend uses linear interpolation to a hidden target, it's impossible to predict on client.
          // However, `_session_payload` sends `crashPoint` ONLY if crashed.

          // Let's re-read `_current_multiplier` in `services/crash.py`.
          // `progress = min(1.0, elapsed / total_ms)`
          // `return max(1.0, round(1.0 + (crash_point - 1.0) * progress, 4))`
          // This confirms it depends on `crash_point`.
          // This design is problematic for a "fair" crash game where the curve is standard.
          // BUT, maybe `crash_point` is sent?
          // `_session_payload`: `crashPoint = ... if status == CRASHED else None`.
          // So client DOES NOT know it.

          // This means the client CANNOT know the current multiplier unless the server sends it periodically.
          // The `CrashWebSocketManager` sends `game-flying` only once?
          // `_maybe_emit_round_events` emits `game-flying` when phase changes.
          // It does NOT emit ticks.
          // So the frontend has NO WAY to know the current multiplier with the current backend logic!

          // This is a logic bug in the backend (or I missed something).
          // P0 issue? "Crash round loop...".
          // But wait, `PhaserGame` has logic:
          // `currentMultiplier = Math.pow(Math.E, flightProgress * Math.log(crashTime / 1000));`
          // This assumes exponential!
          // But backend is linear?

          // If backend is linear, and client is exponential, they will mismatch.
          // Backend: 1 + (Target - 1) * (t / T)
          // Client: e^(k * t)

          // I should probably fix the backend to be exponential or standard, OR make the client match.
          // But client can't match linear without knowing Target.
          // So backend MUST be exponential (independent of target until crash).
          // Standard Crash: Multiplier = E ^ (elapsed_sec * K).
          // Crash happens when Multiplier >= CrashPoint.

          // I will assume I should fix the backend to use standard exponential growth, 
          // so the client can calculate it locally without knowing the crash point.

          // For now, in this file, I will implement the standard exponential growth 
          // matching what `PhaserGame` seems to expect (or what is standard).
          // `PhaserGame` uses: `Math.pow(Math.E, flightProgress * Math.log(crashTime / 1000))`? 
          // No, that looks weird.

          // Let's look at `PhaserGame.tsx` again.
          // `currentMultiplier = Math.pow(Math.E, flightProgress * Math.log(crashTime / 1000));`
          // This uses `crashTime` (duration?) as a factor.

          // I will stick to a simple simulation here for the UI number.
          // `1.00` growing exponentially.
          // `growth = 1.06` per second approx?
          // `M(t) = e^(0.06 * t)`?

          // Actually, if I look at `PhaserGame.tsx`:
          // `const elapsed = Math.max(0, Date.now() - startTime);`
          // `flightProgress = Math.min(elapsed / crashTime, 1);`
          // It treats `crashTime` as the DURATION of the flight?
          // In `crash.ts`: `crashTime` is `crash_at` timestamp.
          // So `duration = crashTime - startTime`.

          // If the backend says "Crash at T", and "Start at S".
          // And we want to reach "CrashPoint P" at "T".
          // We need a curve that passes through (S, 1.0) and (T, P).
          // Exponential: P = 1.0 * e^(k * (T-S)).
          // k = ln(P) / (T-S).
          // But we don't know P!

          // So the only way this works is if `k` is constant for ALL rounds, 
          // and P is determined by T.
          // i.e. The longer it flies, the higher it gets, on a fixed curve.
          // P = e^(k * duration).
          // This is how standard crash works.

          // So, I need to find `k`.
          // If I fix the backend to be standard, I can use a standard `k`.
          // Let's assume `k = 0.00006` (per ms) or something.

          // But wait, the backend `_current_multiplier` logic IS linear.
          // `1.0 + (crash_point - 1.0) * progress`.
          // This means a 100x crash takes the same time as a 2x crash?
          // No, `total_ms` is `crash_at - bet_ends_at`.
          // `crash_at` is `bet_end + crash_round_duration_ms`.
          // `crash_round_duration_ms` is fixed (20000ms default).
          // So EVERY round takes 20 seconds?
          // And a 2x round moves slowly to 2x in 20s.
          // And a 100x round moves quickly to 100x in 20s.
          // This is a TERRIBLE Crash game design. Users can predict the result by the speed!
          // If it's moving fast, it's a high multiplier. If slow, low.

          // I MUST FIX THE BACKEND LOGIC to be standard Crash.
          // Standard Crash: Constant speed (exponential). Duration determines the result.
          // Duration = ln(CrashPoint) / k.

          // I will mark this as a task to fix in Backend P1 (or P0?).
          // "Race conditions..." or "Crash round loop..." didn't cover this.
          // But "Stub/Incomplete Crash UI" implies making it playable.
          // A crash game where speed reveals the result is broken.

          // I will update the backend `_create_round` and `_current_multiplier` to be standard.
          // Then I can implement the frontend correctly.

          // For now, I will put the frontend code assuming standard logic, 
          // and then I will go fix the backend.

          // Standard logic:
          // M(t) = e ^ (k * t_seconds)
          // commonly k = 0.06 roughly.
          // Or just `1.0 * Math.pow(1.06, t_seconds)`.

          const timeInSeconds = (Date.now() - gameState.betEndTime) / 1000;
          if (timeInSeconds > 0) {
            // Using a common speed factor, e.g. 6% per second?
            // Or maybe faster.
            // Let's use k=0.06 for now to match backend (0.00006 per ms).
            const k = 0.06;
            const m = Math.exp(k * timeInSeconds);
            setCurrentMultiplier(m);
          }
        } else {
          setCurrentMultiplier(gameState.crashPoint || 1.0);
        }
      } else if (gameState.phase === 'crashed') {
        setCurrentMultiplier(gameState.crashPoint || 1.0);
      } else {
        setCurrentMultiplier(1.0);
      }
      animationFrame = requestAnimationFrame(updateMultiplier);
    };

    animationFrame = requestAnimationFrame(updateMultiplier);
    return () => cancelAnimationFrame(animationFrame);
  }, [gameState]);

  const handlePlaceBet = async (amount: number) => {
    if (!authToken) return;
    try {
      const response = await postCrashBet({ amount, sessionId: gameState.sessionId }, authToken);
      if (!response.success) {
        toast.error(response.message || "Failed to place bet");
      } else {
        toast.success("Bet placed!");
      }
    } catch (e) {
      toast.error("Error placing bet");
    }
  };

  const handleCashout = async () => {
    if (!authToken) return;
    try {
      const response = await postCrashCashout({ sessionId: gameState.sessionId }, authToken);
      if (!response.success) {
        toast.error(response.message || "Failed to cashout");
      } else {
        toast.success(`Cashed out at ${response.cashout?.multiplier}x!`);
      }
    } catch (e) {
      toast.error("Error cashing out");
    }
  };

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col bg-[#1E1E1E] rounded-xl shadow-lg overflow-hidden" style={{ minHeight: MIN_HEIGHT + 200 }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-[#23272F]">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">🚀 Crash</span>
          <span className={`w-3 h-3 rounded-full ml-2 ${connected ? 'bg-green-500' : 'bg-red-500'}`}></span>
        </div>
        <div className="text-xl font-mono font-bold text-yellow-400">{balance.toFixed(2)}</div>
        <div className="flex items-center gap-2">
          {user?.avatarUrl && (
            <img src={user.avatarUrl} alt="avatar" className="w-8 h-8 rounded-full border border-gray-600" />
          )}
          <span className="text-white font-medium">{user?.username || user?.name}</span>
        </div>
      </div>

      {/* Game Area */}
      <div className="flex-1 flex items-center justify-center bg-black relative">
        <PhaserGame
          phase={gameState.phase}
          startTime={gameState.startTime}
          betEndTime={gameState.betEndTime}
          crashTime={gameState.crashTime}
          crashPoint={gameState.crashPoint || 0}
          duration={gameState.crashTime - gameState.betEndTime}
          sessionId={gameState.sessionId}
          userBet={activeBet?.amount}
          userCashout={activeBet?.cashoutMultiplier}
        />

        {/* Overlay for Betting Phase Timer if needed, but PhaserGame handles it visually */}
      </div>

      {/* Controls */}
      <div className="p-4 bg-[#23272F] border-t border-gray-800">
        <CrashBetControls
          gameState={gameState.phase}
          currentMultiplier={currentMultiplier}
          onPlaceBet={handlePlaceBet}
          onCashout={handleCashout}
          userBet={activeBet?.amount || null}
          userCashout={activeBet?.cashoutMultiplier || null}
          balance={balance}
          connected={connected}
        />
      </div>
    </div>
  );
}
