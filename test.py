import os
import re
import shutil
import sys
import traceback
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# ------------------ VERSION ------------------
VERSION = "9.0.0"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"
UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/test.py"

def write_crash_log(exc: Exception):
    """Écrit l'erreur dans crash.txt"""
    crash_path = os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "crash.txt")
    with open(crash_path, "a", encoding="utf-8") as f:
        f.write(f"--- {traceback.format_exc()} ---\n")

# ------------------ Thread de vérification MAJ ------------------
class UpdateCheckerThread(QThread):
    result = pyqtSignal(str, bool, str)  # latest_version, up_to_date, error_message

    def run(self):
        try:
            r = requests.get(UPDATE_CHECK_URL, timeout=5)
            if r.status_code != 200:
                self.result.emit("", True, "Erreur HTTP lors de la vérification")
                return
            latest_version = r.text.strip().splitlines()[0].strip()
            up_to_date = self.version_tuple(VERSION) >= self.version_tuple(latest_version)
            self.result.emit(latest_version, up_to_date, "")
        except Exception as e:
            self.result.emit("", True, str(e))

    @staticmethod
    def version_tuple(v):
        return tuple(int(x) for x in v.strip().split(".") if x.isdigit())

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
            write_crash_log(e)

def apply_dirs_changes(dirs_to_rename, log_widget, prefix_suffix=""):
    for old, new in dirs_to_rename:
        base_name = os.path.basename(new)
        parent_dir = os.path.dirname(new)
        new_name = os.path.join(parent_dir, f"{prefix_suffix}{base_name}")
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
            write_crash_log(e)

# ------------------ Interface principale ------------------
class VMTPathRenamer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 VMT Path Renamer - Noir/Rouge")
        self.setGeometry(100, 100, 1100, 900)
        self.init_ui()
        self.start_update_check()

    def init_ui(self):
        layout = QVBoxLayout()

        # Label MAJ
        self.update_label = QLabel("🔄 Vérification mise à jour...")
        layout.addWidget(self.update_label)

        def styled_button(text):
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #990000;
                    color: #FFF;
                    font-weight: bold;
                    border-radius: 12px;
                    padding: 12px 20px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: #FF3333;
                }
            """)
            return btn

        # Dossier
        folder_group = QGroupBox("Dossier à scanner")
        folder_layout = QHBoxLayout()
        self.folder_entry = QLineEdit()
        browse_btn = styled_button("📁 Parcourir")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_entry)
        folder_layout.addWidget(browse_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # Nouveau chemin
        path_group = QGroupBox("Nouveau chemin")
        path_layout = QHBoxLayout()
        self.path_entry = QLineEdit()
        path_layout.addWidget(self.path_entry)
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Préfixe/Suffixe
        prefix_group = QGroupBox("Préfixe/Suffixe (optionnel)")
        prefix_layout = QHBoxLayout()
        self.prefix_entry = QLineEdit()
        prefix_layout.addWidget(self.prefix_entry)
        prefix_group.setLayout(prefix_layout)
        layout.addWidget(prefix_group)

        # Actions
        action_group = QGroupBox("Actions")
        action_layout = QHBoxLayout()
        self.run_vmt_btn = styled_button("🔄 Modifier chemins VMT")
        self.run_rename_btn = styled_button("📦 Renommer dossiers")
        self.scan_btn = styled_button("🔍 Scanner dossiers")
        self.reset_btn = styled_button("♻️ Reset")
        self.apply_move_btn = styled_button("✅ Déplacer VMT/VTF")
        self.run_vmt_btn.clicked.connect(self.run_vmt)
        self.run_rename_btn.clicked.connect(self.run_rename)
        self.scan_btn.clicked.connect(self.scan_vmt_dirs)
        self.reset_btn.clicked.connect(self.reset_fields)
        self.apply_move_btn.clicked.connect(self.apply_move_vmt_vtf)
        for btn in [self.run_vmt_btn, self.run_rename_btn, self.scan_btn, self.reset_btn, self.apply_move_btn]:
            action_layout.addWidget(btn)
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        # Log
        layout.addWidget(QLabel("Journal d'activité"))
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        layout.addWidget(self.log_widget)

        # Dossiers détectés
        layout.addWidget(QLabel("Dossiers détectés"))
        self.detected_dirs_widget = QTextEdit()
        layout.addWidget(self.detected_dirs_widget)

        self.setLayout(layout)

        # Style global
        self.setStyleSheet("""
            QWidget {
                background-color: #111;
                color: #FFF;
                font-family: 'Segoe UI';
                font-size: 14px;
            }
            QGroupBox {
                border: 2px solid #990000;
                border-radius: 10px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
                color: #FF3333;
            }
            QLabel {
                color: #FF3333;
                font-weight: bold;
            }
            QLineEdit, QTextEdit {
                background-color: #222;
                color: #FFF;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QTextEdit {
                color: #FF6666;
            }
        """)

    # --- Fonctions principales ---
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
        try:
            MATERIALS_DIR = self.folder_entry.text().strip()
            NEW_PATH = self.path_entry.text().strip().replace('\\','/')
            if not os.path.isdir(MATERIALS_DIR) or not NEW_PATH:
                QMessageBox.critical(self, "Erreur", "Vérifiez dossier et chemin cible.")
                return
            self.log_widget.append("=== Début remplacement chemins VMT ===")
            _, modified_vmt_files = replace_paths_in_vmt(MATERIALS_DIR, NEW_PATH, self.log_widget)
            apply_vmt_changes(modified_vmt_files, self.log_widget)
            self.log_widget.append("=== Remplacement terminé ===")
        except Exception as e:
            write_crash_log(e)
            self.log_widget.append(f"[ERREUR] {e}")

    def run_rename(self):
        self.log_widget.clear()
        try:
            prefix_suffix = self.prefix_entry.text().strip()
            dirs_to_rename = [(line.strip(), line.strip()) for line in self.detected_dirs_widget.toPlainText().splitlines() if line.strip()]
            if not dirs_to_rename:
                self.log_widget.append("Aucun dossier à renommer.")
                return
            apply_dirs_changes(dirs_to_rename, self.log_widget, prefix_suffix=prefix_suffix)
            self.log_widget.append("=== Renommage terminé ===")
        except Exception as e:
            write_crash_log(e)
            self.log_widget.append(f"[ERREUR] {e}")

    def apply_move_vmt_vtf(self):
        self.log_widget.append("=== Début déplacement VMT/VTF ===")
        try:
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
        except Exception as e:
            write_crash_log(e)
            self.log_widget.append(f"[ERREUR] {e}")

    # --- Mise à jour ---
    def start_update_check(self):
        try:
            self.update_thread = UpdateCheckerThread()
            self.update_thread.result.connect(self.update_check_result)
            self.update_thread.start()
        except Exception as e:
            write_crash_log(e)
            self.update_label.setText(f"⚠ Impossible de vérifier la mise à jour: {e}")

    def update_check_result(self, latest_version, up_to_date, error_message):
        if error_message:
            self.update_label.setText(f"⚠ Impossible de vérifier la mise à jour: {error_message}")
        else:
            if up_to_date:
                self.update_label.setText(f"✅ Application à jour ({VERSION})")
            else:
                self.update_label.setText(f"❌ Nouvelle version disponible ({latest_version})")
                reply = QMessageBox.question(self, "Mise à jour disponible",
                                             f"Nouvelle version ({latest_version}) disponible.\nVoulez-vous mettre à jour ?",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.download_update()

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
            write_crash_log(e)
            QMessageBox.warning(self, "Erreur", f"Échec téléchargement : {e}")

# ------------------ Lancement ------------------
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = VMTPathRenamer()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        write_crash_log(e)
        QMessageBox.critical(None, "Crash", f"L'application a crashé : {e}")

