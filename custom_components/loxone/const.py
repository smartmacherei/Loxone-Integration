"""
Loxone constants

For more details about this component, please refer to the documentation at
https://github.com/JoDehli/PyLoxone
"""

# Loxone constants
from typing import Final

from homeassistant.const import Platform

LOXONE_PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.COVER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.ALARM_CONTROL_PANEL,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SELECT,
]

LOXONE_DEFAULT_PORT = 80

ERROR_VALUE = -1
DEFAULT_PORT = 80
DEFAULT_IP = ""

# Dispatcher signal carrying changed Miniserver values to the entities.
SIGNAL_STATE_UPDATE = "loxone_state_update"
DOMAIN = "loxone"
LOX_CONFIG = "loxconfig"

SENDDOMAIN = "loxone_send"
SECUREDSENDDOMAIN = "loxone_send_secured"
DEFAULT = ""

ATTR_UUID = "uuid"

ATTR_VALUE = "value"
ATTR_CODE = "code"
ATTR_COMMAND = "command"
ATTR_DEVICE = "device"
ATTR_AREA_CREATE = "create_areas"
DOMAIN_DEVICES = "devices"

CONF_ACTIONID = "uuidAction"
CONF_LIGHTCONTROLLER_SUBCONTROLS_GEN = "generate_lightcontroller_subcontrols"
# Auto-Discovery: physische Klemmen ohne Visu-Haekchen als Entities ergaenzen.
# Vorgabe True = bisheriges Verhalten. Fuer Kundenprojekte abschaltbar, weil
# grosse Projekte sonst hunderte ungewollte Entities erzeugen.
CONF_AUTO_DISCOVERY = "auto_discovery"
DEFAULT_AUTO_DISCOVERY = True
DEFAULT_FORCE_UPDATE = False

SUPPORT_SUN_AUTOMATION = 1024
SUPPORT_QUICK_SHADE = 2048

SERVICE_ENABLE_SUN_AUTOMATION = "enable_sun_automation"
SERVICE_DISABLE_SUN_AUTOMATION = "disable_sun_automation"
SERVICE_QUICK_SHADE = "quick_shade"

CONF_HVAC_AUTO_MODE = "hvac_auto_mode"

STATE_ON = "on"
STATE_OFF = "off"

DEFAULT_AUDIO_ZONE_V2_PLAY_STATE = -1

THROTTLE_KEEP_ALIVE_TIME = 60

r"""\
cfmt description
(                                  # start of capture group 1
%                                  # literal "%"
(?:                                # first option
(?:[-+0 #]{0,5})                   # optional flags
(?:\d+|\*)?                        # width
(?:\.(?:\d+|\*))?                  # precision
(?:h|l|ll|w|I|I32|I64)?            # size
[cCdiouxXeEfgGaAnpsSZ]             # type
) |                                # OR
%%) 
"""

cfmt = r"(%(?:(?:[-+0 #]{0,5})(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:h|l|ll|w|I|I32|I64)?[cCdiouxXeEfgGaAnpsSZ])|%%)"

# UDP-Push: Port, auf dem die Integration die Logger-Datagramme des Miniservers
# entgegennimmt (Logger-Adresse im Programm: /dev/udp/<HA-IP>/<Port>).
# Optional automatisch eingerichtet durch udp_setup.py. 0 = aus. Der Kanal ersetzt
# fuer auto-entdeckte Klemmen das 30-s-Polling durch Echtzeit; das Polling bleibt
# als Rueckfallebene bestehen.
CONF_UDP_PORT = "udp_port"
DEFAULT_UDP_PORT = 55555

# Automatic program modification is explicit in the setup form. Existing entries
# without this option stay read-only until the user enables it.
CONF_AUTO_CONFIGURE_UDP = "auto_configure_udp"

# Upper bound for terminals that get a UDP logger reference. Protects the
# Miniserver, the network and HA on very large installations; terminals beyond
# the limit keep the 30-second polling. User-adjustable in the setup form.
CONF_UDP_MAX_SIGNALS = "udp_max_signals"
DEFAULT_UDP_MAX_SIGNALS = 500
