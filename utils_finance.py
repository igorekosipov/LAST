def calculate_shift(hours: float, rate: float, revenue: float, percent: float) -> float:
    """
    Рассчитывает зарплату за смену БЕЗ чаевых.
    Итого ЗП = часы × ставка + процент от выручки
    """
    hourly_pay = hours * rate
    revenue_share = revenue * percent / 100
    total = hourly_pay + revenue_share
    return round(total, 2)
