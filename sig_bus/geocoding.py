# -*- coding: utf-8 -*-
"""
/***************************************************************************
 osm_geocoding — Geocodificação usando a API pública do Nominatim (OpenStreetMap)
                                 A QGIS plugin
 ***************************************************************************/
"""

import time
import json
import traceback
from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .address_format import parse_address

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api"
LOG_TAG = "SIG-Bus"


def _pct(valor):
    """Codifica um valor de forma segura para a URL."""
    return QUrl.toPercentEncoding(str(valor)).data().decode('utf-8')


def _log(mensagem, nivel):
    """Registra uma linha no painel "Log Messages", aba SIG-Bus (decisão 52)."""
    QgsMessageLog.logMessage(
        "Geocodificação: {}".format(mensagem), LOG_TAG, nivel)


def _mesmo_texto(a, b):
    """Compara dois textos ignorando caixa e espaços repetidos."""
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())


class NominatimGeocoder(object):
    """
    Classe para geocodificação de endereços usando o serviço público do Nominatim.
    Respeita a política de uso do Nominatim (limite de requisições, User-Agent).
    """
    _last_request_time = 0.0
    _session_cache = {}

    @classmethod
    def clear_cache(cls):
        """Limpa o cache de sessão de requisições de geocodificação."""
        cls._session_cache.clear()

    @classmethod
    def geocode(cls, endereco, contexto=None):
        """
        Geocodifica um endereço usando a API do Nominatim.

        Sem contexto, faz uma busca livre — o comportamento histórico. Com
        contexto (decisões 44 e 47), faz busca estruturada em cascata, parando
        no primeiro acerto: (a) estruturada com número; (b) estruturada sem
        número (rua inteira); (c) busca livre com município/UF/país anexados.

        Garante um intervalo mínimo de 1 segundo entre requisições reais para
        respeitar a política de uso público do Nominatim. Nunca levanta exceção;
        em caso de erro de rede, parsing ou endereço não encontrado, retorna uma
        lista vazia.

        :param endereco: String contendo o endereço a ser geocodificado.
        :param contexto: Dicionário opcional com 'city', 'state', 'country' e
                         'viewbox' (bbox do município no formato
                         'lon_min,lat_max,lon_max,lat_min').
        :return: Lista de dicionários representando os candidatos encontrados,
                 onde cada item tem 'lat', 'lon', etc., ou lista vazia em caso de falha/vazio.
        """
        if not endereco:
            return []

        try:
            urls = cls._montar_urls(endereco, contexto, bounded=True)
        except Exception:
            return []

        for etiqueta, url in urls:
            resultados = cls._buscar(url, etiqueta=etiqueta)
            if resultados:
                return resultados

        if contexto and contexto.get("viewbox"):
            try:
                urls_fallback = cls._montar_urls(endereco, contexto, bounded=False)
            except Exception:
                urls_fallback = []

            for etiqueta, url in urls_fallback:
                resultados = cls._buscar(url, etiqueta=etiqueta)
                if resultados:
                    return resultados

        try:
            return PhotonGeocoder.geocode(endereco, contexto)
        except Exception:
            return []

    @classmethod
    def city_bbox(cls, municipio, uf=None):
        """
        Retorna o bounding box do município no formato 'lon_min,lat_max,lon_max,lat_min'
        para ser utilizado como viewbox no contexto de geocodificação.

        :param municipio: Nome do município (str).
        :param uf: Sigla ou nome do estado (str, opcional).
        :return: String no formato 'lon_min,lat_max,lon_max,lat_min' ou None se não encontrado.
        """
        if not municipio:
            return None

        municipio_str = str(municipio).strip()
        if not municipio_str:
            return None

        uf_str = str(uf).strip() if uf else ""

        params = ["format=json", "countrycodes=br", "limit=1", "city={}".format(_pct(municipio_str))]
        if uf_str:
            params.append("state={}".format(_pct(uf_str)))
        params.append("country=Brasil")

        url = "{}?{}".format(NOMINATIM_SEARCH_URL, "&".join(params))
        resultados = cls._buscar(url, etiqueta="city-bbox")

        if not resultados:
            livre = [municipio_str]
            if uf_str:
                livre.append(uf_str)
            livre.append("Brasil")
            url = "{}?format=json&countrycodes=br&limit=1&q={}".format(
                NOMINATIM_SEARCH_URL, _pct(", ".join(livre))
            )
            resultados = cls._buscar(url, etiqueta="city-bbox livre")

        if resultados and isinstance(resultados, list) and len(resultados) > 0:
            item = resultados[0]
            bbox = item.get("boundingbox")
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                # Nominatim boundingbox: [lat_min, lat_max, lon_min, lon_max]
                # Viewbox format: lon_min,lat_max,lon_max,lat_min
                return "{},{},{},{}".format(bbox[2], bbox[1], bbox[3], bbox[0])

        return None

    @classmethod
    def _montar_urls(cls, endereco, contexto, bounded=True):
        """
        Monta as URLs da cascata de tentativas, na ordem em que devem ser feitas.

        Sem contexto, devolve uma única URL de busca livre (comportamento antigo).
        """
        prefixo = "" if bounded else "sem-bbox "

        if not contexto:
            return [(prefixo + "c-livre",
                     "{}?format=json&q={}".format(NOMINATIM_SEARCH_URL, _pct(endereco)))]

        partes = parse_address(endereco)
        logradouro = (partes.get("logradouro") or "").strip()
        numero = (partes.get("numero") or "").strip()
        bairro = (partes.get("bairro") or "").strip()

        municipio = (contexto.get("city") or "").strip()
        uf = (contexto.get("state") or "").strip()
        pais = (contexto.get("country") or "").strip() or "Brasil"
        viewbox = (contexto.get("viewbox") or "").strip()

        # Parâmetros comuns a todas as tentativas (decisões 44 e 47).
        comuns = ["format=json", "countrycodes=br", "limit=5", "addressdetails=1"]
        if viewbox:
            comuns.append("viewbox={}".format(_pct(viewbox)))
            if bounded:
                comuns.append("bounded=1")

        def estruturada(street):
            params = ["street={}".format(_pct(street))]
            if municipio:
                params.append("city={}".format(_pct(municipio)))
            if uf:
                params.append("state={}".format(_pct(uf)))
            params.append("country={}".format(_pct(pais)))
            return "{}?{}".format(NOMINATIM_SEARCH_URL, "&".join(comuns + params))

        urls = []
        # (a) estruturada com número.
        if logradouro and numero:
            urls.append((prefixo + "a-estruturada-num",
                         estruturada("{} {}".format(numero, logradouro))))
        # (b) estruturada sem número (rua inteira → ponto no meio da via).
        if logradouro:
            urls.append((prefixo + "b-estruturada", estruturada(logradouro)))
        # (c) busca livre com município/UF/país anexados. O bairro sai da lista
        # quando é o próprio município (decisão 53): "Caxias do Sul, Caxias do
        # Sul - RS" pontua pior no Nominatim do que o município uma vez só.
        if municipio and _mesmo_texto(bairro, municipio):
            bairro = ""
        livre = [p for p in (logradouro or endereco, numero, bairro) if p]
        if municipio:
            livre.append("{} - {}".format(municipio, uf) if uf else municipio)
        livre.append(pais)
        urls.append((prefixo + "c-livre", "{}?{}&q={}".format(
            NOMINATIM_SEARCH_URL, "&".join(comuns), _pct(", ".join(livre)))))
        return urls

    @classmethod
    def _get_json(cls, url, etiqueta=None):
        """
        Transporte: faz a requisição e devolve o JSON já decodificado.

        Respeita o intervalo de 1 segundo (uma espera por requisição real) e
        registra a causa de cada falha no QgsMessageLog em vez de falhar em
        silêncio (decisão 52). Devolve o objeto decodificado — `list` ou `dict`,
        conforme o serviço — ou None em qualquer falha. Não interpreta o
        conteúdo: quem chama decide o que é uma resposta válida.
        """
        tag_str = "[{}] ".format(etiqueta) if etiqueta else ""

        if url in cls._session_cache:
            _log("{}cache de sessão — {}".format(tag_str, url), Qgis.MessageLevel.Info)
            return cls._session_cache[url]

        # Garante no mínimo 1 segundo de intervalo entre requisições
        now = time.time()
        elapsed = now - cls._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        cls._last_request_time = time.time()

        try:
            req = QNetworkRequest(QUrl(url))
            req.setRawHeader(b"User-Agent", b"SIG-Bus-QGIS/0.4 (Geocoding)")

            manager = QgsNetworkAccessManager.instance()
            if not manager:
                _log("{}QgsNetworkAccessManager indisponível — {}".format(tag_str, url),
                     Qgis.MessageLevel.Warning)
                return None

            # Executa a requisição síncrona/bloqueante no QGIS
            reply = manager.blockingGet(req)
            if not reply:
                _log("{}sem resposta do servidor — {}".format(tag_str, url),
                     Qgis.MessageLevel.Warning)
                return None

            erro = reply.error()
            if erro != QNetworkReply.NetworkError.NoError:
                _log("{}falha de rede (erro={}) — {}".format(tag_str, erro, url),
                     Qgis.MessageLevel.Warning)
                return None

            content = bytes(reply.content()).decode("utf-8")
            if not content:
                _log("{}resposta vazia (erro={}) — {}".format(tag_str, erro, url),
                     Qgis.MessageLevel.Warning)
                return None

            data = json.loads(content)
            # Nominatim devolve uma lista; o Photon, um GeoJSON com "features".
            if isinstance(data, list):
                candidatos = len(data)
            elif isinstance(data, dict):
                candidatos = len(data.get("features") or [])
            else:
                candidatos = "-"
            _log("{}erro={} candidatos={} — {}".format(tag_str, erro, candidatos, url),
                 Qgis.MessageLevel.Info)
            cls._session_cache[url] = data
            return data

        except Exception:
            # Nunca propaga exceção (contrato da geocodificação), mas registra a
            # causa no log — o silêncio aqui já escondeu um bug inteiro (decisão 52).
            _log("{}exceção ao consultar {}\n{}".format(tag_str, url, traceback.format_exc()),
                 Qgis.MessageLevel.Warning)
            return None

    @classmethod
    def _buscar(cls, url, etiqueta=None):
        """
        Interpretação: casca fina sobre `_get_json` para o formato do Nominatim.

        Devolve a lista de candidatos ou [] em qualquer falha — inclusive quando
        a resposta não é uma lista, que é o contrato desta busca.
        """
        data = cls._get_json(url, etiqueta=etiqueta)
        if not isinstance(data, list):
            if data is not None:
                tag_str = "[{}] ".format(etiqueta) if etiqueta else ""
                _log("{}resposta em formato inesperado — {}".format(tag_str, url),
                     Qgis.MessageLevel.Warning)
            return []
        return data


class PhotonGeocoder(object):
    """
    Geocodificador tolerante a erros de digitação usando a API pública do Photon (Komoot).
    Devolve candidatos no mesmo formato estandardizado ({'lat', 'lon', 'display_name'}).
    """

    @classmethod
    def geocode(cls, endereco, contexto=None):
        """
        Geocodifica um endereço usando a API do Photon.

        :param endereco: String contendo o endereço.
        :param contexto: Dicionário opcional com 'city', 'state', 'country', 'viewbox'.
        :return: Lista de candidatos estandardizados ou [].
        """
        if not endereco:
            return []

        try:
            url = cls._photon_url(endereco, contexto)
        except Exception:
            return []

        resultados = cls._buscar(url, etiqueta="photon")
        return cls._filtrar_municipio(resultados, contexto)

    @classmethod
    def _photon_url(cls, endereco, contexto=None):
        """
        Monta a URL de consulta ao Photon.

        Sem `lang=` (medido: `lang=pt` devolve HTTP 400) e com a bbox
        convertida do `viewbox` do Nominatim (`lon_min,lat_max,lon_max,lat_min`)
        para a ordem do Photon (`minLon,minLat,maxLon,maxLat`) — decisão 57.
        Quando não há bbox, o município/UF entram na própria busca; com bbox o
        recorte geográfico já basta e a consulta fica como foi medida.
        """
        query = str(endereco).strip()
        bbox = None

        if contexto and contexto.get("viewbox"):
            partes = str(contexto["viewbox"]).split(",")
            if len(partes) == 4:
                lon_min, lat_max, lon_max, lat_min = [p.strip() for p in partes]
                bbox = "{},{},{},{}".format(lon_min, lat_min, lon_max, lat_max)

        if contexto and not bbox:
            extras = [(contexto.get("city") or "").strip(),
                      (contexto.get("state") or "").strip(),
                      (contexto.get("country") or "").strip() or "Brasil"]
            query = ", ".join([query] + [e for e in extras if e])

        params = ["q={}".format(_pct(query)), "limit=5"]
        if bbox:
            params.append("bbox={}".format(bbox))

        return "{}?{}".format(PHOTON_SEARCH_URL, "&".join(params))

    @classmethod
    def _filtrar_municipio(cls, resultados, contexto):
        """
        Sem bbox não há recorte geográfico na consulta, então o município do
        contexto é aplicado aqui: candidato de outro município é descartado
        (decisões 47 e 57). Candidato sem `city`/`county` é mantido — o Photon
        não preenche esses campos para toda feature.
        """
        if not resultados or not contexto or contexto.get("viewbox"):
            return resultados

        municipio = (contexto.get("city") or "").strip()
        if not municipio:
            return resultados

        filtrados = []
        for item in resultados:
            props = item.get("properties") or {}
            cidade = props.get("city")
            comarca = props.get("county")
            if (cidade or comarca) and not (_mesmo_texto(cidade, municipio)
                                            or _mesmo_texto(comarca, municipio)):
                continue
            filtrados.append(item)
        return filtrados

    @classmethod
    def _buscar(cls, url, etiqueta=None):
        """
        Interpretação: casca fina sobre `_get_json` para o formato GeoJSON do Photon.

        Devolve a lista de candidatos estandardizados ou [] em qualquer falha.
        """
        data = NominatimGeocoder._get_json(url, etiqueta=etiqueta)
        if not isinstance(data, dict):
            if data is not None:
                tag_str = "[{}] ".format(etiqueta) if etiqueta else ""
                _log("{}resposta em formato inesperado — {}".format(tag_str, url),
                     Qgis.MessageLevel.Warning)
            return []

        features = data.get("features")
        if not isinstance(features, list):
            return []

        resultados = []
        for feat in features:
            if not isinstance(feat, dict):
                continue
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates")
            if not coords or not isinstance(coords, (list, tuple)) or len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            props = feat.get("properties") or {}

            partes = []
            name = props.get("name")
            street = props.get("street")
            housenumber = props.get("housenumber")
            city = props.get("city")
            state = props.get("state")
            country = props.get("country")

            if name:
                partes.append(name)
            elif street:
                if housenumber:
                    partes.append("{} {}".format(street, housenumber))
                else:
                    partes.append(street)

            for item in (city, state, country):
                if item and item not in partes:
                    partes.append(item)

            display_name = ", ".join(partes) if partes else "Desconhecido"

            resultados.append({
                "lat": str(lat),
                "lon": str(lon),
                "display_name": display_name,
                "properties": props
            })
        return resultados
