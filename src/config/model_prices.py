# Prices are in US dollars, per 1,000,000 (1 million) tokens.
# These are EXAMPLE prices for now - change the numbers to the real ones later.
# When a model price changes, just edit the number here.
MODEL_PRICES = {
    "gpt-4o":      {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# If a model_name is not in the list, we use this (0 cost) so the app never crashes.
DEFAULT_PRICE = {"input": 0.0, "output": 0.0}


def get_model_price(model_name: str) -> dict:
    """Give a model name, get back its {'input': ..., 'output': ...} price."""
    return MODEL_PRICES.get(model_name, DEFAULT_PRICE)
