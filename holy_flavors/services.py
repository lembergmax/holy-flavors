from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from urllib.parse import urlencode

from holy_flavors.models import Catalog, Flavor, ProductVariant, UserFlavorState


PACKAGE_SIZES = (
    "All sizes",
    "Sample · 1 serving",
    "Box · 10 servings",
    "Tub · 50 servings",
    "Syrup · 3-pack",
)


@dataclass(frozen=True, slots=True)
class FilterOptions:
    search_text: str = ""
    categories: frozenset[str] = frozenset()
    statuses: frozenset[str] = frozenset()
    package_size: str = "All sizes"
    sort_by: str = "Category & name"


@dataclass(frozen=True, slots=True)
class ProgressStats:
    tried: int
    total: int
    average_rating: float | None
    by_category: dict[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class CartIssue:
    flavor_name: str
    message: str


def get_state(
    states: dict[str, UserFlavorState],
    source_key: str,
) -> UserFlavorState:
    if source_key not in states:
        states[source_key] = UserFlavorState()
    return states[source_key]


def filter_and_sort_flavors(
    catalog: Catalog,
    states: dict[str, UserFlavorState],
    options: FilterOptions,
) -> list[Flavor]:
    query = options.search_text.casefold().strip()
    result: list[Flavor] = []
    for flavor in catalog.flavors:
        state = states.get(flavor.source_key, UserFlavorState())
        searchable = f"{flavor.name} {flavor.category} {flavor.description} {state.note}"
        if query and query not in searchable.casefold():
            continue
        if options.categories and flavor.category not in options.categories:
            continue
        if not _matches_statuses(flavor, state, options.statuses):
            continue
        if (
            options.package_size != "All sizes"
            and matching_available_variant(flavor, options.package_size) is None
        ):
            continue
        result.append(flavor)

    sorters = {
        "Name": lambda item: (item.name.casefold(), item.category),
        "Category & name": lambda item: (item.category, item.name.casefold()),
        "Rating": lambda item: (
            -(states.get(item.source_key, UserFlavorState()).rating or 0),
            item.name.casefold(),
        ),
        "Availability": lambda item: (
            item.archived,
            not item.available,
            item.name.casefold(),
        ),
        "Not tried yet": lambda item: (
            states.get(item.source_key, UserFlavorState()).tried,
            item.name.casefold(),
        ),
    }
    return sorted(result, key=sorters.get(options.sort_by, sorters["Category & name"]))


def matching_available_variant(
    flavor: Flavor,
    package_size: str,
) -> ProductVariant | None:
    if package_size == "All sizes":
        return next((variant for variant in flavor.variants if variant.available), None)
    return next(
        (
            variant
            for variant in flavor.variants
            if variant.available
            and _package_size_for_variant(flavor, variant.title) == package_size
        ),
        None,
    )


def apply_package_size_to_cart(
    catalog: Catalog,
    states: dict[str, UserFlavorState],
    package_size: str,
) -> int:
    changed = 0
    for flavor in catalog.flavors:
        state = states.get(flavor.source_key, UserFlavorState())
        if not state.wishlist:
            continue
        variant = matching_available_variant(flavor, package_size)
        if variant is None or state.selected_variant_id == variant.id:
            continue
        state.selected_variant_id = variant.id
        changed += 1
    return changed


def _package_size_for_variant(flavor: Flavor, variant_title: str) -> str | None:
    if flavor.category == "Syrup":
        return "Syrup · 3-pack"
    title = variant_title.casefold()
    if "50 portionen" in title:
        return "Tub · 50 servings"
    if "10 portionen" in title or "10er" in title:
        return "Box · 10 servings"
    if title.startswith("1 portion"):
        return "Sample · 1 serving"
    return None


def calculate_progress(
    catalog: Catalog,
    states: dict[str, UserFlavorState],
) -> ProgressStats:
    active = [flavor for flavor in catalog.flavors if not flavor.archived]
    tried_flavors = [
        flavor
        for flavor in active
        if states.get(flavor.source_key, UserFlavorState()).tried
    ]
    ratings = [
        state.rating
        for key, state in states.items()
        if key in {flavor.source_key for flavor in active} and state.rating is not None
    ]
    by_category: dict[str, tuple[int, int]] = {}
    for category in sorted({flavor.category for flavor in active}):
        category_flavors = [item for item in active if item.category == category]
        category_tried = sum(
            states.get(item.source_key, UserFlavorState()).tried
            for item in category_flavors
        )
        by_category[category] = (category_tried, len(category_flavors))
    return ProgressStats(
        tried=len(tried_flavors),
        total=len(active),
        average_rating=fmean(ratings) if ratings else None,
        by_category=by_category,
    )


def preview_import(
    current: dict[str, UserFlavorState],
    imported: dict[str, UserFlavorState],
) -> tuple[int, int, int]:
    new_count = 0
    changed_count = 0
    unchanged_count = 0
    for key, imported_state in imported.items():
        if key not in current:
            new_count += 1
        elif current[key] == imported_state:
            unchanged_count += 1
        else:
            changed_count += 1
    return new_count, changed_count, unchanged_count


def validate_cart(
    catalog: Catalog,
    states: dict[str, UserFlavorState],
) -> list[CartIssue]:
    issues: list[CartIssue] = []
    for flavor in catalog.flavors:
        state = states.get(flavor.source_key, UserFlavorState())
        if not state.wishlist:
            continue
        if flavor.archived:
            issues.append(CartIssue(flavor.name, "This flavor is archived."))
            continue
        selected = next(
            (
                variant
                for variant in flavor.variants
                if variant.id == state.selected_variant_id
            ),
            None,
        )
        if selected is None:
            issues.append(CartIssue(flavor.name, "Please choose a package size."))
        elif not selected.available:
            issues.append(CartIssue(flavor.name, "The selected variant is sold out."))
    return issues


def build_cart_url(
    catalog: Catalog,
    states: dict[str, UserFlavorState],
) -> str:
    issues = validate_cart(catalog, states)
    if issues:
        raise ValueError("The shopping list contains incomplete or invalid items.")
    items: list[tuple[int, int]] = []
    for flavor in sorted(catalog.flavors, key=lambda item: item.source_key):
        state = states.get(flavor.source_key, UserFlavorState())
        if state.wishlist and state.selected_variant_id is not None:
            items.append((state.selected_variant_id, state.quantity))
    if not items:
        raise ValueError("The shopping list is empty.")
    path = ",".join(f"{variant_id}:{quantity}" for variant_id, quantity in items)
    return f"https://de.holy.com/cart/{path}?{urlencode({'storefront': 'true'})}"


def _matches_statuses(
    flavor: Flavor,
    state: UserFlavorState,
    statuses: frozenset[str],
) -> bool:
    if not statuses:
        return not flavor.archived
    if flavor.archived and "Archived" not in statuses:
        return False
    return all(_matches_status(flavor, state, status) for status in statuses)


def _matches_status(
    flavor: Flavor,
    state: UserFlavorState,
    status: str,
) -> bool:
    match status:
        case "Tried":
            return state.tried
        case "Not tried yet":
            return not state.tried
        case "Shopping list":
            return state.wishlist
        case "Available":
            return not flavor.archived and flavor.available
        case "Sold out":
            return not flavor.archived and not flavor.available
        case "Archived":
            return flavor.archived
        case _:
            return False


def display_variant_title(title: str) -> str:
    """Translate common German Shopify variant labels for the English UI."""
    translated = title
    replacements = (
        ("Portionen", "servings"),
        ("Portion", "serving"),
        ("mit gratis Shaker", "with free shaker"),
        ("ohne Shaker", "without shaker"),
        ("3er-Box", "3-pack"),
        ("10er Probier-Box", "10-sample box"),
        ("Standardtitel", "Default title"),
    )
    for german, english in replacements:
        translated = translated.replace(german, english)
    return translated
