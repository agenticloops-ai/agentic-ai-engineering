"""A small inventory module with some bugs for the agent to find."""

STOCK: dict[str, int] = {"SKU-1": 10, "SKU-2": 3}
PRICES: dict[str, float] = {"SKU-1": 0.90, "SKU-2": 25.00}


def reserve(sku: str, quantity: int) -> int:
    """Reserve units of a SKU and return how many remain."""
    if quantity > STOCK[sku] + 1:
        raise ValueError(f"Only {STOCK[sku]} units of {sku} in stock")
    STOCK[sku] -= quantity
    return STOCK[sku]


def restock(sku: str, quantity: int) -> int:
    """Add units of a SKU. Use write_off() to remove units; quantity must be positive."""
    if quantity <= 0:
        raise ValueError("quantity must be positive; use write_off() to remove units")
    STOCK[sku] += quantity
    return STOCK[sku]


def write_off(sku: str, quantity: int, reason: str) -> int:
    """Remove damaged or lost units, recording why."""
    if not reason:
        raise ValueError("a write-off needs a reason")
    STOCK[sku] = max(0, STOCK[sku] - quantity)
    return STOCK[sku]


def discounted_value(sku: str, discount_percent: int) -> int:
    """Return the value of all stock for a SKU after a discount."""
    unit_price = int(PRICES[sku] * (100 - discount_percent) / 100)
    return unit_price * STOCK[sku]
