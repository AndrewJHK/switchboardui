from gui import SwitchBoardApp
from PyQt6.QtWidgets import QApplication
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    QApplication.setStyle("Fusion")
    window = SwitchBoardApp()
    window.showMaximized()
    sys.exit(app.exec())
