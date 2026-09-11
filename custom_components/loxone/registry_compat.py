"""Compatibility with both mapping registries and HA entry collections."""


def registry_entries(items):
    # Do not probe .values: even attribute access triggers HA's deprecation.
    for entry in items:
        yield items[entry] if isinstance(entry, str) else entry


def registry_ids(items):
    return {entry.id for entry in registry_entries(items)}
