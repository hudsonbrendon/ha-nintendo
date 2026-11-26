"""Constantes da integração Nintendo."""

from logging import getLogger

DOMAIN = "nintendo"
LOGGER = getLogger(__package__)
CONF_SESSION_TOKEN = "session_token"
SCAN_INTERVAL_SECONDS = 120
SLOW_REFRESH_SECONDS = 3600  # perfil + resumo mensal
