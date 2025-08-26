from PyQt6.QtCore import QThread, QObject, pyqtSignal, pyqtSlot
from python_utils.shared import logger, CustomMQTTClient
import logging

file_handler = logging.FileHandler("app.log", mode='a', encoding='utf-8')
formatter = logging.Formatter(fmt='%(module)s - %(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.propagate = False


class ReconnectWorker(QObject):
    finished = pyqtSignal(bool)

    def __init__(self, client):
        super().__init__()
        self.client = client

    @pyqtSlot()
    def run(self):
        while not self.client.custom_reconnect():
            if QThread.currentThread().isInterruptionRequested():
                self.finished.emit(False)
                return
        self.client.loop_start()
        self.finished.emit(True)
        return
