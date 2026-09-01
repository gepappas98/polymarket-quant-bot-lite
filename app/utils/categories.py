CATEGORIES = ("politics", "sports", "crypto", "other")
_CRYPTO = ("btc", "eth", "sol", "xrp", "bitcoin", "ethereum", "solana")
_POLITICS = ("election", "president", "presidential", "trump", "biden", "harris", "senate", "congress", "governor", "vote", "parliament", "minister", "party")
_SPORTS = ("nba", "nfl", "mlb", "nhl", "ufc", "soccer", "premier-league", "league", "cup", "match", "championship", "super-bowl", "world-series", "tennis", "f1", "-vs-")


def category_for_slug(slug: str) -> str:
    value = (slug or "").lower()
    tokens = value.replace("_", "-").split("-")
    if any(token in _CRYPTO for token in tokens) or "up-or-down" in value:
        return "crypto"
    if any(word in value for word in _POLITICS):
        return "politics"
    if any(word in value for word in _SPORTS):
        return "sports"
    return "other"
