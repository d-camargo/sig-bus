# -*- coding: utf-8 -*-
"""Fonte única da verdade para a configuração de rede da geocodificação.

Não importa Qt nem QGIS. `geocoding.py` lê estas constantes em vez de
duplicá-las — evita, por exemplo, o User-Agent divergir entre provedores.
"""

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api"
GOOGLE_SEARCH_URL = "https://maps.googleapis.com/maps/api/geocode/json"
HOSTS_COM_LIMITE = ("nominatim.openstreetmap.org", "photon.komoot.io")

USER_AGENT = b"SIG-Bus-QGIS/0.4 (Geocoding)"
INTERVALO_MINIMO_SEGUNDOS = 1.0
LOG_TAG = "SIG-Bus"


def get_provider_mode(settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    val = settings.value("SIG-Bus/geocoding/provider", "auto")
    if not isinstance(val, str) or val not in ("auto", "osm"):
        return "auto"
    return val


def set_provider_mode(modo, settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    if modo not in ("auto", "osm"):
        modo = "auto"
    settings.setValue("SIG-Bus/geocoding/provider", modo)


def get_google_api_key(settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    key = settings.value("SIG-Bus/geocoding/google_api_key", "")
    # Só texto conta como chave. Sem esta guarda, um `QSettings` que devolva
    # qualquer outro objeto viraria uma "chave" via `str()` e o plugin
    # dispararia requisições faturáveis com credencial de mentira.
    if not isinstance(key, str):
        return ""
    return key.strip()


def set_google_api_key(chave, settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    settings.setValue("SIG-Bus/geocoding/google_api_key", str(chave or "").strip())

