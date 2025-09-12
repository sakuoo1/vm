import os
import re
import shutil
import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# --- VERSION ET URL ---
VERSION = "0.3"  # version locale
UPDATE_TXT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"
UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/test.py"

# --- Thread vérification mise à jour ---
class UpdateCheckerThread(QThread):
    result = pyqtSignal(str, bool)  # latest_version, up_to_date

    def run(self):
        try:
            r = requests.get(UPDATE_TXT_URL, timeout=5)
            if r.status_code == 200:
                latest_version = r.text.strip().replace('\ufeff','')
                local_tuple = tuple(map(int, VERSION.split(".")))
                latest_tuple = tuple(map(int, latest_version.split(".")))
                up_to_date = local_tuple >= latest_tuple
                self.result.emit(latest_version, up_to_date)
            else:
                self.result.emit("Erreur", False)
        except Exception:
            self.result.emit("Erreur", False)

# --- Les fonctions VMT/Dossier --- (copiées telles quelles)
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

# --- Interface ---
class VMTPathRenamer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 VMT Path Renamer - Noir/Rouge")
        self.setGeometry(100, 100, 1100, 900)
        self.init_ui()
        # Lancer vérification mise à jour
        self.update_label.setText("🔄 Vérification mise à jour...")
        self.check_update()

    def init_ui(self):
        layout = QVBoxLayout()

        # Label mise à jour
        self.update_label = QLabel("🔄 Vérification mise à jour...")
        layout.addWidget(self.update_label)

        # Bouton mise à jour
        self.update_btn = QPushButton("⬇️ Télécharger mise à jour")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.download_update)
        layout.addWidget(self.update_btn)

        # --- Le reste de ton UI existante ---
        # Dossier, chemin, actions, logs, etc. (comme dans ton code)
        # Pour simplifier je laisse l'existant, tu peux copier ton UI actuel ici
        # ...

        self.setLayout(layout)

    # --- Vérification mise à jour ---
    def check_update(self):
        self.update_thread = UpdateCheckerThread()
        self.update_thread.result.connect(self.update_result)
        self.update_thread.start()

    def update_result(self, latest_version, up_to_date):
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

# --- Lancement ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMTPathRenamer()
    window.show()
    sys.exit(app.exec_())
