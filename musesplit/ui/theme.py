"""UI style tokens and stylesheet."""

from __future__ import annotations


def app_stylesheet() -> str:
    return """
QWidget {
    background: #f2efe8;
    color: #1f2933;
    font-family: "Avenir Next", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 12px;
}
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f4f0e8, stop:1 #e8ece5);
}
QFrame#Card {
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid #d7dece;
    border-radius: 14px;
}
QLabel#Title {
    font-size: 24px;
    font-weight: 700;
    color: #102a43;
}
QLabel#Subtitle {
    font-size: 12px;
    color: #486581;
}
QLineEdit, QTextEdit {
    font-size: 12px;
    background: #ffffff;
    border: 1px solid #bcccdc;
    border-radius: 8px;
    padding: 8px;
}
QPushButton {
    background: #2f855a;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #276749;
}
QPushButton:disabled {
    background: #9fb3c8;
}
QCheckBox {
    spacing: 8px;
    font-size: 12px;
}
QProgressBar {
    border: 1px solid #bcccdc;
    border-radius: 8px;
    background: #f0f4f8;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f855a, stop:1 #38a169);
    border-radius: 7px;
}
"""
