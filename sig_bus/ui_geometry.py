# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ui_geometry — Geometria das janelas do SIG-Bus
                                 A QGIS plugin
 A regra de "a janela cabe na tela em que abre" mora aqui, não solta dentro
 do diálogo (decisão 154). As contas são puras — não importam Qt — e por isso
 rodam em teste comum; só `preparar_janela` e `restaurar_se_couber` tocam um
 widget de verdade, e nem elas podem levantar exceção em ambiente headless.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Respiro deixado entre a janela e a borda da área útil da tela.
MARGEM_TELA = 48


def _clampar(desejado, disponivel, margem):
    """Um eixo do clamp da decisão 148: nunca maior que a área útil menos a
    margem, nunca menor que a área útil quando ela é minúscula, nunca ≤ 0."""
    desejado = int(desejado or 0)
    disponivel = int(disponivel or 0)
    limite = disponivel - int(margem or 0)
    if limite <= 0:
        limite = disponivel          # área útil menor que a margem: usa ela inteira
    if limite <= 0:
        limite = desejado            # sem área útil conhecida: fica com o desejado
    valor = min(desejado, limite) if desejado > 0 else limite
    return max(1, valor)


def ajustar_ao_disponivel(desejado_w, desejado_h, disp_w, disp_h,
                          margem=MARGEM_TELA):
    """Tamanho de janela que cabe na área útil (decisão 148).

    O clamp é sempre para baixo: em tela grande devolve o desejado intacto;
    em tela pequena devolve o que cabe. Nunca devolve valor ≤ 0 — geometria
    zero é janela invisível, não janela pequena."""
    return (_clampar(desejado_w, disp_w, margem),
            _clampar(desejado_h, disp_h, margem))


def divisao_splitter(largura_total, fracao=0.55, min_esq=340, min_dir=280):
    """Divide `largura_total` entre os dois painéis do splitter (decisão 151).

    Devolve `[esq, dir]` somando exatamente a largura total. Quando ela não
    comporta os dois mínimos, divide proporcionalmente em vez de zerar um
    lado — painel de largura zero é indistinguível de "sumiu"."""
    total = int(largura_total or 0)
    if total <= 0:
        return [int(min_esq), int(min_dir)]
    if total < int(min_esq) + int(min_dir):
        esq = int(round(total * fracao))
        esq = min(max(esq, 1), total - 1) if total >= 2 else total
        return [esq, total - esq]
    esq = int(round(total * fracao))
    esq = min(max(esq, int(min_esq)), total - int(min_dir))
    return [esq, total - esq]


def cabe_na_tela(x, y, w, h, ax, ay, aw, ah):
    """Diz se o retângulo da janela está contido na área útil (decisão 152).

    É o que impede devolver ao notebook a janela deixada num monitor de
    2560 px: geometria salva que não cabe é descartada."""
    if w <= 0 or h <= 0:
        return False
    return (x >= ax and y >= ay
            and x + w <= ax + aw and y + h <= ay + ah)


# ---------------------------------------------------------------------------
# Aplicação sobre um widget (única parte que toca Qt)
# ---------------------------------------------------------------------------

def _tela_de(widget, tela=None):
    """A tela do próprio widget quando houver; senão a primária. `None` em
    ambiente sem tela resolvível — quem chama tem de aguentar."""
    if tela is not None:
        return tela
    try:
        tela = widget.screen()
    except Exception:
        tela = None
    if tela is not None:
        return tela
    try:
        from qgis.PyQt.QtWidgets import QApplication
        return QApplication.primaryScreen()
    except Exception:
        return None


def preparar_janela(widget, largura, altura, tela=None):
    """Redimensiona `widget` para o que cabe na tela, liga os botões de
    maximizar/minimizar (decisão 149) e centraliza na área útil.

    Sem tela resolvível, só redimensiona — em ambiente headless a função não
    pode levantar exceção."""
    from qgis.PyQt.QtCore import Qt

    widget.setWindowFlags(widget.windowFlags()
                          | Qt.WindowType.WindowMaximizeButtonHint
                          | Qt.WindowType.WindowMinimizeButtonHint)

    alvo = _tela_de(widget, tela)
    area = None
    if alvo is not None:
        try:
            area = alvo.availableGeometry()
        except Exception:
            area = None

    if area is None:
        widget.resize(int(largura), int(altura))
        return

    w, h = ajustar_ao_disponivel(largura, altura, area.width(), area.height())
    widget.resize(w, h)
    widget.move(area.x() + max(0, (area.width() - w) // 2),
                area.y() + max(0, (area.height() - h) // 2))


def restaurar_se_couber(widget, geometria_salva, tela=None):
    """Aplica uma geometria salva (`QWidget.saveGeometry`) só se a janela
    resultante ainda couber na área útil da tela atual (decisão 152).

    Devolve `True` quando a geometria salva ficou valendo. Quando não cabe —
    ou quando não há geometria salva —, o widget fica exatamente como estava
    (isto é, com o resultado de `preparar_janela`)."""
    if not geometria_salva:
        return False

    anterior = widget.saveGeometry()
    try:
        if not widget.restoreGeometry(geometria_salva):
            widget.restoreGeometry(anterior)
            return False
    except Exception:
        return False

    alvo = _tela_de(widget, tela)
    area = None
    if alvo is not None:
        try:
            area = alvo.availableGeometry()
        except Exception:
            area = None
    if area is None:
        return True

    g = widget.frameGeometry()
    if cabe_na_tela(g.x(), g.y(), g.width(), g.height(),
                    area.x(), area.y(), area.width(), area.height()):
        return True

    widget.restoreGeometry(anterior)
    return False
