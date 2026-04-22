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
    rootChanged  = Signal()            # emitida al terminar de girar

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
        self.rootChanged.emit()

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
# Piano con líneas verticales
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Constantes del lattice
# ---------------------------------------------------------------------------
# El círculo de quintas: C G D A E B F# Db Ab Eb Bb F (= notas * 7 % 12)
# Posición Y de cada pitch-class en el lattice:
#   fila = (pc * 7) % 12   →  0=C, 1=G, 2=D, 3=A, 4=E, 5=B, 6=F#, 7=Db, 8=Ab, 9=Eb, 10=Bb, 11=F
# Con N_REPS repeticiones verticales, el total de filas = 12 * N_REPS

N_REPS = 3   # repeticiones verticales del círculo de quintas (3 o 4)


# ---------------------------------------------------------------------------
# LatticeItem  —  QGraphicsItem con el diagrama de notas
# ---------------------------------------------------------------------------
class LatticeItem(QGraphicsItem):
    """
    Lattice fijo de nodos en coordenadas de escena.
    X = MARGIN + (abs_chrom_pos + 0.5) * bkw
    Y = (total_rows - 1 - row) * row_h   donde row = (pc*7)%12 + rep*12
    Los nodos y sus posiciones son siempre los mismos.
    Lo que cambia con la tonalidad son:
      - tamaño/estilo de los círculos (raíz, escala, fuera)
      - líneas de terceras (solo entre notas de la escala)
      - líneas horizontales de tónica y tritono
    """

    def __init__(self, root_note, scale_mask, scene_w, scene_h,
                 bkw, margin, oct_start, oct_end, parent=None):
        super().__init__(parent)
        self._root      = root_note
        self._mask      = scale_mask
        self._w         = scene_w
        self._h         = scene_h
        self._bkw       = bkw
        self._margin    = margin
        self._oct_start = oct_start
        self._oct_end   = oct_end
        self._n_reps    = N_REPS
        self._row_h     = scene_h / (12 * self._n_reps)

    def update_scale(self, root_note, scale_mask):
        self._root = root_note
        self._mask = scale_mask
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self._w, self._h)

    def _node_pos(self, abs_chrom, rep):
        """Posición (x, y) de un nodo dado su posición cromática absoluta y repetición."""
        pc   = abs_chrom % 12
        row  = (pc * 7) % 12 + rep * 12
        total_rows = 12 * self._n_reps
        x = self._margin + (abs_chrom + 0.5) * self._bkw
        y = self._h - (row + 1) * self._row_h
        return QPointF(x, y)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        n_chrom    = 12 * (self._oct_end - self._oct_start)
        row_h      = self._row_h
        r_node     = max(6.0, self._bkw * 0.55)

        # ── Líneas horizontales: tónica (continua) y tritono (discontinua) ───
        root_row_base   = (self._root * 7) % 12
        tritone_row_base = ((self._root + 6) % 12 * 7) % 12
        total_rows = 12 * self._n_reps

        for rep in range(self._n_reps):
            for (base_row, dashed) in [(root_row_base, False), (tritone_row_base, True)]:
                row = base_row + rep * 12
                y   = self._h - (row + 1) * row_h + row_h / 2
                pen = QPen(QColor(220, 60, 120), 1.2)
                if dashed:
                    pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(0, y), QPointF(self._w, y))

        # ── Líneas de terceras/sextas entre nodos de la escala ───────────────
        # Para cada nodo activo, conectar si el destino también está activo:
        #   Tercera mayor  → (+4 semit, +4 filas)
        #   Tercera menor  → (+3 semit, -3 filas)
        #   Sexta mayor    → (-3 semit, +3 filas)  (inversa de 3ª menor)
        #   Sexta menor    → (-4 semit, -4 filas)  (inversa de 3ª mayor)
        painter.setPen(QPen(QColor(80, 80, 80), 1.2))
        for rep in range(self._n_reps):
            for pos in range(n_chrom):
                pc = pos % 12
                if not (self._mask & (1 << pc)):
                    continue
                row = (pc * 7) % 12

                for dx, dy in [(4, 4), (3, -3), (-3, 3), (-4, -4)]:
                    pos2 = pos + dx
                    if pos2 < 0 or pos2 >= n_chrom:
                        continue
                    pc2 = pos2 % 12
                    if not (self._mask & (1 << pc2)):
                        continue
                    row2  = (pc2 * 7) % 12
                    # rep2: la rep donde row2 + rep2*12 = row + rep*12 + dy
                    target = row + rep * 12 + dy
                    rep2   = (target - row2) // 12
                    if rep2 < 0 or rep2 >= self._n_reps:
                        continue
                    painter.drawLine(self._node_pos(pos,  rep),
                                     self._node_pos(pos2, rep2))

        # ── Nodos ────────────────────────────────────────────────────────────
        for rep in range(self._n_reps):
            for pos in range(n_chrom):
                pc      = pos % 12
                p       = self._node_pos(pos, rep)
                is_root = (pc == self._root)
                in_scale= bool(self._mask & (1 << pc))

                # Color del nodo usando el esquema de quintas
                sat = 1.0 if in_scale else 0.12
                color = note_color(pc, sat, 0.88 if in_scale else 0.9)

                if in_scale:
                    painter.setBrush(QBrush(color))
                    painter.setPen(QPen(QColor(60, 60, 60), 1.5))
                    painter.drawEllipse(p, r_node, r_node)
                else:
                    # Punto pequeño
                    painter.setBrush(QBrush(QColor(180, 180, 180)))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(p, r_node * 0.28, r_node * 0.28)
                    continue   # sin etiqueta ni círculo extra

                # Círculo extra para la tónica
                if is_root:
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(QColor(20, 20, 20), 1.5))
                    painter.drawEllipse(p, r_node + 4, r_node + 4)

                # Etiqueta
                lbl  = NOTE_NAMES[pc]
                font = QFont('monospace', max(5, int(r_node * 0.85)))
                painter.setFont(font)
                painter.setPen(QPen(QColor(20, 20, 20)))
                fm = painter.fontMetrics()
                painter.drawText(
                    int(p.x() - fm.horizontalAdvance(lbl) / 2),
                    int(p.y() + fm.height() / 4),
                    lbl
                )


# ---------------------------------------------------------------------------
# PianoView  —  QGraphicsView con lattice + teclado
# ---------------------------------------------------------------------------
class PianoWidget(QGraphicsView):
    """
    QGraphicsView con dos QGraphicsItems apilados:
      - LatticeItem  (zona superior, height = scene_h - PIANO_H)
      - PianoItem    (zona inferior, height = PIANO_H)
    Comparten la misma unidad cromática bkw.
    """

    WHITE_KEYS   = set([0, 2, 4, 5, 7, 9, 11])
    OCTAVE_START = 2
    OCTAVE_END   = 7
    MARGIN       = 9
    PIANO_H      = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_note  = 0
        self._scale_mask = SCALES['Major']

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QBrush(QColor('#ffffff')))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(300, 300)

        self._build_scene()

    def _bkw_for_width(self, w):
        n_chrom = 12 * (self.OCTAVE_END - self.OCTAVE_START)
        return (w - 2 * self.MARGIN) / n_chrom

    def _build_scene(self):
        W   = 1200.0   # escena en coordenadas lógicas; fitInView la escala
        bkw = self._bkw_for_width(W)
        wkw = bkw * 12.0 / 7.0
        PH  = float(self.PIANO_H)

        # Altura del lattice: N_REPS * 12 filas, cada fila = bkw * 1.8
        row_h    = bkw
        lattice_h = 12 * N_REPS * row_h
        total_h   = lattice_h + PH

        self._lattice_item = LatticeItem(
            self._root_note, self._scale_mask,
            W, lattice_h, bkw, self.MARGIN,
            self.OCTAVE_START, self.OCTAVE_END
        )
        self._piano_item = _PianoGraphicsItem(
            self._root_note, self._scale_mask,
            W, PH, bkw, wkw, self.MARGIN,
            self.OCTAVE_START, self.OCTAVE_END
        )

        self._lattice_item.setPos(0, 0)
        self._piano_item.setPos(0, lattice_h)

        self._scene.addItem(self._lattice_item)
        self._scene.addItem(self._piano_item)
        self._scene.setSceneRect(QRectF(0, 0, W, total_h))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def set_scale(self, root_note, scale_mask):
        self._root_note  = root_note
        self._scale_mask = scale_mask
        self._lattice_item.update_scale(root_note, scale_mask)
        self._piano_item.update_scale(root_note, scale_mask)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)


# ---------------------------------------------------------------------------
# _PianoGraphicsItem  —  teclado como QGraphicsItem
# ---------------------------------------------------------------------------
class _PianoGraphicsItem(QGraphicsItem):

    WHITE_KEYS = set([0, 2, 4, 5, 7, 9, 11])
    BK_H_RATIO = 0.55

    def __init__(self, root_note, scale_mask,
                 width, height, bkw, wkw, margin,
                 oct_start, oct_end, parent=None):
        super().__init__(parent)
        self._root  = root_note
        self._mask  = scale_mask
        self._w     = width
        self._h     = height
        self._bkw   = bkw
        self._wkw   = wkw
        self._mg    = margin
        self._os    = oct_start
        self._oe    = oct_end

    def update_scale(self, root_note, scale_mask):
        self._root = root_note
        self._mask = scale_mask
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        bkw = self._bkw
        wkw = self._wkw
        h   = self._h
        bk_h = h * self.BK_H_RATIO

        # Fondo
        painter.fillRect(QRectF(0, 0, self._w, h), QColor(245, 245, 240))

        # Teclas blancas
        wpos = 0
        for n in range(12 * self._os, 12 * self._oe):
            pc = n % 12
            if pc not in self.WHITE_KEYS:
                continue
            x1 = self._mg + wpos * wkw
            x2 = x1 + wkw
            wpos += 1
            fill = QColor(255, 255, 220) if (pc == self._root) else QColor(255, 255, 255)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(QColor(128, 128, 128), 1))
            painter.drawRect(QRectF(x1, 0, wkw, h))
            lbl  = NOTE_NAMES[pc]
            font = QFont('monospace', max(5, int(wkw * 0.38)))
            painter.setFont(font)
            painter.setPen(QPen(QColor(0, 0, 0)))
            fm = painter.fontMetrics()
            painter.drawText(
                int((x1 + x2) / 2 - fm.horizontalAdvance(lbl) / 2),
                int(h - fm.descent() - 2), lbl
            )

        # Teclas negras
        cpos = 0
        for n in range(12 * self._os, 12 * self._oe):
            pc = n % 12
            x1 = self._mg + cpos * bkw
            x2 = x1 + bkw
            cpos += 1
            if pc in self.WHITE_KEYS:
                continue
            fill = QColor(0, 0, 80) if (pc == self._root) else QColor(0, 0, 0)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(QColor(128, 128, 128), 1))
            painter.drawRect(QRectF(x1, 0, bkw, bk_h))
            lbl  = NOTE_NAMES[pc]
            font = QFont('monospace', max(4, int(bkw * 0.38)))
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 255)))
            fm = painter.fontMetrics()
            painter.drawText(
                int((x1 + x2) / 2 - fm.horizontalAdvance(lbl) / 2),
                int(bk_h - fm.descent() - 2), lbl
            )


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
        self.setMinimumSize(900, 650)

        # Layout raíz: horizontal (rueda | piano+botones)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        # --- Lado izquierdo: rueda + botones de escala ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.wheel_view = ChromaticWheelView()
        self.wheel_view.scaleChanged.connect(self.scaleChanged)
        self.wheel_view.scaleChanged.connect(self._on_scale_changed)
        self.wheel_view.ledToggled.connect(self._on_led_manually_toggled)
        self.wheel_view.rootChanged.connect(self._on_root_changed)
        left_layout.addWidget(self.wheel_view, stretch=1)

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

        left_layout.addWidget(btn_frame)
        root_layout.addWidget(left_widget, stretch=0)

        # Separador vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        root_layout.addWidget(sep)

        # --- Lado derecho: piano con líneas ---
        self.piano = PianoWidget()
        root_layout.addWidget(self.piano, stretch=1)

        # Estado inicial
        self._scale_buttons['Major'].setChecked(True)
        self.piano.set_scale(0, SCALES['Major'])

    def _on_scale_changed(self, root: int, mask: int):
        self.piano.set_scale(root, mask)

    def _on_root_changed(self):
        for btn in self._scale_buttons.values():
            btn.setChecked(False)

    def _on_led_manually_toggled(self, note_index: int, state: bool):
        for btn in self._scale_buttons.values():
            btn.setChecked(False)

    def _on_scale_btn(self, name: str):
        for btn_name, btn in self._scale_buttons.items():
            btn.setChecked(btn_name == name)
        root = self.wheel_view.get_root_note()
        mask = SCALES[name]
        # Rotar la máscara de intervalos relativos a pitch classes absolutos
        rotated = ((mask << root) | (mask >> (12 - root))) & 0xFFF
        self.wheel_view.set_scale_mask(rotated)

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
