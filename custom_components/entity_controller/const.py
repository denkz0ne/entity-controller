"""Constants for Entity Controller."""

DOMAIN = "entity_controller"
DOMAIN_SHORT = "ec"

DEFAULT_DELAY_SECONDS = 180.0
DEFAULT_BACKOFF_FACTOR = 1.1
DEFAULT_BACKOFF_MAX_SECONDS = 300.0

SERVICE_ACTIVATE = "activate"
SERVICE_CLEAR_BLOCK = "clear_block"
SERVICE_ENABLE_BLOCK = "enable_block"
SERVICE_ENABLE_STAY_MODE = "enable_stay_mode"
SERVICE_DISABLE_STAY_MODE = "disable_stay_mode"
SERVICE_SET_NIGHT_MODE = "set_night_mode"
