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
from homeassistant.helpers.selector import (AreaSelector, BooleanSelector, SelectSelector, SelectSelectorConfig,
                                            SelectSelectorMode, NumberSelector,
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


async def mapping_form(handler):
    rooms = handler.flow_state.get("rooms", {})
    return vol.Schema({
        vol.Optional("room"): SelectSelector(SelectSelectorConfig(
            options=[{"value": uuid, "label": name} for uuid, name in sorted(rooms.items(), key=lambda pair: (pair[1], pair[0]))],
            mode=SelectSelectorMode.DROPDOWN,
        )),
        vol.Optional("area"): AreaSelector(),
        vol.Optional("remove_mapping", default=False): BooleanSelector(),
        vol.Optional("map_another", default=False): BooleanSelector(),
    })


async def mapping_description(handler):
    from homeassistant.helpers import area_registry as ar

    registry = ar.async_get(handler.parent_handler.hass)
    rooms = handler.flow_state.get("rooms", {})
    lines = []
    for room, area_id in handler.options.get(CONF_ROOM_MAPPING, {}).items():
        area = registry.async_get_area(area_id)
        lines.append(f"{rooms.get(room, room)} → {area.name if area else area_id}")
    return {"mappings": "; ".join(lines) or "—"}


async def validate_mapping(handler, user_input):
    from homeassistant.helpers import area_registry as ar

    mapping = dict(handler.options.get(CONF_ROOM_MAPPING, {}))
    room, area_id = user_input.get("room"), user_input.get("area")
    remove = user_input.get("remove_mapping", False)
    if room:
        # Permit removal of saved mappings for rooms no longer in the project.
        if room not in handler.flow_state.get("rooms", {}) and not (remove and room in mapping):
            raise SchemaFlowError("invalid_room")
        if remove:
            mapping.pop(room, None)
        elif not area_id or ar.async_get(handler.parent_handler.hass).async_get_area(area_id) is None:
            raise SchemaFlowError("invalid_area")
        else:
            mapping[room] = area_id
    elif area_id or remove:
        raise SchemaFlowError("invalid_room")
    return {CONF_ROOM_MAPPING: mapping, "_map_another": user_input.get("map_another", False)}


async def mapping_after_step(options):
    return "room_mapping" if options.pop("_map_another", False) else None


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
        vol.Optional("edit_room_mapping", default=False): BooleanSelector(),
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
        vol.Optional("edit_room_mapping", default=False): BooleanSelector(),
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
                                       next_step=mapping_after_step, description_placeholders=mapping_description),
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
