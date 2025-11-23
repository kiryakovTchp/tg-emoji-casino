from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from apps.bot.infra.settings import get_settings


@dataclass(frozen=True)
class SlotOutcome:
    dice_value: int
    symbols: list[str]
    multiplier: float


class SlotPayouts:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[3]
        config_path = root / "configs" / "payouts.json"
        if not config_path.exists():
            raise FileNotFoundError(
                f"Slot payouts config is missing at {config_path}. Make sure configs/ is bundled with the deployment.",
            )
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._table: dict[int, SlotOutcome] = {
            int(entry["dice_value"]): SlotOutcome(
                dice_value=int(entry["dice_value"]),
                symbols=list(entry.get("symbols", [])),
                multiplier=float(entry.get("multiplier", 0.0)),
            )
            for entry in data
        }

    def outcome(self, dice_value: int) -> SlotOutcome:
        return self._table.get(dice_value, SlotOutcome(dice_value, ["-", "-", "-"], 0.0))

    def calc_payout(self, dice_value: int, bet: int) -> tuple[int, SlotOutcome]:
        outcome = self.outcome(dice_value)
        payout = int(bet * outcome.multiplier)
        return payout, outcome

    def simulate_rtp(self, bet: int, iterations: int = 100_000) -> float:
        samples = []
        for _ in range(iterations):
            dice_value = random.randint(1, 64)
            payout, _ = self.calc_payout(dice_value, bet)
            samples.append(payout / bet if bet else 0)
        return mean(samples) if samples else 0.0


_payouts = SlotPayouts()


def get_slot_payouts() -> SlotPayouts:
    return _payouts


def bonus_bet_limit(coins_bonus: int) -> int:
    settings = get_settings()
    dynamic_cap = int(coins_bonus * settings.bonus_bet_frac)
    return max(0, min(settings.max_bonus_bet_cap, dynamic_cap))
