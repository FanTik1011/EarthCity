def compute_country_cost(area_km2: float, base: int, per_1000: int) -> int:
    return int(round(base + (area_km2 / 1000.0) * per_1000))
