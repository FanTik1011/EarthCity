def limit_for_zoom(zoom: int) -> int:
    z = max(1, min(18, zoom))
    if z <= 3:  return 200
    if z <= 5:  return 600
    if z <= 7:  return 1500
    if z <= 9:  return 3500
    if z <= 11: return 7000
    return 12000
