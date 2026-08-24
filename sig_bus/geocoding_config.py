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


def get_cnefe_base_path(settings=None):
    """Caminho da base local do CNEFE, ou `""` se não houver.

    Mesmo padrão defensivo de `get_google_api_key`: só `str` conta, valor
    estranho no `QSettings` vira o padrão.
    """
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    val = settings.value("SIG-Bus/geocoding/cnefe_base_path", "")
    if not isinstance(val, str):
        return ""
    return val.strip()


def set_cnefe_base_path(caminho, settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    settings.setValue("SIG-Bus/geocoding/cnefe_base_path", str(caminho or "").strip())


def get_cnefe_habilitado(settings=None):
    """Padrão `True` — a base só é consultada se houver caminho configurado,
    então ligado por padrão não muda nada para quem não tem base."""
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    val = settings.value("SIG-Bus/geocoding/cnefe_habilitado", True)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() not in ("false", "0", "no", "nao", "não")
    if isinstance(val, int):
        return bool(val)
    return True


def set_cnefe_habilitado(habilitado, settings=None):
    if settings is None:
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
    settings.setValue("SIG-Bus/geocoding/cnefe_habilitado", bool(habilitado))


def pasta_padrao_bases():
    """`<perfil do QGIS>/sig_bus/cnefe` — onde sugerir salvar as bases.

    Import tardio do QGIS, como já se faz com o `QSettings`, para o módulo
    continuar importável fora do QGIS.
    """
    import os
    try:
        from qgis.core import QgsApplication
        raiz = QgsApplication.qgisSettingsDirPath()
    except Exception:
        raiz = os.path.expanduser("~")
    return os.path.join(raiz, "sig_bus", "cnefe")
