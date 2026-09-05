from __future__ import annotations

import hashlib
import html
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from holy_flavors.models import Catalog, Flavor, ProductVariant, utc_now_iso


SHOP_BASE_URL = "https://de.holy.com"
USER_AGENT = "HOLY-Flavors/1.0 (personal desktop catalog)"

COLLECTION_SPECS = (
    ("Energy", "holy-energy", "01 - Energy Bundle"),
    ("Hydration", "holy-hydration", "03 - Hydration Bundle"),
    ("Iced Tea", "holy-iced-tea", "02 - Iced Tea Bundle"),
    ("Milkshake", "milkshake", "32 - Milkshake Bundle"),
    ("Syrup", "syrup-launch", "43 - Syrup Bundle"),
)


class CatalogError(RuntimeError):
    """Raised when a complete, valid catalog cannot be fetched."""


class CatalogClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout_seconds: int = 25,
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._timeout_seconds = timeout_seconds

    @property
    def session(self) -> requests.Session:
        return self._session

    def fetch_catalog(self) -> Catalog:
        flavors: list[Flavor] = []
        for category, collection_handle, product_type in COLLECTION_SPECS:
            products = self._fetch_collection(collection_handle)
            category_flavors = parse_collection(category, product_type, products)
            if not category_flavors:
                raise CatalogError(
                    f"The {category} category did not contain any flavors."
                )
            flavors.extend(category_flavors)

        keys = [flavor.source_key for flavor in flavors]
        if len(keys) != len(set(keys)):
            raise CatalogError("The HOLY catalog contains duplicate flavor identifiers.")

        return Catalog(
            flavors=tuple(sorted(flavors, key=lambda item: (item.category, item.name))),
            fetched_at=utc_now_iso(),
        )

    def _fetch_collection(self, handle: str) -> list[dict[str, Any]]:
        url = f"{SHOP_BASE_URL}/collections/{handle}/products.json?limit=250"
        try:
            response = self._session.get(url, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CatalogError(
                f"The '{handle}' collection could not be loaded: {exc}"
            ) from exc

        products = payload.get("products")
        if not isinstance(products, list):
            raise CatalogError(f"Invalid response for the '{handle}' collection.")
        return products


def parse_collection(
    category: str,
    expected_product_type: str,
    products: list[dict[str, Any]],
) -> list[Flavor]:
    matching_products = [
        product
        for product in products
        if product.get("product_type") == expected_product_type
    ]
    if category == "Syrup":
        return _parse_syrup_products(matching_products)
    return [_parse_powder_product(category, product) for product in matching_products]


def _parse_powder_product(category: str, product: dict[str, Any]) -> Flavor:
    handle = str(product["handle"])
    return Flavor(
        source_key=f"{_slug(category)}:{handle}",
        name=str(product["title"]).strip(),
        category=category,
        description=_plain_text(str(product.get("body_html") or "")),
        product_url=f"{SHOP_BASE_URL}/products/{handle}",
        image_url=_product_image_url(product),
        variants=tuple(
            _parse_variant(item, product) for item in product.get("variants", [])
        ),
    )


def _parse_syrup_products(products: list[dict[str, Any]]) -> list[Flavor]:
    flavors: list[Flavor] = []
    for product in products:
        handle = str(product["handle"])
        for variant_data in product.get("variants", []):
            variant = _parse_variant(variant_data, product)
            name = variant.title.strip()
            flavors.append(
                Flavor(
                    source_key=f"syrup:{handle}:{_slug(name)}",
                    name=name,
                    category="Syrup",
                    description="A 3-pack of syrup pods for the HOLY Syrup Bottle.",
                    product_url=f"{SHOP_BASE_URL}/products/{handle}?variant={variant.id}",
                    image_url=_variant_image_url(variant_data, product),
                    variants=(variant,),
                )
            )
    return flavors


def _parse_variant(
    data: dict[str, Any],
    product: dict[str, Any],
) -> ProductVariant:
    raw_price = data.get("price", "0")
    try:
        price_cents = int(Decimal(str(raw_price)) * 100)
    except (InvalidOperation, ValueError) as exc:
        raise CatalogError(f"Invalid variant price: {raw_price}") from exc
    return ProductVariant(
        id=int(data["id"]),
        title=str(data.get("title") or "Standard"),
        price_cents=price_cents,
        available=bool(data.get("available", False)),
        image_url=_variant_image_url(data, product),
    )


def merge_catalog(previous: Catalog, current: Catalog) -> Catalog:
    current_by_key = current.by_key()
    merged = list(current.flavors)
    for old_flavor in previous.flavors:
        if old_flavor.source_key not in current_by_key:
            merged.append(replace(old_flavor, archived=True))
    return Catalog(
        flavors=tuple(sorted(merged, key=lambda item: (item.category, item.name))),
        fetched_at=current.fetched_at,
    )


def image_cache_path(images_dir: Path, flavor: Flavor) -> Path:
    digest = hashlib.sha1(flavor.source_key.encode("utf-8")).hexdigest()[:20]
    return images_dir / f"{digest}.png"


def variant_image_cache_path(
    images_dir: Path,
    variant: ProductVariant,
) -> Path:
    digest = hashlib.sha1(f"variant:{variant.id}".encode("utf-8")).hexdigest()[:20]
    return images_dir / f"{digest}.png"


def cache_catalog_images(
    catalog: Catalog,
    images_dir: Path,
    session: requests.Session,
    timeout_seconds: int = 15,
) -> tuple[int, int]:
    images_dir.mkdir(parents=True, exist_ok=True)
    completed = 0
    failed = 0
    for destination, image_url in _catalog_image_targets(catalog, images_dir):
        if destination.exists() or not image_url:
            continue
        try:
            response = session.get(image_url, timeout=timeout_seconds)
            response.raise_for_status()
            image = QImage.fromData(response.content)
            if image.isNull():
                raise ValueError("The image format is not supported")
            scaled = image.scaled(
                520,
                520,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not scaled.save(str(destination), "PNG"):
                raise OSError(f"Image could not be saved: {destination}")
            completed += 1
        except (requests.RequestException, OSError, ValueError):
            failed += 1
    return completed, failed


def _catalog_image_targets(
    catalog: Catalog,
    images_dir: Path,
) -> list[tuple[Path, str]]:
    targets: list[tuple[Path, str]] = []
    for flavor in catalog.flavors:
        targets.append((image_cache_path(images_dir, flavor), flavor.image_url))
        for variant in flavor.variants:
            if variant.image_url and variant.image_url != flavor.image_url:
                targets.append(
                    (variant_image_cache_path(images_dir, variant), variant.image_url)
                )
    return targets


def _product_image_url(product: dict[str, Any]) -> str:
    image = product.get("image")
    if isinstance(image, dict) and image.get("src"):
        return str(image["src"])
    images = product.get("images", [])
    if images and isinstance(images[0], dict):
        return str(images[0].get("src") or "")
    return ""


def _variant_image_url(
    variant: dict[str, Any],
    product: dict[str, Any],
) -> str:
    featured = variant.get("featured_image")
    if isinstance(featured, dict) and featured.get("src"):
        return str(featured["src"])
    image_id = variant.get("image_id")
    if image_id is not None:
        for image in product.get("images", []):
            if image.get("id") == image_id and image.get("src"):
                return str(image["src"])
    return _product_image_url(product)


def _plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split())


def _slug(value: str) -> str:
    normalized = value.lower().replace("&", " und ")
    normalized = (
        normalized.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
