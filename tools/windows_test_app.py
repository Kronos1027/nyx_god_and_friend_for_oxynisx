"""Owned native fixture for opt-in Windows acceptance tests; no personal data."""
import argparse
import json
import os
from pathlib import Path
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    window = QDialog()
    window.setWindowTitle(args.title)
    window.resize(460, 350)
    layout = QVBoxLayout(window)
    edit = QLineEdit()
    edit.setAccessibleName("Fixture input")
    layout.addWidget(edit)
    password = QLineEdit()
    password.setEchoMode(QLineEdit.EchoMode.Password)
    password.setAccessibleName("Fixture password")
    layout.addWidget(password)
    result = QLabel("Waiting")
    button = QPushButton("Apply fixture")
    layout.addWidget(button)
    layout.addWidget(result)
    disabled = QPushButton("Disabled fixture")
    disabled.setEnabled(False)
    layout.addWidget(disabled)
    for _ in range(2):
        layout.addWidget(QPushButton("Duplicate fixture"))
    state = {"clicks": 0}
    def persist(retry=0):
        state["hwnd"] = int(window.winId())
        state["platform"] = app.platformName()
        state["visible"] = window.isVisible()
        state["geometry"] = [window.x(), window.y(), window.width(), window.height()]
        pending = args.state.with_suffix(".pending")
        pending.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(pending, args.state)
        except PermissionError:
            # A Windows reader may briefly hold the old file without delete-sharing.
            # Keep its complete state visible and retry without blocking Qt.
            if retry >= 20:
                raise
            QTimer.singleShot(10, lambda: persist(retry + 1))
    def clicked():
        state.update(text=edit.text(), clicks=state["clicks"] + 1)
        result.setText("Result: " + edit.text())
        persist()
    button.clicked.connect(clicked)
    modal = QDialog(window)
    modal.setWindowTitle(args.title + " modal")
    modal.setModal(True)
    modal_layout = QVBoxLayout(modal)
    modal_layout.addWidget(QLabel("Owned modal fixture"))
    dismiss = QPushButton("Dismiss fixture")
    modal_layout.addWidget(dismiss)
    dismiss.clicked.connect(modal.accept)
    launch_modal = QPushButton("Open modal fixture")
    layout.addWidget(launch_modal)
    def show_modal():
        modal.open()
        state["modal_hwnd"] = int(modal.winId())
        persist()
    launch_modal.clicked.connect(show_modal)
    window.show()
    QTimer.singleShot(50, persist)
    app.exec()


if __name__ == "__main__":
    main()
