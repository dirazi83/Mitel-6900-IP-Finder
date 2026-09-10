#!/usr/bin/env python3
"""Mitel 6900-series IP phone finder (PySide6 GUI).

Nothing to install besides PySide6 for the window itself: discovery uses only
the Python standard library and the ARP cache, so no Nmap, no Npcap, no packet
driver and no administrator rights are required.

  python main.py                       start the GUI
  python main.py 192.168.100.0/24      command line scan
  python main.py 10.0.2.10-60 --csv phones.csv

Only scan networks you administer.
"""
import argparse
import csv
import os
import sys

import scanner
from scanner import FIELDS, Scanner, __version__, expand_targets, local_networks


def attach_console():
    """Frozen builds are windowed; reattach to the parent console for CLI use."""
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return
    import ctypes
    if not ctypes.windll.kernel32.AttachConsole(-1):
        return
    for stream, mode, target in (('stdout', 'w', 1), ('stderr', 'w', 2)):
        try:
            setattr(sys, stream, open('CONOUT$', mode, buffering=1, encoding='utf-8',
                                      errors='replace'))
        except OSError:
            pass

try:
    from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
    from PySide6.QtGui import QAction, QDesktopServices
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
        QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
        QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QWidget,
    )
except ImportError:
    QApplication = None


class ScanWorker(QObject):
    """Runs a Scanner on a worker thread and forwards its callbacks."""

    row = Signal(dict)
    progress = Signal(int, int)
    message = Signal(str)
    finished = Signal(int, int, int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, targets, options):
        super().__init__()
        self.scanner = Scanner(targets, **options)

    @Slot()
    def run(self):
        try:
            rows = self.scanner.run(
                on_progress=lambda done, total: self.progress.emit(done, total),
                on_row=lambda row: self.row.emit(row),
                on_message=lambda text: self.message.emit(text),
            )
        except (OSError, ValueError) as error:
            if self.scanner.cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(error))
            return
        if self.scanner.cancelled:
            self.cancelled.emit()
        else:
            self.finished.emit(len(rows), self.scanner.hosts_seen,
                               self.scanner.macs_seen)

    @Slot()
    def cancel(self):
        self.scanner.cancel()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Mitel 6900 IP Phone Finder %s' % __version__)
        self.resize(1100, 680)
        self.thread = None
        self.worker = None
        self.rows = []
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        form = QFormLayout()
        self.subnet_input = QComboBox()
        self.subnet_input.setEditable(True)
        self.subnet_input.lineEdit().setPlaceholderText('192.168.100.0/24 or 10.0.2.10-60')
        for cidr, alias in local_networks():
            self.subnet_input.addItem(cidr if not alias else '%s   (%s)' % (cidr, alias), cidr)
        form.addRow('Subnet, range or IP:', self.subnet_input)

        self.prefix_input = QLineEdit(', '.join(scanner.DEFAULT_MAC_PREFIXES))
        self.prefix_input.setPlaceholderText('14, 08:00:0f   (comma separated, blank = any)')
        form.addRow('MAC starts with:', self.prefix_input)
        layout.addLayout(form)

        tuning = QHBoxLayout()
        self.deep_check = QCheckBox('HTTP/HTTPS fingerprint')
        self.deep_check.setChecked(True)
        self.deep_check.setToolTip('Reads Server / WWW-Authenticate realm, e.g. Mitel 6915')
        self.sip_check = QCheckBox('SIP OPTIONS probe')
        self.sip_check.setChecked(True)
        self.sip_check.setToolTip('One UDP packet to 5060; returns model and firmware')
        self.mac_only_check = QCheckBox('MAC matches only')
        self.mac_only_check.setToolTip('Ignore hosts that only match by web signature')
        tuning.addWidget(self.deep_check)
        tuning.addWidget(self.sip_check)
        tuning.addWidget(self.mac_only_check)
        tuning.addSpacing(16)
        tuning.addWidget(QLabel('Timeout:'))
        self.timeout_input = QDoubleSpinBox()
        self.timeout_input.setRange(0.1, 5.0)
        self.timeout_input.setSingleStep(0.1)
        self.timeout_input.setValue(0.6)
        self.timeout_input.setSuffix(' s')
        tuning.addWidget(self.timeout_input)
        tuning.addWidget(QLabel('Threads:'))
        self.workers_input = QSpinBox()
        self.workers_input.setRange(1, 256)
        self.workers_input.setValue(128)
        tuning.addWidget(self.workers_input)
        tuning.addStretch()
        layout.addLayout(tuning)

        buttons = QHBoxLayout()
        self.start_button = QPushButton('Start scan')
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton('Export CSV...')
        self.export_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_scan)
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.export_button.clicked.connect(self.export_csv)
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        self.status_label = QLabel('Ready. Scan only networks you administer.')
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, len(FIELDS))
        self.table.setHorizontalHeaderLabels(FIELDS)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self._copy_cell)
        self.table.cellDoubleClicked.connect(self._open_web_ui)
        self.table.setToolTip('Click a cell to copy it. Double-click a row to open the phone web UI.')
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        results_menu = self.menuBar().addMenu('Results')
        clear_action = QAction('Clear results', self)
        clear_action.triggered.connect(self.clear_results)
        results_menu.addAction(clear_action)
        export_action = QAction('Export CSV...', self)
        export_action.triggered.connect(self.export_csv)
        results_menu.addAction(export_action)

    def _current_target_text(self):
        data = self.subnet_input.currentData()
        text = self.subnet_input.currentText().strip()
        if data and text.startswith(data):
            return data
        return text

    @Slot()
    def start_scan(self):
        if self.thread is not None:
            return
        target_text = self._current_target_text()
        if not target_text:
            QMessageBox.warning(self, 'Missing subnet',
                                'Enter an IPv4 subnet, range or address.')
            return
        try:
            targets = expand_targets(target_text)
        except ValueError as error:
            QMessageBox.warning(self, 'Invalid target', str(error))
            return

        prefixes = [part.strip() for part in self.prefix_input.text().split(',') if part.strip()]
        options = dict(
            mac_prefixes=tuple(prefixes),
            deep_probe=self.deep_check.isChecked(),
            sip=self.sip_check.isChecked(),
            timeout=self.timeout_input.value(),
            workers=self.workers_input.value(),
            mac_only=self.mac_only_check.isChecked(),
        )

        self.rows = []
        self.table.setRowCount(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.progress.setRange(0, len(targets))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText('Scanning %s (%d addresses)...' % (target_text, len(targets)))

        self.thread = QThread(self)
        self.worker = ScanWorker(targets, options)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.row.connect(self.add_row)
        self.worker.progress.connect(self.update_progress)
        self.worker.message.connect(self.status_label.setText)
        self.worker.finished.connect(self.scan_finished)
        self.worker.failed.connect(self.scan_failed)
        self.worker.cancelled.connect(self.scan_cancelled)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot()
    def cancel_scan(self):
        if self.worker is not None:
            self.status_label.setText('Cancelling...')
            self.cancel_button.setEnabled(False)
            self.worker.cancel()

    @Slot(int, int)
    def update_progress(self, done, total):
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
        self.progress.setValue(done)

    @Slot(dict)
    def add_row(self, row):
        self.rows.append(row)
        self.table.setSortingEnabled(False)
        index = self.table.rowCount()
        self.table.insertRow(index)
        for column, field in enumerate(FIELDS):
            item = QTableWidgetItem(row[field])
            if field == 'IP address':
                item.setData(Qt.ItemDataRole.UserRole, row[field])
            self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.export_button.setEnabled(True)

    @Slot(int, int, int)
    def scan_finished(self, count, hosts_seen, macs_seen):
        if count:
            self.status_label.setText(
                'Found %d Mitel candidate(s). Responding hosts: %d, MACs resolved: %d.'
                % (count, hosts_seen, macs_seen))
        elif hosts_seen and not macs_seen:
            self.status_label.setText(
                '%d hosts responded but no MAC was resolved. MAC discovery needs the '
                'same VLAN as the phones; try the voice VLAN subnet.' % hosts_seen)
        else:
            self.status_label.setText(
                'No matches. Responding hosts: %d, MACs resolved: %d. Phones are usually '
                'on a separate voice VLAN - scan that subnet.' % (hosts_seen, macs_seen))

    @Slot(str)
    def scan_failed(self, error):
        self.status_label.setText('Scan failed.')
        QMessageBox.critical(self, 'Scan error', error)

    @Slot()
    def scan_cancelled(self):
        self.status_label.setText('Scan cancelled.')

    @Slot()
    def _thread_finished(self):
        self.progress.setVisible(False)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(bool(self.rows))
        self.thread.deleteLater()
        self.thread = None
        self.worker = None

    @Slot(int, int)
    def _copy_cell(self, row, column):
        item = self.table.item(row, column)
        if item and item.text() not in ('', '-'):
            QApplication.clipboard().setText(item.text())
            self.status_label.setText('Copied: %s' % item.text())

    @Slot(int, int)
    def _open_web_ui(self, row, _column):
        item = self.table.item(row, 0)
        if item:
            QDesktopServices.openUrl(QUrl('http://%s/' % item.text()))

    def clear_results(self):
        self.rows = []
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        self.status_label.setText('Results cleared.')

    def export_csv(self):
        if not self.rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export scan results',
                                              'mitel-phones.csv', 'CSV files (*.csv)')
        if not path:
            return
        try:
            write_csv(path, self.rows)
        except OSError as error:
            QMessageBox.critical(self, 'Export error', str(error))
            return
        self.status_label.setText('Saved: %s' % path)

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(3000)
        event.accept()


def write_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run_cli(args):
    try:
        targets = expand_targets(args.target)
    except ValueError as error:
        print('Error: %s' % error, file=sys.stderr)
        return 1
    prefixes = tuple(part.strip() for part in args.mac.split(',') if part.strip())
    engine = Scanner(targets, mac_prefixes=prefixes, deep_probe=not args.no_web,
                     sip=not args.no_sip, timeout=args.timeout,
                     workers=args.threads, mac_only=args.mac_only)
    print('Scanning %s (%d addresses). Only scan networks you administer.'
          % (args.target, len(targets)), flush=True)
    try:
        rows = engine.run(on_message=lambda text: print(text, flush=True))
    except KeyboardInterrupt:
        engine.cancel()
        print('Cancelled.', file=sys.stderr)
        return 130
    if rows:
        widths = {field: max(len(field), *(len(row[field]) for row in rows)) for field in FIELDS}
        print('\n' + ' | '.join(field.ljust(widths[field]) for field in FIELDS))
        print('-+-'.join('-' * widths[field] for field in FIELDS))
        for row in rows:
            print(' | '.join(row[field].ljust(widths[field]) for field in FIELDS))
    print('\nFound %d Mitel candidate(s). Responding hosts: %d, MACs resolved: %d.'
          % (len(rows), engine.hosts_seen, engine.macs_seen))
    if not rows:
        print('No matches does not prove there are no phones: MAC discovery needs the '
              'same VLAN, and phones usually live on a separate voice VLAN.')
    if args.csv:
        write_csv(args.csv, rows)
        print('Saved: %s' % args.csv)
    return 0


def main():
    if len(sys.argv) == 1:
        if QApplication is None:
            print('PySide6 is required for the GUI: python -m pip install PySide6\n'
                  'Command line mode works without it: python main.py 192.168.100.0/24',
                  file=sys.stderr)
            return 1
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        return app.exec()

    attach_console()
    parser = argparse.ArgumentParser(
        prog='MitelPhoneFinder', description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version',
                        version='Mitel 6900 IP Phone Finder %s' % __version__)
    parser.add_argument('target', help='IPv4 subnet (10.0.2.0/24), range (10.0.2.10-60) or IP')
    parser.add_argument('--mac', default=','.join(scanner.DEFAULT_MAC_PREFIXES),
                        help='comma separated MAC prefixes to match (default: 14)')
    parser.add_argument('--mac-only', action='store_true',
                        help='report only MAC matches, ignore web-only signatures')
    parser.add_argument('--no-web', action='store_true', help='skip HTTP/HTTPS fingerprinting')
    parser.add_argument('--no-sip', action='store_true', help='skip the SIP OPTIONS probe')
    parser.add_argument('--timeout', type=float, default=0.6, help='per-port timeout in seconds')
    parser.add_argument('--threads', type=int, default=128, help='concurrent sockets')
    parser.add_argument('--csv', metavar='FILE', help='save matches to CSV')
    return run_cli(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
