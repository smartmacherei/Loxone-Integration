"""
Config Flow for Loxone (smartmacherei)

For more details about this component, please refer to the documentation at
https://github.com/smartmacherei/Loxone-Integration
"""

from typing import Any, Mapping, cast
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from yarl import URL
from homeassistant.const import (CONF_HOST, CONF_PASSWORD, CONF_PORT,
                                 CONF_USERNAME)
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler, SchemaConfigFlowHandler, SchemaFlowError,
    SchemaFlowFormStep)
from homeassistant.helpers.selector import (AreaSelector, BooleanSelector,
                                            NumberSelector,
                                            NumberSelectorConfig,
                                            NumberSelectorMode, TextSelector,
                                            TextSelectorConfig,
                                            TextSelectorType)

from .const import (CONF_AUTO_CONFIGURE_UDP, CONF_AUTO_DISCOVERY, CONF_LIGHTCONTROLLER_SUBCONTROLS_GEN,
                    CONF_SCENE_GEN, CONF_SCENE_GEN_DELAY, CONF_UDP_PORT,
                    DEFAULT_AUTO_DISCOVERY, DEFAULT_DELAY_SCENE, DEFAULT_IP,
                    DEFAULT_PORT, DEFAULT_UDP_PORT, DOMAIN)
from .area_mapping import CONF_ROOM_MAPPING


async def async_load_rooms(hass, options):
    """Read room metadata only; opening the wizard never provisions UDP."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    host, port = options[CONF_HOST], int(options[CONF_PORT])
    parsed = urlparse(host if "://" in host else f"//{host}")
    url = URL.build(scheme=parsed.scheme or ("https" if port == 443 else "http"),
                    host=parsed.hostname, port=parsed.port or port, path="/data/LoxAPP3.json")
    async with async_get_clientsession(hass).get(
        url, auth=aiohttp.BasicAuth(options[CONF_USERNAME], options[CONF_PASSWORD]),
        timeout=aiohttp.ClientTimeout(total=15),
    ) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
    rooms = data.get("rooms", {})
    if not isinstance(rooms, dict):
        raise ValueError("Invalid room list")
    return {uuid: item["name"] for uuid, item in rooms.items()
            if isinstance(uuid, str) and isinstance(item, dict) and isinstance(item.get("name"), str)}


async def mapping_next_step(options):
    return "room_mapping" if options.pop("edit_room_mapping", False) else None


def mapping_fields(handler):
    """Keep readable form labels separate from the UUIDs saved in options."""
    rooms = handler.flow_state.get("rooms", {})
    fields = {}
    for uuid, name in sorted(rooms.items(), key=lambda pair: (pair[1].casefold(), pair[0])):
        label = f"{name} ({uuid})" if list(rooms.values()).count(name) > 1 else name
        # Prefix avoids collisions with connection option names such as password.
        key = f"Loxone: {label}"
        while key in fields:
            key += f" ({uuid})"
        fields[key] = uuid
    return fields


async def mapping_form(handler):
    """Show every room directly, without a nested object editor dialog."""
    return vol.Schema({vol.Optional(label): AreaSelector() for label in mapping_fields(handler)})


async def mapping_suggestions(handler):
    """Let HA preserve submitted selections, including clears, on validation retry."""
    from homeassistant.helpers import area_registry as ar

    registry = ar.async_get(handler.parent_handler.hass)
    saved = handler.options.get(CONF_ROOM_MAPPING, {})
    return {label: saved[uuid] for label, uuid in mapping_fields(handler).items()
            if uuid in saved and registry.async_get_area(saved[uuid]) is not None}


async def validate_mapping(handler, user_input):
    """Save the complete list atomically; cleared fields remove mappings."""
    from homeassistant.helpers import area_registry as ar

    fields = mapping_fields(handler)
    registry = ar.async_get(handler.parent_handler.hass)
    mapping = {}
    for label, area_id in user_input.items():
        if label not in fields:
            raise SchemaFlowError("invalid_room")
        if area_id is None or area_id == "":
            continue
        if not isinstance(area_id, str) or registry.async_get_area(area_id) is None:
            raise SchemaFlowError("invalid_area")
        mapping[fields[label]] = area_id
    return {CONF_ROOM_MAPPING: mapping}


async def validate_loxone_setup(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate Loxone setup."""
    # Validate latin-1 encoding for username and password
    try:
        if CONF_USERNAME in user_input:
            user_input[CONF_USERNAME].encode("latin-1")
    except UnicodeEncodeError as err:
        raise SchemaFlowError(
            "Username contains characters that are not latin-1 compatible"
        ) from err

    try:
        if CONF_PASSWORD in user_input:
            user_input[CONF_PASSWORD].encode("latin-1")
    except UnicodeEncodeError as err:
        raise SchemaFlowError(
            "Password contains characters that are not latin-1 compatible"
        ) from err

    # Ensure port is stored as int
    if CONF_PORT in user_input:
        user_input[CONF_PORT] = int(user_input[CONF_PORT])
    if CONF_SCENE_GEN_DELAY in user_input:
        user_input[CONF_SCENE_GEN_DELAY] = int(user_input[CONF_SCENE_GEN_DELAY])
    if CONF_UDP_PORT in user_input:
        user_input[CONF_UDP_PORT] = int(user_input[CONF_UDP_PORT])

    if user_input.get("edit_room_mapping"):
        try:
            rooms = await async_load_rooms(handler.parent_handler.hass, {**handler.options, **user_input})
        except Exception:
            # HTTP exceptions may carry credentials/server responses. Only the
            # translated error key reaches the dialog; no raw exception logging.
            raise SchemaFlowError("room_fetch_failed") from None
        handler.flow_state["rooms"] = rooms
        # Keep deleted room IDs selectable so their saved mappings can be removed.
        for uuid in handler.options.get(CONF_ROOM_MAPPING, {}):
            handler.flow_state["rooms"].setdefault(uuid, uuid)

    return user_input


DATA_SCHEMA_SETUP = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PASSWORD, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_HOST, default=DEFAULT_IP): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
        ),
        vol.Required(CONF_SCENE_GEN, default=True): BooleanSelector(),
        vol.Optional(CONF_SCENE_GEN_DELAY, default=DEFAULT_DELAY_SCENE): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=3)
        ),
        vol.Required(
            CONF_LIGHTCONTROLLER_SUBCONTROLS_GEN, default=False
        ): BooleanSelector(),
        vol.Required(
            CONF_AUTO_DISCOVERY, default=DEFAULT_AUTO_DISCOVERY
        ): BooleanSelector(),
        vol.Required(CONF_AUTO_CONFIGURE_UDP, default=True): BooleanSelector(),
        vol.Optional("edit_room_mapping", default=True): BooleanSelector(),
        # UDP-Port fuer die Logger-Datagramme des Miniservers (0 = aus).
        vol.Optional(CONF_UDP_PORT, default=DEFAULT_UDP_PORT): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, max=65535)
        ),
    }
)

DATA_SCHEMA_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PASSWORD, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_HOST, default=DEFAULT_IP): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
        ),
        vol.Required(CONF_SCENE_GEN, default=True): BooleanSelector(),
        vol.Optional(CONF_SCENE_GEN_DELAY, default=DEFAULT_DELAY_SCENE): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=3)
        ),
        vol.Required(
            CONF_LIGHTCONTROLLER_SUBCONTROLS_GEN, default=False
        ): BooleanSelector(),
        vol.Required(
            CONF_AUTO_DISCOVERY, default=DEFAULT_AUTO_DISCOVERY
        ): BooleanSelector(),
        vol.Required(CONF_AUTO_CONFIGURE_UDP, default=False): BooleanSelector(),
        vol.Optional("edit_room_mapping", default=True): BooleanSelector(),
        # UDP-Port fuer die Logger-Datagramme des Miniservers (0 = aus).
        vol.Optional(CONF_UDP_PORT, default=DEFAULT_UDP_PORT): NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, max=65535)
        ),
    }
)

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        schema=DATA_SCHEMA_SETUP,
        validate_user_input=validate_loxone_setup,
        next_step=mapping_next_step,
    ),
    "room_mapping": SchemaFlowFormStep(schema=mapping_form, validate_user_input=validate_mapping,
                                       suggested_values=mapping_suggestions),
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        schema=DATA_SCHEMA_OPTIONS,
        validate_user_input=validate_loxone_setup,
        next_step=mapping_next_step,
    ),
    "room_mapping": CONFIG_FLOW["room_mapping"],
}


class LoxoneFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle Loxone config flow."""

    VERSION = 3
    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return "Loxone (smartmacherei)"
