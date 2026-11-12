"""Pricing implementation, versioned independently in the sandbox."""


def price_total(prices, items, customer_id):
    return round(sum(prices[i.sku] * i.qty for i in items), 2)
