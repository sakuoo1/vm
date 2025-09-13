import os

import re

import shutil

import sys

import time

import requests

import platform

import subprocess

import uuid

from PyQt5.QtWidgets import (

    QApplication, QWidget, QLabel, QLineEdit, QPushButton,

    QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QMessageBox, QComboBox

)

from PyQt5.QtCore import Qt, QTimer

import hashlib
from PyQt5.QtWidgets import QDialog, QProgressBar
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont

def get_hardware_id():
    """Génère un identifiant unique basé sur le matériel du PC"""
    try:
        # Récupérer plusieurs identifiants matériels
        system_info = []
        
        # UUID de la carte mère (Windows)
        try:
            if platform.system() == "Windows":
                result = subprocess.run(['wmic', 'csproduct', 'get', 'uuid'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.strip() and 'UUID' not in line:
                            system_info.append(line.strip())
                            break
        except:
            pass
        
        # Numéro de série du processeur
        try:
            if platform.system() == "Windows":
                result = subprocess.run(['wmic', 'cpu', 'get', 'processorid'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.strip() and 'ProcessorId' not in line:
                            system_info.append(line.strip())
                            break
        except:
            pass
        
        # MAC Address de la première interface réseau
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0,2*6,2)][::-1])
            system_info.append(mac)
        except:
            pass
        
        # Nom de la machine
        system_info.append(platform.node())
        
        # Système d'exploitation
        system_info.append(platform.system() + platform.release())
        
        # Si on n'a rien récupéré, utiliser un UUID aléatoire basé sur le node
        if not system_info:
            system_info.append(str(uuid.getnode()))
        
        # Créer un hash unique à partir de toutes ces informations
        combined = ''.join(system_info)
        hwid = hashlib.sha256(combined.encode()).hexdigest()[:32]
        
        print(f"🔧 HWID généré: {hwid}")
        return hwid
        
    except Exception as e:
        print(f"❌ Erreur génération HWID: {e}")
        # Fallback: utiliser l'UUID du node
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]

class AuthWorker(QThread):
    """Thread pour vérifier la clé sans bloquer l'interface"""
    auth_result = pyqtSignal(bool, str, str)
    
    def __init__(self, key, supabase_url, supabase_key):
        super().__init__()
        self.key = key
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
    
    def run(self):
        try:

            key_hash = hashlib.sha256(self.key.encode()).hexdigest()
            

            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            

            url = f"{self.supabase_url}/rest/v1/access_keys?key_hash=eq.{key_hash}&is_active=eq.true"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:

                    key_data = data[0]
                    
                    # Vérifier si la clé est marquée pour revalidation forcée
                    # Note: Le champ force_revalidation doit être ajouté à la table access_keys dans Supabase
                    try:
                        if key_data.get('force_revalidation', False):
                            # Réinitialiser le flag de revalidation
                            self.reset_revalidation_flag(key_data['id'])
                            self.auth_result.emit(False, "Revalidation requise - Veuillez ressaisir votre cle d'acces", "")
                            return
                    except Exception:
                        # Si le champ n'existe pas encore, continuer normalement
                        pass
                    
                    # Vérifier l'expiration
                    if 'expires_at' in key_data and key_data['expires_at']:
                        from datetime import datetime
                        expires_at = datetime.fromisoformat(key_data['expires_at'].replace('Z', '+00:00'))
                        if datetime.now(expires_at.tzinfo) > expires_at:
                            self.auth_result.emit(False, "Clé expirée", "")
                            return
                    
                    # Vérifier le HWID (Hardware ID)
                    current_hwid = get_hardware_id()
                    stored_hwid = key_data.get('hardware_id')
                    
                    if stored_hwid is None:
                        # Première utilisation de la clé - enregistrer le HWID
                        print(f"🔧 Première utilisation - Enregistrement HWID: {current_hwid}")
                        self.update_hardware_id(key_data['id'], current_hwid)
                    elif stored_hwid != current_hwid:
                        # HWID différent - accès refusé
                        print(f"❌ HWID mismatch - Stocké: {stored_hwid}, Actuel: {current_hwid}")
                        self.auth_result.emit(False, "Cette clé est liée à un autre ordinateur. Accès refusé.", "")
                        return
                    else:
                        print(f"✅ HWID vérifié: {current_hwid}")
                    
                    # Mettre à jour la dernière utilisation
                    print(f"Authentification reussie pour cle ID: {key_data['id']}")
                    self.update_last_used(key_data['id'])
                    
                    # Retourner le succès avec le rôle
                    user_role = key_data.get('role', 'user')
                    self.auth_result.emit(True, f"Accès autorisé - {key_data.get('description', 'Utilisateur')} ({user_role})", user_role)
                else:
                    self.auth_result.emit(False, "Clé invalide", "")
            else:
                self.auth_result.emit(False, f"Erreur serveur: {response.status_code}", "")
                
        except requests.exceptions.Timeout:
            self.auth_result.emit(False, "Timeout - Vérifiez votre connexion", "")
        except requests.exceptions.ConnectionError:
            self.auth_result.emit(False, "Pas de connexion internet", "")
        except Exception as e:
            self.auth_result.emit(False, f"Erreur: {str(e)}", "")
    
    def update_last_used(self, key_id):
        """Met à jour la dernière utilisation de la clé"""
        try:
            import datetime
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            
            # Format ISO 8601 correct pour Supabase
            now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
            
            url = f"{self.supabase_url}/rest/v1/access_keys?id=eq.{key_id}"
            data = {'last_used_at': now}
            
            print(f"Mise a jour last_used_at pour cle ID {key_id}: {now}")
            response = requests.patch(url, json=data, headers=headers, timeout=5)
            print(f"✅ Réponse Supabase: {response.status_code}")
            
        except Exception as e:
            print(f"❌ Erreur update_last_used: {str(e)}")  
    
    def update_hardware_id(self, key_id, hwid):
        """Met à jour le HWID associé à une clé"""
        try:
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.supabase_url}/rest/v1/access_keys?id=eq.{key_id}"
            data = {'hardware_id': hwid}
            
            response = requests.patch(url, json=data, headers=headers, timeout=5)
            print(f"✅ HWID enregistré: {response.status_code}")
            
        except Exception as e:
            print(f"❌ Erreur update_hardware_id: {str(e)}")

    def reset_revalidation_flag(self, key_id):
        """Réinitialise le flag de revalidation forcée après utilisation"""
        try:
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.supabase_url}/rest/v1/access_keys?id=eq.{key_id}"
            data = {'force_revalidation': False}
            
            requests.patch(url, json=data, headers=headers, timeout=5)
        except:
            pass

class AuthDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.authenticated = False
        self.worker = None
        

        self.SUPABASE_URL = "https://cmdfrwnfaxapwfydebyr.supabase.co"
        self.SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNtZGZyd25mYXhhcHdmeWRlYnlyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc2NDIwODYsImV4cCI6MjA3MzIxODA4Nn0.NFnhaMp0b7syG8tNVzOIoLiessvyLxUl6jLzIMLsGds"
        
        self.init_ui()
        self.setModal(True)
        
    def init_ui(self):
        self.setWindowTitle("VMT Path Renamer - Connexion")
        self.setFixedSize(520, 420)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        
        # Layout principal Netflix
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(50, 50, 50, 50)
        
        # Header Netflix
        header_layout = QVBoxLayout()
        header_layout.setSpacing(15)
        
        # Logo futuriste style
        logo_label = QLabel("🔐")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setFont(QFont("Inter", 32))
        logo_label.setStyleSheet("""
            QLabel {
                color: #00D4FF;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #0A0A0A);
                border: 3px solid #00D4FF;
                border-radius: 35px;
                padding: 15px;
                margin-bottom: 10px;
            }
        """)
        logo_label.setFixedSize(70, 70)
        header_layout.addWidget(logo_label, 0, Qt.AlignCenter)
        
        # Titre futuriste
        title = QLabel("VMT PATH")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Inter", 24, QFont.Bold))
        title.setStyleSheet("color: #00D4FF; margin: 0; font-weight: 700;")
        header_layout.addWidget(title)
        
        # Sous-titre RENAMER
        subtitle_main = QLabel("RENAMER")
        subtitle_main.setAlignment(Qt.AlignCenter)
        subtitle_main.setFont(QFont("Inter", 16, QFont.Bold))
        subtitle_main.setStyleSheet("color: #FFFFFF; margin: 0; font-weight: 600; letter-spacing: 2px;")
        header_layout.addWidget(subtitle_main)
        
        # Sous-titre futuriste
        subtitle = QLabel("Authentification sécurisée")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Inter", 12))
        subtitle.setStyleSheet("color: #B0B0B0; margin-bottom: 15px; font-weight: 400;")
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
        
        # Séparateur futuriste
        separator = QLabel()
        separator.setFixedHeight(2)
        separator.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 transparent, stop: 0.3 #00D4FF, stop: 0.7 #00D4FF, stop: 1 transparent);
                border-radius: 1px;
                margin: 10px 40px;
            }
        """)
        layout.addWidget(separator)
        
        # Section de saisie Netflix
        input_section = QVBoxLayout()
        input_section.setSpacing(12)
        
        # Label futuriste
        key_label = QLabel("Clé d'Accès")
        key_label.setFont(QFont("Inter", 13, QFont.Bold))
        key_label.setStyleSheet("color: #FFFFFF; margin-bottom: 8px; font-weight: 600;")
        input_section.addWidget(key_label)
        
        # Champ de saisie futuriste
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("xxxx-xxxx-xxxx")
        self.key_input.setFont(QFont("Inter", 13))
        self.key_input.setStyleSheet("""
            QLineEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 16px 20px;
                font-size: 14px;
                font-weight: 400;
                selection-background-color: #00D4FF;
            }
            QLineEdit:focus {
                border-color: #00D4FF;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2A2A2A, stop: 1 #333333);
            }
            QLineEdit:hover {
                border-color: #6C7B7F;
            }
        """)
        self.key_input.returnPressed.connect(self.authenticate)
        input_section.addWidget(self.key_input)
        
        layout.addLayout(input_section)
        
        # Barre de progression futuriste
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 6px;
                background-color: #333333;
                text-align: center;
                color: #FFFFFF;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #00D4FF, stop: 1 #00FF88);
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Message de statut futuriste
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Inter", 11))
        self.status_label.setStyleSheet("color: #B0B0B0; margin: 10px 0; font-weight: 400;")
        layout.addWidget(self.status_label)
        
        # Boutons Netflix
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Bouton Quitter (secondaire futuriste)
        self.quit_button = QPushButton("Quitter")
        self.quit_button.setFont(QFont("Inter", 12, QFont.Bold))
        self.quit_button.clicked.connect(self.reject)
        self.quit_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #6C7B7F, stop: 1 #555555);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 14px 24px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #7A8A8F, stop: 1 #666666);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #555555, stop: 1 #444444);
            }
        """)
        
        # Bouton Se connecter (principal futuriste)
        self.auth_button = QPushButton("🔓 CONNEXION")
        self.auth_button.setFont(QFont("Inter", 12, QFont.Bold))
        self.auth_button.clicked.connect(self.authenticate)
        self.auth_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 14px 24px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
            QPushButton:disabled {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #333333, stop: 1 #2A2A2A);
                color: #707070;
            }
        """)

        

        button_layout.addWidget(self.quit_button)

        button_layout.addWidget(self.auth_button)

        layout.addLayout(button_layout)

        

        self.setLayout(layout)

        

        # Style général futuriste
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
        """)

        

        # Focus automatique sur le champ de saisie

        self.key_input.setFocus()

    

    def authenticate(self):

        key = self.key_input.text().strip()

        

        if not key:

            self.show_error("Veuillez entrer une clé d'accès")

            return

        

        if len(key) < 8:

            self.show_error("La clé doit contenir au moins 8 caractères")

            return

        

        # Désactiver l'interface pendant la vérification

        self.auth_button.setEnabled(False)

        self.key_input.setEnabled(False)

        self.progress_bar.setVisible(True)

        self.progress_bar.setRange(0, 0)  # Animation infinie

        self.status_label.setText("🔍 Vérification de la clé...")

        

        # Lancer la vérification en arrière-plan

        self.worker = AuthWorker(key, self.SUPABASE_URL, self.SUPABASE_ANON_KEY)

        self.worker.auth_result.connect(self.on_auth_result)

        self.worker.start()

    

    def on_auth_result(self, success, message, user_role=""):

        # Réactiver l'interface

        self.auth_button.setEnabled(True)

        self.key_input.setEnabled(True)

        self.progress_bar.setVisible(False)

        

        if success:

            self.status_label.setText(f"✅ {message}")

            self.status_label.setStyleSheet("color: #00FF88; font-size: 11px; margin: 10px 0; font-weight: 500;")

            self.authenticated = True

            self.user_role = user_role  # Stocker le rôle

            

            # Fermer la fenêtre après 1 seconde

            QApplication.processEvents()

            time.sleep(1)

            self.accept()

        else:

            self.show_error(f"❌ {message}")

            self.key_input.clear()

            self.key_input.setFocus()

    

    def show_error(self, message):

        self.status_label.setText(message)

        self.status_label.setStyleSheet("color: #FF4757; font-size: 11px; margin: 10px 0; font-weight: 500;")

    

    def closeEvent(self, event):

        if not self.authenticated:

            reply = QMessageBox.question(

                self, 

                'Quitter', 

                'Êtes-vous sûr de vouloir quitter sans vous authentifier?',

                QMessageBox.Yes | QMessageBox.No,

                QMessageBox.No

            )

            

            if reply == QMessageBox.Yes:

                event.accept()

                sys.exit(0)

            else:

                event.ignore()

        else:

            event.accept()



class ChangelogDialog(QDialog):

    def __init__(self):

        super().__init__()

        self.init_ui()

        

    def init_ui(self):

        self.setWindowTitle("📋 Changelog - Notes de Version")

        self.setFixedSize(800, 600)

        self.setModal(True)

        

        layout = QVBoxLayout()

        layout.setSpacing(20)

        layout.setContentsMargins(30, 30, 30, 30)

        

        # Titre avec style futuriste
        title = QLabel("📋 Changelog - Historique des Versions")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Inter", 18, QFont.Bold))
        title.setStyleSheet("""
            QLabel {
                color: #00D4FF;
                margin-bottom: 20px;
                padding: 15px;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #0A0A0A);
                border: 2px solid #00D4FF;
                border-radius: 12px;
            }
        """)

        layout.addWidget(title)

        

        # Zone de texte avec contenu du changelog

        self.changelog_text = QTextEdit()

        self.changelog_text.setFont(QFont("Consolas", 11))

        self.changelog_text.setReadOnly(True)  # Lecture seule

        

        # Contenu du changelog intégré dans le code

        changelog_content = """

# VMT Path Renamer - Changelog



## Version 17.7.0 - Dernière mise à jour

✨ **Nouvelles fonctionnalités :**

•  Retirer l'option VTF to TGA le temps de le fix 

•  Sécurisation des clées 

• Interface d'authentification moderne

• Vérification automatique des mises à jour

• Interface utilisateur avec thème sombre



## Version 16.5.0 - Version initiale

📁 **Fonctionnalités de base :**


• Renommage de fichiers VMT

• Gestion des dossiers

• Interface utilisateur simple

• Logs d'activité



---

        """

        

        self.changelog_text.setPlainText(changelog_content.strip())

        # Style futuriste pour la zone de texte
        self.changelog_text.setStyleSheet("""
            QTextEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 20px;
                font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                line-height: 1.4;
                selection-background-color: #00D4FF;
            }
            QScrollBar:vertical {
                background: #333333;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #00D4FF;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00E5FF;
            }
        """)

        layout.addWidget(self.changelog_text)

        

        # Bouton fermer avec style futuriste
        close_btn = QPushButton("❌ Fermer")
        close_btn.clicked.connect(self.accept)
        close_btn.setFont(QFont("Inter", 12, QFont.Bold))
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF4757, stop: 1 #CC3A47);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 14px 24px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF5A6B, stop: 1 #E6434F);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CC3A47, stop: 1 #B32D3A);
            }
        """)

        

        # Layout pour centrer le bouton

        button_layout = QHBoxLayout()

        button_layout.addStretch()

        button_layout.addWidget(close_btn)

        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Style général futuriste de la fenêtre
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
        """)

class AdminPanel(QDialog):
    def __init__(self, supabase_url, supabase_key):
        super().__init__()
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.init_ui()
        self.load_keys()
        
        # Timer pour mise à jour automatique
        from PyQt5.QtCore import QTimer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_keys)
        self.refresh_timer.start(10000)  # Rafraîchir toutes les 10 secondes
        
    def init_ui(self):
        self.setWindowTitle("🔧 Panneau Administrateur - Gestion des Clés")
        self.setFixedSize(800, 600)
        self.setModal(True)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Titre futuriste
        title = QLabel("🔧 Gestion des Clés d'Accès")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Inter", 16, QFont.Bold))
        title.setStyleSheet("color: #00D4FF; margin-bottom: 15px; font-weight: 700;")
        layout.addWidget(title)
        
        # Section création de clé
        create_group = QGroupBox("Créer une nouvelle clé")
        create_layout = QVBoxLayout()
        
        # Champs de création
        fields_layout = QHBoxLayout()
        
        # Colonne 1
        col1_layout = QVBoxLayout()
        col1_layout.addWidget(QLabel("Clé:"))

        self.new_key_input = QLineEdit()

        self.new_key_input.setPlaceholderText("Entrez la nouvelle clé...")

        col1_layout.addWidget(self.new_key_input)

        

        col1_layout.addWidget(QLabel("Description:"))

        self.new_desc_input = QLineEdit()

        self.new_desc_input.setPlaceholderText("Description de la clé...")

        col1_layout.addWidget(self.new_desc_input)

        

        # Colonne 2

        col2_layout = QVBoxLayout()

        col2_layout.addWidget(QLabel("Rôle:"))

        self.role_combo = QComboBox()

        self.role_combo.addItems(["user", "admin"])

        col2_layout.addWidget(self.role_combo)

        

        col2_layout.addWidget(QLabel("Expiration (jours):"))

        self.expiry_input = QLineEdit()

        self.expiry_input.setPlaceholderText("Nombre de jours (vide = permanent)")

        col2_layout.addWidget(self.expiry_input)

        

        fields_layout.addLayout(col1_layout)

        fields_layout.addLayout(col2_layout)

        create_layout.addLayout(fields_layout)

        

        # Bouton créer

        self.create_btn = QPushButton("➕ Créer la clé")

        self.create_btn.clicked.connect(self.create_key)

        self.create_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00FF88, stop: 1 #00CC6A);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 14px 24px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AFF99, stop: 1 #00E675);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00CC6A, stop: 1 #00B35C);
            }
        """)

        create_layout.addWidget(self.create_btn)

        

        create_group.setLayout(create_layout)

        layout.addWidget(create_group)

        

        # Liste des clés existantes

        keys_group = QGroupBox("Clés existantes")

        keys_layout = QVBoxLayout()

        

        # Conteneur avec scroll pour les clés

        from PyQt5.QtWidgets import QScrollArea, QWidget

        scroll_area = QScrollArea()

        scroll_widget = QWidget()

        self.keys_container_layout = QVBoxLayout(scroll_widget)

        scroll_area.setWidget(scroll_widget)

        scroll_area.setWidgetResizable(True)

        scroll_area.setMaximumHeight(300)

        keys_layout.addWidget(scroll_area)

        

        # Boutons d'action globaux

        actions_layout = QHBoxLayout()

        

        self.refresh_btn = QPushButton("Actualiser")

        self.refresh_btn.clicked.connect(self.load_keys)

        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
        """)

        

        # Bouton pour voir les clés connectées
        self.connected_keys_btn = QPushButton("👥 Clés Connectées")
        self.connected_keys_btn.clicked.connect(self.show_connected_keys)
        self.connected_keys_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #9933CC, stop: 1 #7A29A3);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 12px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #BB44FF, stop: 1 #9933CC);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #7A29A3, stop: 1 #5C1F7A);
            }
        """)
        
        # Bouton pour forcer la revalidation globale
        self.force_revalidation_btn = QPushButton("Forcer Revalidation")
        self.force_revalidation_btn.clicked.connect(self.force_global_revalidation)
        self.force_revalidation_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF6600, stop: 1 #CC5200);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF8800, stop: 1 #E65C00);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CC5200, stop: 1 #994000);
            }
        """)
        
        # Indicateur de mise à jour automatique
        auto_refresh_label = QLabel("Mise a jour auto: 10s")
        auto_refresh_label.setStyleSheet("color: #888; font-size: 9px; padding: 5px;")
        
        actions_layout.addWidget(self.refresh_btn)
        actions_layout.addWidget(self.connected_keys_btn)
        actions_layout.addWidget(self.force_revalidation_btn)
        actions_layout.addWidget(auto_refresh_label)
        actions_layout.addStretch()

        keys_layout.addLayout(actions_layout)

        

        keys_group.setLayout(keys_layout)

        layout.addWidget(keys_group)

        

        # Bouton fermer futuriste
        close_btn = QPushButton("❌ Fermer")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #666666, stop: 1 #4D4D4D);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 14px 24px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #888888, stop: 1 #666666);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #4D4D4D, stop: 1 #333333);
            }
        """)

        layout.addWidget(close_btn)
        
        # Appliquer le layout et le style général
        self.setLayout(layout)
        
        # Style général futuriste de la fenêtre
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                color: #00D4FF;
                border: 2px solid #333333;
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #00D4FF;
                background: #1A1A1A;
            }
            QLineEdit, QComboBox {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #00D4FF;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 12px;
                margin: 5px 0px;
            }
        """)

    def create_key(self):

        key = self.new_key_input.text().strip()
        desc = self.new_desc_input.text().strip()
        role = self.role_combo.currentText()
        expiry_days = self.expiry_input.text().strip()
        
        if not key:
            QMessageBox.warning(self, "Erreur", "Veuillez entrer une clé")
            return
        
        if len(key) < 4:
            QMessageBox.warning(self, "Erreur", "La clé doit contenir au moins 4 caractères")
            return
        
        try:
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            
            # Préparer les paramètres avec valeurs par défaut explicites
            params = {
                'p_key': key,
                'p_description': desc or f'Clé {role}',
                'p_expires_at': None,

                'p_max_usage': None,
                'p_role': role
            }
            
            # Ajouter expiration si spécifiée
            if expiry_days:
                try:
                    days = int(expiry_days)
                    from datetime import datetime, timedelta
                    expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                    params['p_expires_at'] = expiry_date
                except ValueError:
                    QMessageBox.warning(self, "Erreur", "Nombre de jours invalide")
                    return
            
            # Appeler la fonction Supabase
            url = f"{self.supabase_url}/rest/v1/rpc/create_access_key_with_role"
            response = requests.post(url, json=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                QMessageBox.information(self, "Succès", f"Clé '{key}' créée avec succès!")
                self.new_key_input.clear()
                self.new_desc_input.clear()
                self.expiry_input.clear()
                self.load_keys()
            else:
                error_msg = f"Erreur {response.status_code}: {response.text}"
                QMessageBox.critical(self, "Erreur", error_msg)
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")

    

    def load_keys(self):

        try:

            # Vider le conteneur existant

            for i in reversed(range(self.keys_container_layout.count())):

                child = self.keys_container_layout.itemAt(i).widget()

                if child:

                    child.setParent(None)

            

            headers = {

                'apikey': self.supabase_key,

                'Authorization': f'Bearer {self.supabase_key}',

                'Content-Type': 'application/json'

            }

            

            url = f"{self.supabase_url}/rest/v1/access_keys?select=*&order=created_at.desc"

            response = requests.get(url, headers=headers, timeout=10)

            

            if response.status_code == 200:

                keys = response.json()

                if not keys or len(keys) == 0:

                    no_keys_label = QLabel("📋 Aucune clé trouvée.\n\nVeuillez d'abord créer des clés dans Supabase.")

                    no_keys_label.setAlignment(Qt.AlignCenter)

                    no_keys_label.setStyleSheet("color: #888; padding: 20px;")

                    self.keys_container_layout.addWidget(no_keys_label)

                    return

                

                for key_data in keys:

                    try:

                        key_widget = self.create_key_widget(key_data)
                        if key_widget:
                            self.keys_container_layout.addWidget(key_widget)

                    except Exception as key_error:

                        error_label = QLabel(f"Erreur: {str(key_error)}")

                        error_label.setStyleSheet("color: #FF6666; padding: 5px;")

                        self.keys_container_layout.addWidget(error_label)

                

                # Ajouter un stretch à la fin

                self.keys_container_layout.addStretch()

                

            else:

                error_label = QLabel(f"Erreur {response.status_code}: {response.text}")

                error_label.setStyleSheet("color: #FF6666; padding: 10px;")

                self.keys_container_layout.addWidget(error_label)

                

        except Exception as e:

            error_label = QLabel(f"Erreur de connexion: {str(e)}")

            error_label.setStyleSheet("color: #FF6666; padding: 10px;")

            self.keys_container_layout.addWidget(error_label)

    

    def create_key_widget(self, key_data):

        """Créer un widget pour une clé avec boutons d'action"""

        key_widget = QWidget()

        key_layout = QHBoxLayout(key_widget)

        key_layout.setContentsMargins(10, 5, 10, 5)

        

        # Informations de la clé

        info_layout = QVBoxLayout()

        

        # Ligne 1: Description et statut

        desc = key_data.get('description', 'Sans description')

        status = "🟢 ACTIVE" if key_data.get('is_active', False) else "🔴 INACTIVE"

        role = key_data.get('role', 'user').upper()

        

        title_label = QLabel(f"Cle: {desc}")

        title_label.setFont(QFont("Arial", 10, QFont.Bold))

        title_label.setStyleSheet("color: #FFF;")

        info_layout.addWidget(title_label)

        

        # Ligne 2: Détails

        created = key_data.get('created_at', 'Inconnue')

        if created != 'Inconnue':

            created = created[:10]

        expires = key_data.get('expires_at')

        if expires:

            expires = expires[:10]

        else:

            expires = 'Permanent'

        usage = key_data.get('usage_count', 0)

        

        # Calculer le statut de connexion
        connection_status = self.get_connection_status(key_data)
        
        # Ajouter la dernière utilisation
        last_used = key_data.get('last_used_at', 'Jamais utilisée')
        if last_used != 'Jamais utilisée' and last_used:
            last_used_formatted = last_used[:19].replace('T', ' ')
        else:
            last_used_formatted = 'Jamais utilisée'
        
        details_label = QLabel(f"{status} | {role} | Créée: {created} | Expire: {expires} | Usage: {usage}")
        details_label.setStyleSheet("color: #CCC; font-size: 9px;")
        info_layout.addWidget(details_label)
        
        # Ligne 3: Dernière utilisation
        last_used_label = QLabel(f"🕒 Dernière utilisation: {last_used_formatted}")
        last_used_label.setStyleSheet("color: #87CEEB; font-size: 9px; font-weight: bold;")
        info_layout.addWidget(last_used_label)
        
        # Ligne 4: Statut de connexion
        connection_label = QLabel(connection_status)
        connection_label.setStyleSheet("color: #FFD700; font-size: 9px; font-weight: bold;")
        info_layout.addWidget(connection_label)

        

        key_layout.addLayout(info_layout)

        key_layout.addStretch()

        

        # Boutons d'action

        buttons_layout = QHBoxLayout()

        

        # Stocker la clé réelle pour les actions

        key_widget.key_hash = key_data.get('key_hash', '')

        key_widget.key_id = key_data.get('id', '')

        key_widget.is_active = key_data.get('is_active', False)

        

        if key_widget.is_active:

            deactivate_btn = QPushButton("❌ Désactiver")

            deactivate_btn.clicked.connect(lambda: self.toggle_key_status(key_widget, False))

            deactivate_btn.setStyleSheet("""

                QPushButton {

                    background-color: #CC3333;

                    color: white;

                    font-weight: bold;

                    padding: 5px 10px;

                    border-radius: 3px;

                    border: none;

                    font-size: 9px;

                }

                QPushButton:hover { background-color: #FF4444; }

            """)

            buttons_layout.addWidget(deactivate_btn)

        else:

            activate_btn = QPushButton("✅ Activer")

            activate_btn.clicked.connect(lambda: self.toggle_key_status(key_widget, True))

            activate_btn.setStyleSheet("""

                QPushButton {

                    background-color: #33CC33;

                    color: white;

                    font-weight: bold;

                    padding: 5px 10px;

                    border-radius: 3px;

                    border: none;

                    font-size: 9px;

                }

                QPushButton:hover { background-color: #44FF44; }

            """)

            buttons_layout.addWidget(activate_btn)

        

        # Bouton info/modifier

        info_btn = QPushButton("ℹ️ Info")

        info_btn.clicked.connect(lambda: self.show_key_info(key_data))

        info_btn.setStyleSheet("""

            QPushButton {

                background-color: #666;

                color: white;

                font-weight: bold;

                padding: 5px 10px;

                border-radius: 3px;

                border: none;

                font-size: 9px;

            }

            QPushButton:hover { background-color: #888; }

        """)

        buttons_layout.addWidget(info_btn)
        
        # Bouton forcer revalidation
        revalidate_btn = QPushButton("Revalider")
        revalidate_btn.clicked.connect(lambda: self.force_key_revalidation(key_widget))
        revalidate_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF6600;
                color: white;
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 3px;
                border: none;
                font-size: 9px;
            }
            QPushButton:hover { background-color: #FF8800; }
        """)
        buttons_layout.addWidget(revalidate_btn)

        key_layout.addLayout(buttons_layout)

        # Style du widget

        key_widget.setStyleSheet("""

            QWidget {

                background-color: #333;

                border: 1px solid #555;

                border-radius: 5px;

                margin: 2px;

            }

            QWidget:hover {

                background-color: #444;

                border-color: #777;

            }

        """)

        

        self.keys_container_layout.addWidget(key_widget)

    

    def toggle_key_status(self, key_widget, activate):

        """Activer ou désactiver une clé"""

        try:

            headers = {

                'apikey': self.supabase_key,

                'Authorization': f'Bearer {self.supabase_key}',

                'Content-Type': 'application/json'

            }

            

            function_name = "activate_key_by_hash" if activate else "deactivate_key_by_hash"

            url = f"{self.supabase_url}/rest/v1/rpc/{function_name}"

            params = {'p_key_hash': key_widget.key_hash}

            

            response = requests.post(url, json=params, headers=headers, timeout=10)

            

            if response.status_code == 200:

                result = response.json()

                if result:

                    action = "activée" if activate else "désactivée"

                    QMessageBox.information(self, "Succès", f"Clé {action} avec succès!")

                    self.load_keys()  # Recharger la liste

                else:

                    QMessageBox.warning(self, "Erreur", "Clé non trouvée")

            else:

                QMessageBox.critical(self, "Erreur", f"Erreur: {response.status_code}")

                

        except Exception as e:

            QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")

    

    def show_key_info(self, key_data):

        """Afficher les informations détaillées d'une clé"""

        info_text = f"""

INFORMATIONS DETAILLEES



Description: {key_data.get('description', 'Sans description')}

ID: {key_data.get('id', 'Inconnu')}

Rôle: {key_data.get('role', 'user').upper()}

Statut: {'🟢 ACTIVE' if key_data.get('is_active', False) else '🔴 INACTIVE'}



📅 DATES

Créée le: {key_data.get('created_at', 'Inconnue')[:19] if key_data.get('created_at') else 'Inconnue'}

Expire le: {key_data.get('expires_at', 'Permanent')[:19] if key_data.get('expires_at') else 'Permanent'}

Dernière utilisation: {key_data.get('last_used_at', 'Jamais')[:19] if key_data.get('last_used_at') else 'Jamais'}



📊 STATISTIQUES

Nombre d'utilisations: {key_data.get('usage_count', 0)}

Limite d'utilisation: {key_data.get('max_usage', 'Illimitée') if key_data.get('max_usage') else 'Illimitée'}

        """

        

        QMessageBox.information(self, "Informations de la clé", info_text)

    

    def deactivate_key(self):

        key = self.selected_key_input.text().strip()

        if not key:

            QMessageBox.warning(self, "Erreur", "Veuillez entrer la clé à désactiver")

            return

        

        self.modify_key_status(key, False, "désactiver")

    

    def activate_key(self):

        key = self.selected_key_input.text().strip()

        if not key:

            QMessageBox.warning(self, "Erreur", "Veuillez entrer la clé à activer")

            return

        

        self.modify_key_status(key, True, "activer")

    

    def modify_key_status(self, key, active, action):

        try:

            key_hash = hashlib.sha256(key.encode()).hexdigest()

            

            headers = {

                'apikey': self.supabase_key,

                'Authorization': f'Bearer {self.supabase_key}',

                'Content-Type': 'application/json'

            }

            

            function_name = "activate_key_by_hash" if active else "deactivate_key_by_hash"

            url = f"{self.supabase_url}/rest/v1/rpc/{function_name}"

            params = {'p_key_hash': key_hash}

            

            response = requests.post(url, json=params, headers=headers, timeout=10)

            

            if response.status_code == 200:

                result = response.json()

                if result:

                    QMessageBox.information(self, "Succès", f"Clé {action}ée avec succès!")

                    self.selected_key_input.clear()

                    self.load_keys()

                else:

                    QMessageBox.warning(self, "Erreur", "Clé non trouvée")

            else:
                QMessageBox.critical(self, "Erreur", f"Erreur: {response.status_code}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")

    def show_connected_keys(self):
        """Afficher les clés actuellement connectées (utilisées récemment)"""
        try:
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }

            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            # Requête pour toutes les clés actives
            url = f"{self.supabase_url}/rest/v1/access_keys?select=*&is_active=eq.true&order=last_used_at.desc.nullslast"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                all_keys = response.json()

                if not all_keys:
                    info_text = "🔍 CLÉS CONNECTÉES\n\n❌ Aucune clé active trouvée."
                else:
                    # Filtrer les clés connectées récemment
                    connected_keys = []
                    for key_data in all_keys:
                        last_used = key_data.get('last_used_at')
                        if last_used:
                            try:
                                last_used_dt = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
                                yesterday_dt = datetime.now(last_used_dt.tzinfo) - timedelta(days=1)
                                if last_used_dt >= yesterday_dt:
                                    connected_keys.append(key_data)
                            except:
                                pass
                    
                    if not connected_keys:
                        info_text = "🔍 CLÉS CONNECTÉES\n\n❌ Aucune clé connectée dans les dernières 24 heures."
                        info_text += f"\n\n📋 Clés actives totales: {len(all_keys)}"
                        info_text += "\n\n💡 Les clés apparaîtront ici après leur première utilisation."
                        
                        # Afficher toutes les clés avec leur statut
                        info_text += "\n\n📋 TOUTES LES CLÉS ACTIVES:\n\n"
                        for i, key_data in enumerate(all_keys, 1):
                            desc = key_data.get('description', 'Sans description')
                            role = key_data.get('role', 'user').upper()
                            last_used = key_data.get('last_used_at', 'Jamais utilisée')
                            
                            if last_used != 'Jamais utilisée' and last_used:
                                last_used = last_used[:19].replace('T', ' ')
                            
                            info_text += f"{i}. Cle: {desc}\n"
                            info_text += f"   👤 Rôle: {role}\n"
                            info_text += f"   🕒 Dernière utilisation: {last_used}\n\n"
                    else:
                        info_text = f"🔍 CLÉS CONNECTÉES ({len(connected_keys)} clés actives)\n\n"
                        info_text += "📊 Clés utilisées dans les dernières 24 heures:\n\n"

                        for i, key_data in enumerate(connected_keys, 1):
                            desc = key_data.get('description', 'Sans description')
                            role = key_data.get('role', 'user').upper()
                            last_used = key_data.get('last_used_at', 'Jamais')
                            usage_count = key_data.get('usage_count', 0)

                            if last_used != 'Jamais':
                                last_used = last_used[:19].replace('T', ' ')

                            info_text += f"{i}. Cle: {desc}\n"
                            info_text += f"   👤 Rôle: {role}\n"
                            info_text += f"   🕒 Dernière utilisation: {last_used}\n"
                            info_text += f"   📊 Utilisations totales: {usage_count}\n\n"

                dialog = QDialog(self)
                dialog.setWindowTitle("👥 Clés Actuellement Connectées")
                dialog.setFixedSize(600, 500)
                dialog.setModal(True)

                layout = QVBoxLayout()

                text_widget = QTextEdit()
                text_widget.setPlainText(info_text)
                text_widget.setReadOnly(True)
                text_widget.setFont(QFont("Consolas", 10))
                text_widget.setStyleSheet("""
                    QTextEdit {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                        color: #FFFFFF;
                        border: 2px solid #333333;
                        border-radius: 12px;
                        padding: 10px;
                        font-family: 'Consolas', 'Courier New', monospace;
                    }
                """)
                layout.addWidget(text_widget)

                # Boutons
                buttons_layout = QHBoxLayout()
                
                refresh_btn = QPushButton("Actualiser")
                refresh_btn.clicked.connect(lambda: self.refresh_connected_keys_dialog(dialog, text_widget))
                refresh_btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #00D4FF, stop: 1 #0099CC);
                        color: #000000;
                        font-weight: 600;
                        border: none;
                        border-radius: 12px;
                        padding: 12px 20px;
                        font-size: 13px;
                        min-width: 120px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #1AE5FF, stop: 1 #00B8E6);
                    }
                """)
                
                close_btn = QPushButton("❌ Fermer")
                close_btn.clicked.connect(dialog.accept)
                close_btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #666666, stop: 1 #4D4D4D);
                        color: #FFFFFF;
                        font-weight: 600;
                        border: none;
                        border-radius: 12px;
                        padding: 12px 20px;
                        font-size: 13px;
                        min-width: 120px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #888888, stop: 1 #666666);
                    }
                """)
                
                buttons_layout.addWidget(refresh_btn)
                buttons_layout.addWidget(close_btn)
                layout.addLayout(buttons_layout)

                dialog.setLayout(layout)
                dialog.setStyleSheet("""
                    QDialog {
                        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                            stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                        color: #FFFFFF;
                        font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
                    }
                """)
                dialog.exec_()

            else:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la récupération: {response.status_code}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")

    def refresh_connected_keys_dialog(self, dialog, text_widget):
        """Actualiser les données des clés connectées dans la boîte de dialogue"""
        try:
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }

            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            url = f"{self.supabase_url}/rest/v1/access_keys?select=*&last_used_at=gte.{yesterday}&is_active=eq.true&order=last_used_at.desc"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                connected_keys = response.json()

                if not connected_keys:
                    info_text = "🔍 CLÉS CONNECTÉES\n\n❌ Aucune clé connectée dans les dernières 24 heures."
                else:
                    info_text = f"🔍 CLÉS CONNECTÉES ({len(connected_keys)} clés actives)\n\n"
                    info_text += "📊 Clés utilisées dans les dernières 24 heures:\n\n"

                    for i, key_data in enumerate(connected_keys, 1):
                        desc = key_data.get('description', 'Sans description')
                        role = key_data.get('role', 'user').upper()
                        last_used = key_data.get('last_used_at', 'Jamais')
                        usage_count = key_data.get('usage_count', 0)

                        if last_used != 'Jamais':
                            last_used = last_used[:19].replace('T', ' ')

                        info_text += f"{i}. 🔑 {desc}\n"
                        info_text += f"   👤 Rôle: {role}\n"
                        info_text += f"   🕒 Dernière utilisation: {last_used}\n"
                        info_text += f"   📊 Utilisations totales: {usage_count}\n\n"

                # Ajouter l'heure de dernière mise à jour
                now = datetime.now().strftime('%H:%M:%S')
                info_text += f"\n🕒 Dernière mise à jour: {now}"
                
                text_widget.setPlainText(info_text)
            else:
                text_widget.setPlainText(f"❌ Erreur lors de la récupération: {response.status_code}")

        except Exception as e:
            text_widget.setPlainText(f"❌ Erreur: {str(e)}")

    def get_connection_status(self, key_data):
        """Calculer le statut de connexion d'une clé"""
        try:
            from datetime import datetime, timedelta
            
            last_used = key_data.get('last_used_at')
            if not last_used:
                return "🔴 Jamais connecté"
            
            # Convertir la date de dernière utilisation
            last_used_dt = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
            now = datetime.now(last_used_dt.tzinfo)
            
            # Calculer la différence
            diff = now - last_used_dt
            
            # Déterminer le statut
            if diff.total_seconds() < 300:  # 5 minutes
                return "🟢 Connecté maintenant"
            elif diff.total_seconds() < 3600:  # 1 heure
                minutes = int(diff.total_seconds() / 60)
                return f"🟡 Connecté il y a {minutes} min"
            elif diff.total_seconds() < 86400:  # 24 heures
                hours = int(diff.total_seconds() / 3600)
                return f"🟠 Connecté il y a {hours}h"
            elif diff.days < 7:  # 7 jours
                return f"🔴 Connecté il y a {diff.days} jour(s)"
            else:
                return f"🔴 Inactif depuis {diff.days} jours"
                
        except Exception:
            return "❓ Statut inconnu"

    def force_close_application(self):
        """Forcer la fermeture de l'application avec confirmation"""
        reply = QMessageBox.question(
            self,
            '⚠️ Confirmation de Fermeture Forcée',
            'Êtes-vous sûr de vouloir forcer la fermeture de l\'application?\n\n'
            '⚠️ ATTENTION: Cette action fermera immédiatement l\'application\n'
            'sans sauvegarder les données en cours.\n\n'
            'Cette action est irréversible.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            final_reply = QMessageBox.critical(
                self,
                '🚨 DERNIÈRE CONFIRMATION',
                'DERNIÈRE CHANCE!\n\n'
                '🚨 Vous êtes sur le point de FORCER LA FERMETURE\n'
                'de l\'application VMT Path Renamer.\n\n'
                'Voulez-vous vraiment continuer?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if final_reply == QMessageBox.Yes:
                QMessageBox.information(
                    self,
                    '💀 Fermeture Forcée',
                    'L\'application va se fermer dans 3 secondes...\n\n'
                    '💀 FERMETURE FORCÉE ACTIVÉE'
                )

                import time
                QApplication.processEvents()
                time.sleep(1)

                self.accept()

                QApplication.processEvents()
                time.sleep(1)

                import os
                os._exit(0)
    
    def force_key_revalidation(self, key_widget):
        """Forcer la revalidation d'une clé spécifique"""
        try:
            # Récupérer les informations de la clé
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json'
            }
            
            # Récupérer les détails de la clé
            url = f"{self.supabase_url}/rest/v1/access_keys?id=eq.{key_widget.key_id}"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                key_data = response.json()
                if key_data and len(key_data) > 0:
                    key_info = key_data[0]
                    key_desc = key_info.get('description', 'Clé inconnue')
                    
                    # Confirmation
                    reply = QMessageBox.question(
                        self,
                        'Forcer Revalidation',
                        f'Voulez-vous forcer la revalidation de la clé :\n\n'
                        f'Cle: {key_desc}\n\n'
                        f'⚠️ L\'utilisateur devra ressaisir sa clé pour continuer\n'
                        f'à utiliser l\'application. Si la clé n\'est plus valide,\n'
                        f'il ne pourra plus accéder à l\'application.',
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        # Marquer la clé pour revalidation
                        update_url = f"{self.supabase_url}/rest/v1/access_keys?id=eq.{key_widget.key_id}"
                        update_data = {'force_revalidation': True}
                        
                        update_response = requests.patch(update_url, json=update_data, headers=headers, timeout=10)
                        
                        if update_response.status_code == 200:
                            QMessageBox.information(
                                self, 
                                "✅ Revalidation Forcée", 
                                f"La clé '{key_desc}' a été marquée pour revalidation.\n\n"
                                f"L'utilisateur devra ressaisir sa clé lors de sa prochaine connexion."
                            )
                            self.load_keys()  # Recharger la liste
                        else:
                            QMessageBox.critical(self, "Erreur", f"Erreur lors de la mise à jour: {update_response.status_code}")
                else:
                    QMessageBox.warning(self, "Erreur", "Clé non trouvée")
            else:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la récupération: {response.status_code}")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")
    
    def force_global_revalidation(self):
        """Forcer la revalidation de toutes les clés actives"""
        reply = QMessageBox.question(
            self,
            'Revalidation Globale',
            '⚠️ ATTENTION: Forcer la revalidation globale\n\n'
            'Cette action va marquer TOUTES les clés actives\n'
            'pour revalidation. Tous les utilisateurs devront\n'
            'ressaisir leur clé pour continuer à utiliser l\'application.\n\n'
            'Voulez-vous vraiment continuer?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            final_reply = QMessageBox.critical(
                self,
                '🚨 CONFIRMATION FINALE',
                'DERNIÈRE CHANCE!\n\n'
                '🚨 Vous êtes sur le point de FORCER LA REVALIDATION\n'
                'de TOUTES les clés actives.\n\n'
                'Tous les utilisateurs devront se reconnecter.\n\n'
                'Confirmer cette action?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if final_reply == QMessageBox.Yes:
                try:
                    headers = {
                        'apikey': self.supabase_key,
                        'Authorization': f'Bearer {self.supabase_key}',
                        'Content-Type': 'application/json'
                    }
                    
                    # Marquer toutes les clés actives pour revalidation
                    url = f"{self.supabase_url}/rest/v1/access_keys?is_active=eq.true"
                    update_data = {'force_revalidation': True}
                    
                    response = requests.patch(url, json=update_data, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        QMessageBox.information(
                            self,
                            "✅ Revalidation Globale Activée",
                            "Toutes les clés actives ont été marquées pour revalidation.\n\n"
                            "Tous les utilisateurs devront ressaisir leur clé\n"
                            "lors de leur prochaine connexion."
                        )
                        self.load_keys()  # Recharger la liste
                    else:
                        QMessageBox.critical(self, "Erreur", f"Erreur lors de la mise à jour globale: {response.status_code}")
                        
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Erreur: {str(e)}")


def require_authentication():
    """Fonction à appeler au début de votre application"""
    app = QApplication.instance()

    if app is None:

        app = QApplication(sys.argv)

    

    # Créer et afficher la fenêtre d'authentification

    auth_dialog = AuthDialog()

    

    if auth_dialog.exec_() == QDialog.Accepted:

        # Vérifier si c'est un admin

        if hasattr(auth_dialog, 'user_role') and auth_dialog.user_role == 'admin':

            reply = QMessageBox.question(

                None,

                'Panneau Administrateur',

                'Voulez-vous ouvrir le panneau administrateur?',

                QMessageBox.Yes | QMessageBox.No,

                QMessageBox.No

            )

            

            if reply == QMessageBox.Yes:

                admin_panel = AdminPanel(auth_dialog.SUPABASE_URL, auth_dialog.SUPABASE_ANON_KEY)

                admin_panel.exec_()

        

        return True

    else:

        sys.exit(0)



# ------------------ VERSION ------------------
VERSION = "18.0.0"  # version locale

# ------------------ UPDATE CONFIGURATION ------------------
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/version.txt"
UPDATE_SCRIPT_URL = "https://raw.githubusercontent.com/sakuoo1/vm/main/aa.py"

# Variable globale pour stocker la meilleure URL de téléchargement
BEST_UPDATE_URL = UPDATE_SCRIPT_URL







def parse_version(v):

    try:

        v_clean = (v or "").strip().replace('\ufeff', '').replace('\r', '').replace('\n', '')

        if not v_clean or not v_clean.replace('.', '').isdigit():

            return (0,)

        parts = v_clean.split(".")

        return tuple(int(x) for x in parts if x.isdigit())

    except Exception:

        return (0,)







def log_crash(error_text):

    """Crée un fichier crash.txt avec l'erreur seulement pour les vraies erreurs critiques"""

    try:

        # Ne pas créer de crash.txt pour les erreurs de réseau normales

        if any(keyword in error_text.lower() for keyword in [

            "timeout", "connexion", "récupérer la version", "vérification de mise à jour"

        ]):

            print(f"[INFO] Erreur réseau normale (pas de crash.txt): {error_text}")

            return

            

        crash_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "crash.txt")

        with open(crash_path, "w", encoding="utf-8") as f:

            f.write(f"ERREUR CRITIQUE:\n{error_text}\n\nCeci n'est PAS une erreur de réseau normale.")

    except Exception:

        pass  # si écrire le crash échoue, on ignore







def check_update(silent=False):
    """Vérifie la version sur GitHub de manière optimisée et efficace"""
    
    try:
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        if not silent:
            print(f"[INFO] Vérification de mise à jour - Version locale: {VERSION}")
        
        # Configuration optimisée des URLs
        timestamp = int(time.time())
        
        # URLs prioritaires (CDN rapides en premier)
        urls_config = [
            {
                'url': UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "cdn.jsdelivr.net/gh").replace("/main/", "@main/") + f"?t={timestamp}",
                'priority': 1,
                'timeout': 5
            },
            {
                'url': UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "cdn.statically.io/gh").replace("/main/", "/main/") + f"?t={timestamp}",
                'priority': 2, 
                'timeout': 5
            },
            {
                'url': UPDATE_CHECK_URL + f"?t={timestamp}",
                'priority': 3,
                'timeout': 8
            }
        ]
        
        # Headers optimisés
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'User-Agent': f'VMT-Path-Renamer/{VERSION}',
            'Accept': 'text/plain',
            'Connection': 'close'
        }
        
        local_version_tuple = parse_version(VERSION)
        best_version = None
        best_version_tuple = (0, 0, 0)
        best_url = None
        
        def fetch_version(config):
            """Fonction pour récupérer une version depuis une URL"""
            try:
                response = requests.get(
                    config['url'], 
                    headers=headers, 
                    timeout=config['timeout']
                )
                
                if response.status_code == 200:
                    version_text = response.text.strip().replace('\ufeff', '').replace('\r', '').replace('\n', '').strip()
                    version_tuple = parse_version(version_text)
                    
                    return {
                        'success': True,
                        'version': version_text,
                        'version_tuple': version_tuple,
                        'url': config['url'],
                        'priority': config['priority']
                    }
                else:
                    return {'success': False, 'error': f'HTTP {response.status_code}', 'priority': config['priority']}
                    
            except requests.exceptions.Timeout:
                return {'success': False, 'error': 'Timeout', 'priority': config['priority']}
            except requests.exceptions.ConnectionError:
                return {'success': False, 'error': 'Connection Error', 'priority': config['priority']}
            except Exception as e:
                return {'success': False, 'error': str(e), 'priority': config['priority']}
        
        # Exécution parallèle avec timeout global
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Soumettre toutes les tâches
            future_to_config = {executor.submit(fetch_version, config): config for config in urls_config}
            
            # Récupérer les résultats avec timeout global de 15 secondes
            try:
                for future in as_completed(future_to_config, timeout=15):
                    result = future.result()
                    results.append(result)
                    
                    # Si on trouve une version valide, on peut arrêter plus tôt
                    if result['success'] and result['version_tuple'] > local_version_tuple:
                        if not silent:
                            print(f"[SUCCESS] Version plus récente trouvée: {result['version']} (arrêt anticipé)")
                        # Annuler les autres tâches
                        for f in future_to_config:
                            f.cancel()
                        break
                        
            except Exception as e:
                if not silent:
                    print(f"[WARNING] Timeout global atteint: {e}")
        
        # Analyser les résultats
        successful_results = [r for r in results if r['success']]
        
        if not successful_results:
            error_messages = [r['error'] for r in results if not r['success']]
            return "Erreur", False, f"Aucun serveur accessible. Erreurs: {', '.join(error_messages[:3])}"
        
        # Trouver la meilleure version (trier par priorité puis par version)
        successful_results.sort(key=lambda x: (x['priority'], -x['version_tuple'][0], -x['version_tuple'][1], -x['version_tuple'][2]))
        best_result = successful_results[0]
        
        best_version = best_result['version']
        best_version_tuple = best_result['version_tuple']
        best_url = best_result['url']
        
        # Sauvegarder l'URL optimale pour le téléchargement
        global BEST_UPDATE_URL
        if "jsdelivr.net" in best_url:
            BEST_UPDATE_URL = best_url.replace("version.txt", "test.py").split('?')[0]
        elif "statically.io" in best_url:
            BEST_UPDATE_URL = best_url.replace("version.txt", "test.py").split('?')[0]
        else:
            BEST_UPDATE_URL = UPDATE_SCRIPT_URL

        if not silent:
            print(f"[DEBUG] URL de téléchargement: {BEST_UPDATE_URL}")
        
        # Comparaison des versions
        up_to_date = local_version_tuple >= best_version_tuple
        
        if not silent:
            status = "à jour" if up_to_date else "mise à jour disponible"
            print(f"[INFO] Application {status} (locale: {VERSION}, distante: {best_version})")
        
        return best_version, up_to_date, f"Vérification réussie - Version distante: {best_version}"

    except requests.exceptions.Timeout:
        error_msg = "Timeout lors de la vérification de mise à jour"
        print(f"[INFO] {error_msg} - Réessayez plus tard")
        return "Erreur", False, "Timeout réseau - Réessayez dans quelques minutes"

    except requests.exceptions.ConnectionError:
        error_msg = "Erreur de connexion lors de la vérification de mise à jour"
        print(f"[INFO] {error_msg} - Vérifiez votre connexion internet")
        return "Erreur", False, "Pas de connexion internet"

    except Exception as e:
        error_msg = f"Erreur lors de la vérification de mise à jour: {e}"
        print(f"[DEBUG] {error_msg}")
        
        # Seulement créer crash.txt pour les vraies erreurs critiques
        if "parse" in str(e).lower() or "critical" in str(e).lower():
            log_crash(error_msg)
        
        return "Erreur", False, f"Erreur technique: {str(e)[:50]}..."

# ------------------ Fonctions de téléchargement optimisées ------------------

def download_update_optimized(latest_version, progress_callback=None):
    """Télécharge la mise à jour de manière optimisée avec gestion d'erreurs robuste"""
    
    try:
        import tempfile
        import shutil
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        if progress_callback:
            progress_callback("Préparation du téléchargement...", 5)
        
        # URLs de téléchargement prioritaires
        download_urls = []
        
        # Utiliser l'URL optimale trouvée lors de la vérification
        if BEST_UPDATE_URL and BEST_UPDATE_URL != UPDATE_SCRIPT_URL:
            download_urls.append({
                'url': BEST_UPDATE_URL,
                'priority': 1,
                'timeout': 30
            })
        
        # URLs de fallback
        jsdelivr_url = UPDATE_SCRIPT_URL.replace("raw.githubusercontent.com", "cdn.jsdelivr.net/gh").replace("/main/", "@main/")
        statically_url = UPDATE_SCRIPT_URL.replace("raw.githubusercontent.com", "cdn.statically.io/gh").replace("/main/", "/main/")
        
        download_urls.extend([
            {'url': jsdelivr_url, 'priority': 2, 'timeout': 25},
            {'url': statically_url, 'priority': 3, 'timeout': 25},
            {'url': UPDATE_SCRIPT_URL, 'priority': 4, 'timeout': 30}
        ])
        
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'User-Agent': f'VMT-Path-Renamer/{VERSION}',
            'Accept': 'text/plain, application/octet-stream',
            'Connection': 'close'
        }
        
        def download_from_url(config):
            """Télécharge depuis une URL spécifique"""
            try:
                response = requests.get(
                    config['url'], 
                    headers=headers, 
                    timeout=config['timeout'],
                    stream=True
                )
                
                if response.status_code == 200:
                    content = response.content
                    # Validation basique du contenu
                    if len(content) > 50000 and b'import' in content[:1000]:  # Fichier Python valide
                        return {
                            'success': True,
                            'content': content,
                            'url': config['url'],
                            'priority': config['priority'],
                            'size': len(content)
                        }
                    else:
                        return {'success': False, 'error': 'Contenu invalide', 'priority': config['priority']}
                else:
                    return {'success': False, 'error': f'HTTP {response.status_code}', 'priority': config['priority']}
                    
            except Exception as e:
                return {'success': False, 'error': str(e), 'priority': config['priority']}
        
        if progress_callback:
            progress_callback("Téléchargement en cours...", 20)
        
        # Téléchargement parallèle avec timeout
        successful_download = None
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_config = {executor.submit(download_from_url, config): config for config in download_urls[:2]}
            
            try:
                for future in as_completed(future_to_config, timeout=45):
                    result = future.result()
                    if result['success']:
                        successful_download = result
                        # Annuler les autres téléchargements
                        for f in future_to_config:
                            f.cancel()
                        break
            except Exception:
                pass
        
        # Si le téléchargement parallèle échoue, essayer séquentiellement
        if not successful_download:
            if progress_callback:
                progress_callback("Tentative de téléchargement alternatif...", 40)
                
            for config in download_urls[2:]:
                result = download_from_url(config)
                if result['success']:
                    successful_download = result
                    break
        
        if not successful_download:
            return False, "Échec du téléchargement depuis tous les serveurs"
        
        if progress_callback:
            progress_callback("Installation de la mise à jour...", 70)
        
        # Sauvegarder le fichier
        script_path = os.path.abspath(__file__)
        backup_path = script_path + ".backup"
        
        # Créer une sauvegarde
        try:
            shutil.copy2(script_path, backup_path)
        except Exception as e:
            return False, f"Impossible de créer la sauvegarde: {e}"
        
        # Écrire le nouveau fichier
        try:
            with open(script_path, 'wb') as f:
                f.write(successful_download['content'])
        except Exception as e:
            # Restaurer la sauvegarde en cas d'erreur
            try:
                shutil.copy2(backup_path, script_path)
            except:
                pass
            return False, f"Erreur lors de l'écriture: {e}"
        
        if progress_callback:
            progress_callback("Mise à jour terminée!", 100)
        
        # Nettoyer la sauvegarde après succès
        try:
            os.remove(backup_path)
        except:
            pass
        
        return True, f"Mise à jour réussie vers la version {latest_version} (source: {successful_download['url']})"
        
    except Exception as e:
        return False, f"Erreur critique lors de la mise à jour: {e}"

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















        self.setWindowTitle("SAK VMT RENAME ETC ")
        
        # Style futuriste pour la fenêtre principale
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #FFFFFF;
                font-weight: 500;
            }
            QLineEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #00D4FF;
            }
            QTextEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 8px;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                color: #00D4FF;
                border: 2px solid #333333;
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #00D4FF;
                background: #1A1A1A;
            }
        """)















        self.setGeometry(100, 100, 1100, 900)















        self.init_ui()















        self.manual_check_update()







        







        # Timer pour vérification automatique toutes les 15 minutes







        self.update_timer = QTimer()







        self.update_timer.timeout.connect(self.auto_check_update)




        self.update_timer.start(15 * 60 * 1000)  # 15 minutes en millisecondes
    
    def auto_check_update(self):
        """Vérification automatique silencieuse des mises à jour"""
        try:
            latest_version, up_to_date, error_msg = check_update(silent=True)
            
            if latest_version != "Erreur" and not up_to_date:
                # Mise à jour disponible - notifier discrètement
                self.update_label.setText(f"🔔 Nouvelle version disponible ({latest_version})")
                self.update_btn.setEnabled(True)
                self.log_widget.append(f"🔔 Mise à jour automatique détectée: {latest_version}")
            elif up_to_date:
                # Application à jour
                self.update_label.setText(f"✅ Application à jour ({VERSION})")
                self.update_btn.setEnabled(False)
            # En cas d'erreur, ne rien faire (vérification silencieuse)
            
        except Exception as e:
            # Erreur silencieuse - ne pas déranger l'utilisateur
            print(f"[DEBUG] Erreur vérification automatique: {e}")
            pass



    def init_ui(self):















        layout = QVBoxLayout()















        # Version label + update buttons







        update_layout = QHBoxLayout()







        self.update_label = QLabel("🔄 Vérification mise à jour...")
        self.update_label.setStyleSheet("color: #00D4FF; font-weight: 600; font-size: 14px;")







        self.check_update_btn = QPushButton("🔄 Vérifier")
        self.check_update_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
        """)







        self.check_update_btn.clicked.connect(self.manual_check_update)







        self.debug_btn = QPushButton("🐛 Debug GitHub")
        self.debug_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #9933CC, stop: 1 #7A29A3);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #BB44FF, stop: 1 #9933CC);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #7A29A3, stop: 1 #5C1F7A);
            }
        """)







        self.debug_btn.clicked.connect(self.debug_github)







        self.test_local_btn = QPushButton("🧪 Test Local")
        self.test_local_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF6600, stop: 1 #CC5200);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF8800, stop: 1 #E65C00);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CC5200, stop: 1 #994000);
            }
        """)







        self.test_local_btn.clicked.connect(self.test_local_version)







        self.force_check_btn = QPushButton("⚡ Force Check")
        self.force_check_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FFFF00, stop: 1 #CCCC00);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FFFF33, stop: 1 #E6E600);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CCCC00, stop: 1 #999900);
            }
        """)







        self.force_check_btn.clicked.connect(self.force_check_update)







        self.ultra_check_btn = QPushButton("🚀 Ultra Check")
        self.ultra_check_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00FF88, stop: 1 #00CC6A);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AFF99, stop: 1 #00E675);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00CC6A, stop: 1 #00B35C);
            }
        """)







        self.ultra_check_btn.clicked.connect(self.ultra_check_update)







        self.connection_test_btn = QPushButton("🌐 Test Connexion")
        self.connection_test_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00CCFF, stop: 1 #0099CC);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #33D6FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
        """)







        self.connection_test_btn.clicked.connect(self.test_connection)







        self.update_btn = QPushButton("⬇️ Télécharger mise à jour")
        self.update_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF4757, stop: 1 #CC3A47);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF5A6B, stop: 1 #E6434F);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CC3A47, stop: 1 #B32D3A);
            }
            QPushButton:disabled {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #333333, stop: 1 #2A2A2A);
                color: #707070;
            }
        """)







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















            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                stop: 0 #00D4FF, stop: 1 #0099CC);
            color: #000000;
            font-weight: 600;
            border: none;
            border-radius: 12px;
            padding: 12px 20px;
            font-size: 13px;
            min-width: 120px;

















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















        browse_btn = QPushButton("📁 Parcourir")
        browse_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
        """)















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















        action_layout = QVBoxLayout()







        







        # Première ligne d'actions







        action_layout1 = QHBoxLayout()















        self.run_vmt_btn = QPushButton("🔄 Modifier chemins VMT")
        self.run_vmt_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 160px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0099CC, stop: 1 #007399);
            }
        """)















        self.run_rename_btn = QPushButton("📦 Renommer dossiers")
        self.run_rename_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #9933CC, stop: 1 #7A29A3);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 160px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #BB44FF, stop: 1 #9933CC);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #7A29A3, stop: 1 #5C1F7A);
            }
        """)















        self.scan_btn = QPushButton("🔍 Scanner dossiers")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00FF88, stop: 1 #00CC6A);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 160px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AFF99, stop: 1 #00E675);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00CC6A, stop: 1 #00B35C);
            }
        """)















        self.reset_btn = QPushButton("♻️ Reset")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF6600, stop: 1 #CC5200);
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 160px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #FF8800, stop: 1 #E65C00);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #CC5200, stop: 1 #994000);
            }
        """)















        for btn, func in [(self.run_vmt_btn, self.run_vmt), (self.run_rename_btn, self.run_rename),















                          (self.scan_btn, self.scan_vmt_dirs), (self.reset_btn, self.reset_fields)]:















            btn.clicked.connect(func)















            action_layout1.addWidget(btn)







        







        # Deuxième ligne d'actions







        action_layout2 = QHBoxLayout()















        self.apply_move_btn = QPushButton("✅ Déplacer VMT/VTF")
        self.apply_move_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00FF88, stop: 1 #00CC6A);
                color: #000000;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                padding: 12px 20px;
                font-size: 13px;
                min-width: 160px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AFF99, stop: 1 #00E675);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00CC6A, stop: 1 #00B35C);
            }
        """)







        






















        for btn, func in [(self.apply_move_btn, self.apply_move_vmt_vtf),







                          ]:















            btn.clicked.connect(func)















            action_layout2.addWidget(btn)















        action_layout.addLayout(action_layout1)







        action_layout.addLayout(action_layout2)







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
        self.log_widget.setStyleSheet("""
            QTextEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)







        self.log_widget.setReadOnly(True)







        layout.addWidget(self.log_widget)































        # Dossiers détectés







        layout.addWidget(QLabel("Dossiers détectés"))







        self.detected_dirs_widget = QTextEdit()
        self.detected_dirs_widget.setStyleSheet("""
            QTextEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1E1E1E, stop: 1 #2A2A2A);
                color: #FFFFFF;
                border: 2px solid #333333;
                border-radius: 12px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)







        layout.addWidget(self.detected_dirs_widget)















        # Timer countdown en bas à gauche







        countdown_layout = QHBoxLayout()







        self.countdown_label = QLabel("⏱️ Prochaine vérification dans: 15:00")







        self.countdown_label.setStyleSheet("color: #888888; font-size: 10px;")







        countdown_layout.addWidget(self.countdown_label)







        # Bouton Changelog

        self.changelog_btn = QPushButton("📋 Changelog")

        self.changelog_btn.clicked.connect(self.show_changelog)

        self.changelog_btn.setStyleSheet("""

            QPushButton {

                background-color: #444;

                color: white;

                font-weight: bold;

                padding: 5px 10px;

                border-radius: 3px;

                border: none;

                font-size: 9px;

                margin-left: 10px;

            }

            QPushButton:hover { background-color: #666; }

        """)

        countdown_layout.addWidget(self.changelog_btn)



        countdown_layout.addStretch()  # Pousse le label vers la gauche







        layout.addLayout(countdown_layout)















        self.setLayout(layout)















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
        """Vérification manuelle des mises à jour optimisée"""
        
        self.log_widget.append("🔄 Vérification des mises à jour...")
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("🔄 Vérification...")
        
        try:
            latest_version, up_to_date, error_msg = check_update()
            
            if latest_version == "Erreur":
                self.update_label.setText("⚠️ Impossible de vérifier la mise à jour")
                self.update_btn.setEnabled(False)
                self.log_widget.append(f"❌ Erreur: {error_msg}")
            elif up_to_date:
                self.update_label.setText(f"✅ Application à jour ({VERSION})")
                self.update_btn.setEnabled(False)
                self.log_widget.append(f"✅ Version actuelle: {VERSION} (à jour)")
            else:
                self.update_label.setText(f"🔔 Nouvelle version disponible ({latest_version})")
                self.update_btn.setEnabled(True)
                self.log_widget.append(f"⬇️ Nouvelle version disponible: {latest_version}")
                self.log_widget.append(f"📊 Version locale: {VERSION} < Version distante: {latest_version}")
                
                # Proposer l'installation automatique
                self.force_update_installation(latest_version)
                
        except Exception as e:
            self.update_label.setText("❌ Erreur lors de la vérification")
            self.update_btn.setEnabled(False)
            self.log_widget.append(f"❌ Exception: {str(e)}")
        
        finally:
            # Réactiver le bouton
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText("🔄 Vérifier les mises à jour")


    def force_update_installation(self, latest_version):
        """Force l'installation de la mise à jour avec interface optimisée"""
        
        # Désactiver l'interface principale
        self.setEnabled(False)
        
        # Créer une boîte de dialogue moderne
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("🔄 Mise à jour disponible")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(f"""
🎆 NOUVELLE VERSION DISPONIBLE

Version actuelle: {VERSION}
Nouvelle version: {latest_version}

La mise à jour sera téléchargée et installée automatiquement.
L'application redémarrera après l'installation.

Voulez-vous procéder maintenant?
        """)
        
        install_btn = msg_box.addButton("🚀 Installer", QMessageBox.AcceptRole)
        later_btn = msg_box.addButton("⏰ Plus tard", QMessageBox.RejectRole)
        msg_box.setDefaultButton(install_btn)
        
        # Style futuriste
        msg_box.setStyleSheet("""
            QMessageBox {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI';
                font-size: 12px;
                border: 2px solid #00D4FF;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                color: #FFFFFF;
                background-color: transparent;
                padding: 15px;
                font-size: 13px;
            }
            QMessageBox QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00D4FF, stop: 1 #0099CC);
                color: #FFFFFF;
                font-weight: 600;
                padding: 12px 24px;
                border-radius: 8px;
                border: none;
                min-width: 100px;
                font-size: 12px;
            }
            QMessageBox QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1AE5FF, stop: 1 #00B8E6);
            }
        """)
        
        result = msg_box.exec_()
        
        if result == QMessageBox.AcceptRole:
            self.download_update_with_progress(latest_version)
        else:
            self.setEnabled(True)  # Réactiver l'interface si l'utilisateur refuse
    

    def download_update_with_progress(self, latest_version):
        """Télécharge et installe la mise à jour avec barre de progression"""
        
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal
        
        class UpdateWorker(QThread):
            progress = pyqtSignal(str, int)
            finished = pyqtSignal(bool, str)
            
            def __init__(self, version):
                super().__init__()
                self.version = version
            
            def run(self):
                def progress_callback(message, percent):
                    self.progress.emit(message, percent)
                
                success, message = download_update_optimized(self.version, progress_callback)
                self.finished.emit(success, message)
        
        # Créer la barre de progression
        progress_dialog = QProgressDialog(
            "Préparation du téléchargement...",
            "Annuler",
            0, 100,
            self
        )
        progress_dialog.setWindowTitle("📦 Téléchargement en cours")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        
        # Style de la barre de progression
        progress_dialog.setStyleSheet("""
            QProgressDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0A0A0A, stop: 1 #1A1A1A);
                color: #FFFFFF;
                font-family: 'Inter';
            }
            QProgressBar {
                border: 2px solid #333333;
                border-radius: 8px;
                background-color: #2A2A2A;
                text-align: center;
                color: #FFFFFF;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #00D4FF, stop: 1 #00FF88);
                border-radius: 6px;
            }
        """)
        
        # Créer et démarrer le worker
        self.update_worker = UpdateWorker(latest_version)
        
        def update_progress(message, percent):
            progress_dialog.setLabelText(message)
            progress_dialog.setValue(percent)
        
        def on_update_finished(success, message):
            progress_dialog.close()
            
            if success:
                QMessageBox.information(
                    self,
                    "✅ Mise à jour réussie",
                    f"{message}\n\nL'application va redémarrer maintenant."
                )
                # Redémarrer l'application
                import subprocess
                import sys
                subprocess.Popen([sys.executable] + sys.argv)
                QApplication.quit()
            else:
                QMessageBox.critical(
                    self,
                    "❌ Échec de la mise à jour",
                    f"Erreur: {message}\n\nVeuillez réessayer plus tard."
                )
                self.setEnabled(True)
        
        self.update_worker.progress.connect(update_progress)
        self.update_worker.finished.connect(on_update_finished)
        self.update_worker.start()
        
        progress_dialog.show()
    
    def show_changelog(self):
        """Ouvrir la fenêtre changelog"""
        changelog_dialog = ChangelogDialog()
        changelog_dialog.exec_()

    def update_countdown_display(self):
        """Met à jour l'affichage du countdown toutes les secondes"""
        
        try:
            remaining_seconds = int(self.next_check_time - time.time())




            







            if remaining_seconds <= 0:







                self.countdown_label.setText("⏱️ Vérification en cours...")







                return







            







            minutes = remaining_seconds // 60







            seconds = remaining_seconds % 60







            







            self.countdown_label.setText(f"⏱️ Prochaine vérification dans: {minutes:02d}:{seconds:02d}")







        except Exception:







            # En cas d'erreur, afficher un message par défaut







            self.countdown_label.setText("⏱️ Prochaine vérification dans: --:--")















    def download_update(self):
        """Télécharge et installe automatiquement la mise à jour"""
        try:
            global BEST_UPDATE_URL
            
            # URLs de téléchargement multiples pour robustesse
            download_urls = [
                UPDATE_SCRIPT_URL,
                UPDATE_SCRIPT_URL.replace("raw.githubusercontent.com", "cdn.jsdelivr.net/gh").replace("/main/", "@main/"),
                UPDATE_SCRIPT_URL.replace("raw.githubusercontent.com", "cdn.statically.io/gh").replace("/main/", "/main/"),
                UPDATE_SCRIPT_URL.replace("raw.githubusercontent.com", "gitcdn.xyz/repo").replace("/main/", "/main/"),
            ]
            
            if BEST_UPDATE_URL and BEST_UPDATE_URL not in download_urls:
                download_urls.insert(0, BEST_UPDATE_URL)
            
            self.log_widget.append("=" * 60)
            
            self.log_widget.append("🚀 TÉLÉCHARGEMENT DE LA MISE À JOUR")
            self.log_widget.append("=" * 60)
            self.log_widget.append(f"[MAJ] Version actuelle: {VERSION}")
            
            # Désactiver l'interface pendant le téléchargement
            
            
            self.log_widget.append("=" * 50)
            
            self.log_widget.append("🚀 DÉBUT DE LA MISE À JOUR")
            
            self.log_widget.append("=" * 50)
            
            self.log_widget.append(f"[MAJ] Version actuelle: {VERSION}")
            
            # Désactiver le bouton pendant le téléchargement
            
            


            self.update_btn.setEnabled(False)







            self.update_btn.setText("⬇️ Téléchargement...")







            







            # Essayer chaque URL jusqu'à ce qu'une fonctionne







            script_content = None







            successful_url = None







            







            for url in download_urls:







                try:







                    self.log_widget.append(f"[MAJ] Tentative: {url}")







                    r = requests.get(url, timeout=15)







                    r.raise_for_status()







                    







                    if len(r.text) > 1000:  # Vérifier que c'est un vrai script







                        script_content = r.text







                        successful_url = url







                        self.log_widget.append(f"[MAJ] ✅ Téléchargement réussi depuis: {url}")







                        break







                    else:







                        self.log_widget.append(f"[MAJ] ⚠️ Fichier trop petit: {len(r.text)} caractères")







                        







                except Exception as e:







                    self.log_widget.append(f"[MAJ] ❌ Échec: {e}")







                    continue







            







            if not script_content:







                raise Exception("Impossible de télécharger depuis aucune URL")







            







            self.log_widget.append(f"[MAJ] Téléchargement réussi (taille: {len(script_content)} caractères)")







            self.log_widget.append(f"[MAJ] Source: {successful_url}")







            







            script_path = os.path.abspath(sys.argv[0])







            self.log_widget.append(f"[MAJ] Chemin du script: {script_path}")







            







            # Vérifier les permissions d'écriture







            script_dir = os.path.dirname(script_path)







            if not os.access(script_dir, os.W_OK):







                raise Exception(f"Pas de permission d'écriture dans: {script_dir}")







            







            if os.path.exists(script_path) and not os.access(script_path, os.W_OK):







                raise Exception(f"Pas de permission d'écriture sur: {script_path}")







            







            # Écrire le nouveau fichier directement (sans sauvegarde)







            with open(script_path, "w", encoding="utf-8") as f:







                f.write(script_content)







            







            self.log_widget.append("[MAJ] ✅ Nouveau script écrit avec succès")







            self.log_widget.append("[MAJ] 🔄 Redémarrage de l'application...")







            







            QMessageBox.information(self, "Mise à jour réussie",







                                    "✅ Nouvelle version installée avec succès !\n\n"







                                    "L'application va redémarrer automatiquement.")







            







            # Redémarrer l'application







            python = sys.executable







            os.execl(python, python, *sys.argv)







            







        except PermissionError as e:







            error_msg = f"Permission refusée: {e}\n\nEssayez de:\n1. Fermer l'antivirus temporairement\n2. Exécuter en tant qu'administrateur\n3. Déplacer l'application dans un autre dossier"







            self.log_widget.append(f"[MAJ] ❌ {error_msg}")







            QMessageBox.critical(self, "Erreur de permissions", error_msg)







        except requests.exceptions.Timeout:







            error_msg = "Timeout lors du téléchargement - Réessayez plus tard"







            self.log_widget.append(f"[MAJ] ❌ {error_msg}")







            QMessageBox.warning(self, "Erreur de téléchargement", error_msg)







        except requests.exceptions.ConnectionError:







            error_msg = "Pas de connexion internet - Vérifiez votre connexion"







            self.log_widget.append(f"[MAJ] ❌ {error_msg}")







            QMessageBox.warning(self, "Erreur de connexion", error_msg)







        except Exception as e:







            error_msg = f"Erreur lors de la mise à jour: {e}"







            self.log_widget.append(f"[MAJ] ❌ {error_msg}")







            if "permission" in str(e).lower():







                QMessageBox.critical(self, "Erreur de permissions", 







                                   f"{error_msg}\n\nEssayez d'exécuter en tant qu'administrateur.")







            else:







                QMessageBox.warning(self, "Erreur de mise à jour", error_msg)







        finally:







            # Réactiver le bouton en cas d'erreur







            self.update_btn.setEnabled(True)







            self.update_btn.setText("⬇️ Télécharger mise à jour")















    def debug_github(self):







        """Debug complet de la connexion GitHub avec test de cache"""







        self.log_widget.append("=" * 70)







        self.log_widget.append("🐛 DEBUG GITHUB COMPLET + TEST CACHE")







        self.log_widget.append("=" * 70)







        







        try:







            import time







            import random







            







            # Test 1: Connexion de base







            self.log_widget.append("📡 TEST 1: Connexion de base")







            headers = {







                'Cache-Control': 'no-cache, no-store, must-revalidate',







                'Pragma': 'no-cache',







                'Expires': '0',







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







            







            # Test 2: URLs alternatives pour contourner le cache







            self.log_widget.append("\n📡 TEST 2: URLs alternatives anti-cache")







            







            timestamp = int(time.time() * 1000000)







            random_hash = random.randint(100000, 999999)







            







            alternative_urls = [







                UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "cdn.jsdelivr.net/gh").replace("/main/", "@main/"),







                UPDATE_CHECK_URL.replace("raw.githubusercontent.com", "cdn.statically.io/gh").replace("/main/", "/main/"),







                f"{UPDATE_CHECK_URL}?cache_bust={timestamp}&random={random_hash}",







                f"{UPDATE_CHECK_URL}?t={timestamp}&force=1"







            ]







            







            for i, url in enumerate(alternative_urls):







                try:







                    self.log_widget.append(f"\n🔄 Test URL {i+1}: {url}")







                    r = requests.get(url, timeout=10, headers=headers)







                    if r.status_code == 200:







                        content = r.text.strip().replace('\ufeff', '').replace('\r', '').replace('\n', '')







                        self.log_widget.append(f"✅ Succès: '{content}'")







                    else:







                        self.log_widget.append(f"❌ Erreur: {r.status_code}")







                except Exception as e:







                    self.log_widget.append(f"❌ Exception: {e}")







                







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

                    

                    # Forcer l'installation de la mise à jour

                    self.force_update_installation(test_version)















                    















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















                f"{UPDATE_CHECK_URL}?hash={abs(hash(str(time.time())))}&force=1",















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















                    r = requests.get(url, timeout=10, headers=headers)















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

                        

                        # Forcer l'installation de la mise à jour

                        self.force_update_installation(most_common_version)















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















                        r = requests.get(url, timeout=8, headers=headers)















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

                        

                        # Forcer l'installation de la mise à jour

                        self.force_update_installation(most_common_version)







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







            r = requests.get(UPDATE_CHECK_URL, timeout=10)







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



        # Authentification obligatoire au démarrage



        if require_authentication():



            # L'application QApplication est déjà créée dans require_authentication()



            app = QApplication.instance()



            if app is None:



                app = QApplication(sys.argv)



            



            window = VMTPathRenamer()



            window.show()



            app.exec_()




        else:




            print("Authentification échouée. Application fermée.")



    except Exception as e:



        log_crash(str(e))



        print(f"Erreur au lancement : {e}")



        input("Appuyez sur Entrée pour quitter...")
