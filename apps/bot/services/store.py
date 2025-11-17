from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ShopPackage:
    id: str
    title: str
    description: str
    coins: int
    price_xtr: int
    bonus_coins: int = 0

    @property
    def payload(self) -> str:
        return f"pkg:{self.id}"


SHOP_PACKAGES: tuple[ShopPackage, ...] = (
    ShopPackage(
        id="mini",
        title="Mini Pack",
        description="2 000 коинов + 200 бонусов",
        coins=2_000,
        price_xtr=1_800,
        bonus_coins=200,
    ),
    ShopPackage(
        id="pro",
        title="Pro Pack",
        description="7 000 коинов + 1 000 бонусов",
        coins=7_000,
        price_xtr=4_800,
        bonus_coins=1_000,
    ),
)


def list_packages() -> Iterable[ShopPackage]:
    return SHOP_PACKAGES


def get_package(package_id: str) -> ShopPackage | None:
    return next((pkg for pkg in SHOP_PACKAGES if pkg.id == package_id), None)


def get_package_by_payload(payload: str) -> ShopPackage | None:
    prefix = "pkg:"
    if not payload.startswith(prefix):
        return None
    return get_package(payload[len(prefix) :])
