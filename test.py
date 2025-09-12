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
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# ------------------ VERSION ------------------
VERSION = "0.1"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"
UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/test.py"

def parse_version(v):
    return tuple(map(int, v.strip().split(".")))

# ------------------ Thread vérification mise à jour ------------------
class UpdateCheckerThread(QThread):
    result = pyqtSignal(str, bool)  # latest_version, up_to_date

    def run(self):
        try:
            r = requests.get(UPDATE_CHECK_URL, timeout=5)
            if r.status_code == 200:
                latest_version = r.text.strip()
                up_to_date = parse_version(VERSION) >= parse_version(latest_version)
                self.result.emit(latest_version, up_to_date)
            else:
                self.result.emit("Erreur", True)
        except Exception:
            self.result.emit("Erreur", True)

# ------------------ Fonctions VMT/Dossier ------------------
def read_file(path):
    for enc in ('utf-8','cp1252','latin-1'):
        try:
            with open(path,'r',encoding=enc) as f:
                return f.read(), enc
        except Exception:
            continue
    raise Exception(f"Impossible de lire {path}")

def replace_paths_in_vmt(MATERIALS_DIR, NEW_PATH, log_widget):
    key_pattern = re.compile(r'(\$[a-z0-9_]+\s+)(["\'])([^"\']+)(["\'])', re.IGNORECASE)
    any_quoted = re.compile(r'(["\'])([^"\']*[/\\][^"\']*)\1')
    modified_vmt_files = []
    vmt_dirs = set()
    for root, _, files in os.walk(MATERIALS_DIR):
        for fname in files:
            if not fname.lower().endswith(".vmt"):
                continue
            fullpath = os.path.join(root, fname)
            vmt_dirs.add(root)
            try:
                content, enc = read_file(fullpath)
            except Exception as e:
                log_widget.append(f"[ERREUR LECTURE] {fullpath} -> {e}")
                continue
            lines = content.splitlines(keepends=True)
            new_lines = []
            file_changes = []
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith("//") or stripped.startswith("/*"):
                    new_lines.append(line)
                    continue
                def repl_auto(m):
                    key, quote, pathval = m.group(1), m.group(2), m.group(3).replace('\\','/')
                    parts = pathval.split('/')
                    if len(parts) > 1:
                        newpath = NEW_PATH + '/' + parts[-1]
                        file_changes.append((key.strip(), pathval, newpath))
                        return key + quote + newpath + quote
                    return m.group(0)
                def repl_any_auto(m):
                    quote, pathval = m.group(1), m.group(2).replace('\\','/')
                    parts = pathval.split('/')
                    if len(parts) > 1:
                        newpath = NEW_PATH + '/' + parts[-1]
                        file_changes.append(("<any>", pathval, newpath))
                        return quote + newpath + quote
                    return m.group(0)
                line_mod = key_pattern.sub(repl_auto, line)
                line_mod = any_quoted.sub(repl_any_auto, line_mod)
                new_lines.append(line_mod)
            if file_changes:
                modified_vmt_files.append((fullpath, new_lines, enc, file_changes))
    return vmt_dirs, modified_vmt_files

def apply_vmt_changes(modified_vmt_files, log_widget):
    for fullpath, new_lines, enc, _ in modified_vmt_files:
        try:
            with open(fullpath, "w", encoding=enc) as f:
                f.write(''.join(new_lines))
            log_widget.append(f"[MODIFIÉ] {fullpath}")
        except Exception as e:
            log_widget.append(f"[ERREUR ÉCRITURE] {fullpath} -> {e}")

def apply_dirs_changes(dirs_to_rename, log_widget, prefix_suffix=""):
    for old, new in dirs_to_rename:
        base_name = os.path.basename(new)
        parent_dir = os.path.dirname(new)
        new_name = os.path.join(parent_dir, f"{prefix_suffix}{base_name}" if prefix_suffix else base_name)
        try:
            os.makedirs(os.path.dirname(new_name), exist_ok=True)
            if os.path.exists(new_name):
                for name in os.listdir(old):
                    src = os.path.join(old, name)
                    dst = os.path.join(new_name, name)
                    shutil.move(src, dst)
                try:
                    os.rmdir(old)
                except OSError:
                    pass
                log_widget.append(f"[DOSSIER FUSIONNÉ] {old} -> {new_name}")
            else:
                shutil.move(old, new_name)
                log_widget.append(f"[DOSSIER RENOMMÉ] {old} -> {new_name}")
        except Exception as e:
            log_widget.append(f"[ERREUR RENOMMAGE] {old} -> {new_name} : {e}")

# ------------------ Collecteur Addon ------------------
class AddonMaterialCollector(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧩 Collecte VMT/VTF depuis addon")
        self.setGeometry(150, 150, 800, 550)
        self.setStyleSheet("""
            QWidget{background-color:#1b1b1b; color:#ff3a3a; font-size:14px;}
            QLineEdit, QTextEdit{background-color:#2b2b2b; color:#ffffff; border:1px solid #ff3a3a;}
            QPushButton{background-color:#ff3a3a; color:#1b1b1b; border-radius:5px; padding:5px;}
        """)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        # Addon folder
        addon_group = QGroupBox("Dossier de l'addon")
        addon_layout = QHBoxLayout()
        self.addon_entry = QLineEdit()
        browse_addon_btn = QPushButton("📁 Parcourir")
        browse_addon_btn.clicked.connect(self.browse_addon)
        addon_layout.addWidget(self.addon_entry)
        addon_layout.addWidget(browse_addon_btn)
        addon_group.setLayout(addon_layout)
        layout.addWidget(addon_group)

        # Target folder
        target_group = QGroupBox("Dossier de destination")
        target_layout = QHBoxLayout()
        self.target_entry = QLineEdit()
        browse_target_btn = QPushButton("📁 Parcourir")
        browse_target_btn.clicked.connect(self.browse_target)
        target_layout.addWidget(self.target_entry)
        target_layout.addWidget(browse_target_btn)
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # Filter
        filter_group = QGroupBox("Filtre de matériau (optionnel)")
        filter_layout = QHBoxLayout()
        self.filter_entry = QLineEdit()
        filter_layout.addWidget(self.filter_entry)
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Collect button
        self.collect_btn = QPushButton("✅ Lancer la collecte")
        self.collect_btn.clicked.connect(self.collect_materials)
        layout.addWidget(self.collect_btn)

        # Logs
        layout.addWidget(QLabel("Journal d'activité"))
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
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
        addon_dir = self.addon_entry.text().strip()
        target_dir = self.target_entry.text().strip()
        filter_text = self.filter_entry.text().strip().replace("\\", "/").lower()
        if not os.path.isdir(addon_dir):
            self.log_widget.append("[ERREUR] Le dossier addon n'existe pas.")
            return
        if not os.path.isdir(target_dir):
            self.log_widget.append("[ERREUR] Le dossier de destination n'existe pas.")
            return
        count = 0
        for root, _, files in os.walk(addon_dir):
            for fname in files:
                if not fname.lower().endswith((".vmt", ".vtf")):
                    continue
                rel_path = os.path.relpath(os.path.join(root, fname), addon_dir).replace("\\", "/").lower()
                if filter_text and filter_text not in rel_path:
                    continue
                src = os.path.join(root, fname)
                dst = os.path.join(target_dir, fname)
                base, ext = os.path.splitext(fname)
                i = 1
                while os.path.exists(dst):
                    dst = os.path.join(target_dir, f"{base}_{i}{ext}")
                    i += 1
                try:
                    shutil.copy2(src, dst)
                    count += 1
                    self.log_widget.append(f"[COPIÉ] {src} -> {dst}")
                except Exception as e:
                    self.log_widget.append(f"[ERREUR] {src} -> {e}")
        self.log_widget.append(f"=== Collecte terminée : {count} fichiers copiés ===")

# ------------------ Fenêtre principale ------------------
class VMTPathRenamer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 VMT Path Renamer - Rouge/Noir")
        self.setGeometry(100, 100, 1100, 900)
        self.setStyleSheet("""
            QWidget{background-color:#1b1b1b; color:#ff3a3a; font-size:14px;}
            QLineEdit, QTextEdit{background-color:#2b2b2b; color:#ffffff; border:1px solid #ff3a3a;}
            QPushButton{background-color:#ff3a3a; color:#1b1b1b; border-radius:5px; padding:5px;}
            QPushButton:disabled{background-color:#555555; color:#aaaaaa;}
        """)
        self.init_ui()
        self.start_update_check()

    def init_ui(self):
        layout = QVBoxLayout()
        # Update check
        update_layout = QHBoxLayout()
        self.update_label = QLabel("🔄 Vérification mise à jour...")
        self.update_btn = QPushButton("⬇️ Télécharger mise à jour")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.download_update)
        update_layout.addWidget(self.update_label)
        update_layout.addWidget(self.update_btn)
        layout.addLayout(update_layout)

        # Folder selection
        folder_group = QGroupBox("Dossier à scanner")
        folder_layout = QHBoxLayout()
        self.folder_entry = QLineEdit()
        browse_btn = QPushButton("📁 Parcourir")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_entry)
        folder_layout.addWidget(browse_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # New path
        path_group = QGroupBox("Nouveau chemin (ex: models/nrxa/mayd3)")
        path_layout = QHBoxLayout()
        self.path_entry = QLineEdit()
        path_layout.addWidget(self.path_entry)
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Prefix/Suffix
        prefix_group = QGroupBox("Préfixe/Suffixe (optionnel)")
        prefix_layout = QHBoxLayout()
        self.prefix_entry = QLineEdit()
        prefix_layout.addWidget(self.prefix_entry)
        prefix_group.setLayout(prefix_layout)
        layout.addWidget(prefix_group)

        # Actions
        action_group = QGroupBox("Actions")
        action_layout = QHBoxLayout()
        self.run_vmt_btn = QPushButton("🔄 Modifier chemins VMT")
        self.run_rename_btn = QPushButton("📦 Renommer dossiers")
        self.scan_btn = QPushButton("🔍 Scanner dossiers")
        self.reset_btn = QPushButton("♻️ Reset")
        self.apply_move_btn = QPushButton("✅ Déplacer VMT/VTF")
        self.addon_window_btn = QPushButton("🧩 Collecteur Addon")
        for btn in [self.run_vmt_btn, self.run_rename_btn, self.scan_btn, self.reset_btn, self.apply_move_btn, self.addon_window_btn]:
            action_layout.addWidget(btn)
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        # Logs
        layout.addWidget(QLabel("Journal d'activité"))
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        layout.addWidget(self.log_widget)

        # Detected folders
        layout.addWidget(QLabel("Dossiers détectés"))
        self.detected_dirs_widget = QTextEdit()
        layout.addWidget(self.detected_dirs_widget)

        self.setLayout(layout)

        # Connect buttons
        self.run_vmt_btn.clicked.connect(self.run_vmt)
        self.run_rename_btn.clicked.connect(self.run_rename)
        self.scan_btn.clicked.connect(self.scan_vmt_dirs)
        self.reset_btn.clicked.connect(self.reset_fields)
        self.apply_move_btn.clicked.connect(self.apply_move_vmt_vtf)
        self.addon_window_btn.clicked.connect(self.open_addon_collector)

    # ------------------ Fonctions ------------------
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if folder:
            self.folder_entry.setText(folder)

    def reset_fields(self):
        self.folder_entry.clear()
        self.path_entry.clear()
        self.prefix_entry.clear()
        self.detected_dirs_widget.clear()
        self.log_widget.clear()

    def scan_vmt_dirs(self):
        self.detected_dirs_widget.clear()
        MATERIALS_DIR = self.folder_entry.text().strip()
        if not os.path.isdir(MATERIALS_DIR):
            QMessageBox.critical(self, "Erreur", "Le dossier spécifié n'existe pas.")
            return
        vmt_dirs = set()
        for root, _, files in os.walk(MATERIALS_DIR):
            if any(fname.lower().endswith(".vmt") for fname in files):
                vmt_dirs.add(root)
        for d in sorted(vmt_dirs):
            self.detected_dirs_widget.append(d)
        self.log_widget.append(f"{len(vmt_dirs)} dossiers détectés et listés.")

    def run_vmt(self):
        self.log_widget.clear()
        MATERIALS_DIR = self.folder_entry.text().strip()
        NEW_PATH = self.path_entry.text().strip().replace('\\','/')
        if not os.path.isdir(MATERIALS_DIR) or not NEW_PATH:
            QMessageBox.critical(self, "Erreur", "Vérifiez dossier et chemin cible.")
            return
        self.log_widget.append("=== Début remplacement chemins VMT ===")
        _, modified_vmt_files = replace_paths_in_vmt(MATERIALS_DIR, NEW_PATH, self.log_widget)
        apply_vmt_changes(modified_vmt_files, self.log_widget)
        self.log_widget.append("=== Remplacement terminé ===")

    def run_rename(self):
        self.log_widget.clear()
        prefix_suffix = self.prefix_entry.text().strip()
        dirs_to_rename = [(line.strip(), line.strip()) for line in self.detected_dirs_widget.toPlainText().splitlines() if line.strip()]
        if not dirs_to_rename:
            self.log_widget.append("Aucun dossier à renommer.")
            return
        apply_dirs_changes(dirs_to_rename, self.log_widget, prefix_suffix=prefix_suffix)
        self.log_widget.append("=== Renommage terminé ===")

    def apply_move_vmt_vtf(self):
        self.log_widget.append("=== Début déplacement VMT/VTF ===")
        target_dir = QFileDialog.getExistingDirectory(self, "Choisir le dossier de destination")
        if not target_dir:
            self.log_widget.append("[ANNULÉ] Aucun dossier choisi.")
            return
        prefix_suffix = self.prefix_entry.text().strip()
        for line in self.detected_dirs_widget.toPlainText().splitlines():
            old_dir = line.strip()
            if not old_dir or not os.path.exists(old_dir):
                continue
            base_name = os.path.basename(old_dir)
            dest_dir = os.path.join(target_dir, f"{prefix_suffix}{base_name}" if prefix_suffix else base_name)
            os.makedirs(dest_dir, exist_ok=True)
            for ext in ('.vmt', '.vtf'):
                for fname in os.listdir(old_dir):
                    if fname.lower().endswith(ext):
                        src = os.path.join(old_dir, fname)
                        dst = os.path.join(dest_dir, fname)
                        shutil.move(src, dst)
                        self.log_widget.append(f"[DÉPLACÉ] {src} -> {dst}")
        self.log_widget.append("=== Déplacement VMT/VTF terminé ===")

    def open_addon_collector(self):
        dlg = AddonMaterialCollector()
        dlg.exec_()

    # ------------------ Mise à jour ------------------
    def start_update_check(self):
        self.update_thread = UpdateCheckerThread()
        self.update_thread.result.connect(self.update_check_result)
        self.update_thread.start()

    def update_check_result(self, latest_version, up_to_date):
        if latest_version == "Erreur":
            self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
            self.update_btn.setEnabled(False)
        else:
            if up_to_date:
                self.update_label.setText(f"✅ Application à jour ({VERSION})")
                self.update_btn.setEnabled(False)
            else:
                self.update_label.setText(f"❌ Nouvelle version disponible ({latest_version})")
                self.update_btn.setEnabled(True)

    def download_update(self):
        try:
            r = requests.get(UPDATE_SCRIPT_URL, timeout=10)
            if r.status_code != 200:
                QMessageBox.warning(self, "Erreur", "Impossible de télécharger la nouvelle version.")
                return
            script_path = os.path.abspath(sys.argv[0])
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            QMessageBox.information(self, "Mise à jour", "Nouvelle version installée !\nL'application va redémarrer.")
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Échec téléchargement : {e}")

# ------------------ Lancement ------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMTPathRenamer()
    window.show()
    sys.exit(app.exec_())
