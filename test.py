import requests
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout
from PyQt5.QtCore import Qt
import os

VERSION = "2.0.0"  # Version locale
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/tonrepo/version.txt"
GITHUB_UPDATE_URL = "https://raw.githubusercontent.com/tonrepo/main.py"  # Fichier à télécharger

class UpdateChecker(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vérification de mise à jour")
        self.setGeometry(100, 100, 400, 200)

        self.update_label = QLabel("🔍 Vérification en cours...", self)
        self.update_label.setAlignment(Qt.AlignCenter)

        self.update_status_icon = QLabel("🔄", self)
        self.update_status_icon.setAlignment(Qt.AlignCenter)

        self.update_btn = QPushButton("Mettre à jour", self)
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.launch_update)

        layout = QVBoxLayout()
        layout.addWidget(self.update_status_icon)
        layout.addWidget(self.update_label)
        layout.addWidget(self.update_btn)
        self.setLayout(layout)

        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #f05454;
                font-family: 'Segoe UI';
                font-size: 14px;
            }
            QPushButton {
                background-color: #f05454;
                color: #ffffff;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #ff7676;
            }
            QLabel {
                font-weight: bold;
            }
        """)

        self.check_for_update()

    def check_for_update(self):
        try:
            response = requests.get(GITHUB_VERSION_URL)
            latest_version = response.text.strip()
            up_to_date = latest_version == VERSION
        except Exception:
            latest_version = "Erreur"
            up_to_date = False

        self.update_check_result(latest_version, up_to_date)

    def update_check_result(self, latest_version, up_to_date):
        local_version = VERSION
        if latest_version == "Erreur":
            self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
            self.update_status_icon.setText("❓")
            self.update_btn.setEnabled(False)
        else:
            if up_to_date:
                self.update_label.setText(
                    f"✅ À jour !\nVersion locale : {local_version}\nVersion GitHub : {latest_version}"
                )
                self.update_status_icon.setText("✅")
                self.update_btn.setEnabled(False)
            else:
                self.update_label.setText(
                    f"❌ Mise à jour disponible !\nVersion locale : {local_version}\nVersion GitHub : {latest_version}"
                )
                self.update_status_icon.setText("❌")
                self.update_btn.setEnabled(True)

    def launch_update(self):
        self.update_label.setText("📥 Téléchargement de la mise à jour...")
        self.update_status_icon.setText("🔄")
        self.update_btn.setEnabled(False)

        try:
            response = requests.get(GITHUB_UPDATE_URL)
            with open("main_updated.py", "w", encoding="utf-8") as f:
                f.write(response.text)
            self.update_label.setText("✅ Mise à jour téléchargée : main_updated.py")
            self.update_status_icon.setText("📦")
        except Exception:
            self.update_label.setText("❌ Échec du téléchargement")
            self.update_status_icon.setText("⚠️")

if __name__ == "__main__":
    app = QApplication([])
    window = UpdateChecker()
    window.show()
    app.exec_()

