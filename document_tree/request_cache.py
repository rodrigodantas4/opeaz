"""Request-scoped caches for tree service queries."""


def get_cached_shares(request, entity, fetch_fn):
    if request is None:
        return fetch_fn()

    cache = getattr(request, '_tree_shares_cache', None)
    if cache is None:
        cache = {}
        request._tree_shares_cache = cache

    key = (entity.__class__.__name__, entity.pk)
    if key not in cache:
        cache[key] = fetch_fn()
    return cache[key]
