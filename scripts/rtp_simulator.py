from __future__ import annotations

import argparse

from apps.bot.core.slot_payouts import get_slot_payouts


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate RTP for slot payouts")
    parser.add_argument("--bet", type=int, default=100, help="Bet size in coins")
    parser.add_argument("--iterations", type=int, default=100_000, help="Number of spins")
    args = parser.parse_args()

    payouts = get_slot_payouts()
    rtp = payouts.simulate_rtp(bet=args.bet, iterations=args.iterations)
    print(f"Simulated RTP: {rtp:.4f}")


if __name__ == "__main__":
    main()
