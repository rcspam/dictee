#!/usr/bin/env python3
"""Test window showing 3 pipeline diagram styles side by side.

Run: python3 test_pipeline_styles.py
"""
import os
import sys
import base64
from PyQt6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QFontMetrics, QIcon, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox
)
from PyQt6.QtSvgWidgets import QSvgWidget


ICON_SIZE = 32
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(_PROJECT_DIR, "assets", "icons")

def icon_path(name, theme):
    suffix = "dark" if theme == "dark" else "light"
    return os.path.join(ASSETS_DIR, f"{name}-{suffix}.svg")


def load_pixmap(path, size=ICON_SIZE):
    ic = QIcon(path)
    if not ic.isNull():
        pm = ic.pixmap(size, size)
        if not pm.isNull():
            return pm
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#3daee9"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.end()
    return pm


def pixmap_to_base64(pm):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return base64.b64encode(bytes(ba)).decode("ascii")


# Default pipeline steps (label, enabled)
DEFAULT_STEPS = [
    ("Numbers", True),
    ("Capitalization", True),
    ("Rules", True),
    ("Dict", True),
    ("Continuation", True),
    ("LLM", True),
]

ACCENT = "#3daee9"
ACCENT_DARK = "#2980b9"

THEMES = {
    "dark": {
        "window_bg": "#2b2b2b",
        "panel_bg": "#353535",
        "fg": "#fcfcfc",
        "disabled_text": "#5a5a5a",  # dark on dark
        "disabled_bg": "#3a3a3a",
        "disabled_border": "#555555",
    },
    "light": {
        "window_bg": "#f5f5f5",
        "panel_bg": "#ffffff",
        "fg": "#232629",
        "disabled_text": "#bcbcbc",  # light on light
        "disabled_bg": "#e6e6e6",
        "disabled_border": "#c0c0c0",
    },
}


# Style 1 — QLabel HTML
class HtmlPipeline(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self._steps = DEFAULT_STEPS
        self._theme = "dark"
        self._reload_icons()

    def _reload_icons(self):
        self._in_b64 = pixmap_to_base64(load_pixmap(
            icon_path("audio-input-microphone-low-symbolic", self._theme)))
        self._out_b64 = pixmap_to_base64(load_pixmap(
            icon_path("workspacelistentryicon-pencilandpaper-symbolic", self._theme)))

    def set_theme(self, theme):
        self._theme = theme
        self._reload_icons()
        self._render()

    def set_steps(self, steps):
        self._steps = steps
        self._render()

    def _render(self):
        t = THEMES[self._theme]
        steps = self._steps

        def endpoint(b64):
            return (f'<img src="data:image/png;base64,{b64}" '
                    f'width="{ICON_SIZE}" height="{ICON_SIZE}" '
                    f'style="vertical-align:middle;"/>')

        def arrow(on):
            return (f'<span style="color:{ACCENT};font-size:18px;'
                    f'font-weight:bold;"> &rarr; </span>')

        parts = [endpoint(self._in_b64), arrow(steps[0][1] if steps else True)]
        for i, (label, on) in enumerate(steps):
            color = "white" if on else t["disabled_text"]
            bg = ACCENT if on else t["disabled_bg"]
            border = ACCENT_DARK if on else t["disabled_border"]
            border_style = "solid" if on else "dashed"
            extra = "" if on else (f"text-decoration:line-through;"
                                    f"text-decoration-color:{ACCENT};")
            parts.append(
                f'<span style="background:{bg};color:{color};'
                f'border:2px {border_style} {border};border-radius:6px;'
                f'padding:4px 10px;font-weight:bold;{extra}">{label}</span>'
            )
            if i < len(steps) - 1:
                parts.append(arrow(on and steps[i + 1][1]))
        parts.append(arrow(steps[-1][1] if steps else True))
        parts.append(endpoint(self._out_b64))
        self.setText('<div style="line-height:2.2;">' + "".join(parts) + "</div>")


# Style 2 — Custom QWidget
class WidgetPipeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps = DEFAULT_STEPS
        self._theme = "dark"
        self._reload_icons()
        self.setMinimumHeight(70)

    def _reload_icons(self):
        self._in_pm = load_pixmap(
            icon_path("audio-input-microphone-low-symbolic", self._theme))
        self._out_pm = load_pixmap(
            icon_path("workspacelistentryicon-pencilandpaper-symbolic", self._theme))

    def set_theme(self, theme):
        self._theme = theme
        self._reload_icons()
        self.update()

    def set_steps(self, steps):
        self._steps = steps
        self.update()

    def paintEvent(self, _ev):
        t = THEMES[self._theme]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)

        pad_x = 14
        gap = 28
        h = 36
        ep_r = ICON_SIZE // 2
        boxes = [fm.horizontalAdvance(label) + pad_x * 2 for label, _on in self._steps]
        total_w = ep_r * 4 + gap * 2 + sum(boxes) + gap * (len(boxes) - 1)
        x = max(10, (self.width() - total_w) // 2)
        y = (self.height() - h) // 2
        cy = y + h / 2

        def draw_arrow(x1, x2, _on=True):
            col = QColor(ACCENT)
            p.setPen(QPen(col, 2))
            p.drawLine(QPointF(x1, cy), QPointF(x2, cy))
            p.drawLine(QPointF(x2, cy), QPointF(x2 - 6, cy - 4))
            p.drawLine(QPointF(x2, cy), QPointF(x2 - 6, cy + 4))

        def draw_endpoint(cx, pm):
            rect = QRectF(cx - ep_r, cy - ep_r, ep_r * 2, ep_r * 2)
            p.drawPixmap(rect.toRect(), pm)

        # IN
        draw_endpoint(x + ep_r, self._in_pm)
        seg_start = x + ep_r * 2
        draw_arrow(seg_start + 4, seg_start + gap - 4,
                   self._steps[0][1] if self._steps else True)
        x = seg_start + gap

        for i, ((label, on), bw) in enumerate(zip(self._steps, boxes)):
            rect = QRectF(x, y, bw, h)
            bg = QColor(ACCENT if on else t["disabled_bg"])
            border = QColor(ACCENT_DARK if on else t["disabled_border"])
            text_col = QColor("white" if on else t["disabled_text"])
            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)
            p.fillPath(path, QBrush(bg))
            pen = QPen(border, 1.8)
            if not on:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawPath(path)
            p.setPen(text_col)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

            # Bypass arrow crossing the disabled box
            if not on:
                p.setPen(QPen(QColor(ACCENT), 2))
                p.drawLine(QPointF(x - 2, cy), QPointF(x + bw + 2, cy))

            if i < len(self._steps) - 1:
                next_on = self._steps[i + 1][1]
                draw_arrow(x + bw + 4, x + bw + gap - 4, on and next_on)
            x += bw + gap

        # final arrow + OUT (x already advanced past last box+gap)
        last_on = self._steps[-1][1] if self._steps else True
        draw_arrow(x - gap + 4 + 0, x - 4, last_on)
        draw_endpoint(x + ep_r, self._out_pm)
        p.end()


# Style 3 — SVG embedded
class SvgPipeline(QSvgWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._steps = DEFAULT_STEPS
        self._reload_icons()
        self.setMinimumHeight(80)
        self._render()

    def _reload_icons(self):
        self._in_b64 = pixmap_to_base64(load_pixmap(
            icon_path("audio-input-microphone-low-symbolic", self._theme)))
        self._out_b64 = pixmap_to_base64(load_pixmap(
            icon_path("workspacelistentryicon-pencilandpaper-symbolic", self._theme)))

    def set_theme(self, theme):
        self._theme = theme
        self._reload_icons()
        self._render()

    def set_steps(self, steps):
        self._steps = steps
        self._render()

    def _render(self):
        self._render_svg(self._steps)

    def _render_svg(self, steps):
        t = THEMES[self._theme]
        DIS_TXT = t["disabled_text"]
        DIS_BG = t["disabled_bg"]
        DIS_BORDER = t["disabled_border"]
        char_w = 8
        pad_x = 14
        h = 38
        gap = 32
        ep_r = ICON_SIZE // 2
        boxes = [len(label) * char_w + pad_x * 2 for label, _on in steps]
        total_w = ep_r * 4 + gap * 2 + sum(boxes) + gap * (len(boxes) - 1) + 20
        total_h = h + 20
        y = 10
        cy = y + h / 2

        elems = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}">',
            '<defs>',
            '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto">',
            f'<path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/>',
            '</marker>',
            '<marker id="ard" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto">',
            f'<path d="M0,0 L10,5 L0,10 z" fill="{DIS_TXT}"/>',
            '</marker>',
            '</defs>',
        ]
        def endpoint(cx, b64):
            return (
                f'<image x="{cx - ep_r}" y="{cy - ep_r}" '
                f'width="{ep_r * 2}" height="{ep_r * 2}" '
                f'xlink:href="data:image/png;base64,{b64}"/>'
            )

        def arrow(x1, x2, _on=True):
            return (
                f'<line x1="{x1}" y1="{cy}" x2="{x2}" y2="{cy}" '
                f'stroke="{ACCENT}" stroke-width="2.2" '
                f'marker-end="url(#ar)"/>'
            )

        x = 10
        elems.append(endpoint(x + ep_r, self._in_b64))
        seg_start = x + ep_r * 2
        elems.append(arrow(seg_start + 4, seg_start + gap - 4,
                           steps[0][1] if steps else True))
        x = seg_start + gap

        for i, ((label, on), bw) in enumerate(zip(steps, boxes)):
            bg = ACCENT if on else DIS_BG
            border = ACCENT_DARK if on else DIS_BORDER
            text_col = "white" if on else DIS_TXT
            dash_attr = '' if on else 'stroke-dasharray="5,4" '
            elems.append(
                f'<rect x="{x}" y="{y}" width="{bw}" height="{h}" rx="8" ry="8" '
                f'fill="{bg}" stroke="{border}" stroke-width="1.8" {dash_attr}/>'
            )
            elems.append(
                f'<text x="{x + bw / 2}" y="{y + h / 2 + 5}" '
                f'text-anchor="middle" fill="{text_col}" '
                f'font-family="sans-serif" font-size="13" font-weight="bold">'
                f'{label}</text>'
            )
            # Bypass dashed arrow across disabled box
            if not on:
                elems.append(
                    f'<line x1="{x - 2}" y1="{cy}" x2="{x + bw + 2}" y2="{cy}" '
                    f'stroke="{ACCENT}" stroke-width="2.2"/>'
                )
            if i < len(steps) - 1:
                next_on = steps[i + 1][1]
                elems.append(arrow(x + bw + 4, x + bw + gap - 4, on and next_on))
            x += bw + gap

        last_on = steps[-1][1] if steps else True
        elems.append(arrow(x - gap + 4, x - 4, last_on))
        elems.append(endpoint(x + ep_r, self._out_b64))
        elems.append("</svg>")
        svg_bytes = "\n".join(elems).encode("utf-8")
        self.load(QByteArray(svg_bytes))
        self.setFixedSize(int(total_w), int(total_h))


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pipeline diagram - 3 styles")
        self.resize(900, 600)
        self._theme = "dark"
        root = QVBoxLayout(self)

        # Top bar: theme toggle
        topbar = QHBoxLayout()
        from PyQt6.QtWidgets import QPushButton
        self.btn_theme = QPushButton("Switch to LIGHT theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        topbar.addWidget(self.btn_theme)
        topbar.addStretch()
        root.addLayout(topbar)

        ctrl = QGroupBox("Toggle steps (live update)")
        ctrl_lay = QHBoxLayout(ctrl)
        self.checks = []
        for label, on in DEFAULT_STEPS:
            cb = QCheckBox(label)
            cb.setChecked(on)
            cb.toggled.connect(self._refresh)
            ctrl_lay.addWidget(cb)
            self.checks.append(cb)
        root.addWidget(ctrl)

        g1 = QGroupBox("Style 1 - QLabel HTML  (simple, ~30 lines)")
        QVBoxLayout(g1).addWidget(self._make_html())
        root.addWidget(g1)

        g2 = QGroupBox("Style 2 - QWidget custom paintEvent  (~70 lines)")
        QVBoxLayout(g2).addWidget(self._make_widget())
        root.addWidget(g2)

        g3 = QGroupBox("Style 3 - SVG embedded  (vector scalable, ~70 lines)")
        QVBoxLayout(g3).addWidget(self._make_svg())
        root.addWidget(g3)

        root.addStretch()
        self._refresh()
        self._apply_theme()

    def _make_html(self):
        self.html_pipe = HtmlPipeline()
        return self.html_pipe

    def _make_widget(self):
        self.widget_pipe = WidgetPipeline()
        return self.widget_pipe

    def _make_svg(self):
        self.svg_pipe = SvgPipeline()
        return self.svg_pipe

    def _apply_theme(self):
        t = THEMES[self._theme]
        self.setStyleSheet(
            f"QWidget {{ background-color: {t['window_bg']}; color: {t['fg']}; }}"
            f"QGroupBox {{ background-color: {t['panel_bg']}; "
            f"border: 1px solid {t['disabled_border']}; "
            f"border-radius: 4px; margin-top: 8px; padding-top: 12px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}"
            f"QPushButton {{ background-color: {t['panel_bg']}; color: {t['fg']}; "
            f"border: 1px solid {t['disabled_border']}; padding: 6px 12px; border-radius: 4px; }}"
        )
        for w in (self.html_pipe, self.widget_pipe, self.svg_pipe):
            w.set_theme(self._theme)
        self.btn_theme.setText(
            "Switch to LIGHT theme" if self._theme == "dark" else "Switch to DARK theme")

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme()

    def _refresh(self):
        steps = [(cb.text(), cb.isChecked()) for cb in self.checks]
        self.html_pipe.set_steps(steps)
        self.widget_pipe.set_steps(steps)
        self.svg_pipe.set_steps(steps)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = TestWindow()
    w.show()
    sys.exit(app.exec())
