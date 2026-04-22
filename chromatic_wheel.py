#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChromaticWheelWidget — PySide6 + QGraphicsView
Disco cromático giratorio con LEDs activables.

Uso standalone:
    python chromatic_wheel.py

Uso embebido:
    from chromatic_wheel import ChromaticWheelWidget
    wheel = ChromaticWheelWidget()
    wheel.show()
    # Conectar señales:
    wheel.scaleChanged.connect(lambda root, mask: print(root, bin(mask)))
"""

import sys
import math

from PySide6.QtCore    import Qt, QPointF, QRectF, Signal, QObject, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui     import (QPainter, QPen, QBrush, QColor, QFont,
                               QRadialGradient, QLinearGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QGraphicsView, QGraphicsScene,
                               QGraphicsItem, QGraphicsEllipseItem,
                               QGraphicsSimpleTextItem, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QFrame,
                               QSizePolicy, QGraphicsObject)

# ---------------------------------------------------------------------------
# Constantes musicales
# ---------------------------------------------------------------------------
NOTE_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

SCALES = {
    'Major':           0b101010110101,   # C D E F G A B
    'Natural minor':   0b010110101101,
    'Harmonic minor':  0b100110101101,
    'Melodic minor':   0b100110101101,
    'Dorian':          0b010110101101,
    'Phrygian':        0b010101101101,
    'Lydian':          0b101010110110,  # corregido
    'Mixolydian':      0b010110110101,  # corregido
    'Penta major':     0b000010010101,  # corregido
    'Penta minor':     0b000100101001,  # corregido
    'Blues':           0b000101101001,
    'Chromatic':       0b111111111111,
}

# Major correcto: C(0) D(2) E(4) F(5) G(7) A(9) B(11)
SCALES['Major']         = (1<<0)|(1<<2)|(1<<4)|(1<<5)|(1<<7)|(1<<9)|(1<<11)
SCALES['Natural minor'] = (1<<0)|(1<<2)|(1<<3)|(1<<5)|(1<<7)|(1<<8)|(1<<10)
SCALES['Harmonic minor']= (1<<0)|(1<<2)|(1<<3)|(1<<5)|(1<<7)|(1<<8)|(1<<11)
SCALES['Melodic minor'] = (1<<0)|(1<<2)|(1<<3)|(1<<5)|(1<<7)|(1<<9)|(1<<11)
SCALES['Dorian']        = (1<<0)|(1<<2)|(1<<3)|(1<<5)|(1<<7)|(1<<9)|(1<<10)
SCALES['Phrygian']      = (1<<0)|(1<<1)|(1<<3)|(1<<5)|(1<<7)|(1<<8)|(1<<10)
SCALES['Lydian']        = (1<<0)|(1<<2)|(1<<4)|(1<<6)|(1<<7)|(1<<9)|(1<<11)
SCALES['Mixolydian']    = (1<<0)|(1<<2)|(1<<4)|(1<<5)|(1<<7)|(1<<9)|(1<<10)
SCALES['Penta major']   = (1<<0)|(1<<2)|(1<<4)|(1<<7)|(1<<9)
SCALES['Penta minor']   = (1<<0)|(1<<3)|(1<<5)|(1<<7)|(1<<10)
SCALES['Blues']         = (1<<0)|(1<<3)|(1<<5)|(1<<6)|(1<<7)|(1<<10)
SCALES['Chromatic']     = 0xFFF

# ---------------------------------------------------------------------------
# Colores (HSV por quintas, igual que en melody_pic.py)
# ---------------------------------------------------------------------------
def note_color(note: int, saturation: float = 1.0, value: float = 1.0) -> QColor:
    hue = 360.0 * ((note * 7) % 12) / 12.0
    c = QColor()
    c.setHsvF(hue / 360.0, saturation, value)
    return c


# ---------------------------------------------------------------------------
# Item: LED (círculo verde activable)
# ---------------------------------------------------------------------------
class LedItem(QGraphicsObject):
    """Pequeño LED verde que se puede encender/apagar con un clic."""

    toggled = Signal(int, bool)   # (note_index, new_state)

    COLOR_ON  = QColor('#1D9E75')
    COLOR_OFF = QColor('#ccc')
    COLOR_ON_DARK = QColor('#5DCAA5')

    def __init__(self, note_index: int, radius: float = 9.0, parent=None):
        super().__init__(parent)
        self.note_index = note_index
        self.radius = radius
        self._on = False
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(10)

    @property
    def on(self): return self._on

    @on.setter
    def on(self, value: bool):
        self._on = value
        self.update()

    def boundingRect(self) -> QRectF:
        r = self.radius + 3
        return QRectF(-r, -r, 2*r, 2*r)

    def paint(self, painter: QPainter, option, widget=None):
        r = self.radius
        painter.setRenderHint(QPainter.Antialiasing)
        if self._on:
            # Brillo suave
            grad = QRadialGradient(0, -r*0.3, r*1.5)
            grad.setColorAt(0.0, QColor('#7FFFD4'))
            grad.setColorAt(0.6, self.COLOR_ON)
            grad.setColorAt(1.0, QColor('#085041'))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor('#0F6E56'), 1.2))
        else:
            painter.setBrush(QBrush(QColor('#ddd')))
            painter.setPen(QPen(QColor('#aaa'), 0.8))
        painter.drawEllipse(QRectF(-r, -r, 2*r, 2*r))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on = not self._on
            self.update()
            self.toggled.emit(self.note_index, self._on)
        event.accept()


# ---------------------------------------------------------------------------
# Item: Nodo de nota (círculo exterior con nombre)
# ---------------------------------------------------------------------------
class NoteItem(QGraphicsObject):

    doubleClicked = Signal(int)   # note_index

    def __init__(self, note_index: int, radius: float = 22.0, parent=None):
        super().__init__(parent)
        self.note_index = note_index
        self.radius = radius
        self._is_root = False
        self.setZValue(5)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.PointingHandCursor)

    def set_root(self, is_root: bool):
        self._is_root = is_root
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            parent = self.parentItem()
            if parent is not None:
                pos_in_parent = parent.mapFromScene(event.scenePos())
                parent._dragging = True
                parent._drag_start_angle = parent._angle_from_pos(pos_in_parent)
                parent._drag_start_rot   = parent.rotation()
                parent._moved_during_drag = False
                parent.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        event.accept()
        parent = self.parentItem()
        if parent is not None and parent._dragging:
            pos_in_parent = parent.mapFromScene(event.scenePos())
            cur_angle = parent._angle_from_pos(pos_in_parent)
            delta = cur_angle - parent._drag_start_angle
            while delta > 180:  delta -= 360
            while delta < -180: delta += 360
            parent.setRotation(parent._drag_start_rot + delta)
            parent._moved_during_drag = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            parent = self.parentItem()
            if parent is not None and parent._dragging:
                parent._dragging = False
                parent.setCursor(Qt.OpenHandCursor)
                if parent._moved_during_drag:
                    parent.snap_to_nearest()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            parent = self.parentItem()
            if parent is not None:
                parent._dragging = False
                parent.setCursor(Qt.OpenHandCursor)
            self.doubleClicked.emit(self.note_index)
        event.accept()

    def boundingRect(self) -> QRectF:
        r = self.radius + 2
        return QRectF(-r, -r, 2*r, 2*r)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.radius
        note = self.note_index

        base_color = note_color(note, 0.75, 0.92)
        dim_color  = note_color(note, 0.15, 0.95)
        border_color = note_color(note, 0.9, 0.55)

        if self._is_root:
            painter.setBrush(QBrush(base_color))
            pen = QPen(border_color, 2.5)
        else:
            painter.setBrush(QBrush(dim_color))
            pen = QPen(border_color.darker(110), 1.0)

        painter.setPen(pen)
        painter.drawEllipse(QRectF(-r, -r, 2*r, 2*r))

        # Texto — se contrarresta la rotación del disco para que siempre
        # se lea horizontal, independientemente de la posición del disco.
        font = QFont('Arial', 9 if '#' in NOTE_NAMES[note] or 'b' in NOTE_NAMES[note] else 10)
        font.setBold(self._is_root)
        painter.setFont(font)
        painter.setPen(QPen(QColor('#222') if not self._is_root else QColor('#111')))
        parent = self.parentItem()
        counter_rot = -parent.rotation() if parent is not None else 0.0
        painter.save()
        painter.rotate(counter_rot)
        painter.drawText(QRectF(-r, -r, 2*r, 2*r),
                         Qt.AlignCenter, NOTE_NAMES[note])
        painter.restore()


# ---------------------------------------------------------------------------
# El disco giratorio (QGraphicsItem contenedor)
# ---------------------------------------------------------------------------
class WheelItem(QGraphicsObject):
    """
    Disco que contiene los 12 NoteItems y 12 LedItems.
    Se puede rotar arrastrando con el ratón.
    Emite rotationSnapped cuando termina de girar.
    """

    ledToggled   = Signal(int, bool)   # (note_index, state)
    rotationDone = Signal()

    R_NOTE = 145   # radio al centro de los círculos de nota
    R_LED  = 95    # radio al centro de los LEDs
    R_DISC = 175   # radio del disco exterior
    R_INNER= 70    # radio del hueco central

    def __init__(self, parent=None):
        super().__init__(parent)
        self._leds  = [False] * 12
        self._notes = []
        self._led_items = []
        self._root_note = 0          # índice de la nota arriba (en coords locales)
        self._dragging = False
        self._drag_start_angle = 0.0
        self._drag_start_rot   = 0.0
        self._moved_during_drag = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(1)

        self._build_items()

    # -- construcción --------------------------------------------------------

    def _build_items(self):
        for i in range(12):
            note_item = NoteItem(i, radius=20, parent=self)
            pos = self._note_pos(i, self.R_NOTE)
            note_item.setPos(pos)
            note_item.doubleClicked.connect(self.rotate_to_note)
            self._notes.append(note_item)

            led = LedItem(i, radius=9, parent=self)
            led.setPos(self._note_pos(i, self.R_LED))
            led.toggled.connect(self.ledToggled)
            self._led_items.append(led)

    def _note_pos(self, i: int, r: float) -> QPointF:
        angle = 2 * math.pi * i / 12 - math.pi / 2
        return QPointF(r * math.cos(angle), r * math.sin(angle))

    # -- API pública ---------------------------------------------------------

    def set_led(self, note_index: int, on: bool):
        self._leds[note_index] = on
        self._led_items[note_index].on = on

    def get_led(self, note_index: int) -> bool:
        return self._leds[note_index]

    def get_scale_mask(self) -> int:
        """Devuelve bitmask de 12 bits con los LEDs activos."""
        mask = 0
        for i in range(12):
            if self._led_items[i].on:
                mask |= (1 << i)
        return mask

    def get_root_note(self) -> int:
        """Nota que está actualmente arriba (índice 0-11 cromático)."""
        rot_deg = self.rotation()
        # Cada nota ocupa 30°. La nota 0 empieza arriba (−90°).
        # Cuánto hemos girado en pasos de 30°:
        steps = round(rot_deg / 30.0) % 12
        # La nota arriba es la nota en posición 0 girada -steps
        return (-steps) % 12

    def rotate_to_note(self, note_index: int):
        """Gira el disco para que note_index quede arriba, por el camino más corto."""
        # Rotación actual normalizada a múltiplo de 30°
        current = self.rotation()
        current_steps = round(current / 30.0)
        # Cuántos pasos necesitamos para que note_index esté arriba:
        # la nota arriba es (-current_steps) % 12, queremos note_index arriba
        current_root = (-current_steps) % 12
        delta_steps = (current_root - note_index) % 12
        # Elegir el giro más corto (≤ 6 pasos)
        if delta_steps > 6:
            delta_steps -= 12
        target = (current_steps + delta_steps) * 30.0

        if hasattr(self, '_anim') and self._anim.state() != QPropertyAnimation.Stopped:
            self._anim.stop()

        self._anim = QPropertyAnimation(self, b"rotation")
        self._anim.setDuration(max(120, abs(delta_steps) * 60))
        self._anim.setStartValue(current)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_snap_finished)
        self._anim.start()

    def snap_to_nearest(self):
        """Anima el disco para que quede alineado a la nota más cercana."""
        current = self.rotation()
        nearest = round(current / 30.0) * 30.0
        if abs(nearest - current) < 0.5:
            self.setRotation(nearest)
            self._update_root_highlight()
            self.rotationDone.emit()
            return

        self._anim = QPropertyAnimation(self, b"rotation")
        self._anim.setDuration(160)
        self._anim.setStartValue(current)
        self._anim.setEndValue(nearest)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_snap_finished)
        self._anim.start()

    def _on_snap_finished(self):
        self._update_root_highlight()
        self.rotationDone.emit()

    def _update_root_highlight(self):
        root = self.get_root_note()
        for i, note_item in enumerate(self._notes):
            note_item.set_root(i == root)

    # -- QGraphicsObject interface -------------------------------------------

    def boundingRect(self) -> QRectF:
        r = self.R_DISC + 5
        return QRectF(-r, -r, 2*r, 2*r)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # Disco exterior
        painter.setBrush(QBrush(QColor('#f7f6f2')))
        painter.setPen(QPen(QColor('#bbb'), 1.5))
        painter.drawEllipse(QRectF(-self.R_DISC, -self.R_DISC,
                                   2*self.R_DISC, 2*self.R_DISC))

        # Hueco central
        painter.setBrush(QBrush(QColor('#ffffff')))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-self.R_INNER, -self.R_INNER,
                                   2*self.R_INNER, 2*self.R_INNER))

    # -- Interacción ratón ---------------------------------------------------

    def _angle_from_pos(self, pos: QPointF) -> float:
        return math.degrees(math.atan2(pos.y(), pos.x()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_angle = self._angle_from_pos(event.pos())
            self._drag_start_rot   = self.rotation()
            self._moved_during_drag = False
            self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        if self._dragging:
            cur_angle = self._angle_from_pos(event.pos())
            delta = cur_angle - self._drag_start_angle
            # Normalizar delta para evitar saltos en ±180°
            while delta > 180:  delta -= 360
            while delta < -180: delta += 360
            new_rot = self._drag_start_rot + delta
            self.setRotation(new_rot)
            self._moved_during_drag = True
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor)
            if self._moved_during_drag:
                self.snap_to_nearest()
        event.accept()

    def wheelEvent(self, event):
        delta = event.delta()
        steps = 1 if delta > 0 else -1
        current = self.rotation()
        target  = round(current / 30.0) * 30.0 + steps * 30.0
        self._anim = QPropertyAnimation(self, b"rotation")
        self._anim.setDuration(120)
        self._anim.setStartValue(current)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_snap_finished)
        self._anim.start()
        event.accept()


# ---------------------------------------------------------------------------
# Indicador central (root + notas activas) — item fijo en la escena
# ---------------------------------------------------------------------------
class CenterInfoItem(QGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = 'C'
        self._notes = 'C D E F G A B'
        self.setZValue(20)

    def set_info(self, root: str, notes: str):
        self._root = root
        self._notes = notes
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-65, -28, 130, 56)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        font_big = QFont('Arial', 22, QFont.Bold)
        font_small = QFont('Arial', 8)

        painter.setFont(font_big)
        painter.setPen(QPen(QColor('#222')))
        painter.drawText(QRectF(-65, -28, 130, 34), Qt.AlignCenter, self._root)

        painter.setFont(font_small)
        painter.setPen(QPen(QColor('#666')))
        painter.drawText(QRectF(-65, 8, 130, 20), Qt.AlignCenter, self._notes)


# ---------------------------------------------------------------------------
# Marcador de root (triángulo fijo en la parte superior de la vista)
# ---------------------------------------------------------------------------
class RootMarkerItem(QGraphicsItem):
    def __init__(self, y_pos: float = -168, parent=None):
        super().__init__(parent)
        self.y_pos = y_pos
        self.setZValue(30)

    def boundingRect(self) -> QRectF:
        return QRectF(-8, self.y_pos - 2, 16, 14)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor('#E24B4A')))
        painter.setPen(Qt.NoPen)
        y = self.y_pos
        from PySide6.QtGui import QPolygonF
        painter.drawPolygon(QPolygonF([
            QPointF(0, y + 12),
            QPointF(-7, y),
            QPointF(7, y),
        ]))


# ---------------------------------------------------------------------------
# La vista principal
# ---------------------------------------------------------------------------
class ChromaticWheelView(QGraphicsView):
    """
    QGraphicsView que contiene el disco cromático.
    Señales:
        scaleChanged(root_note: int, scale_mask: int)
    """

    scaleChanged = Signal(int, int)
    ledToggled   = Signal(int, bool)   # reenviada desde WheelItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QBrush(QColor('#faf9f7')))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(420, 420)

        SIZE = 220
        self._scene.setSceneRect(-SIZE, -SIZE, 2*SIZE, 2*SIZE)

        # Items
        self._wheel = WheelItem()
        self._scene.addItem(self._wheel)

        self._center_info = CenterInfoItem()
        self._scene.addItem(self._center_info)

        self._root_marker = RootMarkerItem(y_pos=-168)
        self._scene.addItem(self._root_marker)

        # Conectar señales
        self._wheel.ledToggled.connect(self._on_led_toggled)
        self._wheel.ledToggled.connect(self.ledToggled)
        self._wheel.rotationDone.connect(self._on_rotation_done)

        # Estado inicial: C Major
        self.set_scale_mask(SCALES['Major'])
        self._wheel._update_root_highlight()
        self._update_info()

    # -- API -----------------------------------------------------------------

    def set_scale_mask(self, mask: int):
        for i in range(12):
            self._wheel.set_led(i, bool(mask & (1 << i)))
        self._update_info()

    def get_scale_mask(self) -> int:
        return self._wheel.get_scale_mask()

    def get_root_note(self) -> int:
        return self._wheel.get_root_note()

    def rotate_to_root(self, note_index: int):
        """Gira el disco para que la nota dada quede arriba."""
        current_root = self.get_root_note()
        steps = (current_root - note_index) % 12
        target_rot = self._wheel.rotation() + steps * 30.0
        self._wheel._anim = QPropertyAnimation(self._wheel, b"rotation")
        self._wheel._anim.setDuration(300)
        self._wheel._anim.setStartValue(self._wheel.rotation())
        self._wheel._anim.setEndValue(target_rot)
        self._wheel._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._wheel._anim.finished.connect(self._wheel._on_snap_finished)
        self._wheel._anim.finished.connect(self._update_info)
        self._wheel._anim.start()

    # -- Slots internos ------------------------------------------------------

    def _on_led_toggled(self, note_index: int, state: bool):
        self._update_info()

    def _on_rotation_done(self):
        self._update_info()

    def _update_info(self):
        root = self._wheel.get_root_note()
        mask = self._wheel.get_scale_mask()

        # Notas activas en orden desde la raíz
        active = []
        for i in range(12):
            ni = (root + i) % 12
            if mask & (1 << ni):
                active.append(NOTE_NAMES[ni])

        self._center_info.set_info(NOTE_NAMES[root], ' '.join(active))
        self.scaleChanged.emit(root, mask)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)


# ---------------------------------------------------------------------------
# Widget completo con botones de escala
# ---------------------------------------------------------------------------
class ChromaticWheelWidget(QWidget):
    """
    Widget completo: ChromaticWheelView + botones de escala predefinidos.
    Señal: scaleChanged(root_note: int, scale_mask: int)
    """

    scaleChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Chromatic Scale Wheel')
        self.setMinimumSize(480, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.wheel_view = ChromaticWheelView()
        self.wheel_view.scaleChanged.connect(self.scaleChanged)
        self.wheel_view.ledToggled.connect(self._on_led_manually_toggled)
        layout.addWidget(self.wheel_view, stretch=1)

        # Botones de escalas
        btn_frame = QFrame()
        btn_layout = QVBoxLayout(btn_frame)
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self._scale_buttons = {}
        scales_rows = [
            ['Major', 'Natural minor', 'Harmonic minor', 'Melodic minor'],
            ['Dorian', 'Phrygian', 'Lydian', 'Mixolydian'],
            ['Penta major', 'Penta minor', 'Blues', 'Chromatic'],
        ]
        for row in scales_rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(4)
            for name in row:
                btn = QPushButton(name)
                btn.setCheckable(True)
                btn.setFixedHeight(26)
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 11px;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        background: #fff;
                        padding: 0 4px;
                    }
                    QPushButton:hover { background: #f0f0ee; }
                    QPushButton:checked {
                        background: #E1F5EE;
                        border-color: #1D9E75;
                        color: #0F6E56;
                        font-weight: bold;
                    }
                """)
                btn.clicked.connect(lambda checked, n=name: self._on_scale_btn(n))
                self._scale_buttons[name] = btn
                row_layout.addWidget(btn)
            btn_layout.addLayout(row_layout)

        # Botón limpiar
        clear_btn = QPushButton('Limpiar todo')
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: #fff;
            }
            QPushButton:hover { background: #f0eee8; }
        """)
        clear_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(clear_btn)

        layout.addWidget(btn_frame)

        # Activar Major por defecto
        self._scale_buttons['Major'].setChecked(True)

    def _on_led_manually_toggled(self, note_index: int, state: bool):
        for btn in self._scale_buttons.values():
            btn.setChecked(False)

    def _on_scale_btn(self, name: str):
        for btn_name, btn in self._scale_buttons.items():
            btn.setChecked(btn_name == name)
        self.wheel_view.set_scale_mask(SCALES[name])

    def _clear_all(self):
        for btn in self._scale_buttons.values():
            btn.setChecked(False)
        self.wheel_view.set_scale_mask(0)

    # -- API de conveniencia -------------------------------------------------

    def get_root_note(self) -> int:
        return self.wheel_view.get_root_note()

    def get_scale_mask(self) -> int:
        return self.wheel_view.get_scale_mask()

    def set_scale_mask(self, mask: int):
        self.wheel_view.set_scale_mask(mask)

    def rotate_to_root(self, note_index: int):
        self.wheel_view.rotate_to_root(note_index)


# ---------------------------------------------------------------------------
# Main standalone
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    widget = ChromaticWheelWidget()

    # Demo: imprimir escala al cambiar
    def on_change(root, mask):
        active = [NOTE_NAMES[(root + i) % 12]
                  for i in range(12) if mask & (1 << ((root + i) % 12))]
        print(f"Root: {NOTE_NAMES[root]:3s}  mask: {mask:012b}  notes: {' '.join(active)}")

    widget.scaleChanged.connect(on_change)
    widget.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
