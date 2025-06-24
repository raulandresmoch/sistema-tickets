"""
Google Drive API Integration for Ticket System - Versión con manejo de errores mejorado
Sincronización automática de tickets y archivos adjuntos
"""

import os
import json
import sqlite3
import pickle
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError
import io
import webbrowser

# Configuración
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
FOLDER_NAME = 'Sistema-Tickets-Data'

class GoogleDriveManager:
    def __init__(self):
        self.service = None
        self.authenticated = False
        self.folder_id = None
        self.auth_error = None
        self.init_drive_connection()
    
    def init_drive_connection(self):
        """Inicializa la conexión con Google Drive con manejo de errores mejorado"""
        try:
            creds = None
            
            # Verificar que existe credentials.json
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"❌ Archivo {CREDENTIALS_FILE} no encontrado")
                print("💡 Descarga credentials.json desde Google Cloud Console:")
                print("   https://console.cloud.google.com/apis/credentials")
                return False
            
            # Cargar token existente
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)
            
            # Si no hay credenciales válidas, obtenerlas
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    print("🔄 Renovando token de Google Drive...")
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        print(f"❌ Error renovando token: {e}")
                        # Eliminar token corrupto
                        if os.path.exists(TOKEN_FILE):
                            os.remove(TOKEN_FILE)
                        creds = None
                
                if not creds:
                    print("🔐 Iniciando proceso de autenticación con Google...")
                    print("📋 INSTRUCCIONES IMPORTANTES:")
                    print("   1. Se abrirá tu navegador automáticamente")
                    print("   2. Inicia sesión con tu cuenta Google")
                    print("   3. Si aparece 'Esta app no está verificada':")
                    print("      - Click en 'Configuración avanzada'")
                    print("      - Click en 'Ir a Sistema de Tickets (no seguro)'")
                    print("   4. Acepta los permisos solicitados")
                    print("   5. Espera a que aparezca 'Authentication complete'")
                    print("=" * 60)
                    
                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            CREDENTIALS_FILE, SCOPES)
                        
                        # Configurar servidor local con puerto diferente si hay conflicto
                        creds = flow.run_local_server(
                            port=8080,
                            prompt='consent',
                            authorization_prompt_message='Abriendo navegador para autenticación...',
                            success_message='✅ Autenticación completada! Puedes cerrar esta ventana.',
                            open_browser=True
                        )
                        
                    except Exception as e:
                        print(f"❌ Error en autenticación: {e}")
                        self.auth_error = str(e)
                        
                        # Sugerencias específicas según el error
                        if "access_denied" in str(e):
                            print("\n🔧 SOLUCIONES PARA ERROR 403:")
                            print("1. Ve a Google Cloud Console:")
                            print("   https://console.cloud.google.com/apis/credentials/consent")
                            print("2. Configura OAuth Consent Screen")
                            print("3. Agrega tu email como 'Test User'")
                            print("4. Habilita Google Drive API en:")
                            print("   https://console.cloud.google.com/apis/library")
                            print("5. Verifica que el redirect URI sea: http://localhost:8080/")
                        
                        return False
                
                # Guardar token para la próxima ejecución
                if creds:
                    with open(TOKEN_FILE, 'wb') as token:
                        pickle.dump(creds, token)
                    print("💾 Token guardado para futuras ejecuciones")
            
            # Construir servicio
            self.service = build('drive', 'v3', credentials=creds)
            self.authenticated = True
            
            # Crear/encontrar carpeta del sistema
            success = self.setup_system_folder()
            if not success:
                return False
            
            print("✅ Google Drive conectado exitosamente")
            return True
            
        except HttpError as e:
            print(f"❌ Error HTTP de Google API: {e}")
            self.auth_error = f"HTTP Error: {e}"
            self.authenticated = False
            return False
        except Exception as e:
            print(f"❌ Error conectando Google Drive: {e}")
            self.auth_error = str(e)
            self.authenticated = False
            return False
    
    def setup_system_folder(self):
        """Crea o encuentra la carpeta del sistema en Google Drive"""
        try:
            # Buscar carpeta existente
            results = self.service.files().list(
                q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                print(f"✅ Carpeta encontrada: {FOLDER_NAME}")
            else:
                # Crear nueva carpeta
                folder_metadata = {
                    'name': FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                self.folder_id = folder.get('id')
                print(f"✅ Carpeta creada: {FOLDER_NAME}")
            
            return True
            
        except HttpError as e:
            print(f"❌ Error HTTP configurando carpeta: {e}")
            return False
        except Exception as e:
            print(f"❌ Error configurando carpeta: {e}")
            return False
    
    def test_connection(self):
        """Prueba la conexión con Google Drive"""
        try:
            if not self.authenticated:
                return False, "No autenticado"
            
            # Intentar listar archivos en la carpeta raíz
            results = self.service.files().list(
                pageSize=1,
                fields="files(id, name)"
            ).execute()
            
            return True, "Conexión exitosa"
            
        except HttpError as e:
            return False, f"Error HTTP: {e}"
        except Exception as e:
            return False, f"Error: {e}"
    
    def upload_database(self, db_path='tickets.db'):
        """Sube la base de datos a Google Drive"""
        try:
            if not self.authenticated or not os.path.exists(db_path):
                return False
            
            # Buscar archivo existente
            results = self.service.files().list(
                q=f"name='tickets.db' and parents='{self.folder_id}' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            media = MediaFileUpload(db_path, mimetype='application/octet-stream')
            
            if files:
                # Actualizar archivo existente
                file_id = files[0]['id']
                updated_file = self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                print("✅ Base de datos actualizada en Google Drive")
            else:
                # Crear nuevo archivo
                file_metadata = {
                    'name': 'tickets.db',
                    'parents': [self.folder_id]
                }
                
                created_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                print("✅ Base de datos subida a Google Drive")
            
            return True
            
        except HttpError as e:
            print(f"❌ Error HTTP subiendo base de datos: {e}")
            return False
        except Exception as e:
            print(f"❌ Error subiendo base de datos: {e}")
            return False
    
    def download_database(self, db_path='tickets.db'):
        """Descarga la base de datos desde Google Drive"""
        try:
            if not self.authenticated:
                return False
            
            # Buscar archivo
            results = self.service.files().list(
                q=f"name='tickets.db' and parents='{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                print("⚠️ No se encontró base de datos en Google Drive")
                return False
            
            file_id = files[0]['id']
            
            # Descargar archivo
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Guardar archivo
            with open(db_path, 'wb') as f:
                f.write(fh.getvalue())
            
            print("✅ Base de datos descargada desde Google Drive")
            return True
            
        except HttpError as e:
            print(f"❌ Error HTTP descargando base de datos: {e}")
            return False
        except Exception as e:
            print(f"❌ Error descargando base de datos: {e}")
            return False
    
    def upload_attachment(self, file_path, ticket_id):
        """Sube un archivo adjunto a Google Drive"""
        try:
            if not self.authenticated or not os.path.exists(file_path):
                return None
            
            filename = os.path.basename(file_path)
            
            # Crear subcarpeta para attachments si no existe
            attachments_folder_id = self.get_or_create_attachments_folder()
            
            file_metadata = {
                'name': f"ticket_{ticket_id}_{filename}",
                'parents': [attachments_folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size'
            ).execute()
            
            print(f"✅ Archivo adjunto subido: {filename}")
            
            return {
                'drive_id': uploaded_file.get('id'),
                'name': uploaded_file.get('name'),
                'size': uploaded_file.get('size'),
                'original_name': filename
            }
            
        except HttpError as e:
            print(f"❌ Error HTTP subiendo archivo adjunto: {e}")
            return None
        except Exception as e:
            print(f"❌ Error subiendo archivo adjunto: {e}")
            return None
    
    def get_or_create_attachments_folder(self):
        """Obtiene o crea la carpeta de archivos adjuntos"""
        try:
            # Buscar carpeta existente
            results = self.service.files().list(
                q=f"name='attachments' and parents='{self.folder_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                return folders[0]['id']
            else:
                # Crear carpeta
                folder_metadata = {
                    'name': 'attachments',
                    'parents': [self.folder_id],
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                return folder.get('id')
                
        except Exception as e:
            print(f"❌ Error con carpeta attachments: {e}")
            return self.folder_id  # Fallback a carpeta principal
    
    def sync_tickets_to_drive(self):
        """Sincroniza todos los datos a Google Drive"""
        try:
            if not self.authenticated:
                print("⚠️ Google Drive no autenticado")
                return False
            
            # Probar conexión antes de sincronizar
            success, message = self.test_connection()
            if not success:
                print(f"❌ Error de conexión: {message}")
                return False
            
            # Subir base de datos
            success = self.upload_database()
            
            if success:
                # Actualizar timestamp de última sincronización
                self.update_sync_timestamp()
                print("🔄 Sincronización a Drive completada")
            
            return success
            
        except Exception as e:
            print(f"❌ Error en sincronización a Drive: {e}")
            return False
    
    def sync_tickets_from_drive(self):
        """Sincroniza datos desde Google Drive"""
        try:
            if not self.authenticated:
                print("⚠️ Google Drive no autenticado")
                return False
            
            # Probar conexión antes de sincronizar
            success, message = self.test_connection()
            if not success:
                print(f"❌ Error de conexión: {message}")
                return False
            
            # Verificar si hay datos más recientes en Drive
            if self.check_drive_has_newer_data():
                # Hacer backup de datos locales
                backup_path = f"tickets_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                if os.path.exists('tickets.db'):
                    os.rename('tickets.db', backup_path)
                    print(f"📁 Backup creado: {backup_path}")
                
                # Descargar datos de Drive
                success = self.download_database()
                
                if success:
                    print("🔄 Sincronización desde Drive completada")
                    return True
                else:
                    # Restaurar backup si falla
                    if os.path.exists(backup_path):
                        os.rename(backup_path, 'tickets.db')
                        print("🔄 Backup restaurado")
                    return False
            else:
                print("ℹ️ Los datos locales están actualizados")
                return True
                
        except Exception as e:
            print(f"❌ Error en sincronización desde Drive: {e}")
            return False
    
    def check_drive_has_newer_data(self):
        """Verifica si Google Drive tiene datos más recientes"""
        try:
            # Buscar archivo en Drive
            results = self.service.files().list(
                q=f"name='tickets.db' and parents='{self.folder_id}' and trashed=false",
                fields="files(id, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                return False
            
            # Comparar fechas de modificación
            drive_modified = files[0]['modifiedTime']
            
            if not os.path.exists('tickets.db'):
                return True
            
            local_modified = datetime.fromtimestamp(
                os.path.getmtime('tickets.db')
            ).isoformat() + 'Z'
            
            return drive_modified > local_modified
            
        except Exception as e:
            print(f"❌ Error verificando fechas: {e}")
            return False
    
    def update_sync_timestamp(self):
        """Actualiza el timestamp de última sincronización"""
        try:
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            
            # Crear tabla de configuración si no existe
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Actualizar timestamp
            cursor.execute('''
                INSERT OR REPLACE INTO sync_config (key, value, updated_at)
                VALUES ('last_sync', ?, CURRENT_TIMESTAMP)
            ''', (datetime.now().isoformat(),))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error actualizando timestamp: {e}")
    
    def get_drive_status(self):
        """Obtiene el estado de la conexión con Google Drive"""
        if not self.authenticated:
            return {
                'status': 'Desconectado',
                'folder_id': None,
                'last_sync': None,
                'error': self.auth_error
            }
        
        try:
            # Probar conexión
            success, message = self.test_connection()
            if not success:
                return {
                    'status': 'Error',
                    'error': message
                }
            
            # Obtener último sync
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM sync_config WHERE key = "last_sync"')
            result = cursor.fetchone()
            last_sync = result[0] if result else 'Nunca'
            conn.close()
            
            return {
                'status': 'Conectado',
                'folder_id': self.folder_id,
                'last_sync': last_sync,
                'folder_name': FOLDER_NAME
            }
            
        except Exception as e:
            return {
                'status': 'Error',
                'error': str(e)
            }

def init_google_drive():
    """Función para inicializar Google Drive Manager"""
    try:
        drive_manager = GoogleDriveManager()
        return drive_manager
    except Exception as e:
        print(f"❌ Error inicializando Google Drive: {e}")
        return None

# Función de prueba con diagnósticos mejorados
if __name__ == "__main__":
    print("🧪 Probando conexión con Google Drive...")
    print("=" * 50)
    
    drive = init_google_drive()
    
    if drive and drive.authenticated:
        print("✅ Conexión exitosa!")
        
        # Probar funciones
        success, message = drive.test_connection()
        print(f"🔍 Test de conexión: {message}")
        
        # Probar sincronización
        if os.path.exists('tickets.db'):
            print("🔄 Probando sincronización...")
            success = drive.sync_tickets_to_drive()
            if success:
                print("✅ Sincronización exitosa!")
            else:
                print("❌ Error en sincronización")
        else:
            print("⚠️ No se encontró tickets.db para sincronizar")
            
        # Mostrar estado
        status = drive.get_drive_status()
        print(f"📊 Estado: {status}")
        
    else:
        print("❌ Error en la conexión")
        if drive and drive.auth_error:
            print(f"🔍 Detalles del error: {drive.auth_error}")
        
        print("\n🔧 PASOS PARA SOLUCIONAR:")
        print("1. Verificar credentials.json existe")
        print("2. Configurar OAuth Consent Screen en Google Cloud Console")
        print("3. Agregar tu email como Test User")
        print("4. Habilitar Google Drive API")
        print("5. Verificar redirect URI: http://localhost:8080/")