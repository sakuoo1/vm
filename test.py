import os

import re

import shutil

import sys

import requests

from PyQt5.QtWidgets import (

    QApplication, QWidget, QLabel, QLineEdit, QPushButton,

    QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QMessageBox

)

from PyQt5.QtCore import Qt



# ------------------ VERSION ------------------

VERSION = "10.0.0"  # version locale

UPDATE_CHECK_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"

UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/test.py"



def parse_version(v):
    try:
        v_clean = (v or "").strip().replace('\ufeff', '').replace('\r', '').replace('\n', '')
        return tuple(int(x) for x in v_clean.split("."))
    except Exception:
        return (0,)



def log_crash(error_text):

    """Crée un fichier crash.txt avec l'erreur"""

    try:

        crash_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "crash.txt")

        with open(crash_path, "w", encoding="utf-8") as f:

            f.write(error_text)

    except Exception:

        pass  # si écrire le crash échoue, on ignore



def check_update():
    """Vérifie la version sur GitHub avec contournement ultra-robuste du cache"""
    try:
        import time
        import random
        print(f"[DEBUG] Vérification de la mise à jour...")
        print(f"[DEBUG] URL: {UPDATE_CHECK_URL}")
        print(f"[DEBUG] Version locale: {VERSION}")
        
        # Méthodes ultra-multiples pour contourner le cache GitHub
        timestamp = int(time.time())
        random_hash = random.randint(100000, 999999)
        urls_to_try = [
            # URL originale
            UPDATE_CHECK_URL,
            # URLs avec timestamps variés
            f"{UPDATE_CHECK_URL}?t={timestamp}",
            f"{UPDATE_CHECK_URL}?v={timestamp}&nocache=1",
            f"{UPDATE_CHECK_URL}?timestamp={timestamp}&force=1",
            f"{UPDATE_CHECK_URL}?hash={random_hash}&t={timestamp}",
            f"{UPDATE_CHECK_URL}?cache_bust={timestamp}&random={random_hash}",
            # URLs avec paramètres différents
            f"{UPDATE_CHECK_URL}?refresh=1&t={timestamp}",
            f"{UPDATE_CHECK_URL}?bypass_cache=1&v={timestamp}",
            f"{UPDATE_CHECK_URL}?nocache=1&timestamp={timestamp}&random={random_hash}",
            # URL alternative GitHub
            UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "github.com").replace("/main/", "/blob/main/"),
            # URLs avec millisecondes
            f"{UPDATE_CHECK_URL}?ms={int(time.time() * 1000)}",
            f"{UPDATE_CHECK_URL}?micro={int(time.time() * 1000000)}"
        ]
        
        # Headers ultra-agressifs
        headers_variants = [
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'User-Agent': f'VMT-Path-Renamer/{VERSION}',
                'Accept': 'text/plain, */*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'close'
            },
            {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'User-Agent': f'Mozilla/5.0 VMT-Path-Renamer/{VERSION}',
                'Accept': '*/*',
                'Connection': 'keep-alive'
            },
            {
                'Cache-Control': 'no-store',
                'User-Agent': f'VMT-Path-Renamer-ForceCheck/{VERSION}',
                'Accept': 'text/plain',
                'Connection': 'close'
            }
        ]
        
        successful_results = []
        
        # Essayer toutes les combinaisons URL + headers
        for i, url in enumerate(urls_to_try):
            for j, headers in enumerate(headers_variants):
                try:
                    print(f"[DEBUG] Tentative {i+1}.{j+1}: {url}")
                    
                    r = requests.get(url, timeout=8, headers=headers)
                    print(f"[DEBUG] Statut HTTP: {r.status_code}")
                    
                    if r.status_code == 200:
                        latest_version_raw = r.text.strip()
                        print(f"[DEBUG] Version brute: '{latest_version_raw}'")
                        
                        if latest_version_raw:
                            latest_version_clean = latest_version_raw.replace('\ufeff', '').replace('\r', '').replace('\n', '')
                            successful_results.append((latest_version_clean, url, headers))
                            print(f"[DEBUG] ✅ Succès avec URL {i+1}.{j+1}")
                            
                            # Si on a plusieurs résultats cohérents, on peut s'arrêter
                            if len(successful_results) >= 3:
                                break
                        else:
                            print(f"[DEBUG] ⚠️ Réponse vide avec URL {i+1}.{j+1}")
                    else:
                        print(f"[DEBUG] ❌ Erreur HTTP {r.status_code} avec URL {i+1}.{j+1}")
                        
                except Exception as e:
                    print(f"[DEBUG] ❌ Exception avec URL {i+1}.{j+1}: {e}")
                    continue
            
            # Petite pause entre les URLs pour éviter le rate limiting
            time.sleep(0.1)
        
        if not successful_results:
            return "Erreur", False, "Impossible de récupérer la version depuis GitHub"
        
        # Analyser les résultats pour trouver la version la plus fréquente
        version_counts = {}
        for version, url, headers in successful_results:
            if version not in version_counts:
                version_counts[version] = []
            version_counts[version].append((url, headers))
        
        # Prendre la version la plus fréquente
        most_common_version = max(version_counts.keys(), key=lambda v: len(version_counts[v]))
        most_common_count = len(version_counts[most_common_version])
        
        print(f"[DEBUG] Résultats: {len(successful_results)} succès")
        for version, results in version_counts.items():
            print(f"[DEBUG] Version '{version}': {len(results)} fois")
        
        print(f"[DEBUG] Version finale: '{most_common_version}' (trouvée {most_common_count} fois)")
        
        # Parsing et comparaison
        local_version_tuple = parse_version(VERSION)
        latest_version_tuple = parse_version(most_common_version)
        
        print(f"[DEBUG] Version locale tuple: {local_version_tuple}")
        print(f"[DEBUG] Version GitHub tuple: {latest_version_tuple}")
        
        up_to_date = local_version_tuple >= latest_version_tuple
        print(f"[DEBUG] À jour: {up_to_date}")
        
        return most_common_version, up_to_date, f"Récupéré {most_common_count} fois depuis GitHub"
        
    except requests.exceptions.Timeout:
        error_msg = "Timeout lors de la vérification de mise à jour"
        print(f"[DEBUG] {error_msg}")
        log_crash(error_msg)
        return "Erreur", False, error_msg
    except requests.exceptions.ConnectionError:
        error_msg = "Erreur de connexion lors de la vérification de mise à jour"
        print(f"[DEBUG] {error_msg}")
        log_crash(error_msg)
        return "Erreur", False, error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la vérification de mise à jour: {e}"
        print(f"[DEBUG] {error_msg}")
        log_crash(error_msg)
        return "Erreur", False, error_msg



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



# ------------------ Interface principale ------------------

class VMTPathRenamer(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("🎬 VMT Path Renamer - Noir/Rouge")

        self.setGeometry(100, 100, 1100, 900)

        self.init_ui()

        self.auto_check_update()



    def init_ui(self):

        layout = QVBoxLayout()

        # Version label + update buttons
        update_layout = QHBoxLayout()
        self.update_label = QLabel("🔄 Vérification mise à jour...")
        self.check_update_btn = QPushButton("🔄 Vérifier")
        self.check_update_btn.clicked.connect(self.manual_check_update)
        self.debug_btn = QPushButton("🐛 Debug GitHub")
        self.debug_btn.clicked.connect(self.debug_github)
        self.test_local_btn = QPushButton("🧪 Test Local")
        self.test_local_btn.clicked.connect(self.test_local_version)
        self.force_check_btn = QPushButton("⚡ Force Check")
        self.force_check_btn.clicked.connect(self.force_check_update)
        self.ultra_check_btn = QPushButton("🚀 Ultra Check")
        self.ultra_check_btn.clicked.connect(self.ultra_check_update)
        self.connection_test_btn = QPushButton("🌐 Test Connexion")
        self.connection_test_btn.clicked.connect(self.test_connection)
        self.update_btn = QPushButton("⬇️ Télécharger mise à jour")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.download_update)
        update_layout.addWidget(self.update_label)
        update_layout.addWidget(self.check_update_btn)
        update_layout.addWidget(self.debug_btn)
        update_layout.addWidget(self.test_local_btn)
        update_layout.addWidget(self.force_check_btn)
        update_layout.addWidget(self.ultra_check_btn)
        update_layout.addWidget(self.connection_test_btn)
        update_layout.addWidget(self.update_btn)
        layout.addLayout(update_layout)



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

        self.folder_entry.setPlaceholderText("Ex: C:/Jeu/materials")

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

        self.path_entry.setPlaceholderText("Ex: models/nrxa/mayd3")

        path_layout.addWidget(self.path_entry)

        path_group.setLayout(path_layout)

        layout.addWidget(path_group)



        # Préfixe/Suffixe

        prefix_group = QGroupBox("Préfixe/Suffixe (optionnel)")

        prefix_layout = QHBoxLayout()

        self.prefix_entry = QLineEdit()

        self.prefix_entry.setPlaceholderText("Ex: nrxa_ ou _new")

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

        for btn, func in [(self.run_vmt_btn, self.run_vmt), (self.run_rename_btn, self.run_rename),

                          (self.scan_btn, self.scan_vmt_dirs), (self.reset_btn, self.reset_fields),

                          (self.apply_move_btn, self.apply_move_vmt_vtf)]:

            btn.clicked.connect(func)

            action_layout.addWidget(btn)

        action_group.setLayout(action_layout)

        layout.addWidget(action_group)



        # Logs
        log_layout = QHBoxLayout()
        log_layout.addWidget(QLabel("Journal d'activité"))
        clear_logs_btn = QPushButton("🗑️ Effacer")
        clear_logs_btn.clicked.connect(self.clear_logs)
        log_layout.addWidget(clear_logs_btn)
        layout.addLayout(log_layout)
        
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

    def clear_logs(self):
        """Efface le journal d'activité"""
        self.log_widget.clear()
        self.log_widget.append("🗑️ Journal effacé")



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

        vmt_dirs, modified_vmt_files = replace_paths_in_vmt(MATERIALS_DIR, NEW_PATH, self.log_widget)

        apply_vmt_changes(modified_vmt_files, self.log_widget)

        self.log_widget.append("=== Remplacement terminé ===")



    def run_rename(self):

        self.log_widget.clear()

        prefix_suffix = self.prefix_entry.text().strip()

        dirs_to_rename = [(line.strip(), line.strip())

                          for line in self.detected_dirs_widget.toPlainText().splitlines()

                          if line.strip()]

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



    # ------------------ Mise à jour ------------------
    def manual_check_update(self):
        """Vérification manuelle des mises à jour"""
        self.log_widget.append("🔄 Vérification manuelle des mises à jour...")
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("🔄 Vérification...")
        
        try:
            self.auto_check_update()
        finally:
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText("🔄 Vérifier")

    def auto_check_update(self):
        self.log_widget.append("🔄 Vérification de la mise à jour...")
        latest_version, up_to_date, error_msg = check_update()
        
        if latest_version == "Erreur":
            self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
            self.update_btn.setEnabled(False)
            self.log_widget.append(f"❌ Erreur de vérification: {error_msg}")
            QMessageBox.warning(self, "Erreur mise à jour",
                                f"Impossible de vérifier la mise à jour.\n"
                                f"Détails: {error_msg}\n"
                                "Consultez crash.txt pour plus d'informations.")
        elif up_to_date:
            self.update_label.setText(f"✅ Application à jour ({VERSION})")
            self.update_btn.setEnabled(False)
            self.log_widget.append(f"✅ Version actuelle: {VERSION} (à jour)")
        else:
            self.update_label.setText(f"❌ Nouvelle version disponible ({latest_version})")
            self.update_btn.setEnabled(True)
            self.log_widget.append(f"⬇️ Nouvelle version disponible: {latest_version}")
            self.log_widget.append(f"📊 Version locale: {VERSION} < Version GitHub: {latest_version}")
            QMessageBox.information(self, "Mise à jour disponible",
                                    f"Une nouvelle version est disponible !\n\n"
                                    f"Version actuelle: {VERSION}\n"
                                    f"Nouvelle version: {latest_version}\n\n"
                                    "Cliquez sur le bouton pour mettre à jour.")



    def download_update(self):
        try:
            self.log_widget.append("=" * 50)
            self.log_widget.append("🚀 DÉBUT DE LA MISE À JOUR")
            self.log_widget.append("=" * 50)
            self.log_widget.append(f"[MAJ] URL de téléchargement: {UPDATE_SCRIPT_URL}")
            self.log_widget.append(f"[MAJ] Version actuelle: {VERSION}")
            
            # Désactiver le bouton pendant le téléchargement
            self.update_btn.setEnabled(False)
            self.update_btn.setText("⬇️ Téléchargement...")
            
            r = requests.get(UPDATE_SCRIPT_URL, timeout=15)
            r.raise_for_status()
            
            self.log_widget.append(f"[MAJ] Téléchargement réussi (taille: {len(r.text)} caractères)")
            
            script_path = os.path.abspath(sys.argv[0])
            self.log_widget.append(f"[MAJ] Chemin du script: {script_path}")
            
            # Créer une sauvegarde
            backup_path = script_path + ".bak"
            if os.path.exists(script_path):
                try:
                    shutil.copy2(script_path, backup_path)
                    self.log_widget.append(f"[MAJ] ✅ Sauvegarde créée: {backup_path}")
                except Exception as e:
                    self.log_widget.append(f"[MAJ] ⚠️ Impossible de créer la sauvegarde: {e}")
            
            # Écrire le nouveau fichier
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            
            self.log_widget.append("[MAJ] ✅ Nouveau script écrit avec succès")
            self.log_widget.append("[MAJ] 🔄 Redémarrage de l'application...")
            
            QMessageBox.information(self, "Mise à jour réussie",
                                    "✅ Nouvelle version installée avec succès !\n\n"
                                    "L'application va redémarrer automatiquement.\n"
                                    f"Sauvegarde disponible: {backup_path}")
            
            # Redémarrer l'application
            python = sys.executable
            os.execl(python, python, *sys.argv)
            
        except requests.exceptions.Timeout:
            error_msg = "Timeout lors du téléchargement de la mise à jour"
            self.log_widget.append(f"[MAJ] ❌ {error_msg}")
            log_crash(error_msg)
            QMessageBox.warning(self, "Erreur de téléchargement", error_msg)
        except requests.exceptions.ConnectionError:
            error_msg = "Erreur de connexion lors du téléchargement"
            self.log_widget.append(f"[MAJ] ❌ {error_msg}")
            log_crash(error_msg)
            QMessageBox.warning(self, "Erreur de connexion", error_msg)
        except Exception as e:
            error_msg = f"Erreur lors de la mise à jour: {e}"
            self.log_widget.append(f"[MAJ] ❌ {error_msg}")
            log_crash(error_msg)
            QMessageBox.warning(self, "Erreur de mise à jour", error_msg)
        finally:
            # Réactiver le bouton en cas d'erreur
            self.update_btn.setEnabled(True)
            self.update_btn.setText("⬇️ Télécharger mise à jour")

    def debug_github(self):
        """Debug complet de la connexion GitHub"""
        self.log_widget.append("=" * 70)
        self.log_widget.append("🐛 DEBUG GITHUB COMPLET")
        self.log_widget.append("=" * 70)
        
        try:
            import time
            
            # Test 1: Connexion de base
            self.log_widget.append("📡 TEST 1: Connexion de base")
            headers = {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'User-Agent': 'VMT-Path-Renamer-Debug/1.0'
            }
            
            self.log_widget.append(f"🌐 URL: {UPDATE_CHECK_URL}")
            self.log_widget.append(f"📋 Headers: {headers}")
            
            start_time = time.time()
            r = requests.get(UPDATE_CHECK_URL, timeout=15, headers=headers)
            end_time = time.time()
            
            self.log_widget.append(f"⏱️ Temps de réponse: {end_time - start_time:.2f}s")
            self.log_widget.append(f"📊 Statut HTTP: {r.status_code}")
            self.log_widget.append(f"📏 Taille: {len(r.text)} caractères")
            
            if r.status_code == 200:
                content = r.text.strip()
                self.log_widget.append(f"📄 Contenu brut: '{content}'")
                self.log_widget.append(f"📄 Contenu nettoyé: '{content.replace(chr(65279), '').replace('\\r', '').replace('\\n', '')}'")
                
                # Test de parsing
                try:
                    version_tuple = parse_version(content)
                    self.log_widget.append(f"✅ Version parsée: {version_tuple}")
                    
                    # Comparaison avec version locale
                    local_tuple = parse_version(VERSION)
                    self.log_widget.append(f"📊 Version locale: {VERSION} -> {local_tuple}")
                    
                    if local_tuple >= version_tuple:
                        self.log_widget.append("✅ Application à jour")
                    else:
                        self.log_widget.append("⬇️ Mise à jour disponible")
                        
                except Exception as e:
                    self.log_widget.append(f"❌ Erreur parsing: {e}")
            else:
                self.log_widget.append(f"❌ Erreur HTTP: {r.status_code}")
                self.log_widget.append(f"📄 Réponse: {r.text[:200]}...")
                
        except Exception as e:
            self.log_widget.append(f"❌ Erreur générale: {e}")
        
        self.log_widget.append("=" * 70)
        self.log_widget.append("✅ DEBUG TERMINÉ")
        self.log_widget.append("=" * 70)

    def test_local_version(self):
        """Test de version locale avec création de fichier de test"""
        self.log_widget.append("=" * 60)
        self.log_widget.append("🧪 TEST LOCAL - Création et test de version")
        self.log_widget.append("=" * 60)
        
        try:
            # Créer un fichier de version de test local
            test_version = "12.0.0"  # Version plus récente pour tester
            test_file = "version_test.txt"
            
            self.log_widget.append(f"📝 Création du fichier de test: {test_file}")
            self.log_widget.append(f"📝 Version de test: {test_version}")
            
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_version)
            
            self.log_widget.append(f"✅ Fichier créé: {test_file}")
            
            # Test de lecture du fichier local
            self.log_widget.append("\n📖 Test de lecture du fichier local:")
            with open(test_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
            self.log_widget.append(f"📄 Contenu lu: '{content}'")
            
            # Test de parsing
            try:
                version_tuple = parse_version(content)
                self.log_widget.append(f"✅ Version parsée: {version_tuple}")
                
                # Comparaison avec version locale
                local_tuple = parse_version(VERSION)
                self.log_widget.append(f"📊 Version locale: {VERSION} -> {local_tuple}")
                self.log_widget.append(f"📊 Version test: {test_version} -> {version_tuple}")
                
                if local_tuple >= version_tuple:
                    self.log_widget.append("✅ Application à jour (vs fichier test)")
                else:
                    self.log_widget.append("⬇️ Mise à jour disponible (vs fichier test)")
                    
            except Exception as e:
                self.log_widget.append(f"❌ Erreur parsing: {e}")
            
            # Nettoyage
            try:
                os.remove(test_file)
                self.log_widget.append(f"\n🗑️ Fichier de test supprimé: {test_file}")
            except Exception as e:
                self.log_widget.append(f"\n⚠️ Impossible de supprimer {test_file}: {e}")
                
        except Exception as e:
            self.log_widget.append(f"❌ Erreur générale: {e}")
        
        self.log_widget.append("=" * 60)
        self.log_widget.append("✅ TEST LOCAL TERMINÉ")
        self.log_widget.append("=" * 60)

    def force_check_update(self):
        """Vérification forcée avec toutes les méthodes anti-cache"""
        self.log_widget.append("=" * 70)
        self.log_widget.append("⚡ VÉRIFICATION FORCÉE - Contournement cache GitHub")
        self.log_widget.append("=" * 70)
        
        try:
            import time
            
            # Désactiver le bouton pendant la vérification
            self.force_check_btn.setEnabled(False)
            self.force_check_btn.setText("⚡ Vérification...")
            
            # Méthodes multiples pour contourner le cache
            urls_to_try = [
                UPDATE_CHECK_URL,
                f"{UPDATE_CHECK_URL}?t={int(time.time())}",
                f"{UPDATE_CHECK_URL}?v={int(time.time())}&nocache=1",
                f"{UPDATE_CHECK_URL}?hash={hash(time.time())}&force=1",
                f"{UPDATE_CHECK_URL}?timestamp={int(time.time() * 1000)}",
                UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "github.com").replace("/main/", "/blob/main/")
            ]
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'User-Agent': f'VMT-Path-Renamer-ForceCheck/{VERSION}',
                'Accept': 'text/plain, */*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'close'
            }
            
            self.log_widget.append(f"🎯 Version locale: {VERSION}")
            self.log_widget.append(f"📋 Headers anti-cache: {headers}")
            self.log_widget.append("")
            
            successful_results = []
            
            for i, url in enumerate(urls_to_try):
                try:
                    self.log_widget.append(f"🔄 Tentative {i+1}/{len(urls_to_try)}")
                    self.log_widget.append(f"🌐 URL: {url}")
                    
                    start_time = time.time()
                    r = requests.get(url, timeout=8, headers=headers)
                    end_time = time.time()
                    
                    response_time = end_time - start_time
                    self.log_widget.append(f"⏱️ Temps: {response_time:.2f}s | Statut: {r.status_code}")
                    
                    if r.status_code == 200:
                        content = r.text.strip()
                        if content:
                            clean_content = content.replace('\ufeff', '').replace('\r', '').replace('\n', '')
                            successful_results.append((clean_content, url, response_time))
                            self.log_widget.append(f"✅ Succès: '{clean_content}'")
                        else:
                            self.log_widget.append("⚠️ Réponse vide")
                    else:
                        self.log_widget.append(f"❌ Erreur HTTP: {r.status_code}")
                        
                except Exception as e:
                    self.log_widget.append(f"❌ Exception: {e}")
                
                self.log_widget.append("")
                time.sleep(0.5)  # Petite pause entre les tentatives
            
            # Analyse des résultats
            if successful_results:
                self.log_widget.append("📊 ANALYSE DES RÉSULTATS:")
                self.log_widget.append("=" * 50)
                
                # Grouper par version
                version_groups = {}
                for version, url, time_taken in successful_results:
                    if version not in version_groups:
                        version_groups[version] = []
                    version_groups[version].append((url, time_taken))
                
                for version, results in version_groups.items():
                    self.log_widget.append(f"📄 Version '{version}' trouvée {len(results)} fois:")
                    for url, time_taken in results:
                        self.log_widget.append(f"  🌐 {url} ({time_taken:.2f}s)")
                
                # Prendre la version la plus fréquente
                most_common_version = max(version_groups.keys(), key=lambda v: len(version_groups[v]))
                self.log_widget.append(f"\n🎯 Version la plus fréquente: '{most_common_version}'")
                
                # Comparaison avec version locale
                try:
                    local_tuple = parse_version(VERSION)
                    remote_tuple = parse_version(most_common_version)
                    
                    self.log_widget.append(f"📊 Version locale: {VERSION} -> {local_tuple}")
                    self.log_widget.append(f"📊 Version GitHub: {most_common_version} -> {remote_tuple}")
                    
                    if local_tuple >= remote_tuple:
                        self.log_widget.append("✅ Application à jour")
                        self.update_label.setText(f"✅ Application à jour ({VERSION})")
                        self.update_btn.setEnabled(False)
                    else:
                        self.log_widget.append("⬇️ Mise à jour disponible")
                        self.update_label.setText(f"❌ Nouvelle version disponible ({most_common_version})")
                        self.update_btn.setEnabled(True)
                        
                except Exception as e:
                    self.log_widget.append(f"❌ Erreur parsing: {e}")
            else:
                self.log_widget.append("❌ Aucune requête réussie")
                self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
                self.update_btn.setEnabled(False)
                
        except Exception as e:
            self.log_widget.append(f"❌ Erreur générale: {e}")
        finally:
            # Réactiver le bouton
            self.force_check_btn.setEnabled(True)
            self.force_check_btn.setText("⚡ Force Check")
        
        self.log_widget.append("=" * 70)
        self.log_widget.append("✅ VÉRIFICATION FORCÉE TERMINÉE")
        self.log_widget.append("=" * 70)

    def ultra_check_update(self):
        """Vérification ultra-rapide avec toutes les méthodes anti-cache"""
        self.log_widget.append("=" * 80)
        self.log_widget.append("🚀 ULTRA CHECK - Méthodes ultra-agressives anti-cache")
        self.log_widget.append("=" * 80)
        
        try:
            import time
            import random
            
            # Désactiver le bouton pendant la vérification
            self.ultra_check_btn.setEnabled(False)
            self.ultra_check_btn.setText("🚀 Ultra Check...")
            
            self.log_widget.append(f"🎯 Version locale: {VERSION}")
            self.log_widget.append(f"🌐 URL GitHub: {UPDATE_CHECK_URL}")
            self.log_widget.append("")
            
            # Méthodes ultra-multiples
            timestamp = int(time.time())
            random_hash = random.randint(100000, 999999)
            urls_to_try = [
                UPDATE_CHECK_URL,
                f"{UPDATE_CHECK_URL}?t={timestamp}",
                f"{UPDATE_CHECK_URL}?v={timestamp}&nocache=1",
                f"{UPDATE_CHECK_URL}?timestamp={timestamp}&force=1",
                f"{UPDATE_CHECK_URL}?hash={random_hash}&t={timestamp}",
                f"{UPDATE_CHECK_URL}?cache_bust={timestamp}&random={random_hash}",
                f"{UPDATE_CHECK_URL}?refresh=1&t={timestamp}",
                f"{UPDATE_CHECK_URL}?bypass_cache=1&v={timestamp}",
                f"{UPDATE_CHECK_URL}?nocache=1&timestamp={timestamp}&random={random_hash}",
                f"{UPDATE_CHECK_URL}?ms={int(time.time() * 1000)}",
                f"{UPDATE_CHECK_URL}?micro={int(time.time() * 1000000)}"
            ]
            
            headers_variants = [
                {
                    'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'User-Agent': f'VMT-Path-Renamer-Ultra/{VERSION}',
                    'Accept': 'text/plain, */*',
                    'Connection': 'close'
                },
                {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'User-Agent': f'Mozilla/5.0 VMT-Path-Renamer/{VERSION}',
                    'Accept': '*/*',
                    'Connection': 'keep-alive'
                },
                {
                    'Cache-Control': 'no-store',
                    'User-Agent': f'VMT-Path-Renamer-UltraCheck/{VERSION}',
                    'Accept': 'text/plain',
                    'Connection': 'close'
                }
            ]
            
            successful_results = []
            
            self.log_widget.append("🔄 Test de toutes les combinaisons URL + Headers...")
            
            for i, url in enumerate(urls_to_try):
                for j, headers in enumerate(headers_variants):
                    try:
                        start_time = time.time()
                        r = requests.get(url, timeout=5, headers=headers)
                        end_time = time.time()
                        response_time = end_time - start_time
                        
                        if r.status_code == 200:
                            content = r.text.strip()
                            if content:
                                clean_content = content.replace('\ufeff', '').replace('\r', '').replace('\n', '')
                                successful_results.append((clean_content, url, response_time))
                                self.log_widget.append(f"✅ {i+1}.{j+1}: '{clean_content}' ({response_time:.2f}s)")
                                
                                # Arrêter si on a assez de résultats cohérents
                                if len(successful_results) >= 5:
                                    break
                            else:
                                self.log_widget.append(f"⚠️ {i+1}.{j+1}: Réponse vide")
                        else:
                            self.log_widget.append(f"❌ {i+1}.{j+1}: HTTP {r.status_code}")
                            
                    except Exception as e:
                        self.log_widget.append(f"❌ {i+1}.{j+1}: {str(e)[:50]}...")
                
                if len(successful_results) >= 5:
                    break
                time.sleep(0.05)  # Pause très courte
            
            # Analyse des résultats
            if successful_results:
                self.log_widget.append("\n📊 ANALYSE ULTRA-RÉSULTATS:")
                self.log_widget.append("=" * 60)
                
                # Grouper par version
                version_groups = {}
                for version, url, time_taken in successful_results:
                    if version not in version_groups:
                        version_groups[version] = []
                    version_groups[version].append((url, time_taken))
                
                for version, results in version_groups.items():
                    self.log_widget.append(f"📄 Version '{version}': {len(results)} fois")
                    for url, time_taken in results:
                        self.log_widget.append(f"  🌐 {url} ({time_taken:.2f}s)")
                
                # Prendre la version la plus fréquente
                most_common_version = max(version_groups.keys(), key=lambda v: len(version_groups[v]))
                most_common_count = len(version_groups[most_common_version])
                
                self.log_widget.append(f"\n🎯 VERSION ULTRA-CONFIRMÉE: '{most_common_version}'")
                self.log_widget.append(f"📊 Trouvée {most_common_count} fois sur {len(successful_results)} tentatives")
                
                # Comparaison avec version locale
                try:
                    local_tuple = parse_version(VERSION)
                    remote_tuple = parse_version(most_common_version)
                    
                    self.log_widget.append(f"📊 Version locale: {VERSION} -> {local_tuple}")
                    self.log_widget.append(f"📊 Version GitHub: {most_common_version} -> {remote_tuple}")
                    
                    if local_tuple >= remote_tuple:
                        self.log_widget.append("✅ APPLICATION À JOUR (ultra-confirmé)")
                        self.update_label.setText(f"✅ Application à jour ({VERSION})")
                        self.update_btn.setEnabled(False)
                    else:
                        self.log_widget.append("⬇️ MISE À JOUR DISPONIBLE (ultra-confirmé)")
                        self.update_label.setText(f"❌ Nouvelle version disponible ({most_common_version})")
                        self.update_btn.setEnabled(True)
                        
                except Exception as e:
                    self.log_widget.append(f"❌ Erreur parsing: {e}")
            else:
                self.log_widget.append("❌ Aucune requête réussie")
                self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
                self.update_btn.setEnabled(False)
                
        except Exception as e:
            self.log_widget.append(f"❌ Erreur générale: {e}")
        finally:
            # Réactiver le bouton
            self.ultra_check_btn.setEnabled(True)
            self.ultra_check_btn.setText("🚀 Ultra Check")
        
        self.log_widget.append("=" * 80)
        self.log_widget.append("✅ ULTRA CHECK TERMINÉ")
        self.log_widget.append("=" * 80)

    def test_connection(self):
        """Test de connexion simple et rapide"""
        self.log_widget.append("=" * 50)
        self.log_widget.append("🌐 TEST DE CONNEXION SIMPLE")
        self.log_widget.append("=" * 50)
        
        try:
            import time
            
            # Test de base
            self.log_widget.append(f"🌐 Test de connexion à: {UPDATE_CHECK_URL}")
            
            start_time = time.time()
            r = requests.get(UPDATE_CHECK_URL, timeout=5)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            self.log_widget.append(f"⏱️ Temps de réponse: {response_time:.2f}s")
            self.log_widget.append(f"📊 Statut HTTP: {r.status_code}")
            self.log_widget.append(f"📏 Taille de la réponse: {len(r.text)} caractères")
            
            if r.status_code == 200:
                content = r.text.strip()
                self.log_widget.append(f"📄 Contenu: '{content}'")
                
                # Test de parsing
                try:
                    version_tuple = parse_version(content)
                    self.log_widget.append(f"✅ Version parsée: {version_tuple}")
                    
                    # Comparaison rapide
                    local_tuple = parse_version(VERSION)
                    if local_tuple >= version_tuple:
                        self.log_widget.append("✅ Application à jour")
                    else:
                        self.log_widget.append("⬇️ Mise à jour disponible")
                        
                except Exception as e:
                    self.log_widget.append(f"❌ Erreur parsing: {e}")
            else:
                self.log_widget.append(f"❌ Erreur HTTP: {r.status_code}")
                
        except Exception as e:
            self.log_widget.append(f"❌ Erreur de connexion: {e}")
        
        self.log_widget.append("=" * 50)
        self.log_widget.append("✅ TEST DE CONNEXION TERMINÉ")
        self.log_widget.append("=" * 50)

# ------------------ Lancement ------------------
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = VMTPathRenamer()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        log_crash(str(e))
        print(f"Erreur au lancement : {e}")
        input("Appuyez sur Entrée pour quitter...")



