import os 
import re
import shutil
import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QMessageBox,
    QDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor, QPalette

# ------------------ VERSION ------------------
VERSION = "0.3"  # Version locale actuelle
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"
UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/test.py"

def parse_version(v):
    return tuple(map(int, v.strip().split(".")))

# ------------------ Fonctions VMT/Dossier ------------------
# (ici toutes les fonctions précédentes read_file, replace_paths_in_vmt, apply_vmt_changes, etc.)
# Je les laisse inchangées pour garder ton logic.

# ------------------ Collecteur Addon ------------------
class AddonMaterialCollector(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧩 Collecte VMT/VTF depuis addon")
        self.setGeometry(150, 150, 800, 550)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setStyleSheet("background-color: #1b1b1b; color: white;")
        
        # Dossier addon
        addon_group = QGroupBox("Dossier de l'addon")
        addon_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        addon_layout = QHBoxLayout()
        self.addon_entry = QLineEdit()
        self.addon_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        browse_addon_btn = QPushButton("📁 Parcourir")
        browse_addon_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        browse_addon_btn.clicked.connect(self.browse_addon)
        addon_layout.addWidget(self.addon_entry)
        addon_layout.addWidget(browse_addon_btn)
        addon_group.setLayout(addon_layout)
        layout.addWidget(addon_group)

        # Dossier cible
        target_group = QGroupBox("Dossier de destination")
        target_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        target_layout = QHBoxLayout()
        self.target_entry = QLineEdit()
        self.target_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        browse_target_btn = QPushButton("📁 Parcourir")
        browse_target_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        browse_target_btn.clicked.connect(self.browse_target)
        target_layout.addWidget(self.target_entry)
        target_layout.addWidget(browse_target_btn)
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # Filtre
        filter_group = QGroupBox("Filtre de matériau (optionnel)")
        filter_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        filter_layout = QHBoxLayout()
        self.filter_entry = QLineEdit()
        self.filter_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        filter_layout.addWidget(self.filter_entry)
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Bouton Collecte
        self.collect_btn = QPushButton("✅ Lancer la collecte")
        self.collect_btn.setStyleSheet("background-color: red; color: white; font-weight: bold; height: 35px;")
        self.collect_btn.clicked.connect(self.collect_materials)
        layout.addWidget(self.collect_btn)

        # Log
        layout.addWidget(QLabel("Journal d'activité"))
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setStyleSheet("background-color: #2b2b2b; color: white;")
        layout.addWidget(self.log_widget)

        self.setLayout(layout)

    def browse_addon(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de l'addon")
        if folder:
            self.addon_entry.setText(folder)

    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de destination")
        if folder:
            self.target_entry.setText(folder)

    def collect_materials(self):
        self.log_widget.clear()
        # Logique de collecte inchangée...
        self.log_widget.append("=== Collecte terminée ===")

# ------------------ Fenêtre principale ------------------
class VMTPathRenamer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 VMT Path Renamer - Rouge/Noir")
        self.setGeometry(100, 100, 1100, 900)
        self.init_ui()
        self.check_update()

    def init_ui(self):
        self.setStyleSheet("background-color: #1b1b1b; color: white; font-size: 14px;")
        layout = QVBoxLayout()

        # Barre mise à jour
        update_layout = QHBoxLayout()
        self.update_label = QLabel("🔄 Vérification mise à jour...")
        self.update_label.setStyleSheet("color: red; font-weight: bold;")
        self.update_btn = QPushButton("⬇️ Télécharger nouvelle version")
        self.update_btn.setStyleSheet("background-color: red; color: white; font-weight: bold; height: 30px;")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.download_update)
        update_layout.addWidget(self.update_label)
        update_layout.addWidget(self.update_btn)
        layout.addLayout(update_layout)

        # Dossier à scanner
        folder_group = QGroupBox("Dossier à scanner")
        folder_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        folder_layout = QHBoxLayout()
        self.folder_entry = QLineEdit()
        self.folder_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        browse_btn = QPushButton("📁 Parcourir")
        browse_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_entry)
        folder_layout.addWidget(browse_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # Nouveau chemin
        path_group = QGroupBox("Nouveau chemin (ex: models/nrxa/mayd3)")
        path_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        path_layout = QHBoxLayout()
        self.path_entry = QLineEdit()
        self.path_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        path_layout.addWidget(self.path_entry)
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Préfixe/Suffixe
        prefix_group = QGroupBox("Préfixe/Suffixe (optionnel)")
        prefix_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        prefix_layout = QHBoxLayout()
        self.prefix_entry = QLineEdit()
        self.prefix_entry.setStyleSheet("background-color: #2b2b2b; color: white; border: 1px solid red;")
        prefix_layout.addWidget(self.prefix_entry)
        prefix_group.setLayout(prefix_layout)
        layout.addWidget(prefix_group)

        # Actions
        action_group = QGroupBox("Actions")
        action_group.setStyleSheet("QGroupBox { color: red; font-weight: bold; }")
        action_layout = QHBoxLayout()
        self.run_vmt_btn = QPushButton("🔄 Modifier chemins VMT")
        self.run_rename_btn = QPushButton("📦 Renommer dossiers")
        self.scan_btn = QPushButton("🔍 Scanner dossiers")
        self.reset_btn = QPushButton("♻️ Reset")
        self.apply_move_btn = QPushButton("✅ Déplacer VMT/VTF")
        self.addon_window_btn = QPushButton("🧩 Collecteur Addon")
        for btn in [self.run_vmt_btn, self.run_rename_btn, self.scan_btn, self.reset_btn, self.apply_move_btn, self.addon_window_btn]:
            btn.setStyleSheet("background-color: red; color: white; font-weight: bold; height: 30px;")
            action_layout.addWidget(btn)
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        # Logs
        layout.addWidget(QLabel("Journal d'activité"))
        self.log_widget = QTextEdit()
        self.log_widget.setStyleSheet("background-color: #2b2b2b; color: white;")
        layout.addWidget(self.log_widget)

        # Dossiers détectés
        layout.addWidget(QLabel("Dossiers détectés"))
        self.detected_dirs_widget = QTextEdit()
        self.detected_dirs_widget.setStyleSheet("background-color: #2b2b2b; color: white;")
        layout.addWidget(self.detected_dirs_widget)

        self.setLayout(layout)

        # Connexions
        self.run_vmt_btn.clicked.connect(self.run_vmt)
        self.run_rename_btn.clicked.connect(self.run_rename)
        self.scan_btn.clicked.connect(self.scan_vmt_dirs)
        self.reset_btn.clicked.connect(self.reset_fields)
        self.apply_move_btn.clicked.connect(self.apply_move_vmt_vtf)
        self.addon_window_btn.clicked.connect(self.open_addon_collector)

    # ------------------ Les autres fonctions check_update, download_update, etc. restent inchangées ------------------

# ------------------ Lancement ------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMTPathRenamer()
    window.show()
    sys.exit(app.exec_())
