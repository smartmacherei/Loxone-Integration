"""Entry-scoped one-shot event listeners with idempotent cleanup."""


def listen_once(hass, entry, event_type, listener):
    """Unsubscribe exactly once, whether the event fires or the entry unloads."""
    from homeassistant.core import callback

    unsubscribe = None

    @callback
    def cancel():
        nonlocal unsubscribe
        if unsubscribe is not None:
            remove, unsubscribe = unsubscribe, None
            remove()

    @callback
    def handle(event):
        if unsubscribe is None:
            return  # A queued event can run after unloading.
        cancel()
        hass.async_create_task(listener(event))

    unsubscribe = hass.bus.async_listen(event_type, handle)
    entry.async_on_unload(cancel)
