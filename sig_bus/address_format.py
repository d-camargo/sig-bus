"""Módulo puro para formatação e análise de endereços de paradas de ônibus.

Não importa Qt nem QGIS.
"""

import unicodedata

ADDRESS_PATTERN_HINT = (
    "Padrão: Logradouro, Número - Bairro (bairro opcional). "
    "Município e UF vêm da configuração da agência."
)

ADDRESS_PLACEHOLDER = "Rua Giuseppe Fórmolo, 210 - Centro"


def _is_number_like(s: str) -> bool:
    """Verifica se uma string parece um número de endereço."""
    if not s:
        return False
    s_clean = s.strip().lower()
    if any(s_clean.startswith(prefix) for prefix in ["s/n", "sn", "sem num", "sem n"]):
        return True
    return any(c.isdigit() for c in s_clean)


def parse_address(texto: str) -> dict:
    """Analisa uma string de endereço no padrão do SIG-Bus.

    Retorna um dicionário com as chaves:
    - 'logradouro': str
    - 'numero': str ou None
    - 'bairro': str ou None

    Tolerante a:
    - Bairro ausente
    - Número ausente
    - '-' ou ',' como separador do bairro
    - Espaços em excesso
    - String vazia (não levanta exceção)
    """
    if not texto or not texto.strip():
        return {"logradouro": "", "numero": None, "bairro": None}

    txt = texto.strip()

    # Se houver vírgula(s), dividimos por vírgula
    parts = [p.strip() for p in txt.split(",") if p.strip()]

    if len(parts) >= 3:
        # Ex: "Rua A, 210, Centro"
        logradouro = parts[0]
        numero = parts[1]
        bairro = ", ".join(parts[2:])
        return {
            "logradouro": logradouro,
            "numero": numero if numero else None,
            "bairro": bairro if bairro else None,
        }

    if len(parts) == 2:
        # Ex: "Rua Giuseppe Fórmolo, 210 - Centro" ou "Rua Giuseppe Fórmolo, 210" ou "Rua Giuseppe Fórmolo, Centro"
        logradouro = parts[0]
        rest = parts[1]

        if "-" in rest:
            num_part, bairro_part = rest.split("-", 1)
            num_str = num_part.strip()
            bairro_str = bairro_part.strip()
            return {
                "logradouro": logradouro,
                "numero": num_str if num_str else None,
                "bairro": bairro_str if bairro_str else None,
            }
        else:
            if _is_number_like(rest):
                return {
                    "logradouro": logradouro,
                    "numero": rest,
                    "bairro": None,
                }
            else:
                return {
                    "logradouro": logradouro,
                    "numero": None,
                    "bairro": rest,
                }

    # len(parts) == 1 (sem vírgulas)
    # Ex: "Rua Giuseppe Fórmolo - Centro" ou "Rua Giuseppe Fórmolo"
    if " - " in txt:
        log_part, bairro_part = txt.split(" - ", 1)
        return {
            "logradouro": log_part.strip(),
            "numero": None,
            "bairro": bairro_part.strip() if bairro_part.strip() else None,
        }
    elif "-" in txt:
        # Pode ser "Rua A - Centro" ou "Rua BR-101"
        # Se contiver ' - ' já cobrimos. Se for '-', verifica se lado direito parece bairro ou número
        left, right = txt.rsplit("-", 1)
        left_str = left.strip()
        right_str = right.strip()
        # Se o lado esquerdo for muito curto (ex BR-101) e o direito for só dígitos, é logradouro único
        if left_str.isupper() and len(left_str) <= 3 and right_str.isdigit():
            return {
                "logradouro": txt,
                "numero": None,
                "bairro": None,
            }
        return {
            "logradouro": left_str,
            "numero": None,
            "bairro": right_str if right_str else None,
        }
    else:
        return {
            "logradouro": txt,
            "numero": None,
            "bairro": None,
        }


def normalizar_logradouro(texto: str) -> str:
    """Normaliza um logradouro para comparação: minúsculas, sem acentos
    (via unicodedata.normalize('NFKD', ...)) e espaços colapsados.

    Usada para detectar quando a geocodificação aceitou um candidato com
    grafia diferente da digitada (decisão 59), sem afetar o texto exibido.
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())


def format_address(partes: dict) -> str:
    """Reconstrói uma string de endereço canônica a partir de um dicionário.

    Caminho inverso de parse_address. Entrada esperada:
    dict com chaves 'logradouro', 'numero', 'bairro'.
    """
    if not partes:
        return ""

    logradouro = (partes.get("logradouro") or "").strip()
    numero = partes.get("numero")
    if numero is not None:
        numero = str(numero).strip()
        if not numero:
            numero = None

    bairro = partes.get("bairro")
    if bairro is not None:
        bairro = str(bairro).strip()
        if not bairro:
            bairro = None

    if not logradouro:
        return ""

    if numero and bairro:
        return f"{logradouro}, {numero} - {bairro}"
    elif numero:
        return f"{logradouro}, {numero}"
    elif bairro:
        return f"{logradouro} - {bairro}"
    else:
        return logradouro
