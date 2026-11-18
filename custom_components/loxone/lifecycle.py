"""Entry-scoped one-shot event listeners with idempotent cleanup."""
import asyncio
import logging
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


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


# entry_id -> token rejections in a row; outlives the reload it causes.
TOKEN_FAILURES = "loxone_token_failures"
TOKEN_RETRY_MAX = 300


def token_retry_delay(failures):
    """Seconds before the reload after ``failures`` token rejections in a row: 1, 2, 4 ... 300."""
    return min(2 ** (failures - 1), TOKEN_RETRY_MAX)


def token_accepted(hass, entry_id, api):
    """A connection that authenticated ends a series of token rejections."""
    failures = hass.data.get(TOKEN_FAILURES)
    if failures and entry_id in failures and api.authentication_state == "accepted":
        del failures[entry_id]


def listener_ended(hass, entry_id, task, reload, forget_token):
    """Every end of the WebSocket listener by an error reloads; the reload marks the connection loss.

    An unload cancels the task and an HA stop ends it regularly: no reload. A Miniserver that keeps
    rejecting the token while setup still works is retried with a growing delay, not every second.
    """
    from websockets.exceptions import ConnectionClosedOK

    from .pyloxone_api.exceptions import (LoxoneConnectionClosedOk, LoxoneConnectionError,
                                          LoxoneOutOfServiceException, LoxoneTokenError)
    if task.cancelled():
        _LOGGER.debug("Loxone WebSocket listener cancelled during cleanup")
        return
    error = task.exception()
    if error is None:
        return
    if isinstance(error, LoxoneTokenError):
        failures = hass.data.setdefault(TOKEN_FAILURES, {})
        failures[entry_id] = failures.get(entry_id, 0) + 1
        delay = token_retry_delay(failures[entry_id])
        _LOGGER.error("Loxone Miniserver rejected the token (%s time(s) in a row); next attempt in %s s, at %s",
                      failures[entry_id], delay, (datetime.now() + timedelta(seconds=delay)).strftime("%H:%M:%S"))
        forget_token()
        reload(delay)
        return
    if isinstance(error, (LoxoneOutOfServiceException, LoxoneConnectionError, LoxoneConnectionClosedOk,
                          ConnectionClosedOK)):
        _LOGGER.debug("Loxone %s received. Try to reloading Loxone integration.", type(error).__name__)
    else:
        _LOGGER.warning("Loxone WebSocket listener failed, reloading: %r", error)
    reload(1.0)


async def save_token_and_close(hass, entry, api):
    """HA stop: keep the token for the next start, then close the connection."""
    try:
        token = api.get_token_dict()
        if token.get("token"):
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,  # preserve existing data
                    "token": token["token"],
                    "hash_alg": token["hash_alg"],
                    "valid_until": token["valid_until"],
                },
            )
    finally:
        await api.close()
