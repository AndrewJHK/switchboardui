from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QLabel, QGroupBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from python_utils.BrokerMessage import ProtoMQTTController
from python_utils.proto_files import broker_msg_out_pb2, origin_pb2, switchboard_pb2
from python_utils.shared import CustomMQTTClient, read_config, logger
from utilities import ReconnectWorker
import json
from collections import OrderedDict

config = read_config("config.json")


def _load_switch_names(cfg) -> OrderedDict:
    raw = cfg.get("switch_names", {})
    ordered = OrderedDict(sorted(raw.items(), key=lambda kv: int(kv[0].split("_")[1])))
    result = OrderedDict()
    for sb_key, names_dict in ordered.items():
        if isinstance(names_dict, dict):
            pairs = sorted(names_dict.items(), key=lambda kv: int(kv[0].split("_")[1]))
            names = [v if v else f"SW {i}" for i, (_, v) in enumerate(pairs)]
            result[sb_key] = names
        elif isinstance(names_dict, list):
            result[sb_key] = [n if n else f"SW {i}" for i, n in enumerate(names_dict)]
        else:
            result[sb_key] = [f"SW {i}" for i in range(12)]
    return result


def _origin_enum_for(index_1_based: int):
    name = f"ORIGIN_SWITCHBOARD_{index_1_based}"
    return getattr(origin_pb2, name, getattr(origin_pb2, "ORIGIN_SWITCHBOARD_1", 0))


class SwitchWidget(QGroupBox):
    toggled = pyqtSignal()

    def __init__(self, name, ishold):
        super().__init__()

        self.state = 0

        self.button = QPushButton("0")
        self.button.setCheckable(True)
        self.button.setEnabled(False)
        self.button.setStyleSheet("background-color: #ed2f21;font-weight: 600")
        self.button.setFixedHeight(60)
        self.button.pressed.connect(self.handle_press)
        self.button.released.connect(self.handle_release)

        self.state_layout = QHBoxLayout()

        self.button_ishold = QCheckBox()
        self.button_ishold.setChecked(ishold)
        self.button_ishold.clicked.connect(self.handle_mode_change)
        self.hold_label = QLabel("Hold behaviour")

        self.state_layout.addWidget(self.button_ishold, alignment=Qt.AlignmentFlag.AlignRight)
        self.state_layout.addWidget(self.hold_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.name = QLineEdit(name)

        self.switch_layout = QVBoxLayout()

        self.switch_layout.addWidget(self.button)
        self.switch_layout.addLayout(self.state_layout)
        self.switch_layout.addWidget(self.name)

        self.setLayout(self.switch_layout)

    def handle_press(self):
        if self.button_ishold.isChecked():
            self.activate()
        else:
            match self.state:
                case 0:
                    self.activate()
                case 1:
                    self.deactivate()

    def handle_release(self):
        if self.button_ishold.isChecked():
            self.deactivate()

    def activate(self):
        self.state = 1
        self.button.setText("1")
        self.button.setStyleSheet("background-color: #00FF00;font-weight: 600")
        self.toggled.emit()

    def deactivate(self):
        self.state = 0
        self.button.setText("0")
        self.button.setStyleSheet("background-color: #ed2f21;font-weight: 600")
        self.toggled.emit()

    def handle_mode_change(self):
        self.state = 0
        self.button.setText("0")
        self.button.setStyleSheet("background-color: #ed2f21;font-weight: 600")

    def set_state_silent(self, state: int):
        self.state = 1 if state else 0
        if self.state == 1:
            self.button.setText("1")
            self.button.setStyleSheet("background-color: #00FF00;font-weight: 600")
            self.button.setChecked(True)
        else:
            self.button.setText("0")
            self.button.setStyleSheet("background-color: #ed2f21;font-weight: 600")
            self.button.setChecked(False)


class SwitchboardWidget(QGroupBox):
    def __init__(self, title, topic, publisher_client, proto_controller, switch_names):
        super().__init__()

        self.publisher_client = publisher_client
        self.proto_controller = proto_controller
        self.message_to_send = switchboard_pb2.SwitchBoardOutData()
        self.topic = topic

        self.switchboard_layout = QVBoxLayout()

        self.top_row_layout = QHBoxLayout()
        self.bottom_row_layout = QHBoxLayout()

        self.switches = [SwitchWidget(name=n, ishold=False) for n in switch_names]

        for sw in self.switches:
            sw.toggled.connect(self.publish_state)

        for i, sw in enumerate(self.switches):
            (self.top_row_layout if i < len(self.switches) // 2 else self.bottom_row_layout).addWidget(sw)

        self.switchboard_name = QLabel(title)
        self.switchboard_name.setStyleSheet("font-size: 30px")
        self.switchboard_name.setMaximumHeight(60)

        self.switchboard_layout.addWidget(self.switchboard_name, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.switchboard_layout.addLayout(self.top_row_layout)
        self.switchboard_layout.addLayout(self.bottom_row_layout)
        self.setLayout(self.switchboard_layout)

    def publish_state(self):
        bitstring = "".join(str(sw.state) for sw in self.switches[::-1])
        self.message_to_send.switches.value = int(bitstring, 2)
        msg = self.proto_controller.to_protobuf(data=self.message_to_send).SerializeToString()
        self.publisher_client.publish(self.topic, msg)

    def apply_value(self, value: int):
        bitstring = bin(value)[2:].zfill(12)
        for i, sw in enumerate(self.switches[::-1]):
            sw.set_state_silent(int(bitstring[i]))


class SwitchBoardApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SwitchBoardApp")

        self.sb_names = _load_switch_names(config)  # OrderedDict: sb_key -> [names...]
        self.sb_keys = list(self.sb_names.keys())  # ['sb_1', 'sb_2', ...]
        self.sb_count = len(self.sb_keys)

        if self.sb_count == 0:
            logger.warning(
                "No switchboards defined in config['switch_names']; defaulting to one board with 12 switches.")
            self.sb_names = OrderedDict([("sb_1", [f"SW {i}" for i in range(12)])])
            self.sb_keys = ["sb_1"]
            self.sb_count = 1

        # PROTO CONTROLLERS
        self.proto_controllers = {
            key: ProtoMQTTController(broker_msg_out_pb2.SwitchBoardMsgOut, _origin_enum_for(i + 1))
            for i, key in enumerate(self.sb_keys)
        }

        # PUBLISHER
        topics = [(f"switchboard-{i}/out", 2) for i in range(1, self.sb_count + 1)]

        self.publisher = CustomMQTTClient(
            ip="localhost",
            port=1883,
            topics=topics,
            broker_name="SwitchboardMockupPublisher",
            keepalive=60
        )

        self.publisher.on_message = self.custom_on_message

        # RECONNECT THREADS
        self.publisher_thread_running = False
        self._publisher_reconnect_thread = None
        self._publisher_reconnect_worker = None

        # MAIN LAYOUT
        self.main_layout = QVBoxLayout()

        # SETUP LAYOUT
        self.setup_layout = QHBoxLayout()

        # IP SETUP LAYOUT
        self.ip_layout = QVBoxLayout()
        self.broker_label = QLabel("Enter the broker IP")
        self.broker_label.setStyleSheet("font-size: 20px")
        self.broker_label.setMaximumHeight(40)
        self.broker_ip = QLineEdit("localhost")
        self.ip_layout.addWidget(self.broker_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ip_layout.addWidget(self.broker_ip)

        # PORT SETUP LAYOUT
        self.port_layout = QVBoxLayout()
        self.port_label = QLabel("Enter the broker port")
        self.port_label.setStyleSheet("font-size: 20px")
        self.port_label.setMaximumHeight(40)
        self.port = QLineEdit("1883")
        self.port_layout.addWidget(self.port_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.port_layout.addWidget(self.port)

        self.setup_layout.addLayout(self.ip_layout)
        self.setup_layout.addLayout(self.port_layout)

        # LOCKIN BUTTON
        self.lockin_button = QPushButton()
        self.lockin_button.setText("Lock in setup")
        self.lockin_button.setEnabled(True)
        self.lockin_button.clicked.connect(self.on_lockin)

        # RESET BUTTON
        self.reset_button = QPushButton()
        self.reset_button.setText("Reset switches and setup")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self.on_reset)

        # APPLY CACHED BUTTON
        self.apply_cached_button = QPushButton("Apply cached states")
        self.apply_cached_button.clicked.connect(self.apply_cached)

        # SAVE BUTTON
        self.save_button = QPushButton("Save switch names to config")
        self.save_button.clicked.connect(self.on_save_config)

        # COMBINE ALL LAYOUTS
        self.main_layout.addLayout(self.setup_layout)
        self.main_layout.addWidget(self.lockin_button)
        self.main_layout.addWidget(self.reset_button)
        self.main_layout.addWidget(self.apply_cached_button)
        self.main_layout.addWidget(self.save_button)

        # CREATE SWITCHBOARDS AND ASSIGN THEM TO MAIN LAYOUT
        self.switchboards = []
        for i, sb_key in enumerate(self.sb_keys, start=1):
            controller = self.proto_controllers[sb_key]
            names = self.sb_names[sb_key]
            topic = f"switchboard-{i}/out"

            sb_widget = SwitchboardWidget(
                title=f"SwitchBoard {i}",
                publisher_client=self.publisher,
                proto_controller=controller,
                topic=topic,
                switch_names=names
            )
            self.switchboards.append(sb_widget)
            self.main_layout.addWidget(sb_widget)

        # CACHE
        self.switch_cache = {sb_key: None for sb_key in self.sb_keys}

        self.setLayout(self.main_layout)

    def on_lockin(self):
        new_ip = self.broker_ip.text().strip()
        new_port = int(self.port.text().strip())
        self.lockin_button.setEnabled(False)
        self.broker_ip.setDisabled(True)
        self.port.setDisabled(True)
        self.reset_button.setEnabled(True)

        self.publisher._ip = new_ip
        self.publisher._port = new_port

        # BACKGROUND RECONNECT THREADS
        self._publisher_reconnect_thread = QThread()
        self._publisher_reconnect_worker = ReconnectWorker(self.publisher)
        self._publisher_reconnect_worker.moveToThread(self._publisher_reconnect_thread)
        self._publisher_reconnect_thread.started.connect(self._publisher_reconnect_worker.run)
        self._publisher_reconnect_worker.finished.connect(self._reconnect_thread_cleanup)
        self._publisher_reconnect_thread.finished.connect(self._publisher_reconnect_thread.deleteLater)
        self.publisher_thread_running = True
        self._publisher_reconnect_thread.start()


        for switchboard in self.switchboards:
            for switch in switchboard.switches:
                switch.button.setEnabled(True)

    def _reconnect_thread_cleanup(self, success: bool):
        self.publisher_thread_running = False
        self._publisher_reconnect_thread.quit()
        self._publisher_reconnect_worker.deleteLater()
        self._publisher_reconnect_thread.deleteLater()
        self.broker_ip.setEnabled(True)
        self.port.setEnabled(True)
        if success:
            logger.info(f"Successfully connected to a broker")
        else:
            logger.info(f"Successfully cancelled connect loop to a broker")
            self.lockin_button.setEnabled(True)

    def on_reset(self):
        if self.publisher_thread_running:
            self._publisher_reconnect_thread.requestInterruption()
        else:
            self.lockin_button.setEnabled(True)

        self.publisher.loop_stop()
        self.publisher.disconnect()
        self.reset_button.setEnabled(False)
        logger.info("Successfully disconnected from broker")

        for switchboard in self.switchboards:
            for switch in switchboard.switches:
                switch.deactivate()
                switch.button.setChecked(False)
                switch.button_ishold.setChecked(False)
                switch.button.setEnabled(False)

    def on_save_config(self):
        updated_config = {"switch_names": {}}
        for i, (sb_key, sb_widget) in enumerate(zip(self.sb_keys, self.switchboards)):
            updated_config["switch_names"][sb_key] = {}
            for j, switch in enumerate(sb_widget.switches):
                updated_config["switch_names"][sb_key][f"sw_{j}"] = switch.name.text()

        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(updated_config, f, indent=4, ensure_ascii=False)
            logger.info("Switch names saved to config.json")
        except Exception as e:
            logger.error("Error", f"Failed to save config: {e}")

    def apply_cached(self):
        for idx, sb in enumerate(self.switchboards, start=1):
            val = self.switch_cache.get(f"sb_{idx}")
            if val is not None:
                sb.apply_value(val)

    def custom_on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            if topic.startswith("switchboard-") and topic.endswith("/out"):
                num_str = topic.split("-")[1].split("/")[0]
                key = f"sb_{num_str}"
                if key not in self.proto_controllers:
                    logger.warning(f"Received topic for unknown board: {topic}")
                    return

                proto_controller = self.proto_controllers[key]
                received_message = proto_controller.from_protobuf(msg)
                value = int(received_message.data.switches.value)
                self.switch_cache[key] = value
            else:
                return
        except Exception as e:
            logger.error(f"Failed to parse message from {topic}: {e}")
