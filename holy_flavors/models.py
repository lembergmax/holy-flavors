from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


CATEGORIES = ("Energy", "Hydration", "Iced Tea", "Milkshake", "Syrup")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class ProductVariant:
    id: int
    title: str
    price_cents: int
    available: bool
    image_url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductVariant:
        return cls(
            id=int(data["id"]),
            title=str(data["title"]),
            price_cents=int(data["price_cents"]),
            available=bool(data["available"]),
            image_url=str(data.get("image_url", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Flavor:
    source_key: str
    name: str
    category: str
    description: str
    product_url: str
    image_url: str
    variants: tuple[ProductVariant, ...]
    archived: bool = False

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"Unknown category: {self.category}")
        if not self.source_key or not self.name:
            raise ValueError("source_key and name must not be empty")

    @property
    def available(self) -> bool:
        return not self.archived and any(variant.available for variant in self.variants)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Flavor:
        return cls(
            source_key=str(data["source_key"]),
            name=str(data["name"]),
            category=str(data["category"]),
            description=str(data.get("description", "")),
            product_url=str(data.get("product_url", "")),
            image_url=str(data.get("image_url", "")),
            variants=tuple(
                ProductVariant.from_dict(item) for item in data.get("variants", [])
            ),
            archived=bool(data.get("archived", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["variants"] = [variant.to_dict() for variant in self.variants]
        return result


@dataclass(slots=True)
class UserFlavorState:
    tried: bool = False
    rating: float | None = None
    note: str = ""
    wishlist: bool = False
    selected_variant_id: int | None = None
    quantity: int = 1

    def __post_init__(self) -> None:
        if self.rating is not None:
            doubled = float(self.rating) * 2
            if not 0.5 <= self.rating <= 5.0 or not doubled.is_integer():
                raise ValueError("Ratings must be between 0.5 and 5 in half steps")
        if self.quantity < 1:
            raise ValueError("Quantity must be at least 1")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserFlavorState:
        rating_value = data.get("rating")
        variant_value = data.get("selected_variant_id")
        return cls(
            tried=bool(data.get("tried", False)),
            rating=float(rating_value) if rating_value is not None else None,
            note=str(data.get("note", "")),
            wishlist=bool(data.get("wishlist", False)),
            selected_variant_id=(
                int(variant_value) if variant_value is not None else None
            ),
            quantity=int(data.get("quantity", 1)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Catalog:
    flavors: tuple[Flavor, ...] = field(default_factory=tuple)
    fetched_at: str = ""

    @classmethod
    def empty(cls) -> Catalog:
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Catalog:
        return cls(
            flavors=tuple(Flavor.from_dict(item) for item in data.get("flavors", [])),
            fetched_at=str(data.get("fetched_at", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "fetched_at": self.fetched_at,
            "flavors": [flavor.to_dict() for flavor in self.flavors],
        }

    def by_key(self) -> dict[str, Flavor]:
        return {flavor.source_key: flavor for flavor in self.flavors}
