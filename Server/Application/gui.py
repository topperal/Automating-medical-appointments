# -*- coding: utf-8 -*-
import sys
import os
import json
import threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox, QFormLayout,
    QDialog, QDialogButtonBox  # <-- добавлено для окна предпросмотра
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

from ocr_engine import process_pdf
from ner_extractor import extract_appointments, save_json
from crypto_utils import encrypt_json
from yadisk_uploader import test_connection, upload_file, create_folder


class SignalEmitter(QObject):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    preview_signal = pyqtSignal(dict)  # <-- новый сигнал для предпросмотра


class JsonPreviewDialog(QDialog):
    """Окно предпросмотра JSON перед шифрованием"""
    def __init__(self, json_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр JSON перед шифрованием")
        self.setMinimumSize(600, 500)
        self.json_data = json_data
        self.result = False  # True = продолжить, False = отмена
        
        layout = QVBoxLayout(self)
        
        # Информация
        info = QLabel(f"Пациент ID: {json_data.get('patient_id', 'N/A')}")
        info.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(info)
        
        count = len(json_data.get('appointments', []))
        count_label = QLabel(f"Найдено назначений: {count}")
        layout.addWidget(count_label)
        
        # Текст JSON
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        json_str = json.dumps(json_data, ensure_ascii=False, indent=4)
        self.text_edit.setText(json_str)
        layout.addWidget(self.text_edit)
        
        # Кнопки
        buttons = QDialogButtonBox()
        btn_ok = QPushButton("✓ Все верно, продолжить")
        btn_ok.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 16px;")
        btn_cancel = QPushButton("✗ Отмена")
        btn_cancel.setStyleSheet("background-color: #f44336; color: white; padding: 8px 16px;")
        
        buttons.addButton(btn_ok, QDialogButtonBox.AcceptRole)
        buttons.addButton(btn_cancel, QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(buttons)
    
    def accept(self):
        self.result = True
        super().accept()
    
    def reject(self):
        self.result = False
        super().reject()


class MedCardApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Обработка амбулаторных карт")
        self.setMinimumSize(800, 700)
        self.signal = SignalEmitter()
        self.signal.log_signal.connect(self.append_log)
        self.signal.finished_signal.connect(self.on_finished)
        self.signal.error_signal.connect(self.on_error)
        self.signal.preview_signal.connect(self.show_preview)  # <-- подключаем предпросмотр
        self.pending_data = None  # <-- временное хранилище данных
        self.setup_ui()
    
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Заголовок
        title = QLabel("Обработка амбулаторной карты")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # 1. PDF файл
        pdf_group = QGroupBox("1. Выбор PDF файла")
        pdf_layout = QHBoxLayout()
        self.pdf_path = QLineEdit()
        self.pdf_path.setPlaceholderText("Путь к PDF файлу...")
        pdf_layout.addWidget(self.pdf_path)
        btn_browse = QPushButton("Обзор...")
        btn_browse.clicked.connect(self.browse_pdf)
        pdf_layout.addWidget(btn_browse)
        pdf_group.setLayout(pdf_layout)
        layout.addWidget(pdf_group)
        
        # 2. Настройки
        settings_group = QGroupBox("2. Настройки обработки")
        settings_layout = QFormLayout()
        
        self.target_page = QSpinBox()
        self.target_page.setRange(1, 20)
        self.target_page.setValue(3)
        settings_layout.addRow("Страница с назначениями:", self.target_page)
        
        self.room_id = QLineEdit("27")
        settings_layout.addRow("Номер палаты:", self.room_id)
        
        self.secret_key = QLineEdit()
        self.secret_key.setEchoMode(QLineEdit.Password)
        settings_layout.addRow("Секретный ключ:", self.secret_key)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # 3. Яндекс.Диск
        ya_group = QGroupBox("3. Яндекс.Диск (опционально)")
        ya_layout = QFormLayout()
        
        self.ya_token = QLineEdit()
        self.ya_token.setEchoMode(QLineEdit.Password)
        ya_layout.addRow("OAuth токен:", self.ya_token)
        
        self.ya_folder = QLineEdit("/ER/MedCards")
        ya_layout.addRow("Папка на Диске:", self.ya_folder)
        
        btn_test = QPushButton("Проверить соединение")
        btn_test.clicked.connect(self.test_ya_connection)
        ya_layout.addRow(btn_test)
        
        ya_group.setLayout(ya_layout)
        layout.addWidget(ya_group)
        
        # Кнопка запуска
        self.btn_process = QPushButton("▶ Начать обработку")
        self.btn_process.setStyleSheet("font-size: 14px; padding: 10px;")
        self.btn_process.clicked.connect(self.start_processing)
        layout.addWidget(self.btn_process)
        
        # Прогресс
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        
        # Лог
        log_group = QGroupBox("Лог выполнения")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
    
    def browse_pdf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Выберите PDF файл", "", "PDF files (*.pdf);;All files (*.*)"
        )
        if filename:
            self.pdf_path.setText(filename)
            self.log(f"Выбран файл: {filename}")
    
    def log(self, message):
        self.log_text.append(message)
    
    def append_log(self, message):
        self.log(message)
    
    def test_ya_connection(self):
        token = self.ya_token.text().strip()
        if not token:
            QMessageBox.warning(self, "Внимание", "Введите OAuth токен")
            return
        
        if test_connection(token):
            QMessageBox.information(self, "Успех", "Соединение с Яндекс.Диском установлено!")
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось подключиться к Яндекс.Диску")
    
    def start_processing(self):
        if not self.pdf_path.text():
            QMessageBox.warning(self, "Внимание", "Выберите PDF файл")
            return
        
        if not self.secret_key.text():
            QMessageBox.warning(self, "Внимание", "Введите секретный ключ для шифрования")
            return
        
        self.btn_process.setEnabled(False)
        self.progress.show()
        
        thread = threading.Thread(target=self.process)
        thread.daemon = True
        thread.start()
    
    def process(self):
        try:
            pdf_path = self.pdf_path.text()
            room_id = self.room_id.text()
            secret = self.secret_key.text()
            page = self.target_page.value() - 1
            
            # 1. OCR
            self.signal.log_signal.emit("🔍 Этап 1: Извлечение текста из PDF...")
            text = process_pdf(pdf_path, target_page=page)
            self.signal.log_signal.emit(f"✓ Текст извлечен, длина: {len(text)} символов")
            
            if not text:
                raise Exception("Не удалось извлечь текст из PDF")
            
            # 2. NER
            self.signal.log_signal.emit("📝 Этап 2: Извлечение назначений...")
            data = extract_appointments(text)
            count = len(data['appointments'])
            self.signal.log_signal.emit(f"✓ Найдено назначений: {count}")
            
            if count == 0:
                raise Exception("Назначения не найдены. Проверьте страницу PDF.")
            
            # 3. СОХРАНЯЕМ JSON для предпросмотра
            json_file = "appointments_preview.json"
            save_json(data, json_file)
            self.signal.log_signal.emit(f"💾 JSON сохранен для предпросмотра: {json_file}")
            
            # <-- ОТПРАВЛЯЕМ СИГНАЛ ДЛЯ ПРЕДПРОСМОТРА (в главном потоке)
            self.pending_data = {
                'data': data,
                'room_id': room_id,
                'secret': secret,
                'json_file': json_file
            }
            self.signal.preview_signal.emit(data)
            
        except Exception as e:
            self.signal.error_signal.emit(str(e))
    
    def show_preview(self, json_data):
        """Показывает окно предпросмотра JSON (выполняется в главном потоке)"""
        dialog = JsonPreviewDialog(json_data, self)
        dialog.exec_()
        
        if dialog.result:
            # Пользователь нажал "Продолжить"
            self.signal.log_signal.emit("👍 Пользователь подтвердил JSON, продолжаем...")
            self.continue_processing()
        else:
            # Пользователь нажал "Отмена"
            self.signal.log_signal.emit("❌ Шифрование отменено пользователем")
            self.on_finished()
    
    def continue_processing(self):
        """Продолжение после предпросмотра"""
        try:
            data = self.pending_data['data']
            room_id = self.pending_data['room_id']
            secret = self.pending_data['secret']
            json_file = self.pending_data['json_file']
            
            # 4. Шифрование
            self.signal.log_signal.emit("🔐 Этап 4: Шифрование AES-256...")
            enc_file = encrypt_json(json_file, room_id, secret, delete_original=False)
            self.signal.log_signal.emit(f"✓ Файл зашифрован: {enc_file}")
            self.signal.log_signal.emit(f"📄 JSON сохранен для проверки: {json_file}")
            
            # 5. Яндекс.Диск
            token = self.ya_token.text().strip()
            if token:
                self.signal.log_signal.emit("☁ Этап 5: Загрузка на Яндекс.Диск...")
                folder = self.ya_folder.text()
                create_folder(folder, token)
                
                remote_path = f"{folder}/{enc_file}"
                if upload_file(enc_file, remote_path, token):
                    self.signal.log_signal.emit(f"✓ Загружено: {remote_path}")
                else:
                    self.signal.log_signal.emit("✗ Ошибка загрузки на Яндекс.Диск")
            else:
                self.signal.log_signal.emit("ℹ Яндекс.Диск пропущен")
            
            self.signal.log_signal.emit("\n" + "="*50)
            self.signal.log_signal.emit("✅ ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО!")
            self.signal.log_signal.emit(f"Пациент ID: {data['patient_id']}")
            self.signal.log_signal.emit("="*50)
            
            self.signal.finished_signal.emit()
            
        except Exception as e:
            self.signal.error_signal.emit(str(e))
    
    def on_finished(self):
        self.progress.hide()
        self.btn_process.setEnabled(True)
        self.pending_data = None
    
    def on_error(self, error_msg):
        self.progress.hide()
        self.btn_process.setEnabled(True)
        self.log(f"\n❌ ОШИБКА: {error_msg}")
        QMessageBox.critical(self, "Ошибка", error_msg)
        self.pending_data = None


def main():
    app = QApplication(sys.argv)
    window = MedCardApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()