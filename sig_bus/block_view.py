# -*- coding: utf-8 -*-
"""
/***************************************************************************
 block_view — viewport do Diagrama de Blocos (SIG-Bus)
                                 A QGIS plugin
 QGraphicsView com zoom (roda do mouse), pan (botão do meio) e exportação
 para PNG/SVG. Não conhece o modelo — só exibe a BlockScene.
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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtWidgets import QGraphicsView


class BlockView(QGraphicsView):
    """View do diagrama: zoom na roda, pan no botão do meio."""

    _ZOOM_STEP = 1.15
    _MIN_SCALE = 0.15
    _MAX_SCALE = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setBackgroundBrush(Qt.white)
        self._scale = 1.0
        self._panning = False
        self._pan_last = None

    # --- Zoom -----------------------------------------------------------
    def wheelEvent(self, event):
        factor = self._ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self._ZOOM_STEP
        new_scale = self._scale * factor
        if new_scale < self._MIN_SCALE or new_scale > self._MAX_SCALE:
            return
        self._scale = new_scale
        self.scale(factor, factor)

    def reset_zoom(self):
        self.resetTransform()
        self._scale = 1.0

    def fit_all(self):
        """Enquadra a cena inteira na viewport (todas as faixas visíveis).

        Sem isso, uma linha movimentada gera uma faixa de ida muito alta que
        empurra a faixa de volta para fora da tela."""
        scene = self.scene()
        if scene is None:
            return
        self.resetTransform()
        self.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
        # Registra a escala resultante para os limites de zoom funcionarem.
        self._scale = self.transform().m11() or 1.0

    # --- Pan (botão do meio) -------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- Exportação -----------------------------------------------------
    def export_png(self, path, scale=2.0):
        """Renderiza a cena inteira num PNG. scale aumenta a resolução."""
        scene = self.scene()
        if scene is None:
            return False
        rect = scene.sceneRect()
        img = QImage(int(rect.width() * scale), int(rect.height() * scale),
                     QImage.Format_ARGB32)
        img.fill(Qt.white)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        scene.render(painter, target=img.rect(), source=rect)
        painter.end()
        return img.save(path, 'PNG')

    def export_svg(self, path):
        """Renderiza a cena num SVG (QtSvg pode não estar disponível)."""
        try:
            from qgis.PyQt.QtSvg import QSvgGenerator
        except ImportError:
            return False
        scene = self.scene()
        if scene is None:
            return False
        rect = scene.sceneRect()
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(rect.size().toSize())
        gen.setViewBox(rect)
        gen.setTitle('Diagrama de Blocos — SIG-Bus')
        painter = QPainter(gen)
        scene.render(painter, source=rect)
        painter.end()
        return True
