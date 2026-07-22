"""Constants for the MCZ Maestro integration."""

from datetime import timedelta

DOMAIN = "mcz_maestro"

CONF_DEFAULT_HOST = "192.168.120.1"
CONF_DEFAULT_PORT = 81

DEFAULT_NAME = "Poêle MCZ Maestro"
POLL_INTERVAL = timedelta(seconds=15)
REQUEST_TIMEOUT = 10
MAX_DATA_AGE_SECONDS = 40
COMMAND_MIN_INTERVAL_SECONDS = 1.0
COMMAND_CONFIRMATION_TIMEOUT_SECONDS = 20.0
COMMAND_CONFIRMATION_POLL_INTERVAL_SECONDS = 1.0

PLATFORMS = [
    "binary_sensor",
    "button",
    "climate",
    "select",
    "sensor",
    "switch",
]

CELL_POWER = 34
CELL_POWER_LEVEL = 36
CELL_FAN_FRONT = 37
CELL_FAN_DUCTED_1 = 38
CELL_FAN_DUCTED_2 = 39
CELL_CONTROL_MODE = 40
CELL_ECO_MODE = 41
CELL_TARGET_TEMPERATURE = 42
CELL_SILENT_MODE = 45

POWER_ON = 1
POWER_OFF = 40

TEMPERATURE_STATUS_OK = "ok"
TEMPERATURE_STATUS_THERMOSTAT_OFF = "thermostat_off"
TEMPERATURE_STATUS_THERMOSTAT_ON = "thermostat_on"
TEMPERATURE_STATUS_FAULT = "fault"
TEMPERATURE_STATUS_DISCONNECTED = "disconnected"

STOVE_STATES = {
    0: "Éteint",
    1: "Contrôle chaud ou froid",
    2: "Nettoyage à froid",
    3: "Chargement à froid",
    4: "Allumage 1 à froid",
    5: "Allumage 2 à froid",
    6: "Nettoyage à chaud",
    7: "Chargement à chaud",
    8: "Allumage 1 à chaud",
    9: "Allumage 2 à chaud",
    10: "Stabilisation",
    11: "Puissance 1",
    12: "Puissance 2",
    13: "Puissance 3",
    14: "Puissance 4",
    15: "Puissance 5",
    30: "Diagnostic",
    31: "Allumé",
    40: "Extinction",
    41: "Refroidissement",
    42: "Nettoyage basse puissance",
    43: "Nettoyage haute puissance",
    44: "Déblocage de la vis sans fin",
    45: "Auto Eco",
    46: "Veille",
    48: "Diagnostic",
    49: "Chargement de la vis sans fin",
    50: "A01 — Échec d'allumage",
    51: "A02 — Absence de flamme",
    52: "A03 — Surchauffe du réservoir",
    53: "A04 — Température des fumées trop élevée",
    54: "A05 — Obstruction du conduit ou vent",
    55: "A08 — Ventilateur des fumées",
    56: "A09 — Sonde des fumées",
    57: "A11 — Motoréducteur",
    58: "A13 — Température de la carte mère",
    59: "A14 — Défaut Active",
    60: "A18 — Alarme température d'eau",
    61: "A19 — Sonde d'eau défectueuse",
    62: "A20 — Sonde auxiliaire défectueuse",
    63: "A21 — Alarme pressostat",
    64: "A22 — Sonde ambiante défectueuse",
    65: "A23 — Défaut de fermeture du brasier",
    66: "A12 — Contrôleur du motoréducteur",
    67: "A17 — Vis sans fin bloquée",
    69: "Attente des sécurités",
}

STOVE_ON_STATES = set(range(1, 16)) | {31, 40, 41, 42, 43}
ALARM_STATES = set(range(50, 70))
DIAGNOSTIC_STATES = {30, 48}
POWER_ADJUSTMENT_STATES = {0, 11, 12, 13, 14, 15}
