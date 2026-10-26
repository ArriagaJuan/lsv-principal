"""Interfaz LSV + Trigger (reconstrucción asistida por grabaciones).

El original se ve en VS Code en el video; esta implementación reproduce el flujo
principal y se distingue de una transcripción exacta del programa perdido.
"""
import json
import math
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets, QtGui

from acquisition_plan import AcquisitionPlan
from config import LASER_BAUDRATE, MIN_SERIAL_SAMPLE_PERIOD_SECONDS
from config_store import ConfigStore
from exporter import export_records, prepare_export_directory
from lsv_connection import LSVConnection
from measurements import integrate_distance
from trigger import TriggerController


def parse_lsv_velocity(response):
    """Solo admite líneas numéricas de la respuesta V. No confundir estados con valores."""
    for raw in reversed(str(response).replace(',', '.').splitlines()):
        candidate = raw.strip().lstrip('Vv:= ').strip()
        try:
            value = float(candidate)
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    raise ValueError(f"El lector no devolvió velocidad numérica: {response!r}")


class LsvWorker(QtCore.QThread):
    sample = QtCore.Signal(object)
    status = QtCore.Signal(str)
    completed = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, laser, trigger, *, duration_s, cycles, pause_s,
                 sample_s, time_offset_s, simulate, autosave, trigger_d12_us=0, trigger_d10_us=0, parent=None):
        super().__init__(parent)
        self.laser = laser
        self.trigger = trigger
        self.duration_s = float(duration_s)
        self.cycles = int(cycles)
        self.pause_s = float(pause_s)
        self.sample_s = max(MIN_SERIAL_SAMPLE_PERIOD_SECONDS, float(sample_s))
        self.time_offset_s = float(time_offset_s)
        self.simulate = bool(simulate)
        self.trigger_d12_us = int(trigger_d12_us)
        self.trigger_d10_us = int(trigger_d10_us)
        self.autosave = Path(autosave)
        self.cancel = threading.Event()
        self.plan = AcquisitionPlan(self.duration_s, self.cycles, self.pause_s)
        self.rows = []

    def request_stop(self):
        self.cancel.set()

    def _wait(self, seconds):
        return not self.cancel.wait(max(0.0, seconds))

    def run(self):
        try:
            self.autosave.parent.mkdir(parents=True, exist_ok=True)
            with self.autosave.open('w', encoding='utf-8') as journal:
                for cycle in range(1, self.cycles + 1):
                    if self.cancel.is_set():
                        break
                    if cycle > 1 and not self._wait(self.pause_s):
                        break
                    self.plan.start_attempt()
                    attempt_number = self.plan.current_attempt
                    self.status.emit(f"Ciclo {cycle}/{self.cycles}: intento {attempt_number} en curso")
                    trigger_active = False
                    trigger_ack = None
                    trigger_sent_ns = None
                    trigger_ack_ns = None
                    try:
                        # En modo real, solo actúa sobre el trigger tras autorización de la interfaz.
                        if not self.simulate and self.trigger.connected:
                            # Marcamos activo ANTES del envío: si se pierde ACK, RESET sigue obligado.
                            trigger_active = True
                            trigger_ack = self.trigger.start(self.trigger_d12_us, self.trigger_d10_us)
                            trigger_sent_ns = self.trigger.last_command_monotonic_ns
                            trigger_ack_ns = self.trigger.last_ack_monotonic_ns
                            self.status.emit(f'Trigger TTL V1: {trigger_ack} · D12={self.trigger_d12_us} µs, D10={self.trigger_d10_us} µs')
                        start = time.monotonic()
                        last_t = last_v = None
                        distance = 0.0
                        tick = 0
                        while not self.cancel.is_set():
                            elapsed = time.monotonic() - start
                            if elapsed > self.duration_s + 0.01:
                                break
                            if self.simulate:
                                # Datos etiquetados como simulados: jamás utilizar para calibración.
                                velocity = 1200.0 + 3.0 * math.sin(elapsed * 2.0)
                            else:
                                velocity = parse_lsv_velocity(self.laser.query_laser('v'))
                            if last_t is not None:
                                distance = integrate_distance(last_t, last_v, elapsed, velocity, distance)
                            last_t, last_v = elapsed, velocity
                            row = {
                                "cycle": cycle,
                                "attempt": attempt_number,
                                "raw_time_s": round(elapsed, 6),
                                "time_s": round(elapsed + self.time_offset_s, 6),
                                "velocity_m_min": round(velocity, 8),
                                "distance_m": round(distance, 8),
                                "simulated": self.simulate,
                                "trigger_ack": trigger_ack if not self.simulate else "SIMULADO",
                                "trigger_command_monotonic_ns": trigger_sent_ns,
                                "trigger_ack_monotonic_ns": trigger_ack_ns,
                                "trigger_d12_us": self.trigger_d12_us if not self.simulate else 0,
                                "trigger_d10_us": self.trigger_d10_us if not self.simulate else 0,
                                "acquired_at": datetime.now().isoformat(timespec='milliseconds'),
                            }
                            journal.write(json.dumps(row, ensure_ascii=False) + '\n')
                            journal.flush()
                            self.rows.append(row)
                            self.sample.emit(row)
                            tick += 1
                            remaining = self.sample_s * tick - (time.monotonic() - start)
                            if remaining > 0 and not self._wait(remaining):
                                break
                        if self.cancel.is_set():
                            self.plan.interrupt('Detenido por usuario')
                            break
                        self.plan.complete_attempt()
                        self.status.emit(f"Ciclo {cycle}/{self.cycles} terminado")
                    except Exception as exc:
                        self.plan.fail(str(exc))
                        self.error.emit(str(exc))
                        break
                    finally:
                        if trigger_active or (not self.simulate and self.trigger.connected):
                            try:
                                self.trigger.stop()
                            except Exception as exc:
                                self.error.emit(f"Error al detener el trigger: {exc}")
                journal.write(json.dumps({"kind": "attempts", "attempts": [a.__dict__ for a in self.plan.attempts]}, ensure_ascii=False) + '\n')
                journal.flush()
        except BaseException as exc:
            self.error.emit(f"Error durante la adquisición: {exc}")
        finally:
            self.completed.emit({"rows": self.rows, "attempts": self.plan.attempts,
                                 "autosave": str(self.autosave), "state": self.plan.state})


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('LSV principal · integración Arduino TTL V1 (reconstrucción)')
        self.resize(1050, 760)
        self.cfg = ConfigStore()
        self.laser = LSVConnection()
        self.trigger = TriggerController()
        self.worker = None
        self.rows = []
        self.attempts = []
        self.data_exported = True
        self._make_ui()
        self._populate_ports()
        self._load_settings()

    def _make_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        header = QtWidgets.QLabel('LSV principal / Arduino TTL V1 · Recuperación funcional')
        font = header.font(); font.setPointSize(15); font.setBold(True); header.setFont(font)
        outer.addWidget(header)
        warning = QtWidgets.QLabel('TTL V1 coincide con el firmware recuperado · validar niveles y tiempos antes de medir')
        warning.setStyleSheet('color: #9A5600; font-weight: bold;')
        outer.addWidget(warning)
        config = QtWidgets.QGroupBox('Comunicación')
        form = QtWidgets.QGridLayout(config)
        self.connection = QtWidgets.QComboBox(); self.connection.addItems(['RS232', 'TCP'])
        self.reader_port = QtWidgets.QComboBox(); self.reader_port.setEditable(True)
        self.trigger_port = QtWidgets.QComboBox(); self.trigger_port.setEditable(True)
        self.host = QtWidgets.QLineEdit()
        self.tcpport = QtWidgets.QSpinBox(); self.tcpport.setRange(1,65535)
        self.simulate = QtWidgets.QCheckBox('Simulación (sin conexiones ni salidas físicas)')
        self.simulate.setChecked(True)
        self.connect_laser = QtWidgets.QPushButton('Conectar LSV')
        self.connect_trigger = QtWidgets.QPushButton('Conectar trigger TTL V1')
        self.check_trigger = QtWidgets.QPushButton('Consultar Arduino (sin disparar)')
        self.refresh = QtWidgets.QPushButton('Actualizar puertos')
        form.addWidget(QtWidgets.QLabel('Interfaz LSV:'),0,0);form.addWidget(self.connection,0,1)
        form.addWidget(QtWidgets.QLabel('Puerto LSV:'),0,2);form.addWidget(self.reader_port,0,3)
        form.addWidget(QtWidgets.QLabel('Trigger TTL:'),1,0);form.addWidget(self.trigger_port,1,1)
        form.addWidget(QtWidgets.QLabel('Host TCP:'),1,2);form.addWidget(self.host,1,3)
        form.addWidget(QtWidgets.QLabel('Puerto TCP:'),2,0);form.addWidget(self.tcpport,2,1)
        form.addWidget(self.refresh,2,3)
        form.addWidget(self.simulate,3,0,1,4)
        form.addWidget(self.connect_laser,4,0,1,2);form.addWidget(self.connect_trigger,4,2,1,2)
        form.addWidget(self.check_trigger,5,0,1,4)
        outer.addWidget(config)

        plan_group=QtWidgets.QGroupBox('Plan de adquisición')
        plan=QtWidgets.QGridLayout(plan_group)
        self.duration=QtWidgets.QDoubleSpinBox();self.duration.setRange(.5,3600);self.duration.setDecimals(2);self.duration.setValue(20);self.duration.setSuffix(' s')
        self.cycles=QtWidgets.QSpinBox();self.cycles.setRange(1,10000);self.cycles.setValue(3)
        self.pause=QtWidgets.QDoubleSpinBox();self.pause.setRange(0,3600);self.pause.setValue(3);self.pause.setSuffix(' s')
        self.sampleperiod=QtWidgets.QDoubleSpinBox();self.sampleperiod.setDecimals(2);self.sampleperiod.setRange(.5,10);self.sampleperiod.setValue(.5);self.sampleperiod.setSuffix(' s')
        self.offset=QtWidgets.QDoubleSpinBox();self.offset.setDecimals(3);self.offset.setRange(-20,20);self.offset.setSingleStep(.01);self.offset.setValue(0);self.offset.setSuffix(' s')
        self.divisor=QtWidgets.QSpinBox();self.divisor.setRange(1,1024);self.divisor.setValue(16)
        for i,(label,widget) in enumerate([('Segundos/ciclo',self.duration),('Ciclos',self.cycles),('Pausa entre ciclos',self.pause),('Intervalo de lectura',self.sampleperiod),('Desfase manual (sin calibrar)',self.offset),('Divisor DAQ (referencia)',self.divisor)]):
            row=i//3;col=(i%3)*2;plan.addWidget(QtWidgets.QLabel(label),row,col);plan.addWidget(widget,row,col+1)
        # Con firmware Arduino UNO V1 se envía PULSE, no START.
        # Los canales comienzan desactivados hasta configurar la duración.
        self.pulse12=QtWidgets.QSpinBox();self.pulse12.setRange(0,1000000);self.pulse12.setValue(0);self.pulse12.setSuffix(' us')
        self.pulse10=QtWidgets.QSpinBox();self.pulse10.setRange(0,1000000);self.pulse10.setValue(0);self.pulse10.setSuffix(' us')
        plan.addWidget(QtWidgets.QLabel('Arduino V1: pulso D12 (us)'),2,0)
        plan.addWidget(self.pulse12,2,1)
        plan.addWidget(QtWidgets.QLabel('Arduino V1: pulso D10 (us)'),2,2)
        plan.addWidget(self.pulse10,2,3)
        outer.addWidget(plan_group)

        controls=QtWidgets.QHBoxLayout()
        self.start_btn=QtWidgets.QPushButton('Iniciar adquisición')
        self.stop_btn=QtWidgets.QPushButton('Detener / cancelar')
        self.stop_btn.setEnabled(False)
        self.export_btn=QtWidgets.QPushButton('Exportar Excel')
        self.select_folder=QtWidgets.QPushButton('Carpeta de exportación')
        for w in (self.start_btn,self.stop_btn,self.export_btn,self.select_folder):controls.addWidget(w)
        outer.addLayout(controls)
        self.status_text=QtWidgets.QLabel('Modo de simulación: listo')
        outer.addWidget(self.status_text)
        self.counter=QtWidgets.QLabel('Sin mediciones')
        outer.addWidget(self.counter)
        self.table=QtWidgets.QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(('Ciclo','Intento','Tiempo bruto (s)','Tiempo alineado (s)','Velocidad (m/min)','Distancia (m)'))
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table,stretch=1)
        self.log=QtWidgets.QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(115)
        outer.addWidget(self.log)
        self.connect_laser.clicked.connect(self._connect_lsv)
        self.connect_trigger.clicked.connect(self._connect_trigger)
        self.refresh.clicked.connect(self._populate_ports)
        self.check_trigger.clicked.connect(self._check_arduino)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.export_btn.clicked.connect(self._export)
        self.select_folder.clicked.connect(self._choose_folder)
        self.simulate.toggled.connect(self._update_connection_mode)
        self._update_connection_mode()

    def _load_settings(self):
        cfg=self.cfg
        self.reader_port.setCurrentText(str(cfg.get('reader_port', 'COM5')))
        self.trigger_port.setCurrentText(str(cfg.get('trigger_port', 'COM6')))
        self.host.setText(str(cfg.get('lsv_host')))
        self.tcpport.setValue(int(cfg.get('lsv_port')))
        self.divisor.setValue(int(cfg.get('lsv_daq_divisor')))
        self.connection.setCurrentText(str(cfg.get('lsv_connection')))
        self.pulse12.setValue(int(cfg.get('trigger_d12_us', 0)))
        self.pulse10.setValue(int(cfg.get('trigger_d10_us', 0)))

    def _save_settings(self):
        self.cfg.update({'reader_port':self.reader_port.currentText(),'trigger_port':self.trigger_port.currentText(),
                         'lsv_host':self.host.text().strip(),'lsv_port':self.tcpport.value(),
                         'lsv_connection':self.connection.currentText(),'lsv_daq_divisor':self.divisor.value(),
                         'trigger_d12_us':self.pulse12.value(),'trigger_d10_us':self.pulse10.value()})
        self.cfg.save()

    def _populate_ports(self):
        try:
            from serial.tools import list_ports
            names=[p.device for p in list_ports.comports()]
        except ImportError:
            names=[]
        for combo in (self.reader_port,self.trigger_port):
            current=combo.currentText()
            combo.clear();combo.addItems(names);combo.setCurrentText(current)

    def _note(self, message):
        self.status_text.setText(message)
        self.log.appendPlainText(f'[{datetime.now():%H:%M:%S}] {message}')

    def _update_connection_mode(self):
        enabled=not self.simulate.isChecked()
        self.connect_laser.setEnabled(enabled)
        self.connect_trigger.setEnabled(enabled)
        self.check_trigger.setEnabled(enabled)
        if not enabled:
            self._note('SIMULACIÓN: datos generados artificialmente; NO son mediciones')

    def _confirm_hardware(self):
        answer=QtWidgets.QMessageBox.warning(self,'Confirmación de seguridad',
            'Los comandos se reconstruyeron de una grabación y NO están validados con tu firmware. '
            'Confirma que equipos y actuadores están en un estado seguro y supervisado.\n\n'
            '¿Autorizar conexión y comandos al hardware?',
            QtWidgets.QMessageBox.StandardButton.Yes|QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        return answer==QtWidgets.QMessageBox.StandardButton.Yes

    def _connect_lsv(self):
        if not self._confirm_hardware():return
        try:
            if self.connection.currentText()=='RS232':
                self.laser.open_serial(self.reader_port.currentText(),LASER_BAUDRATE)
            else:
                self.laser.open_tcp(self.host.text(),self.tcpport.value())
            self._note('LSV conectado: '+self.connection.currentText())
            self._save_settings()
        except Exception as exc:
            self._note('Error LSV: '+str(exc))
            QtWidgets.QMessageBox.critical(self,'Conexión LSV',str(exc))

    def _connect_trigger(self):
        if not self._confirm_hardware():return
        try:
            info=self.trigger.connect(self.trigger_port.currentText())
            self._note('Trigger conectado: '+info)
            self._save_settings()
        except Exception as exc:
            self._note('Error de trigger: '+str(exc))
            QtWidgets.QMessageBox.critical(self,'Trigger',str(exc))

    def _check_arduino(self):
        if self.worker and self.worker.isRunning():
            QtWidgets.QMessageBox.warning(self, 'Trigger', 'No consultar durante una adquisición.');return
        try:
            state = self.trigger.status()
            self._note('Arduino TTL V1: ' + state)
            QtWidgets.QMessageBox.information(self, 'Estado Arduino (sin disparo)', state)
        except Exception as exc:
            self._note('Error consultando Arduino: ' + str(exc))
            QtWidgets.QMessageBox.warning(self, 'Arduino', str(exc))

    def _start(self):
        if self.worker is not None and self.worker.isRunning():return
        if not self.simulate.isChecked():
            if not (self.laser.connected and self.trigger.connected):
                QtWidgets.QMessageBox.warning(self,'Faltan conexiones','Conecta LSV y trigger antes de iniciar.');return
            if self.trigger.mode == 'v1' and not (self.pulse12.value() or self.pulse10.value()):
                QtWidgets.QMessageBox.warning(self,'Arduino V1',
                    'Selecciona la duración del pulso D12 o D10 en microsegundos.\n'
                    'Ambos canales están desactivados (0 us).');return
            if not self._confirm_hardware():return
        if self.rows and not self.data_exported:
            answer=QtWidgets.QMessageBox.question(self,'Datos pendientes',
                'Hay datos sin exportar. ¿Deseas iniciar una nueva sesión? Se conserva el respaldo JSONL anterior.',
                QtWidgets.QMessageBox.StandardButton.Yes|QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:return
        self._save_settings()
        self.rows=[];self.attempts=[];self.table.setRowCount(0);self.data_exported=False
        folder=prepare_export_directory(self.cfg.get('export_directory'))
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        journal=folder/'respaldos_jsonl'/f'captura_{stamp}.jsonl'
        self.worker=LsvWorker(self.laser,self.trigger,duration_s=self.duration.value(),cycles=self.cycles.value(),
                    pause_s=self.pause.value(),sample_s=self.sampleperiod.value(),time_offset_s=self.offset.value(),
                    simulate=self.simulate.isChecked(),autosave=journal,
                    trigger_d12_us=self.pulse12.value(),trigger_d10_us=self.pulse10.value())
        self.worker.sample.connect(self._receive)
        self.worker.status.connect(self._note)
        self.worker.error.connect(lambda message:self._note('ERROR: '+message))
        self.worker.completed.connect(self._finished)
        self.start_btn.setEnabled(False);self.stop_btn.setEnabled(True)
        self.connect_trigger.setEnabled(False);self.connect_laser.setEnabled(False)
        self.simulate.setEnabled(False);self.check_trigger.setEnabled(False)
        self._note('Iniciando; respaldo automático: '+str(journal))
        self.worker.start()

    def _receive(self,row):
        self.rows.append(row)
        if self.table.rowCount()>=400:
            self.table.removeRow(0)
        idx=self.table.rowCount();self.table.insertRow(idx)
        vals=[row['cycle'],row['attempt'],row['raw_time_s'],row['time_s'],row['velocity_m_min'],row['distance_m']]
        for i,value in enumerate(vals):
            self.table.setItem(idx,i,QtWidgets.QTableWidgetItem(f'{value:.4f}' if isinstance(value,float) else str(value)))
        if len(self.rows)%5==0 or len(self.rows)==1:
            self.counter.setText(f"Muestras: {len(self.rows)} · Última velocidad {row['velocity_m_min']:.3f} m/min · Distancia {row['distance_m']:.4f} m")
        self.table.scrollToBottom()

    def _stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self._note('Solicitando parada segura del ensayo...')

    def _finished(self, data):
        # on_sample también se ejecuta por señales; reutilizar filas desde hilo no pierde muestras.
        self.rows=list(data.get('rows',[]))
        self.attempts=list(data.get('attempts',[]))
        self.start_btn.setEnabled(True);self.stop_btn.setEnabled(False)
        self.simulate.setEnabled(True);self._update_connection_mode()
        self._note(f"Adquisición terminada ({data.get('state')}). Respaldo: {data.get('autosave')}")
        if self.rows:
            self._note('Datos pendientes de exportación en Excel.')
        else:
            self.data_exported=True

    def _choose_folder(self):
        chosen=QtWidgets.QFileDialog.getExistingDirectory(self,'Carpeta para guardar Excel',str(self.cfg.get('export_directory')))
        if chosen:
            self.cfg.update({'export_directory':chosen});self._save_settings();self._note('Carpeta: '+chosen)

    def _export(self):
        if self.worker and self.worker.isRunning():
            QtWidgets.QMessageBox.warning(self,'Sesión activa','Detén la adquisición antes de exportar.');return
        if not self.rows:
            QtWidgets.QMessageBox.information(self,'Exportar','Todavía no hay datos capturados.');return
        try:
            metadata={'Origen':'SIMULACIÓN - NO USAR EN CALIBRACIÓN' if all(row.get('simulated') for row in self.rows) else 'EQUIPO REAL - VALIDACIÓN PENDIENTE',
                      'Desfase manual (s)':self.offset.value(), 'Divisor DAQ':self.divisor.value(),
                      'Intervalo de lectura (s)':self.sampleperiod.value(),
                      'Firmware trigger':'TTL V1 original, D12/D10 9600 baud',
                      'Importante sincronización':'ACK serial no es timestamp del flanco TTL',
                      'Duración D12 (µs)':self.pulse12.value(), 'Duración D10 (µs)':self.pulse10.value()}
            path=export_records(self.rows,self.attempts,output_directory=self.cfg.get('export_directory'),metadata=metadata)
            self.data_exported=True
            self._note(f'Excel guardado: {path}')
            QtWidgets.QMessageBox.information(self,'Exportación lista',f'Guardado en:\n{path}')
        except Exception as exc:
            self._note('Error de exportación: '+str(exc))
            QtWidgets.QMessageBox.critical(self,'Exportación',str(exc))

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            if not self.worker.wait(5000):
                event.ignore()
                QtWidgets.QMessageBox.warning(self,'Adquisición activa','La lectura sigue deteniéndose; prueba cerrar después.');return
        self._save_settings()
        try:self.trigger.close()
        except Exception:pass
        try:self.laser.close()
        except Exception:pass
        event.accept()


def run():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window=Window();window.show()
    return app.exec()

if __name__=='__main__':
    raise SystemExit(run())
