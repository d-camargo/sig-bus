# -*- coding: utf-8 -*-
"""
/***************************************************************************
 osm_geocoding — Geocodificação usando a API pública do Nominatim (OpenStreetMap)
                                 A QGIS plugin
 ***************************************************************************/
"""

import os
import re
import time
import json
import traceback
from urllib.parse import urlsplit
from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .address_format import parse_address
from .street_index import corrigir
from .cnefe_base import BaseInvalida, descrever_base
from .cnefe_geocoder import CnefeGeocoder
from .cnefe_padrao import normalizar_municipio, normalizar_texto, normalizar_uf
from .geocoding_config import (
    NOMINATIM_SEARCH_URL, PHOTON_SEARCH_URL, GOOGLE_SEARCH_URL, HOSTS_COM_LIMITE,
    USER_AGENT, INTERVALO_MINIMO_SEGUNDOS, LOG_TAG,
    get_provider_mode, get_google_api_key,
    get_cnefe_base_path, get_cnefe_habilitado,
)


def _pct(valor):
    """Codifica um valor de forma segura para a URL."""
    return QUrl.toPercentEncoding(str(valor)).data().decode('utf-8')


def _redigir_credenciais(texto):
    """Substitui valores de credenciais/chaves por *** antes de logar (decisão 65)."""
    if not texto:
        return texto
    res = re.sub(r'(?i)(\b(?:key|api_key|token|secret|password|passwd|pwd|auth)=)[^&]*', r'\1***', str(texto))
    res = re.sub(r'//([^:@]+):([^@]+)@', r'//\1:***@', res)
    return res


def _log(mensagem, nivel):
    """Registra uma linha no painel "Log Messages", aba SIG-Bus (decisão 52). Redige credenciais (decisão 65)."""
    msg_redigida = _redigir_credenciais(mensagem)
    QgsMessageLog.logMessage(
        "Geocodificação: {}".format(msg_redigida), LOG_TAG, nivel)


def _mesmo_texto(a, b):
    """Compara dois textos ignorando caixa e espaços repetidos."""
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())


class NominatimGeocoder(object):
    """
    Classe para geocodificação de endereços usando o serviço público do Nominatim.
    Respeita a política de uso do Nominatim (limite de requisições, User-Agent).
    """
    _last_request_time = {}
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

        Respeita o intervalo de 1 segundo por host, para os hosts em
        `HOSTS_COM_LIMITE` (decisão 67), e registra a causa de cada falha no
        QgsMessageLog em vez de falhar em silêncio (decisão 52). Devolve o
        objeto decodificado — `list` ou `dict`, conforme o serviço — ou None
        em qualquer falha. Não interpreta o conteúdo: quem chama decide o que
        é uma resposta válida.
        """
        tag_str = "[{}] ".format(etiqueta) if etiqueta else ""

        if url in cls._session_cache:
            _log("{}cache de sessão — {}".format(tag_str, url), Qgis.MessageLevel.Info)
            return cls._session_cache[url]

        # Garante no mínimo 1 segundo de intervalo por host para hosts com limite (decisão 67).
        # O host sai do `urlsplit` da stdlib, não do `QUrl`: é a mesma resposta sem
        # depender do Qt para uma conta de string.
        host = urlsplit(url).hostname or ""
        if host in HOSTS_COM_LIMITE:
            now = time.time()
            last_time = cls._last_request_time.get(host, 0.0)
            elapsed = now - last_time
            if elapsed < INTERVALO_MINIMO_SEGUNDOS:
                time.sleep(INTERVALO_MINIMO_SEGUNDOS - elapsed)
            cls._last_request_time[host] = time.time()

        try:
            req = QNetworkRequest(QUrl(url))
            req.setRawHeader(b"User-Agent", USER_AGENT)

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
        for item in data:
            if isinstance(item, dict):
                item["provider"] = "nominatim"
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
                "properties": props,
                "provider": "photon"
            })
        return resultados


class GoogleGeocoder(object):
    """
    Geocodificador usando a API do Google Maps Geocoding (decisões 63 e 69).
    Devolve candidatos no mesmo formato estandardizado ({'lat', 'lon', 'display_name', ...}).
    """

    #: Último `status`/`error_message` diferente de OK/ZERO_RESULTS devolvido pelo
    #: Google, para a mensagem de fim de lote apontar a causa provável em vez de
    #: culpar a grafia do endereço (decisão 64). None quando não houve erro.
    ultimo_erro = None

    @classmethod
    def geocode(cls, endereco, contexto=None, chave=""):
        """
        Geocodifica um endereço usando a API do Google.

        :param endereco: String contendo o endereço.
        :param contexto: Dicionário opcional com 'city', 'state', 'country', 'viewbox'.
        :param chave: String contendo a chave da API do Google.
        :return: Lista de candidatos estandardizados ou [].
        """
        if not endereco:
            return []
        if not chave:
            chave = get_google_api_key()
        if not chave:
            return []

        try:
            url = cls._google_url(endereco, contexto, chave)
        except Exception:
            return []

        return cls._buscar(url, etiqueta="google")

    @classmethod
    def _google_url(cls, endereco, contexto=None, chave=""):
        """
        Monta a URL de consulta ao Google Geocoding API.

        Converte a bbox do Nominatim ('lon_min,lat_max,lon_max,lat_min') para
        a ordem do Google ('lat_min,lon_min|lat_max,lon_max') no parâmetro `bounds=`.
        Sem `viewbox` no contexto, a URL não leva `bounds`.
        """
        query = str(endereco).strip()
        extras = []
        if contexto:
            city = (contexto.get("city") or "").strip()
            state = (contexto.get("state") or "").strip()
            country = (contexto.get("country") or "").strip() or "Brasil"
            if city:
                if state:
                    extras.append("{} - {}".format(city, state))
                else:
                    extras.append(city)
            if country:
                extras.append(country)

        partes_end = [query] + [e for e in extras if e]
        full_address = ", ".join(partes_end)

        params = [
            "address={}".format(_pct(full_address)),
            "components=country:BR",
            "language=pt-BR",
            "region=br",
        ]
        if chave:
            params.append("key={}".format(_pct(chave)))

        if contexto and contexto.get("viewbox"):
            partes_box = str(contexto["viewbox"]).split(",")
            if len(partes_box) == 4:
                lon_min, lat_max, lon_max, lat_min = [p.strip() for p in partes_box]
                bounds = "{},{}|{},{}".format(lat_min, lon_min, lat_max, lon_max)
                params.append("bounds={}".format(bounds))

        return "{}?{}".format(GOOGLE_SEARCH_URL, "&".join(params))

    #: `types` do Google que caracterizam um acerto de nível-rua — a lista de
    #: aceitação da decisão 66. Tudo que não cruza com ela (`locality`,
    #: `administrative_area_level_*`, `postal_code`, `neighborhood`, …) é o
    #: centro de uma área, não um endereço, e vira parada num ponto errado que
    #: ninguém confere. `establishment`/`point_of_interest` ficam porque parada
    #: de ônibus é descrita por referência com frequência.
    _TYPES_NIVEL_RUA = frozenset((
        "street_address",
        "route",
        "premise",
        "subpremise",
        "intersection",
        "establishment",
        "point_of_interest",
    ))

    @classmethod
    def _buscar(cls, url, etiqueta=None):
        """
        Interpretação: casca fina sobre `_get_json` para o formato do Google Geocoding.

        Trata `status` (decisão 64): `ZERO_RESULTS` é resposta vazia normal;
        qualquer outro status diferente de `OK` vira `Warning` no log com o
        `error_message` do corpo e fica em `ultimo_erro`, para a cascata grátis
        continuar sem que o usuário perca a causa. Descarta candidatos que não
        são de nível-rua (decisão 66), dizendo no log qual `types` motivou o
        descarte. Devolve a lista de candidatos estandardizados ou [] em
        qualquer falha.
        """
        data = NominatimGeocoder._get_json(url, etiqueta=etiqueta)
        if not isinstance(data, dict):
            if data is not None:
                tag_str = "[{}] ".format(etiqueta) if etiqueta else ""
                _log("{}resposta em formato inesperado — {}".format(tag_str, url),
                     Qgis.MessageLevel.Warning)
            return []

        tag_str = "[{}] ".format(etiqueta) if etiqueta else ""
        status = data.get("status")
        if status != "OK":
            if status and status != "ZERO_RESULTS":
                detalhe = data.get("error_message") or ""
                cls.ultimo_erro = "{}{}".format(status, ": " + detalhe if detalhe else "")
                _log("{}status={}{} — {}".format(
                    tag_str, status, " (" + detalhe + ")" if detalhe else "", url),
                     Qgis.MessageLevel.Warning)
            return []

        cls.ultimo_erro = None

        results = data.get("results")
        if not isinstance(results, list):
            return []

        candidatos = []
        for item in results:
            if not isinstance(item, dict):
                continue

            item_types = item.get("types") or []
            if not any(t in cls._TYPES_NIVEL_RUA for t in item_types):
                _log("{}candidato descartado por não ser de nível-rua: types={} — {}".format(
                    tag_str, item_types, item.get("formatted_address") or "?"),
                     Qgis.MessageLevel.Info)
                continue

            geom = item.get("geometry") or {}
            loc = geom.get("location") or {}
            lat = loc.get("lat")
            lng = loc.get("lng")
            if lat is None or lng is None:
                continue

            candidatos.append({
                "lat": str(lat),
                "lon": str(lng),
                "display_name": item.get("formatted_address") or "Desconhecido",
                "types": item_types,
                "partial_match": item.get("partial_match", False),
                "location_type": geom.get("location_type"),
                "provider": "google",
            })
        return candidatos


def _degrau_corretor(endereco, contexto):
    """
    Último degrau da cascata (decisão 68): todos os provedores voltaram vazios,
    então o nome da via passa pelo corretor de grafia sobre o banco vivo do OSM.

    Com o nome corrigido, tenta **uma** vez o Nominatim de novo — é ele que
    resolve número de casa, coisa que o `center` da via do Overpass não faz. Se
    esse reteste também voltar vazio, o candidato é montado direto do `center`.
    Nos dois ramos o candidato sai com o nome real em `properties.street`, para
    o `(via: <nome real>)` da decisão 59 disparar: aqui o acerto é palpite de
    similaridade, e palpite se declara.
    """
    partes = parse_address(endereco)
    logradouro = (partes.get("logradouro") or "").strip() or str(endereco).strip()
    numero = (partes.get("numero") or "").strip()
    viewbox = contexto.get("viewbox")

    corr = corrigir(logradouro, viewbox)
    if not corr:
        return []

    nome_real, lat, lon = corr

    endereco_corrigido = "{}, {}".format(nome_real, numero) if numero else nome_real
    try:
        resultados = NominatimGeocoder.geocode(endereco_corrigido, contexto)
    except Exception:
        resultados = []
    if resultados:
        for item in resultados:
            if isinstance(item, dict):
                item.setdefault("properties", {})["street"] = nome_real
        return resultados

    return [{
        "lat": str(lat),
        "lon": str(lon),
        "display_name": nome_real,
        "properties": {"street": nome_real},
        "provider": "osm-overpass",
    }]


#: (caminho, mtime) -> procedência da base. `descrever_base` conta as linhas
#: das duas tabelas; sem cache isso rodaria uma vez por parada do lote.
_CACHE_BASE = {}

#: País aceito para consultar o CNEFE. Vazio conta como Brasil porque o campo
#: País do assistente Construir GTFS é fixo em "Brasil".
PAISES_BRASIL = ("", "BRASIL", "BRAZIL", "BR")


def _descrever_base_cacheado(caminho):
    try:
        chave = (caminho, os.path.getmtime(caminho))
    except OSError:
        return None
    if chave not in _CACHE_BASE:
        try:
            _CACHE_BASE[chave] = descrever_base(caminho)
        except BaseInvalida:
            _CACHE_BASE[chave] = None
    return _CACHE_BASE[chave]


def _base_cnefe_aplicavel(contexto):
    """Caminho da base a usar, ou `None` (decisão 171).

    O CNEFE só entra quando o país é o Brasil **e** o município da base é o
    município da agência. Base de outro município nunca é usada: um acerto
    silencioso na cidade errada é pior que nenhum acerto.
    """
    caminho = get_cnefe_base_path()
    if not caminho or not get_cnefe_habilitado():
        return None

    contexto = contexto or {}
    if normalizar_texto(contexto.get("country")) not in PAISES_BRASIL:
        return None

    info = _descrever_base_cacheado(caminho)
    if not info:
        return None

    cidade = normalizar_municipio(contexto.get("city"))
    if not cidade or cidade != normalizar_municipio(info.get("municipio")):
        return None

    uf = normalizar_uf(contexto.get("state"))
    if uf and uf != normalizar_uf(info.get("estado")):
        return None

    return caminho


def geocode(endereco, contexto=None):
    """
    Ponto de entrada da geocodificação: percorre os provedores em ordem e
    devolve os candidatos do primeiro que responder não-vazio (decisão 61, 63).

    Quando `get_provider_mode()` for `"auto"` e houver chave do Google, a ordem
    passa a ser Google → Nominatim → Photon (decisão 63).
    Sem chave, ou com o modo `"osm"`, a lista fica (Nominatim → Photon) e nenhuma
    requisição sai para `maps.googleapis.com`.

    Antes de tudo, se o endereço for brasileiro e houver base local do CNEFE
    do município da agência (`_base_cnefe_aplicavel`, decisão 171), a base é
    consultada primeiro: acerto com número devolve na hora, sem gastar
    requisição nenhuma (decisão 168). Acerto que só localiza a **via** fica
    guardado e só é usado se todo o resto voltar vazio — o centroide de uma
    avenida longa pode ficar a quilômetros do ponto certo, e nesse caso um
    acerto com número do Nominatim é melhor.

    Com todos os provedores vazios e `viewbox` no contexto, ainda roda o
    corretor de grafia sobre o banco vivo do OSM (`_degrau_corretor`, decisão 68).

    Nunca levanta exceção — provedor que falha conta como resposta vazia e a
    cascata segue para o próximo.

    :param endereco: String contendo o endereço a ser geocodificado.
    :param contexto: Dicionário opcional com 'city', 'state', 'country' e
                     'viewbox' (bbox do município no formato
                     'lon_min,lat_max,lon_max,lat_min').
    :return: Lista de candidatos ({'lat', 'lon', ...}) ou lista vazia.
    """
    if not endereco:
        return []

    modo = get_provider_mode()
    chave = get_google_api_key()

    # A base local é acréscimo, nunca regressão: qualquer problema aqui deixa
    # a cascata exatamente como era antes dela existir.
    de_via = []
    try:
        caminho_cnefe = _base_cnefe_aplicavel(contexto)
        if caminho_cnefe:
            candidatos = CnefeGeocoder.geocode(endereco, contexto, caminho_cnefe)
            if candidatos:
                if candidatos[0].get("preciso"):
                    return candidatos
                de_via = candidatos
    except Exception:
        de_via = []

    provedores = []
    if modo == "auto" and chave:
        provedores.append(GoogleGeocoder)
    provedores.extend([NominatimGeocoder, PhotonGeocoder])

    for provedor in provedores:
        try:
            if provedor is GoogleGeocoder:
                resultados = provedor.geocode(endereco, contexto, chave=chave)
            else:
                resultados = provedor.geocode(endereco, contexto)
        except Exception:
            resultados = []
        if resultados:
            return resultados

    if de_via:
        return de_via

    if contexto and contexto.get("viewbox"):
        try:
            return _degrau_corretor(endereco, contexto)
        except Exception:
            return []

    return []
