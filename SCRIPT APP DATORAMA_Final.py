import sys
import os
import socket
import ipaddress
import subprocess
import re
import json
import requests
import shutil
import copy
import time
import base64
import hashlib
import functools
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                            QMessageBox, QPushButton, QLabel, QHBoxLayout, 
                            QGridLayout, QFrame, QScrollArea, QSplashScreen,
                            QFileDialog, QProgressBar, QStatusBar, QDialog,
                            QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
                            QListWidget, QCheckBox, QGroupBox, QTabWidget, 
                            QLineEdit, QListWidgetItem, QInputDialog)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEngineDownloadItem
from PyQt5.QtCore import QUrl, Qt, QTimer, pyqtSignal, QDir
from PyQt5.QtGui import QFont, QIcon, QCursor, QPixmap

# Importar librería de cifrado
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    ENCRYPTION_AVAILABLE = True
except ImportError:
    print("⚠️ ADVERTENCIA: Librería 'cryptography' no encontrada. Las URLs no podrán ser cifradas/descifradas.")
    print("   Instale con: pip install cryptography")
    ENCRYPTION_AVAILABLE = False

# Configuración de archivos y rutas
CONFIG_FILE = "dashboard_config.json"

# Configuración para el servidor remoto - URL de GitHub implementada
CONFIG_URL = "https://raw.githubusercontent.com/ingeamoreno/datorama-config/refs/heads/main/dashboard_config.json"
REMOTE_CONFIG_ENABLED = True  # Siempre habilitado
REMOTE_TIMEOUT = 10  # Timeout para conexiones
MAX_RETRY_ATTEMPTS = 3  # Número de intentos para cargar la configuración remota
RETRY_DELAY = 2  # Segundos entre intentos

# Configuración de cifrado
ENCRYPTION_SECRET = "WMT_DTR_2025_SECURE_KEY_v1.0_PROD_ENV_ENCRYPTED_URLS"
ENCRYPTION_SALT = b"WMT_DATORAMA_SALT_2025"  # Salt fijo para consistencia

# Configuración de proxy corporativo
CORPORATE_PROXY = "http://sysproxy.wal-mart.com:8080"
CORPORATE_NETWORK_INDICATORS = [
    "wal-mart.com",
    "walmart.com", 
    "walgreens.com",
    "sysproxy.wal-mart.com"
]

# Configuración para GitHub API
GITHUB_OWNER = "ingeamoreno"
GITHUB_REPO = "datorama-config"
GITHUB_BRANCH = "main"
GITHUB_FILE_PATH = "dashboard_config.json"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

# Configuración para la verificación automática
AUTO_UPDATE_CHECK = True
AUTO_UPDATE_INTERVAL = 1  # Verificación cada hora
LAST_UPDATE_CHECK_FILE = "last_update_check.txt"

# Configuración para verificación periódica de usuarios
PERIODIC_USER_CHECK = True  # Habilitar verificación periódica
USER_CHECK_INTERVAL = 15  # Verificar cada 15 minutos
USER_CHECK_TIMEOUT = 5  # Timeout más corto para verificación en segundo plano

# Variables globales para manejo de proxy
_current_session = None
_is_corporate_network = None

# Variables globales para cifrado
_cipher_suite = None

def resource_path(relative_path):
    """ Obtiene la ruta absoluta a un recurso, funciona tanto para desarrollo como para el archivo compilado """
    try:
        # PyInstaller crea una carpeta temporal y almacena la ruta en _MEIPASS
        base_path = sys._MEIPASS
        print(f"Usando ruta PyInstaller: {base_path}")
    except Exception:
        # En desarrollo, usar el directorio del SCRIPT, no el directorio actual
        base_path = os.path.dirname(os.path.abspath(__file__))
        print(f"Usando ruta del script: {base_path}")

    full_path = os.path.join(base_path, relative_path)
    print(f"Buscando recurso: {relative_path} en: {full_path} (¿existe?: {os.path.exists(full_path)})")
    
    # Si no se encuentra, intentar en el directorio actual como fallback
    if not os.path.exists(full_path):
        fallback_path = os.path.join(os.path.abspath("."), relative_path)
        print(f"Intentando ruta alternativa: {fallback_path} (¿existe?: {os.path.exists(fallback_path)})")
        if os.path.exists(fallback_path):
            return fallback_path
    
    return full_path

# ============================================================================
# CLASE PARA MANEJO DE DESCARGAS (NUEVA FUNCIONALIDAD INTEGRADA)
# ============================================================================

class DownloadManager:
    """
    Manejador de descargas para QWebEngineView
    Esta clase se encarga de interceptar y manejar todas las solicitudes de descarga
    """
    def __init__(self, parent=None):
        self.parent = parent
        self.downloads = {}
        self.progress_bars = {}
        
    def setup_download_handler(self, web_view):
        """Configura el manejador de descargas para un QWebEngineView específico"""
        # Obtener el perfil del navegador
        profile = web_view.page().profile()
        
        # Conectar la señal de descarga con nuestro manejador
        profile.downloadRequested.connect(self.handle_download_request)
        print(f"🔽 Manejador de descargas configurado para ventana")
    
    def handle_download_request(self, download_item):
        """Maneja una solicitud de descarga"""
        # Obtener el nombre sugerido del archivo
        suggested_filename = download_item.suggestedFileName()
        
        # Determinar la carpeta de descargas predeterminada
        default_path = QDir.homePath() + "/Downloads/" + suggested_filename
        
        print(f"📥 Solicitud de descarga interceptada: {suggested_filename}")
        
        # Solicitar al usuario que elija dónde guardar el archivo
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Guardar archivo",
            default_path,
            "Todos los archivos (*.*)"
        )
        
        # Si el usuario canceló la selección, cancelar la descarga
        if not file_path:
            download_item.cancel()
            print("❌ Descarga cancelada por el usuario")
            return
        
        # Configurar la ruta de destino
        download_item.setPath(file_path)
        
        # Asegurar que existe una barra de estado en la ventana principal
        if not hasattr(self.parent, 'statusBar') or self.parent.statusBar() is None:
            self.parent.setStatusBar(QStatusBar())
        
        # Crear una barra de progreso en la barra de estado
        progress_bar = QProgressBar()
        progress_bar.setMaximumHeight(15)
        progress_bar.setMaximumWidth(200)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("%p% - " + os.path.basename(file_path))
        
        # Guardar referencia a la barra de progreso usando el ID de la descarga
        download_id = id(download_item)
        self.progress_bars[download_id] = progress_bar
        
        # Añadir la barra de progreso a la barra de estado
        self.parent.statusBar().addWidget(progress_bar)
        
        # Conectar la señal de progreso
        download_item.downloadProgress.connect(
            lambda received, total: self.update_progress(download_id, received, total)
        )
        
        # Iniciar la descarga
        download_item.accept()
        print(f"✅ Descarga iniciada: {file_path}")
        
        # Conectar señales para rastrear la finalización y errores
        download_item.finished.connect(lambda: self.download_finished(file_path, download_id))
        
        # Mostrar mensaje de inicio de descarga
        QMessageBox.information(
            self.parent,
            "Descarga iniciada",
            f"La descarga de {os.path.basename(file_path)} ha comenzado.\n"
            f"El archivo se guardará en: {file_path}\n\n"
            f"Puedes ver el progreso en la barra de estado."
        )
    
    def update_progress(self, download_id, received, total):
        """Actualiza la barra de progreso para una descarga"""
        if download_id in self.progress_bars and total > 0:
            progress = int(received * 100 / total)
            self.progress_bars[download_id].setValue(progress)
    
    def download_finished(self, file_path, download_id):
        """Maneja la finalización de una descarga"""
        print(f"🎉 Descarga completada: {file_path}")
        
        # Mostrar mensaje de finalización
        QMessageBox.information(
            self.parent,
            "Descarga completada",
            f"La descarga se ha completado exitosamente.\n"
            f"Archivo guardado en: {file_path}"
        )
        
        # Eliminar la barra de progreso de la barra de estado
        if download_id in self.progress_bars:
            self.parent.statusBar().removeWidget(self.progress_bars[download_id])
            del self.progress_bars[download_id]

# ============================================================================
# FUNCIONES DE CIFRADO Y CONFIGURACIÓN (SIN CAMBIOS)
# ============================================================================

def get_encryption_key():
    """
    Genera una clave de cifrado consistente basada en la clave secreta
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=ENCRYPTION_SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(ENCRYPTION_SECRET.encode()))
    return key

def get_cipher_suite():
    """
    Obtiene o crea el conjunto de cifrado Fernet
    """
    global _cipher_suite
    
    if not ENCRYPTION_AVAILABLE:
        return None
        
    if _cipher_suite is None:
        try:
            key = get_encryption_key()
            _cipher_suite = Fernet(key)
            print("🔐 Sistema de cifrado inicializado correctamente")
        except Exception as e:
            print(f"❌ Error al inicializar cifrado: {e}")
            _cipher_suite = None
    
    return _cipher_suite

def encrypt_url(url):
    """
    Cifra una URL usando Fernet
    Retorna la URL cifrada en base64 o la URL original si hay error
    """
    if not ENCRYPTION_AVAILABLE or not url:
        return url
    
    try:
        cipher_suite = get_cipher_suite()
        if cipher_suite is None:
            return url
            
        # Cifrar la URL
        encrypted_url = cipher_suite.encrypt(url.encode('utf-8'))
        # Convertir a base64 para almacenamiento JSON seguro
        encrypted_b64 = base64.b64encode(encrypted_url).decode('utf-8')
        
        print(f"🔒 URL cifrada: {url[:50]}...")
        return encrypted_b64
        
    except Exception as e:
        print(f"❌ Error al cifrar URL: {e}")
        return url

def decrypt_url(encrypted_url):
    """
    Descifra una URL cifrada
    Retorna la URL original o la URL sin cambios si hay error o no está cifrada
    """
    if not ENCRYPTION_AVAILABLE or not encrypted_url:
        return encrypted_url
    
    # Si la URL parece ser una URL normal (contiene http), no intentar descifrar
    if encrypted_url.startswith(('http://', 'https://')):
        return encrypted_url
    
    try:
        cipher_suite = get_cipher_suite()
        if cipher_suite is None:
            return encrypted_url
            
        # Decodificar de base64
        encrypted_bytes = base64.b64decode(encrypted_url.encode('utf-8'))
        # Descifrar
        decrypted_url = cipher_suite.decrypt(encrypted_bytes).decode('utf-8')
        
        print(f"🔓 URL descifrada correctamente")
        return decrypted_url
        
    except Exception as e:
        print(f"⚠️ Error al descifrar URL (posiblemente no cifrada): {e}")
        return encrypted_url

def encrypt_dashboard_urls(config):
    """
    Cifra todas las URLs en la configuración de dashboards
    Retorna una copia de la configuración con URLs cifradas
    """
    if not ENCRYPTION_AVAILABLE:
        print("⚠️ Cifrado no disponible, configuración sin cambios")
        return config
    
    encrypted_config = copy.deepcopy(config)
    
    if 'dashboards' in encrypted_config:
        for name, url in encrypted_config['dashboards'].items():
            encrypted_config['dashboards'][name] = encrypt_url(url)
    
    # Marcar como cifrado
    encrypted_config['encrypted'] = True
    encrypted_config['encryption_version'] = "1.0"
    
    print(f"🔒 Configuración cifrada: {len(encrypted_config.get('dashboards', {}))} URLs procesadas")
    return encrypted_config

def decrypt_dashboard_urls(config):
    """
    Descifra todas las URLs en la configuración de dashboards
    Retorna una copia de la configuración con URLs descifradas
    """
    if not ENCRYPTION_AVAILABLE:
        return config
    
    # Si no está marcada como cifrada, retornar sin cambios
    if not config.get('encrypted', False):
        print("📖 Configuración no cifrada, no se requiere descifrado")
        return config
    
    decrypted_config = copy.deepcopy(config)
    
    if 'dashboards' in decrypted_config:
        for name, encrypted_url in decrypted_config['dashboards'].items():
            decrypted_config['dashboards'][name] = decrypt_url(encrypted_url)
    
    print(f"🔓 Configuración descifrada: {len(decrypted_config.get('dashboards', {}))} URLs procesadas")
    return decrypted_config

# ============================================================================
# FUNCIONES DE RED Y CONECTIVIDAD (SIN CAMBIOS)
# ============================================================================

def detect_corporate_network():
    """
    Detecta si estamos ejecutándose en la red corporativa de Walmart
    """
    global _is_corporate_network
    
    if _is_corporate_network is not None:
        return _is_corporate_network
    
    print("🔍 Detectando entorno de red...")
    
    try:
        # Método 1: Verificar variables de entorno de proxy
        for env_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            proxy_url = os.environ.get(env_var, '')
            if any(indicator in proxy_url.lower() for indicator in CORPORATE_NETWORK_INDICATORS):
                print(f"✅ Red corporativa detectada via variable de entorno: {env_var}={proxy_url}")
                _is_corporate_network = True
                return True
        
        # Método 2: Verificar nombre del dominio del equipo
        try:
            hostname = socket.getfqdn()
            if any(indicator in hostname.lower() for indicator in CORPORATE_NETWORK_INDICATORS):
                print(f"✅ Red corporativa detectada via hostname: {hostname}")
                _is_corporate_network = True
                return True
        except Exception as e:
            print(f"⚠️ Error al obtener hostname: {e}")
        
        # Método 3: Verificar conectividad directa vs proxy
        test_url = "https://api.github.com"
        
        # Probar sin proxy primero
        try:
            print("🌐 Probando conectividad directa...")
            response = requests.get(test_url, timeout=3, proxies={'http': '', 'https': ''})
            if response.status_code == 200:
                print("✅ Conectividad directa exitosa - Red externa")
                _is_corporate_network = False
                return False
        except Exception as e:
            print(f"❌ Conectividad directa falló: {e}")
        
        # Probar con proxy corporativo
        try:
            print("🏢 Probando conectividad con proxy corporativo...")
            proxies = {
                'http': CORPORATE_PROXY,
                'https': CORPORATE_PROXY
            }
            response = requests.get(test_url, timeout=5, proxies=proxies)
            if response.status_code == 200:
                print("✅ Conectividad con proxy exitosa - Red corporativa")
                _is_corporate_network = True
                return True
        except Exception as e:
            print(f"❌ Conectividad con proxy falló: {e}")
        
        # Si ningún método funciona, asumir red externa
        print("⚠️ No se pudo determinar el tipo de red, asumiendo red externa")
        _is_corporate_network = False
        return False
        
    except Exception as e:
        print(f"❌ Error al detectar red corporativa: {e}")
        _is_corporate_network = False
        return False

def configure_proxy_environment():
    """
    Configura las variables de entorno del proxy si estamos en red corporativa
    """
    if detect_corporate_network():
        print(f"🔧 Configurando proxy corporativo: {CORPORATE_PROXY}")
        os.environ['HTTP_PROXY'] = CORPORATE_PROXY
        os.environ['HTTPS_PROXY'] = CORPORATE_PROXY
        os.environ['http_proxy'] = CORPORATE_PROXY
        os.environ['https_proxy'] = CORPORATE_PROXY
        return True
    else:
        print("🌐 Red externa detectada, sin proxy necesario")
        # Limpiar variables de proxy si existen
        for env_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            if env_var in os.environ:
                del os.environ[env_var]
        return False

def get_requests_session():
    """
    Obtiene una sesión de requests configurada apropiadamente para el entorno actual
    """
    global _current_session
    
    if _current_session is None:
        _current_session = requests.Session()
        
        # Configurar headers comunes
        _current_session.headers.update({
            'User-Agent': 'DatoramaDashboard/1.0',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        # Configurar proxy si estamos en red corporativa
        if detect_corporate_network():
            print(f"🔧 Configurando sesión con proxy: {CORPORATE_PROXY}")
            _current_session.proxies.update({
                'http': CORPORATE_PROXY,
                'https': CORPORATE_PROXY
            })
        else:
            print("🌐 Configurando sesión sin proxy")
            _current_session.proxies.clear()
    
    return _current_session

def test_connectivity():
    """
    Prueba la conectividad con GitHub usando la configuración actual
    """
    try:
        print("🧪 Probando conectividad con GitHub...")
        session = get_requests_session()
        
        # Probar conectividad básica
        response = session.get("https://api.github.com", timeout=10)
        if response.status_code == 200:
            print("✅ Conectividad básica con GitHub: OK")
            
            # Probar acceso al repositorio específico
            response = session.get(CONFIG_URL, timeout=10)
            if response.status_code == 200:
                print("✅ Acceso al repositorio de configuración: OK")
                return True
            else:
                print(f"❌ Error al acceder al repositorio: {response.status_code}")
                return False
        else:
            print(f"❌ Error de conectividad básica: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error en prueba de conectividad: {e}")
        return False

def get_current_username():
    """
    Obtiene el nombre de usuario actual del sistema
    """
    try:
        return os.getlogin()
    except Exception:
        try:
            import getpass
            return getpass.getuser()
        except Exception:
            return None

# ============================================================================
# FUNCIONES DE CONFIGURACIÓN Y CARGA (SIN CAMBIOS)
# ============================================================================

def load_config():
    """
    Carga la configuración desde GitHub primero, luego local como fallback
    Retorna un diccionario con la configuración (URLs descifradas para uso)
    """
    # Configurar proxy antes de hacer cualquier petición
    configure_proxy_environment()
    
    config = {
        "dashboards": {},
        "authorized_users": [],
        "admin_users": [],
        "version": "1.0.0",
        "last_updated": "",
        "require_corporate_network": False,
        "changelog": [],
        "using_local_config": False,
        "encrypted": False
    }
    
    # Registrar el intento de carga de configuración
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando carga de configuración desde GitHub")
    
    # Mostrar información del entorno
    if detect_corporate_network():
        print(f"🏢 Entorno: Red corporativa (usando proxy: {CORPORATE_PROXY})")
    else:
        print("🌐 Entorno: Red externa (conexión directa)")
    
    try:
        # PRIORIDAD: Siempre intentar cargar desde GitHub primero
        remote_loaded = False
        if CONFIG_URL:
            retry_count = 0
            while retry_count < MAX_RETRY_ATTEMPTS and not remote_loaded:
                try:
                    print(f"Intento {retry_count + 1}/{MAX_RETRY_ATTEMPTS} de cargar desde GitHub...")
                    
                    # Usar la sesión configurada con proxy si es necesario
                    session = get_requests_session()
                    response = session.get(CONFIG_URL, timeout=REMOTE_TIMEOUT)
                    
                    if response.status_code == 200:
                        remote_config = response.json()
                        
                        # Descifrar URLs si la configuración está cifrada
                        if remote_config.get('encrypted', False):
                            print("🔐 Configuración cifrada detectada, descifrando URLs...")
                            remote_config = decrypt_dashboard_urls(remote_config)
                        
                        config.update(remote_config)
                        config['using_local_config'] = False
                        
                        encryption_status = "🔐 CIFRADA" if remote_config.get('encrypted', False) else "📖 No cifrada"
                        print(f"✅ Configuración cargada desde GitHub - Versión: {config.get('version', 'N/A')} ({encryption_status})")
                        print(f"   📊 Usuarios autorizados: {len(config.get('authorized_users', []))}")
                        print(f"   🔑 Administradores: {len(config.get('admin_users', []))}")
                        print(f"   🎛️ Dashboards: {len(config.get('dashboards', {}))}")
                        
                        # Guardar copia local para uso offline (manteniendo cifrado si es necesario)
                        try:
                            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                                json.dump(remote_config, f, indent=4, ensure_ascii=False)
                            print(f"   💾 Copia local guardada en: {CONFIG_FILE}")
                        except Exception as e:
                            print(f"   ⚠️ No se pudo guardar copia local: {e}")
                        
                        remote_loaded = True
                        
                    else:
                        print(f"   ❌ Error HTTP {response.status_code} desde GitHub")
                        retry_count += 1
                        
                except requests.exceptions.Timeout:
                    print(f"   ⏰ Timeout al conectar con GitHub")
                    retry_count += 1
                except requests.exceptions.ConnectionError as e:
                    print(f"   🌐 Error de conexión con GitHub: {e}")
                    retry_count += 1
                except requests.exceptions.ProxyError as e:
                    print(f"   🔄 Error de proxy: {e}")
                    retry_count += 1
                except Exception as e:
                    print(f"   ❌ Error inesperado: {e}")
                    retry_count += 1
                
                # Esperar antes del siguiente intento
                if retry_count < MAX_RETRY_ATTEMPTS and not remote_loaded:
                    print(f"   ⏳ Esperando {RETRY_DELAY} segundos antes del siguiente intento...")
                    time.sleep(RETRY_DELAY)
        
        # FALLBACK: Si GitHub falla, usar configuración local
        if not remote_loaded:
            print(f"⚠️ GitHub no disponible, intentando configuración local...")
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        local_config = json.load(f)
                        
                        # Descifrar URLs si la configuración está cifrada
                        if local_config.get('encrypted', False):
                            print("🔐 Configuración local cifrada detectada, descifrando URLs...")
                            local_config = decrypt_dashboard_urls(local_config)
                        
                        config.update(local_config)
                        config['using_local_config'] = True
                        
                    encryption_status = "🔐 CIFRADA" if local_config.get('encrypted', False) else "📖 No cifrada"
                    print(f"📁 Configuración local cargada - Versión: {config.get('version', 'N/A')} ({encryption_status})")
                    print(f"   📊 Usuarios autorizados: {len(config.get('authorized_users', []))}")
                    print(f"   🔑 Administradores: {len(config.get('admin_users', []))}")
                    print(f"   ⚠️ ADVERTENCIA: Usando configuración local, podría estar desactualizada")
                    
                except Exception as e:
                    print(f"❌ Error al leer configuración local: {e}")
                    # Usar configuración por defecto
                    print(f"🔧 Usando configuración por defecto")
                    config = create_default_config()
            else:
                print(f"📁 No existe configuración local, creando configuración por defecto")
                config = create_default_config()
        
        # Validar configuración cargada
        validate_config(config)
        
    except Exception as e:
        print(f"❌ Error crítico al cargar configuración: {e}")
        QMessageBox.critical(
            None,
            "Error de Configuración",
            f"Error crítico al cargar la configuración:\n{str(e)}\n\nUsando configuración por defecto."
        )
        config = create_default_config()
    
    # Mostrar resumen final
    print(f"\n📋 CONFIGURACIÓN FINAL:")
    print(f"   Origen: {'📡 GitHub' if not config.get('using_local_config') else '📁 Local'}")
    print(f"   Versión: {config.get('version', 'N/A')}")
    print(f"   Usuarios autorizados: {len(config.get('authorized_users', []))}")
    print(f"   Administradores: {len(config.get('admin_users', []))}")
    print(f"   Cifrado: {'🔐 Sí' if config.get('encrypted', False) else '📖 No'}")
    
    return config

def create_default_config():
    """Crea una configuración por defecto"""
    current_user = get_current_username()
    
    default_config = {
        "dashboards": {
            "Onsite/Offsite": "https://platform-us2.datorama.com/external/dashboard?embedpage=bab9f8f9-6567-4383-a166-b867db0f46dc",
            "Display Onsite Attribution": "https://platform-us2.datorama.com/external/dashboard?embedpage=f06ec4c2-c795-4c3b-a0b8-bfdc1883d6be"
        },
        "authorized_users": [
            "m0b0xkx", "l0p08ai", "a0r0xe9", "j0r14n8", "m0g0tiz"
        ],
        "admin_users": ["m0g0tiz"],
        "version": "1.0.0",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "require_corporate_network": False,
        "changelog": [
            {
                "version": "1.0.0",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "author": "Sistema",
                "changes": ["Configuración por defecto creada automáticamente"]
            }
        ],
        "using_local_config": True,
        "encrypted": False
    }
    
    # Agregar usuario actual si no está en la lista
    if current_user and current_user.lower() not in [u.lower() for u in default_config["authorized_users"]]:
        default_config["authorized_users"].append(current_user)
        print(f"   👤 Usuario actual '{current_user}' agregado a configuración por defecto")
    
    # Guardar configuración por defecto
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"   💾 Configuración por defecto guardada en: {CONFIG_FILE}")
    except Exception as e:
        print(f"   ⚠️ No se pudo guardar configuración por defecto: {e}")
    
    return default_config

def validate_config(config):
    """Valida que la configuración tenga la estructura correcta"""
    required_fields = ['dashboards', 'authorized_users', 'admin_users', 'version']
    
    for field in required_fields:
        if field not in config:
            print(f"⚠️ Campo faltante en configuración: {field}")
            if field == 'dashboards':
                config[field] = {}
            elif field in ['authorized_users', 'admin_users']:
                config[field] = []
            elif field == 'version':
                config[field] = '1.0.0'
    
    # Asegurar que hay al menos un administrador
    if not config.get('admin_users'):
        if config.get('authorized_users'):
            config['admin_users'] = [config['authorized_users'][0]]
            print(f"   🔧 Administrador por defecto: {config['admin_users'][0]}")
        else:
            config['admin_users'] = ['admin']
            print(f"   🔧 Administrador genérico creado")

def is_authorized_user(username, authorized_users):
    """
    Verifica si el usuario está en la lista de usuarios autorizados
    """
    if not username or not authorized_users:
        return False
    # Convertir a minúsculas para evitar problemas de mayúsculas/minúsculas
    return username.lower() in [user.lower() for user in authorized_users]

def is_admin_user(username, admin_users):
    """
    Verifica si el usuario tiene privilegios de administrador
    """
    if not username or not admin_users:
        return False
    # Convertir a minúsculas para evitar problemas de mayúsculas/minúsculas
    return username.lower() in [user.lower() for user in admin_users]

# ============================================================================
# FUNCIONES PARA GITHUB API (SIN CAMBIOS)
# ============================================================================

def get_github_token():
    """
    Obtiene el token de GitHub desde un archivo local o variable de entorno
    """
    # Opción 1: Desde archivo local (más seguro)
    token_file = "github_token.txt"
    if os.path.exists(token_file):
        try:
            with open(token_file, 'r') as f:
                token = f.read().strip()
                if token:
                    return token
        except Exception as e:
            print(f"Error al leer token desde archivo: {e}")
    
    # Opción 2: Desde variable de entorno
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    
    return None

def setup_github_token():
    """
    Configura el token de GitHub por primera vez
    """
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Configuración de GitHub")
    msg.setText("Para publicar automáticamente en GitHub, necesita configurar un token de acceso.")
    msg.setInformativeText(
        "Pasos para obtener un token:\n"
        "1. Vaya a GitHub.com → Settings → Developer settings → Personal access tokens\n"
        "2. Genere un nuevo token con permisos 'repo'\n"
        "3. Copie el token generado\n\n"
        "¿Desea configurar el token ahora?"
    )
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    
    if msg.exec_() == QMessageBox.Yes:
        token, ok = QInputDialog.getText(
            None, 
            "Token de GitHub", 
            "Pegue su token de acceso personal de GitHub:",
            echo=QLineEdit.Password
        )
        
        if ok and token.strip():
            # Guardar token en archivo local
            try:
                with open("github_token.txt", 'w') as f:
                    f.write(token.strip())
                QMessageBox.information(None, "Token Guardado", "Token de GitHub guardado correctamente.")
                return token.strip()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"No se pudo guardar el token: {e}")
    
    return None

def validate_github_token(token):
    """
    Valida que el token de GitHub sea válido y tenga los permisos necesarios
    """
    if not token or len(token.strip()) < 10:
        return False, "Token inválido o muy corto"
    
    try:
        session = get_requests_session()
        session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        # Verificar acceso al repositorio
        repo_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        response = session.get(repo_url, timeout=10)
        
        if response.status_code == 200:
            repo_data = response.json()
            permissions = repo_data.get('permissions', {})
            
            # Verificar permisos de escritura
            if permissions.get('push', False):
                return True, "Token válido con permisos de escritura"
            else:
                return False, "El token no tiene permisos de escritura en el repositorio"
        elif response.status_code == 401:
            return False, "Token inválido o expirado"
        elif response.status_code == 404:
            return False, f"Repositorio {GITHUB_OWNER}/{GITHUB_REPO} no encontrado o sin acceso"
        else:
            return False, f"Error al validar token: {response.status_code}"
            
    except Exception as e:
        return False, f"Error de conexión al validar token: {str(e)}"

def publish_to_github_api(config_data):
    """
    Publica la configuración en GitHub usando la API
    IMPORTANTE: Cifra las URLs antes de publicar
    """
    token = get_github_token()
    
    if not token:
        token = setup_github_token()
        if not token:
            return False, "Token de GitHub no configurado"
    
    # Validar el token antes de usarlo
    is_valid, validation_message = validate_github_token(token)
    if not is_valid:
        return False, f"Token no válido: {validation_message}"
    
    try:
        # IMPORTANTE: Cifrar las URLs antes de publicar
        print("🔐 Cifrando configuración antes de publicar...")
        encrypted_config = encrypt_dashboard_urls(config_data)
        
        # Usar la sesión configurada con proxy
        session = get_requests_session()
        session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        })
        
        # 1. Obtener información actual del archivo (para el SHA)
        print("Obteniendo información del archivo actual...")
        response = session.get(GITHUB_API_URL, timeout=10)
        
        current_sha = None
        if response.status_code == 200:
            current_file = response.json()
            current_sha = current_file['sha']
            print(f"SHA actual del archivo: {current_sha}")
        elif response.status_code == 404:
            print("El archivo no existe, se creará nuevo")
        else:
            error_msg = f"Error al obtener información del archivo: {response.status_code}"
            try:
                error_details = response.json()
                if 'message' in error_details:
                    error_msg += f" - {error_details['message']}"
            except:
                pass
            return False, error_msg
        
        # 2. Preparar el contenido (configuración cifrada)
        json_content = json.dumps(encrypted_config, indent=4, ensure_ascii=False)
        encoded_content = base64.b64encode(json_content.encode('utf-8')).decode('utf-8')
        
        # 3. Preparar el commit
        version = config_data.get("version", "1.0.0")
        commit_message = f'Actualización automática de configuración cifrada - v{version}\n\nActualizado desde la aplicación de administración'
        
        commit_data = {
            'message': commit_message,
            'content': encoded_content,
            'branch': GITHUB_BRANCH
        }
        
        # Incluir SHA si el archivo existe
        if current_sha:
            commit_data['sha'] = current_sha
        
        # 4. Hacer el commit
        print("Publicando configuración cifrada en GitHub...")
        response = session.put(GITHUB_API_URL, json=commit_data, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json()
            commit_url = result['commit']['html_url'] if 'commit' in result else "N/A"
            print(f"✅ Publicado correctamente: {result['commit']['message']}")
            return True, f"Configuración cifrada publicada exitosamente en GitHub\nCommit: {commit_url}"
        else:
            error_msg = f"Error al publicar: {response.status_code}"
            try:
                error_details = response.json()
                if 'message' in error_details:
                    error_msg += f" - {error_details['message']}"
                if 'errors' in error_details:
                    for error in error_details['errors']:
                        error_msg += f"\n  • {error.get('message', str(error))}"
            except:
                error_msg += f"\nRespuesta: {response.text[:200]}"
            return False, error_msg
            
    except requests.exceptions.Timeout:
        return False, "Tiempo de espera agotado al conectar con GitHub"
    except requests.exceptions.ConnectionError:
        return False, "Error de conexión con GitHub. Verifique su conexión a internet"
    except requests.exceptions.ProxyError:
        return False, "Error de proxy al conectar con GitHub. Verifique la configuración del proxy"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"

# Función nueva para verificación silenciosa de usuarios
def check_user_authorization_silent(current_user):
    """
    Verifica silenciosamente si el usuario sigue autorizado en GitHub
    Retorna (is_authorized, config) o (None, None) si hay error de conexión
    """
    if not CONFIG_URL or not current_user:
        return None, None
    
    try:
        session = get_requests_session()
        response = session.get(CONFIG_URL, timeout=USER_CHECK_TIMEOUT)
        
        if response.status_code == 200:
            remote_config = response.json()
            
            # Descifrar si es necesario para verificar usuarios
            if remote_config.get('encrypted', False):
                # No necesitamos descifrar URLs para verificar usuarios
                pass
            
            authorized_users = remote_config.get('authorized_users', [])
            is_authorized = is_authorized_user(current_user, authorized_users)
            return is_authorized, remote_config
        else:
            return None, None
            
    except Exception:
        return None, None

# Función para verificar actualizaciones de configuración
def check_remote_updates(current_config):
    """
    Verifica si hay actualizaciones disponibles en el servidor remoto
    Retorna (hay_actualizacion, nueva_config) o (False, None) si no hay actualizaciones
    """
    if not CONFIG_URL:
        return False, None
    
    try:
        print(f"Verificando actualizaciones en: {CONFIG_URL}")
        session = get_requests_session()
        response = session.get(CONFIG_URL, timeout=REMOTE_TIMEOUT)
        
        if response.status_code == 200:
            remote_config = response.json()
            
            # Descifrar si es necesario para comparar versiones
            if remote_config.get('encrypted', False):
                remote_config = decrypt_dashboard_urls(remote_config)
            
            # Comparar versiones
            current_version = current_config.get('version', '1.0.0')
            remote_version = remote_config.get('version', '1.0.0')
            
            if remote_version > current_version:
                print(f"Nueva versión disponible: {remote_version} (actual: {current_version})")
                return True, remote_config
            else:
                print("No hay actualizaciones disponibles")
                return False, None
        else:
            print(f"Error al verificar actualizaciones. Código: {response.status_code}")
            return False, None
            
    except Exception as e:
        print(f"Error al verificar actualizaciones: {e}")
        return False, None

# Función para aplicar actualizaciones
def apply_update(new_config):
    """
    Aplica la nueva configuración, guardando una copia de seguridad de la anterior
    Retorna True si se aplicó correctamente, False en caso contrario
    """
    try:
        # Crear una copia de seguridad
        if os.path.exists(CONFIG_FILE):
            backup_path = f"{CONFIG_FILE}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(CONFIG_FILE, backup_path)
            print(f"Copia de seguridad creada en {backup_path}")
        
        # Guardar la nueva configuración (descifrada para uso local)
        local_config = copy.deepcopy(new_config)
        local_config['encrypted'] = False  # Marcar como no cifrada para uso local
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(local_config, f, indent=4, ensure_ascii=False)
        
        print(f"Configuración actualizada correctamente a la versión {new_config.get('version')}")
        return True
    except Exception as e:
        print(f"Error al aplicar actualización: {e}")
        return False

def get_network_info():
    """
    Obtiene información detallada de la red utilizando ipconfig
    """
    try:
        # Ejecutar ipconfig /all y capturar la salida
        if os.name == 'nt':  # Windows
            result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, encoding='latin-1')
            ipconfig_output = result.stdout
        else:  # Linux/Mac
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            ipconfig_output = result.stdout
            
        return ipconfig_output
    except Exception as e:
        print(f"Error al obtener información de red: {e}")
        return ""

def is_corporate_network(config):
    """
    Verifica si está en la red corporativa basado en la configuración
    """
    # Verificar si la restricción está habilitada en la configuración
    if not config.get('require_corporate_network', False):
        print("La verificación de red corporativa está deshabilitada en la configuración.")
        return True
    
    # Aquí iría tu lógica original para verificar la red corporativa
    # Por ahora, siempre devolvemos True
    return True

def create_encrypted_config_file():
    """
    Función auxiliar para crear un archivo de configuración cifrado
    para que puedas subirlo manualmente a GitHub
    """
    if not ENCRYPTION_AVAILABLE:
        print("❌ Error: Librería 'cryptography' no disponible")
        return None
    
    # Cargar configuración actual
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ Error al leer configuración: {e}")
            return None
    else:
        print("❌ Error: No se encontró archivo de configuración")
        return None
    
    # Cifrar configuración
    encrypted_config = encrypt_dashboard_urls(config)
    
    # Guardar archivo cifrado
    encrypted_filename = "dashboard_config_encrypted.json"
    try:
        with open(encrypted_filename, 'w', encoding='utf-8') as f:
            json.dump(encrypted_config, f, indent=4, ensure_ascii=False)
        
        print(f"✅ Archivo de configuración cifrado creado: {encrypted_filename}")
        print(f"🔐 URLs cifradas: {len(encrypted_config.get('dashboards', {}))}")
        print(f"📤 Suba este archivo a GitHub para reemplazar la configuración actual")
        
        return encrypted_filename
    except Exception as e:
        print(f"❌ Error al guardar archivo cifrado: {e}")
        return None

# ============================================================================
# DIÁLOGOS Y CLASES DE INTERFAZ (SIN CAMBIOS IMPORTANTES)
# ============================================================================

# Diálogo para mostrar el registro de cambios
class ChangelogDialog(QDialog):
    """Diálogo para mostrar el historial de cambios"""
    def __init__(self, changelog_entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historial de cambios")
        self.setMinimumSize(500, 400)
        
        # Layout principal
        layout = QVBoxLayout(self)
        
        # Título
        title_label = QLabel("Historial de cambios")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Contenido del registro de cambios
        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        
        # Generar contenido con formato HTML para mejor presentación
        html_content = "<html><body style='font-family: Arial, sans-serif;'>"
        
        # Ordenar las entradas por versión (más reciente primero)
        sorted_entries = sorted(changelog_entries, key=lambda x: x.get('version', '0.0.0'), reverse=True)
        
        for entry in sorted_entries:
            version = entry.get('version', '?')
            date = entry.get('date', '?')
            author = entry.get('author', '?')
            changes = entry.get('changes', [])
            
            html_content += f"<h3>Versión {version} <span style='font-weight: normal; font-size: 0.8em;'>({date})</span></h3>"
            html_content += f"<p style='margin-top: -10px; color: #666;'>Por: {author}</p>"
            
            if changes:
                html_content += "<ul>"
                for change in changes:
                    html_content += f"<li>{change}</li>"
                html_content += "</ul>"
            else:
                html_content += "<p>No hay detalles disponibles para esta versión.</p>"
            
            html_content += "<hr>"
        
        html_content += "</body></html>"
        changelog_text.setHtml(html_content)
        layout.addWidget(changelog_text)
        
        # Botón de cerrar
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

# Clase ConfigAdminTool - Herramienta de Administración (SIN CAMBIOS)
class ConfigAdminTool(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)  # Crear una copia para trabajar
        self.original_config = copy.deepcopy(config)  # Copia para comparar cambios
        self.setWindowTitle("🔧 Herramienta de Administración")
        self.setMinimumSize(800, 600)
        
        # Intentar establecer el icono
        try:
            icon_path = resource_path("walmart.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Error al establecer icono: {e}")
        
        # Establecer el layout principal
        main_layout = QVBoxLayout(self)
        
        # Banner de cifrado si está disponible
        if ENCRYPTION_AVAILABLE:
            encryption_banner = QLabel("🔐 CIFRADO ACTIVADO - Las URLs se cifran automáticamente antes de publicar")
            encryption_banner.setStyleSheet("""
                background-color: #D4EDDA;
                color: #155724;
                padding: 8px;
                border: 1px solid #C3E6CB;
                border-radius: 4px;
                font-weight: bold;
            """)
            encryption_banner.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(encryption_banner)
        else:
            encryption_warning = QLabel("⚠️ CIFRADO NO DISPONIBLE - Instale 'cryptography' para cifrar URLs")
            encryption_warning.setStyleSheet("""
                background-color: #FFF3CD;
                color: #856404;
                padding: 8px;
                border: 1px solid #FFEAA7;
                border-radius: 4px;
                font-weight: bold;
            """)
            encryption_warning.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(encryption_warning)
        
        # Crear pestañas
        tab_widget = QTabWidget()
        
        # Pestaña: Dashboards
        dashboard_tab = QWidget()
        tab_widget.addTab(dashboard_tab, "📊 Dashboards")
        self._setup_dashboard_tab(dashboard_tab)
        
        # Pestaña: Usuarios
        users_tab = QWidget()
        tab_widget.addTab(users_tab, "👥 Usuarios")
        self._setup_users_tab(users_tab)
        
        # Pestaña: Historial de cambios
        changelog_tab = QWidget()
        tab_widget.addTab(changelog_tab, "📝 Historial")
        self._setup_changelog_tab(changelog_tab)
        
        # Pestaña: Configuración
        settings_tab = QWidget()
        tab_widget.addTab(settings_tab, "⚙️ Configuración")
        self._setup_settings_tab(settings_tab)
        
        main_layout.addWidget(tab_widget)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        
        self.save_button = QPushButton("💾 Guardar Cambios")
        self.save_button.clicked.connect(self.save_changes)
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        
        publish_text = "🚀 Publicar a GitHub (Cifrado)"
        if not ENCRYPTION_AVAILABLE:
            publish_text = "🚀 Publicar a GitHub (Sin cifrar)"
            
        self.publish_button = QPushButton(publish_text)
        self.publish_button.clicked.connect(self.publish_to_github)
        self.publish_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0069d9;
            }
        """)
        
        self.cancel_button = QPushButton("❌ Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.publish_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(buttons_layout)
    
    def _setup_dashboard_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # Lista de dashboards actuales
        self.dashboards_list = QTableWidget()
        self.dashboards_list.setColumnCount(3)
        self.dashboards_list.setHorizontalHeaderLabels(["Nombre", "URL", "Acciones"])
        self.dashboards_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Agregar dashboards a la tabla
        self._refresh_dashboards_list()
        
        layout.addWidget(QLabel("Dashboards configurados:"))
        layout.addWidget(self.dashboards_list)
        
        # Formulario para agregar/editar dashboard
        form_group = QGroupBox("Agregar/Editar Dashboard")
        form_layout = QGridLayout(form_group)
        
        self.dashboard_name_edit = QLineEdit()
        self.dashboard_url_edit = QLineEdit()
        
        form_layout.addWidget(QLabel("Nombre:"), 0, 0)
        form_layout.addWidget(self.dashboard_name_edit, 0, 1)
        form_layout.addWidget(QLabel("URL:"), 1, 0)
        form_layout.addWidget(self.dashboard_url_edit, 1, 1)
        
        # Nota sobre cifrado
        if ENCRYPTION_AVAILABLE:
            encryption_note = QLabel("🔐 Nota: Las URLs se cifrarán automáticamente al publicar")
            encryption_note.setStyleSheet("color: #666; font-style: italic;")
            form_layout.addWidget(encryption_note, 2, 0, 1, 2)
        
        buttons_layout = QHBoxLayout()
        self.add_dashboard_button = QPushButton("➕ Agregar Dashboard")
        self.add_dashboard_button.clicked.connect(self.add_dashboard)
        
        self.update_dashboard_button = QPushButton("✏️ Actualizar Dashboard")
        self.update_dashboard_button.clicked.connect(self.update_dashboard)
        self.update_dashboard_button.setEnabled(False)
        
        self.clear_form_button = QPushButton("🗑️ Limpiar Formulario")
        self.clear_form_button.clicked.connect(self.clear_dashboard_form)
        
        buttons_layout.addWidget(self.add_dashboard_button)
        buttons_layout.addWidget(self.update_dashboard_button)
        buttons_layout.addWidget(self.clear_form_button)
        
        form_layout.addLayout(buttons_layout, 3, 0, 1, 2)
        
        layout.addWidget(form_group)
    
    def _refresh_dashboards_list(self):
        self.dashboards_list.setRowCount(0)
        
        # Añadir dashboards a la tabla
        for row, (name, url) in enumerate(self.config.get('dashboards', {}).items()):
            self.dashboards_list.insertRow(row)
            name_item = QTableWidgetItem(name)
            
            # Mostrar URL truncada para mejor visualización
            display_url = url[:80] + "..." if len(url) > 80 else url
            url_item = QTableWidgetItem(display_url)
            url_item.setToolTip(url)  # Mostrar URL completa en tooltip
            
            self.dashboards_list.setItem(row, 0, name_item)
            self.dashboards_list.setItem(row, 1, url_item)
            
            # Agregar botones de acción
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            
            edit_button = QPushButton("✏️")
            edit_button.setFixedWidth(30)
            edit_button.setToolTip("Editar")
            edit_button.clicked.connect(lambda _, r=row, n=name: self.edit_dashboard(r, n))
            
            delete_button = QPushButton("🗑️")
            delete_button.setFixedWidth(30)
            delete_button.setToolTip("Eliminar")
            delete_button.clicked.connect(lambda _, n=name: self.delete_dashboard(n))
            
            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)
            
            self.dashboards_list.setCellWidget(row, 2, action_widget)
        
        self.dashboards_list.resizeColumnsToContents()
        self.dashboards_list.resizeRowsToContents()
    
    def add_dashboard(self):
        name = self.dashboard_name_edit.text().strip()
        url = self.dashboard_url_edit.text().strip()
        
        if not name or not url:
            QMessageBox.warning(self, "Datos Incompletos", "Por favor ingrese nombre y URL.")
            return
        
        if name in self.config.get('dashboards', {}):
            QMessageBox.warning(self, "Duplicado", f"Ya existe un dashboard con el nombre '{name}'.")
            return
        
        # Añadir a la configuración (URL sin cifrar - se cifrará al publicar)
        if 'dashboards' not in self.config:
            self.config['dashboards'] = {}
        
        self.config['dashboards'][name] = url
        
        # Actualizar la tabla
        self._refresh_dashboards_list()
        
        # Limpiar el formulario
        self.clear_dashboard_form()
        
        QMessageBox.information(self, "Dashboard Agregado", f"Dashboard '{name}' agregado correctamente.")
    
    def edit_dashboard(self, row, name):
        # Cargar datos del dashboard seleccionado en el formulario
        url = self.config['dashboards'][name]
        
        self.dashboard_name_edit.setText(name)
        self.dashboard_url_edit.setText(url)
        
        # Cambiar el estado de los botones
        self.add_dashboard_button.setEnabled(False)
        self.update_dashboard_button.setEnabled(True)
        
        # Guardar el nombre original para la actualización
        self.current_editing_name = name
    
    def update_dashboard(self):
        new_name = self.dashboard_name_edit.text().strip()
        new_url = self.dashboard_url_edit.text().strip()
        
        if not new_name or not new_url:
            QMessageBox.warning(self, "Datos Incompletos", "Por favor ingrese nombre y URL.")
            return
        
        # Si se cambió el nombre, verificar que no exista otro con ese nombre
        if new_name != self.current_editing_name and new_name in self.config['dashboards']:
            QMessageBox.warning(self, "Duplicado", f"Ya existe un dashboard con el nombre '{new_name}'.")
            return
        
        # Eliminar el elemento anterior si cambió el nombre
        if new_name != self.current_editing_name:
            del self.config['dashboards'][self.current_editing_name]
        
        # Actualizar con los nuevos datos
        self.config['dashboards'][new_name] = new_url
        
        # Actualizar la tabla
        self._refresh_dashboards_list()
        
        # Limpiar el formulario y restaurar botones
        self.clear_dashboard_form()
        
        QMessageBox.information(self, "Dashboard Actualizado", f"Dashboard actualizado correctamente.")
    
    def delete_dashboard(self, name):
        # Confirmar eliminación
        confirm = QMessageBox.question(
            self, 
            "Confirmar Eliminación",
            f"¿Está seguro de eliminar el dashboard '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Eliminar de la configuración
            del self.config['dashboards'][name]
            
            # Actualizar la tabla
            self._refresh_dashboards_list()
            
            QMessageBox.information(self, "Dashboard Eliminado", f"Dashboard '{name}' eliminado correctamente.")
    
    def clear_dashboard_form(self):
        self.dashboard_name_edit.clear()
        self.dashboard_url_edit.clear()
        self.add_dashboard_button.setEnabled(True)
        self.update_dashboard_button.setEnabled(False)
        self.current_editing_name = None
    
    def _setup_users_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # Sección de usuarios autorizados 
        regular_users_group = QGroupBox("👥 Usuarios Autorizados")
        regular_layout = QVBoxLayout(regular_users_group)
        
        self.users_list = QListWidget()
        self._refresh_users_list()
        
        regular_layout.addWidget(QLabel("Estos usuarios pueden acceder a la aplicación:"))
        regular_layout.addWidget(self.users_list)
        
        # Formulario para añadir usuarios
        user_form_layout = QHBoxLayout()
        
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Ingrese un ID de usuario")
        
        add_user_button = QPushButton("➕ Agregar Usuario")
        add_user_button.clicked.connect(self.add_user)
        
        delete_user_button = QPushButton("🗑️ Eliminar Usuario")
        delete_user_button.clicked.connect(self.delete_user)
        
        user_form_layout.addWidget(self.user_edit)
        user_form_layout.addWidget(add_user_button)
        user_form_layout.addWidget(delete_user_button)
        
        regular_layout.addLayout(user_form_layout)
        
        # Sección de administradores
        admin_users_group = QGroupBox("🔑 Usuarios Administradores")
        admin_layout = QVBoxLayout(admin_users_group)
        
        self.admin_list = QListWidget()
        self._refresh_admin_list()
        
        admin_layout.addWidget(QLabel("Estos usuarios tienen acceso a herramientas de administración:"))
        admin_layout.addWidget(self.admin_list)
        
        # Formulario para añadir administradores
        admin_form_layout = QHBoxLayout()
        
        self.admin_edit = QLineEdit()
        self.admin_edit.setPlaceholderText("Ingrese un ID de administrador")
        
        add_admin_button = QPushButton("🔑 Agregar Administrador")
        add_admin_button.clicked.connect(self.add_admin)
        
        delete_admin_button = QPushButton("🗑️ Eliminar Administrador")
        delete_admin_button.clicked.connect(self.delete_admin)
        
        admin_form_layout.addWidget(self.admin_edit)
        admin_form_layout.addWidget(add_admin_button)
        admin_form_layout.addWidget(delete_admin_button)
        
        admin_layout.addLayout(admin_form_layout)
        
        # Agregar advertencia 
        warning_label = QLabel("⚠️ IMPORTANTE: Asegúrese de mantener al menos un usuario administrador.")
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        admin_layout.addWidget(warning_label)
        
        # Agregar todo al layout principal
        layout.addWidget(regular_users_group)
        layout.addWidget(admin_users_group)
    
    def _refresh_users_list(self):
        self.users_list.clear()
        
        # Agregar usuarios a la lista
        admin_users = self.config.get('admin_users', [])
        for user in self.config.get('authorized_users', []):
            display_text = user
            if user in admin_users:
                display_text += " [ADMIN]"
            self.users_list.addItem(display_text)
            
    def _refresh_admin_list(self):
        self.admin_list.clear()
        
        # Agregar administradores a la lista
        for user in self.config.get('admin_users', []):
            self.admin_list.addItem(user)
    
    def add_user(self):
        user = self.user_edit.text().strip()
        
        if not user:
            QMessageBox.warning(self, "Dato Incompleto", "Por favor ingrese un ID de usuario.")
            return
        
        if 'authorized_users' not in self.config:
            self.config['authorized_users'] = []
        
        # Verificar si ya existe
        if user.lower() in [u.lower() for u in self.config['authorized_users']]:
            QMessageBox.warning(self, "Duplicado", f"El usuario '{user}' ya está en la lista.")
            return
        
        # Añadir a la configuración
        self.config['authorized_users'].append(user)
        
        # Actualizar la lista
        self._refresh_users_list()
        
        # Limpiar el campo
        self.user_edit.clear()
        
        QMessageBox.information(self, "Usuario Agregado", f"Usuario '{user}' agregado correctamente.")
    
    def delete_user(self):
        selected_items = self.users_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "Selección Requerida", "Por favor seleccione un usuario para eliminar.")
            return
        
        # Extraer el nombre de usuario (sin [ADMIN])
        user_text = selected_items[0].text()
        user = user_text.replace(" [ADMIN]", "").strip()
        
        # Confirmar eliminación
        confirm = QMessageBox.question(
            self, 
            "Confirmar Eliminación",
            f"¿Está seguro de eliminar el usuario '{user}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Verificar si el usuario también es administrador
            if user.lower() in [u.lower() for u in self.config.get('admin_users', [])]:
                admin_confirm = QMessageBox.question(
                    self,
                    "Usuario Administrador",
                    f"Este usuario '{user}' también es administrador. ¿Desea quitarlo también de la lista de administradores?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if admin_confirm == QMessageBox.Yes:
                    # Eliminar de la lista de administradores
                    self.config['admin_users'] = [u for u in self.config['admin_users'] if u.lower() != user.lower()]
                    self._refresh_admin_list()
            
            # Eliminar de la configuración
            self.config['authorized_users'] = [u for u in self.config['authorized_users'] if u.lower() != user.lower()]
            
            # Actualizar la lista
            self._refresh_users_list()
            
            QMessageBox.information(self, "Usuario Eliminado", f"Usuario '{user}' eliminado correctamente.")
    
    def add_admin(self):
        """Añade un usuario a la lista de administradores"""
        user = self.admin_edit.text().strip()
        
        if not user:
            QMessageBox.warning(self, "Dato Incompleto", "Por favor ingrese un ID de usuario.")
            return
        
        # Inicializar lista si no existe
        if 'admin_users' not in self.config:
            self.config['admin_users'] = []
        
        # Verificar si ya existe
        if user.lower() in [u.lower() for u in self.config['admin_users']]:
            QMessageBox.warning(self, "Duplicado", f"El usuario '{user}' ya está en la lista de administradores.")
            return
        
        # Verificar si el usuario existe en la lista de usuarios autorizados
        if 'authorized_users' in self.config and user.lower() not in [u.lower() for u in self.config['authorized_users']]:
            # Preguntar si desea añadirlo también como usuario autorizado
            reply = QMessageBox.question(
                self,
                "Usuario no autorizado",
                f"El usuario '{user}' no está en la lista de usuarios autorizados.\n"
                f"¿Desea añadirlo también como usuario autorizado?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.config['authorized_users'].append(user)
                self._refresh_users_list()
        
        # Añadir a la configuración
        self.config['admin_users'].append(user)
        
        # Actualizar la lista
        self._refresh_admin_list()
        
        # Limpiar el campo
        self.admin_edit.clear()
        
        QMessageBox.information(self, "Administrador Agregado", f"Usuario '{user}' agregado como administrador.")
    
    def delete_admin(self):
        """Elimina un usuario de la lista de administradores"""
        selected_items = self.admin_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "Selección Requerida", "Por favor seleccione un administrador para eliminar.")
            return
        
        user = selected_items[0].text()
        
        # Verificar que no sea el último administrador
        if len(self.config.get('admin_users', [])) <= 1:
            QMessageBox.critical(
                self,
                "Error",
                "No se puede eliminar el último administrador.\n"
                "Debe haber al menos un usuario con privilegios de administrador."
            )
            return
        
        # Confirmar eliminación
        confirm = QMessageBox.question(
            self, 
            "Confirmar Eliminación",
            f"¿Está seguro de eliminar al administrador '{user}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Eliminar de la configuración
            self.config['admin_users'] = [u for u in self.config['admin_users'] if u.lower() != user.lower()]
            
            # Actualizar la lista
            self._refresh_admin_list()
            self._refresh_users_list()  # También actualizar la lista de usuarios
            
            QMessageBox.information(self, "Administrador Eliminado", f"Administrador '{user}' eliminado correctamente.")
    
    def _setup_changelog_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # Lista de entradas del historial
        self.changelog_list = QListWidget()
        
        # Añadir entradas del historial
        self._refresh_changelog_list()
        
        layout.addWidget(QLabel("Historial de cambios:"))
        layout.addWidget(self.changelog_list)
        
        # Formulario para añadir nueva entrada
        form_group = QGroupBox("Agregar nueva entrada al historial")
        form_layout = QGridLayout(form_group)
        
        self.version_edit = QLineEdit()
        self.author_edit = QLineEdit()
        self.change_edit = QTextEdit()
        self.change_edit.setMaximumHeight(100)
        
        form_layout.addWidget(QLabel("Versión:"), 0, 0)
        form_layout.addWidget(self.version_edit, 0, 1)
        form_layout.addWidget(QLabel("Autor:"), 1, 0)
        form_layout.addWidget(self.author_edit, 1, 1)
        form_layout.addWidget(QLabel("Cambios:"), 2, 0)
        form_layout.addWidget(self.change_edit, 2, 1)
        
        # Sugerir nueva versión
        current_version = self.config.get('version', '1.0.0')
        parts = current_version.split('.')
        if len(parts) >= 3:
            try:
                minor = int(parts[-1]) + 1
                new_version = f"{parts[0]}.{parts[1]}.{minor}"
                self.version_edit.setText(new_version)
            except ValueError:
                pass
        
        # Proponer usuario actual
        try:
            current_user = get_current_username()
            self.author_edit.setText(current_user)
        except:
            pass
        
        add_button = QPushButton("➕ Añadir Entrada")
        add_button.clicked.connect(self.add_changelog_entry)
        
        form_layout.addWidget(add_button, 3, 1)
        
        layout.addWidget(form_group)
    
    def _refresh_changelog_list(self):
        self.changelog_list.clear()
        
        # Ordenar entradas de más reciente a más antigua
        sorted_entries = sorted(
            self.config.get('changelog', []), 
            key=lambda x: x.get('version', '0.0.0'), 
            reverse=True
        )
        
        # Agregar entradas a la lista
        for entry in sorted_entries:
            version = entry.get('version', '?')
            date = entry.get('date', '?')
            author = entry.get('author', '?')
            
            item_text = f"v{version} ({date}) - Por: {author}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, entry)  # Guardar datos completos
            
            self.changelog_list.addItem(item)
    
    def add_changelog_entry(self):
        version = self.version_edit.text().strip()
        author = self.author_edit.text().strip()
        changes_text = self.change_edit.toPlainText().strip()
        
        if not version or not author or not changes_text:
            QMessageBox.warning(self, "Datos Incompletos", "Por favor complete todos los campos.")
            return
        
        # Verificar formato de versión
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            QMessageBox.warning(
                self, 
                "Formato Incorrecto", 
                "La versión debe tener el formato X.Y.Z (ejemplo: 1.0.0)"
            )
            return
        
        # Dividir cambios en lista por líneas
        changes_list = [line.strip() for line in changes_text.split('\n') if line.strip()]
        
        # Crear nueva entrada
        new_entry = {
            'version': version,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'author': author,
            'changes': changes_list
        }
        
        # Añadir a la configuración
        if 'changelog' not in self.config:
            self.config['changelog'] = []
        
        self.config['changelog'].append(new_entry)
        
        # Actualizar versión principal
        self.config['version'] = version
        
        # Actualizar fecha de actualización
        self.config['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Actualizar la lista
        self._refresh_changelog_list()
        
        # Limpiar formulario
        self.change_edit.clear()
        QMessageBox.information(
            self, 
            "Entrada Agregada", 
            f"Se ha agregado la entrada para la versión {version}.\n"
            f"La versión de la configuración ha sido actualizada."
        )
    
    def _setup_settings_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # Información de cifrado
        encryption_group = QGroupBox("🔐 Estado del Cifrado")
        encryption_layout = QVBoxLayout(encryption_group)
        
        if ENCRYPTION_AVAILABLE:
            encryption_info = "✅ Cifrado AES-256 Disponible"
            encryption_color = "#D4EDDA"
            encryption_detail = f"Clave: {ENCRYPTION_SECRET[:20]}...{ENCRYPTION_SECRET[-10:]}"
        else:
            encryption_info = "❌ Cifrado No Disponible"
            encryption_color = "#F8D7DA"
            encryption_detail = "Instale 'cryptography' para habilitar el cifrado: pip install cryptography"
        
        encryption_label = QLabel(encryption_info)
        encryption_label.setStyleSheet(f"background-color: {encryption_color}; padding: 8px; border-radius: 4px; font-weight: bold;")
        encryption_layout.addWidget(encryption_label)
        
        encryption_detail_label = QLabel(encryption_detail)
        encryption_detail_label.setStyleSheet("color: #666; font-family: monospace;")
        encryption_layout.addWidget(encryption_detail_label)
        
        layout.addWidget(encryption_group)
        
        # Información de conectividad
        connectivity_group = QGroupBox("🌐 Estado de Conectividad")
        connectivity_layout = QVBoxLayout(connectivity_group)
        
        # Mostrar información del entorno actual
        if detect_corporate_network():
            env_info = f"🏢 Red Corporativa (Proxy: {CORPORATE_PROXY})"
            env_color = "#D1ECF1"
        else:
            env_info = "🌐 Red Externa (Conexión Directa)"
            env_color = "#D4EDDA"
        
        env_label = QLabel(env_info)
        env_label.setStyleSheet(f"background-color: {env_color}; padding: 8px; border-radius: 4px; font-weight: bold;")
        connectivity_layout.addWidget(env_label)
        
        # Botón para probar conectividad
        test_button = QPushButton("🧪 Probar Conectividad con GitHub")
        test_button.clicked.connect(self.test_github_connectivity)
        connectivity_layout.addWidget(test_button)
        
        layout.addWidget(connectivity_group)
        
        # Opciones de configuración general
        settings_group = QGroupBox("⚙️ Configuración General")
        settings_layout = QVBoxLayout(settings_group)
        
        # Opción de verificación de red corporativa
        self.require_corporate_check = QCheckBox("Requerir red corporativa para acceso")
        self.require_corporate_check.setChecked(self.config.get('require_corporate_network', False))
        settings_layout.addWidget(self.require_corporate_check)
        
        # Opción de verificación automática de actualizaciones
        self.auto_update_check = QCheckBox("Verificar actualizaciones automáticamente")
        self.auto_update_check.setChecked(True)  # Por defecto activado
        settings_layout.addWidget(self.auto_update_check)
        
        # Configuración de URL remota
        remote_url_layout = QHBoxLayout()
        remote_url_layout.addWidget(QLabel("URL de configuración remota:"))
        
        self.remote_url_edit = QLineEdit()
        self.remote_url_edit.setText(CONFIG_URL)
        self.remote_url_edit.setReadOnly(True)  # Solo lectura
        remote_url_layout.addWidget(self.remote_url_edit)
        
        settings_layout.addLayout(remote_url_layout)
        
        layout.addWidget(settings_group)
        
        # Información de GitHub
        github_group = QGroupBox("🔗 Configuración de GitHub")
        github_layout = QVBoxLayout(github_group)
        
        # Botón para configurar token
        token_button = QPushButton("🔑 Configurar Token de GitHub")
        token_button.clicked.connect(self.configure_github_token)
        github_layout.addWidget(token_button)
        
        # Información del repositorio
        repo_info = QLabel(f"Repositorio: {GITHUB_OWNER}/{GITHUB_REPO}")
        repo_info.setStyleSheet("color: #666;")
        github_layout.addWidget(repo_info)
        
        layout.addWidget(github_group)
        
        # Información adicional
        info_group = QGroupBox("ℹ️ Información")
        info_layout = QVBoxLayout(info_group)
        
        info_text = QLabel(
            "Esta herramienta permite administrar la configuración de la aplicación.\n"
            "• Los cambios se guardan localmente sin cifrar\n"
            "• Use 'Publicar a GitHub' para sincronizar con todos los usuarios\n"
            "• Las URLs se cifran automáticamente antes de publicar en GitHub\n"
            "• Los usuarios verán los cambios automáticamente\n"
            "• La aplicación detecta automáticamente el entorno de red y configura el proxy"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        layout.addWidget(info_group)
        
        # Espaciador
        layout.addStretch()
    
    def test_github_connectivity(self):
        """Prueba la conectividad con GitHub"""
        # Crear un diálogo de progreso
        progress = QMessageBox()
        progress.setIcon(QMessageBox.Information)
        progress.setWindowTitle("Probando conectividad")
        progress.setText("Probando conectividad con GitHub...")
        progress.setStandardButtons(QMessageBox.NoButton)
        progress.show()
        QApplication.processEvents()
        
        try:
            success = test_connectivity()
            progress.close()
            
            if success:
                QMessageBox.information(
                    self,
                    "Conectividad Exitosa",
                    "✅ La conectividad con GitHub está funcionando correctamente.\n"
                    f"Entorno: {'Red Corporativa (con proxy)' if detect_corporate_network() else 'Red Externa (directa)'}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Error de Conectividad",
                    "❌ No se pudo establecer conectividad con GitHub.\n"
                    "Verifique su conexión a internet y la configuración del proxy."
                )
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self,
                "Error de Prueba",
                f"❌ Error al probar conectividad:\n{str(e)}"
            )
    
    def configure_github_token(self):
        """Configurar el token de GitHub"""
        current_token = get_github_token()
        
        if current_token:
            # Mostrar token parcial
            masked_token = current_token[:8] + "..." + current_token[-4:] if len(current_token) > 12 else "***"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Token de GitHub")
            msg.setText(f"Ya existe un token configurado: {masked_token}")
            msg.setInformativeText("¿Qué desea hacer?")
            msg.addButton("Reemplazar", QMessageBox.AcceptRole)
            msg.addButton("Verificar", QMessageBox.ActionRole)
            msg.addButton("Cancelar", QMessageBox.RejectRole)
            
            result = msg.exec_()
            
            if result == 1:  # Verificar
                is_valid, message = validate_github_token(current_token)
                status = "✅ Válido" if is_valid else "❌ Inválido"
                QMessageBox.information(self, "Verificación de Token", f"{status}\n\n{message}")
                return
            elif result == 2:  # Cancelar
                return
        
        # Configurar nuevo token
        new_token = setup_github_token()
        if new_token:
            QMessageBox.information(self, "Token Configurado", "Token de GitHub configurado correctamente.")
    
    def save_changes(self):
        """Guardar cambios en la configuración local (sin cifrar)"""
        try:
            # Actualizar opciones de configuración
            self.config['require_corporate_network'] = self.require_corporate_check.isChecked()
            
            # Actualizar fecha de última actualización
            self.config['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Crear una copia de seguridad
            if os.path.exists(CONFIG_FILE):
                backup_path = f"{CONFIG_FILE}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                shutil.copy2(CONFIG_FILE, backup_path)
            
            # Guardar la configuración SIN CIFRAR localmente
            local_config = copy.deepcopy(self.config)
            local_config['encrypted'] = False  # Marcar como no cifrada para uso local
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_config, f, indent=4, ensure_ascii=False)
            
            QMessageBox.information(
                self,
                "Cambios Guardados",
                "La configuración ha sido guardada localmente (sin cifrar).\n"
                "Para sincronizar con otros usuarios, use 'Publicar a GitHub'."
            )
            
            # Cerrar el diálogo
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error al guardar la configuración: {str(e)}"
            )
    
    def publish_to_github(self):
        """Publicar cambios a GitHub automáticamente (cifrado)"""
        
        # Confirmar que el usuario quiere publicar
        encryption_note = ""
        if ENCRYPTION_AVAILABLE:
            encryption_note = "\n🔐 Las URLs serán cifradas automáticamente antes de publicar."
        else:
            encryption_note = "\n⚠️ ADVERTENCIA: Las URLs se publicarán SIN CIFRAR."
        
        confirm = QMessageBox.question(
            self,
            "Confirmar Publicación",
            f"¿Está seguro de que desea publicar los cambios a GitHub?{encryption_note}\n\n"
            "Esto actualizará la configuración para todos los usuarios.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if confirm != QMessageBox.Yes:
            return
        
        # Validar que hay cambios para publicar
        if self.config == self.original_config:
            QMessageBox.information(
                self,
                "Sin cambios",
                "No hay cambios para publicar."
            )
            return
        
        # Crear un diálogo de progreso
        progress_dialog = QMessageBox(self)
        progress_dialog.setWindowTitle("Publicando...")
        progress_dialog.setText("Publicando configuración en GitHub...")
        progress_dialog.setInformativeText("Cifrando URLs y enviando datos...")
        progress_dialog.setStandardButtons(QMessageBox.Cancel)
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()
        
        # Procesar eventos para mostrar el diálogo
        QApplication.processEvents()
        
        try:
            # Actualizar la configuración con timestamp actual
            self.config['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            print("🚀 Iniciando publicación en GitHub...")
            
            # Publicar en GitHub (la función se encarga del cifrado automáticamente)
            success, message = publish_to_github_api(self.config)
            
            # Cerrar diálogo de progreso
            progress_dialog.close()
            QApplication.processEvents()
            
            if success:
                # Éxito - mostrar mensaje detallado
                success_msg = QMessageBox(self)
                success_msg.setIcon(QMessageBox.Information)
                success_msg.setWindowTitle("🎉 Publicación Exitosa")
                success_msg.setText("¡Configuración publicada exitosamente!")
                info_text = f"Versión: {self.config.get('version', '1.0.0')}\n"
                
                if ENCRYPTION_AVAILABLE:
                    info_text += "🔐 URLs cifradas automáticamente\n"
                else:
                    info_text += "⚠️ URLs publicadas sin cifrar\n"
                
                info_text += f"Los cambios se aplicarán automáticamente:\n"
                info_text += f"• Verificación de usuarios: en máximo {USER_CHECK_INTERVAL} minutos\n"
                info_text += f"• Configuración completa: al reiniciar la aplicación"
                
                success_msg.setInformativeText(info_text)
                success_msg.setDetailedText(message)
                success_msg.setStandardButtons(QMessageBox.Ok)
                success_msg.exec_()
                
                # También guardar localmente (sin cifrar para uso local)
                try:
                    local_config = copy.deepcopy(self.config)
                    local_config['encrypted'] = False  # Local sin cifrar
                    
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(local_config, f, indent=4, ensure_ascii=False)
                    print("💾 Configuración guardada localmente tras publicación exitosa")
                except Exception as e:
                    print(f"⚠️ Advertencia: No se pudo guardar localmente: {e}")
                
                # Cerrar el diálogo de administración
                self.accept()
                
            else:
                # Error - mostrar mensaje detallado
                error_msg = QMessageBox(self)
                error_msg.setIcon(QMessageBox.Critical)
                error_msg.setWindowTitle("❌ Error de Publicación")
                error_msg.setText("No se pudo publicar en GitHub")
                error_msg.setInformativeText(
                    "Los cambios se pueden guardar localmente.\n"
                    "Puede intentar publicar nuevamente."
                )
                error_msg.setDetailedText(f"Detalles del error:\n{message}")
                error_msg.setStandardButtons(QMessageBox.Ok)
                error_msg.exec_()
                
                # Ofrecer guardar localmente
                local_save = QMessageBox.question(
                    self,
                    "Guardar Localmente",
                    "¿Desea guardar los cambios localmente?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if local_save == QMessageBox.Yes:
                    self.save_changes()
        
        except Exception as e:
            # Asegurar que el diálogo se cierre en caso de error inesperado
            try:
                progress_dialog.close()
            except:
                pass
            
            QMessageBox.critical(
                self,
                "Error Inesperado",
                f"Error inesperado al publicar:\n{str(e)}\n\n"
                f"Por favor, intente nuevamente o contacte al administrador."
            )

# ============================================================================
# CLASE PRINCIPAL DEL VISOR DE DASHBOARDS (CON DESCARGA INTEGRADA)
# ============================================================================

class DatoramaViewer(QMainWindow):
    """
    Ventana principal para visualizar dashboards de Datorama
    INTEGRADA CON DOWNLOADMANAGER PARA MANEJAR DESCARGAS
    """
    windowClosed = pyqtSignal(str)
    
    def __init__(self, datorama_url, title, instance_number):
        super().__init__()
        self.title = title
        self.instance_number = instance_number
        
        # Establecer título de la ventana
        window_title = f"{title} - Instancia {instance_number}"
        self.setWindowTitle(window_title)
        self.setGeometry(100, 100, 1200, 800)
        
        # Establecer el icono de la ventana
        try:
            icon_path = resource_path("walmart.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Error al establecer el icono: {e}")
        
        # Crear un widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Crear un layout vertical
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Crear un visor web
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        # Crear una barra de estado
        self.setStatusBar(QStatusBar())
        
        # *** INTEGRACIÓN CLAVE: CONFIGURAR EL MANEJADOR DE DESCARGAS ***
        print(f"🔽 Configurando manejador de descargas para: {title}")
        self.download_manager = DownloadManager(self)
        self.download_manager.setup_download_handler(self.web_view)
        
        # Cargar la URL
        self.web_view.setUrl(QUrl(datorama_url))
        
        # Mostrar mensaje de carga en la barra de estado
        self.statusBar().showMessage(f"Cargando {title}...")
        
        # Conectar señal de carga finalizada
        self.web_view.loadFinished.connect(self.on_load_finished)
        
    def on_load_finished(self, success):
        """Maneja el evento de finalización de carga del contenido web"""
        if success:
            # Mensaje que incluye información sobre descargas
            self.statusBar().showMessage(
                "Tablero cargado correctamente. 🔽 Para descargar archivos, use los botones del dashboard.", 
                5000
            )
            print(f"✅ Dashboard '{self.title}' cargado con soporte de descargas")
        else:
            self.statusBar().showMessage("Error al cargar el tablero.", 5000)
            print(f"❌ Error al cargar dashboard '{self.title}'")
        
    def closeEvent(self, event):
        # Emitir señal de cierre antes de aceptar el evento
        print(f"🚪 Cerrando ventana: {self.title} - Instancia {self.instance_number}")
        self.windowClosed.emit(self.title)
        event.accept()

# ============================================================================
# COMPONENTES DE INTERFAZ (SIN CAMBIOS)
# ============================================================================

class IndicatorLabel(QLabel):
    """Etiqueta personalizada para los indicadores numéricos"""
    def __init__(self, number, parent=None):
        super().__init__(str(number), parent)
        self.setFixedSize(25, 25)
        self.setAlignment(Qt.AlignCenter)
        self.setInactive()
        
    def setActive(self):
        """Configura el estilo para un indicador activo (azul)"""
        self.setStyleSheet("""
            background-color: #007bff;
            color: white;
            border-radius: 12px;
            font-weight: bold;
            border: 1px solid #0056b3;
        """)
        
    def setInactive(self):
        """Configura el estilo para un indicador inactivo (gris)"""
        self.setStyleSheet("""
            background-color: #e0e0e0;
            color: #999999;
            border-radius: 12px;
            border: 1px solid #cccccc;
        """)

class DashboardButton(QWidget):
    clicked = pyqtSignal()
    
    def __init__(self, dashboard_name, parent=None):
        super().__init__(parent)
        self.dashboard_name = dashboard_name
        self.setMinimumHeight(50)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        # Layout principal (horizontal)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 5, 15, 5)
        
        # Widget indicador de activación (barra lateral izquierda)
        self.active_indicator = QWidget()
        self.active_indicator.setFixedWidth(4)
        self.active_indicator.setFixedHeight(30)
        self.active_indicator.setStyleSheet("background-color: transparent;")
        
        # Texto del dashboard
        self.text_label = QLabel(dashboard_name)
        self.text_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        # Contenedor para el indicador de activación y el texto (lado izquierdo)
        left_container = QHBoxLayout()
        left_container.setContentsMargins(0, 0, 0, 0)
        left_container.setSpacing(10)
        left_container.addWidget(self.active_indicator)
        left_container.addWidget(self.text_label)
        
        # Agregar el contenedor izquierdo al layout principal
        main_widget = QWidget()
        main_widget.setLayout(left_container)
        main_layout.addWidget(main_widget, 1)
        
        # Espacio flexible
        main_layout.addStretch()
        
        # Indicadores numéricos (a la derecha)
        self.indicator1 = IndicatorLabel(1)
        self.indicator2 = IndicatorLabel(2)
        
        main_layout.addWidget(self.indicator1)
        main_layout.addWidget(self.indicator2)
        
        # Estilo general del botón - más limpio y plano
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QWidget:hover {
                background-color: #f5f5f5;
                border: 1px solid #d0d0d0;
            }
        """)
    
    def mousePressEvent(self, event):
        """Manejador del evento de presionar el botón"""
        self.setStyleSheet("""
            QWidget {
                background-color: #e6e6e6;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
            }
        """)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Manejador del evento de soltar el botón"""
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QWidget:hover {
                background-color: #f5f5f5;
                border: 1px solid #d0d0d0;
            }
        """)
        # Emitir señal de clic
        self.clicked.emit()
        super().mouseReleaseEvent(event)
    
    def update_indicators(self, count):
        """Actualiza los indicadores visuales basado en el número de instancias abiertas"""
        # Activar/desactivar indicadores según el conteo
        if count >= 1:
            self.indicator1.setActive()
            # Activar el indicador visual en el lado izquierdo
            self.active_indicator.setStyleSheet("""
                background-color: #007bff;
                border-radius: 2px;
            """)
            # Cambiar estilo del botón para mostrar estado activo
            self.setStyleSheet("""
                QWidget {
                    background-color: #f0f8ff;
                    border: 1px solid #b8daff;
                    border-radius: 4px;
                }
                QWidget:hover {
                    background-color: #e6f2ff;
                    border: 1px solid #9fcdff;
                }
            """)
        else:
            self.indicator1.setInactive()
            # Desactivar el indicador visual
            self.active_indicator.setStyleSheet("background-color: transparent;")
            # Restaurar estilo normal
            self.setStyleSheet("""
                QWidget {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                }
                QWidget:hover {
                    background-color: #f5f5f5;
                    border: 1px solid #d0d0d0;
                }
            """)
            
        if count >= 2:
            self.indicator2.setActive()
        else:
            self.indicator2.setInactive()

# ============================================================================
# CLASE PRINCIPAL DE SELECCIÓN DE DASHBOARDS
# ============================================================================


# ============================================================================
# INTEGRACIÓN DE SISTEMA DE TICKETS - AGREGADO AUTOMÁTICAMENTE
# ============================================================================

# Importaciones adicionales para el sistema de tickets
import flask
from flask import Flask, render_template_string, jsonify
import werkzeug.serving
import logging


# INTEGRACIÓN COMPLETA: DATORAMA + SISTEMA DE TICKETS
# Integra el sistema de tickets Flask DENTRO de la aplicación PyQt5 de Datorama
class DashboardSelector(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.dashboards = config.get('dashboards', {})
        self.config = config
        
        # Obtener el usuario actual y verificar privilegios
        self.current_username = get_current_username()
        self.is_authorized = is_authorized_user(self.current_username, config.get('authorized_users', []))
        self.is_admin = is_admin_user(self.current_username, config.get('admin_users', []))
        
        # Diccionario para rastrear ventanas abiertas
        self.open_viewers = {}
        
        # Diccionario para rastrear los botones de los dashboards
        self.dashboard_buttons = {}
        
        # Establecer el icono de la ventana
        try:
            icon_path = resource_path("walmart.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Error al establecer el icono de la ventana principal: {e}")
        
        # Mostrar la versión de la configuración en la barra de título
        version = config.get('version', '1.0.0')
        last_updated = config.get('last_updated', 'N/A')
        
        self.initUI(version, last_updated)
        
        # Configurar verificación automática de actualizaciones
        self.setup_auto_update_check()
        
        # Configurar verificación periódica de autorización de usuarios
        if PERIODIC_USER_CHECK:
            self.user_check_timer = QTimer(self)
            self.user_check_timer.timeout.connect(self.periodic_user_authorization_check)
            check_interval_ms = USER_CHECK_INTERVAL * 60 * 1000
            self.user_check_timer.start(check_interval_ms)
            print(f"🛡️ Verificación periódica de usuario activada: cada {USER_CHECK_INTERVAL} minutos")
        
        # Si estamos usando configuración local, mostrar un indicador
        if self.config.get('using_local_config', False):
            self.show_local_config_indicator()
    
    def periodic_user_authorization_check(self):
        """
        Verifica periódicamente si el usuario actual sigue autorizado
        """
        print(f"🔍 Verificando autorización del usuario: {self.current_username}")
        
        # Intentar verificación silenciosa
        is_authorized, new_config = check_user_authorization_silent(self.current_username)
        
        if is_authorized is None:
            print("⚠️ No se pudo verificar autorización (problema de conexión)")
            return
        
        if not is_authorized:
            print(f"🚨 ACCESO REVOCADO para usuario: {self.current_username}")
            
            # Cerrar todas las ventanas de dashboards inmediatamente
            self.close_all_dashboard_windows()
            
            # Mostrar mensaje crítico
            error_msg = QMessageBox()
            error_msg.setIcon(QMessageBox.Critical)
            error_msg.setWindowTitle("Acceso Revocado")
            error_msg.setText("Su acceso a esta aplicación ha sido revocado.")
            error_msg.setInformativeText(
                f"El usuario '{self.current_username}' ya no está autorizado para usar esta aplicación.\n\n"
                f"Por favor, contacte al área de DATA si considera que esto es un error."
            )
            error_msg.setStandardButtons(QMessageBox.Ok)
            error_msg.exec_()
            
            # Cerrar la aplicación inmediatamente
            QApplication.quit()
            return
        
        print(f"✅ Usuario {self.current_username} sigue autorizado")
    
    def close_all_dashboard_windows(self):
        """Cierra todas las ventanas de dashboards abiertas inmediatamente"""
        print("🔒 Cerrando todas las ventanas de dashboards...")
        
        open_titles = list(self.open_viewers.keys())
        
        for title in open_titles:
            if title in self.open_viewers:
                for viewer in self.open_viewers[title]:
                    try:
                        if viewer.isVisible():
                            viewer.close()
                        print(f"  ✓ Cerrada ventana: {title}")
                    except RuntimeError:
                        pass
        
        self.open_viewers.clear()
    
    def show_local_config_indicator(self):
        # Cambiar el color de fondo de la barra de estado a amarillo claro
        self.statusBar().setStyleSheet("background-color: #FFEB3B; color: black;")
        # Mostrar mensaje de advertencia en la barra de estado
        self.statusBar().showMessage("⚠️ Usando configuración local (no se pudo conectar a GitHub)", 0)
    
    def initUI(self, version, last_updated):
        # Configurar la ventana principal
        admin_suffix = " [ADMINISTRADOR]" if self.is_admin else ""
        encryption_suffix = ""
        if self.config.get('encrypted', False):
            encryption_suffix = " 🔐"
        elif ENCRYPTION_AVAILABLE:
            encryption_suffix = " 🔓"
        
        self.setWindowTitle(f"Selector de Tableros de Información (v{version}){admin_suffix}{encryption_suffix}")
        self.setGeometry(700, 250, 800, 800)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Banner de administrador (solo para admins)
        if self.is_admin:
            admin_banner = QLabel("🔑 MODO ADMINISTRADOR - Tiene acceso a herramientas de administración")
            admin_banner.setStyleSheet("""
                background-color: #D1ECF1;
                color: #0C5460;
                padding: 8px;
                border: 1px solid #BEE5EB;
                border-radius: 4px;
                font-weight: bold;
            """)
            admin_banner.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(admin_banner)
        
        # Banner de cifrado si está habilitado
        if self.config.get('encrypted', False):
            encryption_banner = QLabel("🔐 CONFIGURACIÓN CIFRADA - URLs protegidas con AES-256")
            encryption_banner.setStyleSheet("""
                background-color: #D4EDDA;
                color: #155724;
                padding: 8px;
                border: 1px solid #C3E6CB;
                border-radius: 4px;
                font-weight: bold;
            """)
            encryption_banner.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(encryption_banner)
        elif ENCRYPTION_AVAILABLE:
            encryption_info = QLabel("🔓 Cifrado disponible pero no activado en esta configuración")
            encryption_info.setStyleSheet("""
                background-color: #FFF3CD;
                color: #856404;
                padding: 6px;
                border: 1px solid #FFEAA7;
                border-radius: 4px;
                font-size: 10px;
            """)
            encryption_info.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(encryption_info)
        
        # Banner de funcionalidad de descarga
        download_banner = QLabel("🔽 DESCARGA ACTIVADA - Los archivos de los dashboards se pueden descargar")
        download_banner.setStyleSheet("""
            background-color: #E7F3FF;
            color: #014361;
            padding: 6px;
            border: 1px solid #B8DAFF;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10px;
        """)
        download_banner.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(download_banner)
        
        # Título de la aplicación
        title_label = QLabel("Tableros de Información Corporativa")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Subtítulo 
        subtitle_label = QLabel("Seleccione un tablero para visualizar")
        subtitle_label.setFont(QFont("Arial", 12))
        subtitle_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle_label)
        
        # Información de usuario actual
        user_info_text = f"Usuario: {self.current_username}"
        if self.is_admin:
            user_info_text += " (Administrador)"
        user_info_label = QLabel(user_info_text)
        user_info_label.setFont(QFont("Arial", 9))
        user_info_label.setAlignment(Qt.AlignCenter)
        user_info_label.setStyleSheet("color: #666;")
        main_layout.addWidget(user_info_label)
        
        # Información de última actualización
        update_text = f"Última actualización: {last_updated}"
        update_label = QLabel(update_text)
        update_label.setFont(QFont("Arial", 8))
        update_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(update_label)
        
        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)
        
        # Área desplazable para la lista
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll_area)
        
        # Widget contenedor para el área desplazable
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)
        
        # Layout de lista vertical
        list_layout = QVBoxLayout(scroll_content)
        list_layout.setSpacing(10)
        list_layout.setContentsMargins(20, 20, 20, 20)

        # Crear botones personalizados para cada tablero
        for dashboard_name, dashboard_url in self.dashboards.items():
            button = DashboardButton(dashboard_name)
            button.clicked.connect(
                functools.partial(self.open_dashboard, dashboard_url, dashboard_name)
            )
            self.dashboard_buttons[dashboard_name] = button
            list_layout.addWidget(button)
        
        # Agregar espaciado al final
        list_layout.addStretch()
        
        # Añadir botones en un layout horizontal
        buttons_layout = QHBoxLayout()
        
        # Botón para verificar actualizaciones
        check_updates_button = QPushButton("📥 Verificar Actualizaciones")
        check_updates_button.clicked.connect(self.check_for_updates)
        buttons_layout.addWidget(check_updates_button)
        
        # Botón para ver el registro de cambios
        view_changelog_button = QPushButton("📝 Ver Historial")
        view_changelog_button.clicked.connect(self.view_changelog)
        buttons_layout.addWidget(view_changelog_button)
        
        # Botón de administración (solo para administradores)
        if self.is_admin:
            admin_button = QPushButton("🔧 Administración")
            admin_button.clicked.connect(self.open_admin_tool)
            # Estilo para destacar el botón de administración
            admin_button.setStyleSheet("""
                QPushButton {
                    background-color: #007bff;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #0069d9;
                }
            """)
            buttons_layout.addWidget(admin_button)
        
        main_layout.addLayout(buttons_layout)
        
        # Agregar barra de estado a la ventana principal
        self.setStatusBar(QStatusBar())
        status_message = "Seleccione un tablero para comenzar 🔽 Descargas habilitadas"
        if self.is_admin:
            status_message += " [Administrador]"
        if self.config.get('encrypted', False):
            status_message += " [Cifrado]"
        self.statusBar().showMessage(status_message)
    
    def open_admin_tool(self):
        """Abre la herramienta de administración (solo para administradores)"""
        # Verificar nuevamente los privilegios (doble seguridad)
        if not self.is_admin:
            QMessageBox.warning(
                self,
                "Acceso Denegado",
                "No tiene privilegios de administrador para acceder a esta función."
            )
            return
        
        # Abrir la herramienta de administración
        admin_tool = ConfigAdminTool(self.config, self)
        result = admin_tool.exec_()
        
        # Si se aceptaron los cambios, recargar la configuración
        if result == QDialog.Accepted:
            # Recargar configuración
            updated_config = load_config()
            
            # Actualizar configuración en memoria
            self.config = updated_config
            self.dashboards = updated_config.get('dashboards', {})
            
            # Actualizar privilegios
            self.is_authorized = is_authorized_user(self.current_username, updated_config.get('authorized_users', []))
            self.is_admin = is_admin_user(self.current_username, updated_config.get('admin_users', []))
            
            # Actualizar interfaz
            self.refresh_dashboard_list()
            
            # Mostrar mensaje informativo
            QMessageBox.information(
                self,
                "Configuración Actualizada",
                "La configuración ha sido actualizada. Algunos cambios pueden requerir reiniciar la aplicación."
            )
    
    def view_changelog(self):
        """Muestra el registro de cambios en un diálogo"""
        changelog_entries = self.config.get('changelog', [])
        
        if not changelog_entries:
            QMessageBox.information(
                self,
                "Historial de cambios",
                "No hay información disponible sobre el historial de cambios."
            )
            return
        
        # Mostrar el diálogo de historial de cambios
        dialog = ChangelogDialog(changelog_entries, self)
        dialog.exec_()
    
    def refresh_dashboard_list(self):
        """Actualiza la lista de dashboards después de cambios en la configuración"""
        # Limpiar referencias a ventanas abiertas
        self.open_viewers = {}
        self.dashboard_buttons = {}
        
        # Obtener el widget de contenido del área de desplazamiento
        scroll_content = None
        for scroll_area in self.findChildren(QScrollArea):
            scroll_content = scroll_area.widget()
            break
        
        if not scroll_content:
            return
        
        # Limpiar el layout existente y recrear los botones
        if scroll_content.layout():
            # Eliminar todos los widgets del layout
            while scroll_content.layout().count():
                item = scroll_content.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        
        # Crear nuevo layout
        list_layout = QVBoxLayout(scroll_content)
        list_layout.setSpacing(10)
        list_layout.setContentsMargins(20, 20, 20, 20)
        
        # Crear botones para cada dashboard
        for dashboard_name, dashboard_url in self.dashboards.items():
            button = DashboardButton(dashboard_name)
            button.clicked.connect(
                functools.partial(self.open_dashboard, dashboard_url, dashboard_name)
            )
            self.dashboard_buttons[dashboard_name] = button
            list_layout.addWidget(button)
        
        # Agregar espaciado al final
        list_layout.addStretch()
    
    def setup_auto_update_check(self):
        """Configura la verificación automática de actualizaciones"""
        if not AUTO_UPDATE_CHECK:
            return
        
        # Verificar si se debe hacer una comprobación
        last_check_time = self.get_last_update_check_time()
        current_time = datetime.now()
        
        if last_check_time is None or (current_time - last_check_time).total_seconds() > AUTO_UPDATE_INTERVAL * 3600:
            # Programar la verificación para unos segundos después del inicio
            QTimer.singleShot(5000, self.auto_check_for_updates)
        
        # Programar verificaciones periódicas
        auto_timer = QTimer(self)
        auto_timer.timeout.connect(self.auto_check_for_updates)
        auto_timer.start(AUTO_UPDATE_INTERVAL * 3600 * 1000)  # Convertir horas a milisegundos
    
    def get_last_update_check_time(self):
        """Obtiene la última vez que se verificaron las actualizaciones"""
        try:
            if os.path.exists(LAST_UPDATE_CHECK_FILE):
                with open(LAST_UPDATE_CHECK_FILE, 'r') as f:
                    timestamp_str = f.read().strip()
                    return datetime.fromisoformat(timestamp_str)
        except Exception:
            pass
        return None
    
    def save_last_update_check_time(self):
        """Guarda el tiempo de la última verificación de actualizaciones"""
        try:
            with open(LAST_UPDATE_CHECK_FILE, 'w') as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            print(f"Error al guardar tiempo de verificación: {e}")
    
    def auto_check_for_updates(self):
        """Verificación automática silenciosa de actualizaciones"""
        try:
            has_update, new_config = check_remote_updates(self.config)
            self.save_last_update_check_time()
            
            if has_update:
                # Mostrar notificación de actualización disponible
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Actualización Disponible")
                msg.setText("Nueva versión de configuración disponible")
                msg.setInformativeText(
                    f"Versión actual: {self.config.get('version', '1.0.0')}\n"
                    f"Nueva versión: {new_config.get('version', '1.0.0')}\n\n"
                    f"¿Desea aplicar la actualización ahora?"
                )
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                
                if msg.exec_() == QMessageBox.Yes:
                    self.apply_configuration_update(new_config)
        except Exception as e:
            print(f"Error en verificación automática: {e}")
    
    def check_for_updates(self):
        """Verifica manualmente si hay actualizaciones de configuración disponibles"""
        # Crear un diálogo de progreso
        progress = QMessageBox()
        progress.setIcon(QMessageBox.Information)
        progress.setWindowTitle("Verificando actualizaciones")
        progress.setText("Verificando si hay actualizaciones disponibles...")
        progress.setStandardButtons(QMessageBox.NoButton)
        progress.show()
        QApplication.processEvents()
        
        try:
            has_update, new_config = check_remote_updates(self.config)
            self.save_last_update_check_time()
            
            progress.close()
            
            if has_update:
                # Mostrar información sobre la actualización
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Actualización Disponible")
                msg.setText("Nueva versión de configuración disponible")
                msg.setInformativeText(
                    f"Versión actual: {self.config.get('version', '1.0.0')}\n"
                    f"Nueva versión: {new_config.get('version', '1.0.0')}\n\n"
                    f"¿Desea aplicar la actualización ahora?"
                )
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                
                if msg.exec_() == QMessageBox.Yes:
                    self.apply_configuration_update(new_config)
            else:
                QMessageBox.information(
                    self,
                    "Sin actualizaciones",
                    f"Ya tiene la versión más reciente de la configuración.\n"
                    f"Versión actual: {self.config.get('version', '1.0.0')}"
                )
        except Exception as e:
            progress.close()
            QMessageBox.warning(
                self,
                "Error de verificación",
                f"No se pudo verificar las actualizaciones:\n{str(e)}"
            )
    
    def apply_configuration_update(self, new_config):
        """Aplica una actualización de configuración"""
        try:
            if apply_update(new_config):
                QMessageBox.information(
                    self,
                    "Actualización Aplicada",
                    f"La configuración ha sido actualizada a la versión {new_config.get('version', '1.0.0')}.\n"
                    f"Algunos cambios requerirán reiniciar la aplicación para aplicarse completamente."
                )
                
                # Actualizar configuración en memoria
                self.config = new_config
                self.dashboards = new_config.get('dashboards', {})
                
                # Actualizar privilegios del usuario
                self.is_authorized = is_authorized_user(self.current_username, new_config.get('authorized_users', []))
                self.is_admin = is_admin_user(self.current_username, new_config.get('admin_users', []))
                
                # Actualizar interfaz
                self.refresh_dashboard_list()
                
            else:
                QMessageBox.warning(
                    self,
                    "Error de Actualización",
                    "No se pudo aplicar la actualización. Inténtelo nuevamente más tarde."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Crítico",
                f"Error al aplicar la actualización:\n{str(e)}"
            )
    
    def open_dashboard(self, url, title):
        """
        *** MÉTODO CRÍTICO: AQUÍ SE INTEGRA LA FUNCIONALIDAD DE DESCARGA ***
        """
        # Inicializar la lista de visualizadores para este dashboard si no existe
        if title not in self.open_viewers:
            self.open_viewers[title] = []
        
        # Limpiar referencias a ventanas cerradas
        self.purge_closed_windows(title)
        
        # Obtener lista actual de visualizadores activos
        active_viewers = self.open_viewers[title]
        
        # Verificar si ya hay dos instancias abiertas
        if len(active_viewers) >= 2:
            QMessageBox.warning(
                self,
                "Advertencia",
                f"Ya has abierto dos ventanas del mismo dashboard '{title}'.",
                QMessageBox.Ok
            )
            return
        
        # Determinar el número de instancia para la nueva ventana
        instance_number = len(active_viewers) + 1
        
        # Actualizar barra de estado
        status_message = f"Abriendo tablero: {title} con descarga habilitada..."
        if self.is_admin:
            status_message += " [Administrador]"
        if self.config.get('encrypted', False):
            status_message += " [Cifrado]"
        self.statusBar().showMessage(status_message, 3000)
        
        # *** CREAR NUEVA INSTANCIA CON DOWNLOADMANAGER INTEGRADO ***
        print(f"🚀 Abriendo dashboard '{title}' con soporte de descargas")
        viewer = DatoramaViewer(url, title, instance_number)
        
        # Conectar la señal personalizada de cierre
        viewer.windowClosed.connect(self.on_viewer_closed)
        
        # Guardar la referencia a la nueva ventana
        self.open_viewers[title].append(viewer)
        
        # Actualizar los indicadores visuales
        self.update_indicators(title)
        
        # Mostrar la ventana
        viewer.show()
        
        print(f"✅ Dashboard '{title}' abierto exitosamente con descarga habilitada")
    
    def on_viewer_closed(self, title):
        """Método para manejar el cierre de una ventana de visualización"""
        QTimer.singleShot(100, lambda: self.update_dashboard_button(title))
    
    def update_dashboard_button(self, title):
        """Actualiza un botón específico después de que cambia el estado"""
        self.purge_closed_windows(title)
        self.update_indicators(title)
    
    def purge_closed_windows(self, title):
        """Elimina referencias a ventanas cerradas"""
        if title in self.open_viewers:
            active_viewers = []
            for viewer in self.open_viewers[title]:
                try:
                    if viewer.isVisible() and not viewer.isHidden():
                        active_viewers.append(viewer)
                except RuntimeError:
                    pass
            self.open_viewers[title] = active_viewers
    
    def update_indicators(self, title):
        """Actualiza los indicadores visuales para un dashboard específico"""
        if title in self.dashboard_buttons and title in self.open_viewers:
            count = len(self.open_viewers[title])
            self.dashboard_buttons[title].update_indicators(count)
    
    def closeEvent(self, event):
        """Cierra todas las ventanas abiertas cuando se cierra la ventana principal"""
        # Detener timers
        if hasattr(self, 'user_check_timer'):
            self.user_check_timer.stop()
            print("🛑 Verificación periódica de usuario detenida")

        # Cerrar todas las ventanas de dashboards
        self.close_all_dashboard_windows()

        # Continuar con el cierre normal
        event.accept()

# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    # Verificar disponibilidad de cifrado al inicio
    if not ENCRYPTION_AVAILABLE:
        print("⚠️ ADVERTENCIA: Librería 'cryptography' no encontrada")
        print("   Para habilitar el cifrado de URLs, instale: pip install cryptography")
        print("   La aplicación funcionará normalmente pero sin cifrado\n")
    else:
        print("🔐 Sistema de cifrado AES-256 disponible")
        print(f"🔑 Clave de cifrado configurada: {ENCRYPTION_SECRET[:20]}...\n")
    
    # Configurar proxy antes de hacer cualquier cosa
    configure_proxy_environment()
    
    # Inicializar aplicación
    app = QApplication(sys.argv)
    
    # Establecer el icono para toda la aplicación
    try:
        icon_path = resource_path("walmart.ico")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            app.setWindowIcon(app_icon)
            print(f"Icono de aplicación establecido desde: {icon_path}")
    except Exception as e:
        print(f"Error al establecer el icono de la aplicación: {e}")
    
    # Crear splash screen
    try:
        splash_paths = [
            resource_path("home.png"),
            "home.png",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "home.png")
        ]
        
        splash_pixmap = None
        for path in splash_paths:
            if os.path.exists(path):
                splash_pixmap = QPixmap(path)
                if not splash_pixmap.isNull():
                    print(f"Imagen de splash cargada desde: {path}")
                    break
        
        if splash_pixmap is None or splash_pixmap.isNull():
            print("No se encontró imagen de splash, creando una por defecto")
            splash_pixmap = QPixmap(400, 300)
            splash_pixmap.fill(Qt.white)
            
        splash_pixmap = splash_pixmap.scaled(1200, 800, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        splash = QSplashScreen(splash_pixmap)
        splash.show()
        
        # Mensaje en splash screen adaptado al entorno
        splash_message = ""
        if detect_corporate_network():
            splash_message = "🏢 Cargando configuración desde GitHub (red corporativa)"
        else:
            splash_message = "🌐 Cargando configuración desde GitHub (red externa)"
        
        if ENCRYPTION_AVAILABLE:
            splash_message += " 🔐"
        
        splash_message += " 🔽"  # Indicador de descarga
        
        splash.showMessage(splash_message, Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    except Exception as e:
        print(f"Error al crear el splash screen: {e}")
        splash_pixmap = QPixmap(400, 300)
        splash_pixmap.fill(Qt.white)
        splash = QSplashScreen(splash_pixmap)
        splash.show()
        splash.showMessage("Cargando aplicación con descarga habilitada...", Qt.AlignCenter, Qt.black)
    
    # Procesar eventos
    app.processEvents()
    
    # Mostrar información del entorno de red
    if detect_corporate_network():
        print(f"🏢 ENTORNO: Red corporativa detectada")
        print(f"🔄 PROXY: {CORPORATE_PROXY}")
    else:
        print(f"🌐 ENTORNO: Red externa detectada")
        print(f"🔗 CONEXIÓN: Directa (sin proxy)")
    
    print(f"🔽 FUNCIONALIDAD: Descarga de archivos HABILITADA")
    
    # Cargar configuración (SIEMPRE desde GitHub primero)
    config = load_config()

    # Mostrar información sobre verificación periódica
    if PERIODIC_USER_CHECK:
        print(f"🛡️ Verificación periódica de usuarios: ACTIVADA (cada {USER_CHECK_INTERVAL} minutos)")
    else:
        print("⚠️ Verificación periódica de usuarios: DESACTIVADA")
    
    # Mostrar mensaje si estamos usando configuración local
    if config.get('using_local_config', False):
        splash.showMessage("⚠️ Usando configuración local...", Qt.AlignBottom | Qt.AlignCenter, Qt.yellow)
        app.processEvents()
        
        QTimer.singleShot(500, lambda: QMessageBox.warning(
            None,
            "Configuración Local",
            "No se pudo conectar al repositorio remoto de GitHub.\n"
            "La aplicación está usando la última configuración local disponible.\n"
            "Se seguirán realizando intentos para conectar con GitHub en segundo plano.\n\n"
            f"Entorno detectado: {'Red corporativa' if detect_corporate_network() else 'Red externa'}\n"
            f"Cifrado: {'Disponible' if ENCRYPTION_AVAILABLE else 'No disponible'}\n"
            f"Descarga: Habilitada"
        ))

    # Actualizar mensaje de carga
    splash.showMessage("Verificando acceso...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()
    
    # Verificar red corporativa
    if not is_corporate_network(config):
        splash.close()
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Warning)
        error_box.setWindowTitle("Acceso Denegado")
        error_box.setText("Acceso denegado. Solo se puede acceder desde la red corporativa de Walmart.")
        
        net_info = get_network_info()
        ip_pattern = r'Direcci.n IPv4[.\s]*: ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)'
        ip_matches = re.findall(ip_pattern, net_info)
        ip_info = "Direcciones IP detectadas:\n" + "\n".join(ip_matches)
        
        error_box.setDetailedText(ip_info)
        error_box.exec_()
        sys.exit(1)
    
    # Verificar autorización de usuario
    current_user = get_current_username()
    print(f"👤 Usuario para validación: '{current_user}'")
    
    authorized_users = config.get('authorized_users', [])
    admin_users = config.get('admin_users', [])
    print(f"📋 Usuarios autorizados en configuración: {len(authorized_users)}")
    print(f"🔑 Administradores en configuración: {len(admin_users)}")
    
    if not current_user:
        splash.close()
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Error del Sistema")
        error_box.setText("No se pudo determinar el usuario actual del sistema.")
        error_box.setInformativeText("Por favor, contacte al administrador del sistema.")
        error_box.exec_()
        sys.exit(1)
    
    # Verificar autorización
    is_authorized = is_authorized_user(current_user, authorized_users)
    is_admin = is_admin_user(current_user, admin_users)
    
    if not is_authorized:
        splash.close()
        
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Warning)
        error_box.setWindowTitle("Acceso Denegado")
        error_box.setText(f"Acceso denegado para el usuario: '{current_user}'")
        info_text = f"""
El usuario '{current_user}' no está autorizado para usar esta aplicación.

Configuración cargada desde: {'GitHub' if not config.get('using_local_config') else 'Archivo local'}
Entorno de red: {'Corporativa (con proxy)' if detect_corporate_network() else 'Externa (directa)'}
Cifrado: {'Habilitado' if ENCRYPTION_AVAILABLE else 'No disponible'}
Descarga: Habilitada
Versión: {config.get('version', 'N/A')}
Usuarios autorizados: {len(authorized_users)}
Administradores: {len(admin_users)}

Por favor, contacte al área de DATA para solicitar acceso.
"""
        error_box.setInformativeText(info_text)
        error_box.exec_()
        sys.exit(1)
    
    # Si llegamos aquí, el usuario está autorizado
    auth_message = f"✅ Acceso concedido al usuario: {current_user}"
    if is_admin:
        auth_message += " (ADMINISTRADOR)"
    print(auth_message)
    print(f"🔽 Funcionalidad de descarga: HABILITADA")
    
    # Actualizar mensaje de carga
    final_message = "Iniciando aplicación con descarga..."
    if is_admin:
        final_message += " [ADMINISTRADOR]"
    if detect_corporate_network():
        final_message += " [Red Corporativa]"
    if config.get('encrypted', False):
        final_message += " [Cifrado]"
    splash.showMessage(final_message, Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()
    
    # Crear la ventana de selección de tableros
    selector = DashboardSelector(config)
    
    # Mostrar la pantalla de inicio durante 3 segundos
    QTimer.singleShot(3000, lambda: [splash.finish(selector), selector.show()])
    
    print(f"\n🎉 ¡APLICACIÓN INICIADA EXITOSAMENTE!")
    print(f"   ✅ Usuario autorizado: {current_user}")
    print(f"   🔽 Descarga de archivos: HABILITADA")
    print(f"   🔐 Cifrado: {'Disponible' if ENCRYPTION_AVAILABLE else 'No disponible'}")
    print(f"   🌐 Red: {'Corporativa' if detect_corporate_network() else 'Externa'}")
    print(f"   📊 Dashboards disponibles: {len(config.get('dashboards', {}))}")
    
    # Ejecutar la aplicación
    sys.exit(app.exec_())

# Función auxiliar para administradores
def create_encrypted_config():
    """
    Función para que los administradores puedan crear el archivo cifrado inicial
    Ejecutar esta función por separado para generar el archivo cifrado
    """
    print("🔐 Generando archivo de configuración cifrado...")
    filename = create_encrypted_config_file()
    
    if filename:
        print(f"\n✅ ARCHIVO CREADO EXITOSAMENTE: {filename}")
        print(f"📤 Suba este archivo a GitHub para reemplazar la configuración actual")
        print(f"🔒 Las URLs han sido cifradas con AES-256")
    else:
        print(f"\n❌ ERROR: No se pudo crear el archivo cifrado")

if __name__ == '__main__':
    # Si se ejecuta con argumento 'encrypt', crear archivo cifrado
    if len(sys.argv) > 1 and sys.argv[1] == 'encrypt':
        create_encrypted_config()
    else:
        main()