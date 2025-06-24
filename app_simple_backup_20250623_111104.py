"""
Sistema de Tickets - Versión con Google Drive
Incluye sincronización automática sin romper funcionalidad local
"""

import os
import json
import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.utils import secure_filename

from telegram_notifications import (
    telegram_notifier, notify_new_ticket_async, notify_ticket_update_async, 
    notify_ticket_comment_async, configure_notifications, get_notification_config,
    test_telegram_bot, send_telegram_test
)

# Intentar importar Google Drive (funciona sin él si no está disponible)
try:
    from google_drive_api import GoogleDriveManager, init_google_drive
    GOOGLE_DRIVE_AVAILABLE = True
    print("✅ Google Drive API disponible")
except ImportError as e:
    print(f"⚠️ Google Drive API no disponible: {e}")
    print("ℹ️ El sistema funcionará en modo local únicamente")
    GOOGLE_DRIVE_AVAILABLE = False

# Configuración de la aplicación
app = Flask(__name__)
app.secret_key = 'tu-clave-secreta-super-segura-cambiar-en-produccion'

# Configuración
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'docx'}
DATABASE = 'tickets.db'
AUTO_SYNC_INTERVAL = 300  # 5 minutos

# Crear carpetas necesarias
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class TicketSystemWithDrive:
    def __init__(self):
        self.init_database()
        self.drive_manager = None
        self.sync_thread = None
        
        # Inicializar Google Drive si está disponible
        if GOOGLE_DRIVE_AVAILABLE:
            self.init_google_drive()
        
        # Iniciar sincronización automática
        self.start_auto_sync()
        
        print("✅ Sistema de tickets inicializado")
        
    def init_database(self):
        """Inicializa la base de datos SQLite local"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                is_developer BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de tickets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT DEFAULT 'Abierto',
                user_id INTEGER,
                assigned_to INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                attachments TEXT,
                drive_attachments TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (assigned_to) REFERENCES users (id)
            )
        ''')
        
        # Tabla de comentarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                user_id INTEGER,
                comment TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabla de configuración de sincronización
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Crear usuarios por defecto
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, email, is_developer) 
            VALUES ('admin', 'admin@empresa.com', 1)
        ''')
        
        # Agregar algunos usuarios de ejemplo
        example_users = [
            ('juan.perez', 'juan.perez@empresa.com', 0),
            ('maria.garcia', 'maria.garcia@empresa.com', 0),
            ('carlos.dev', 'carlos.dev@empresa.com', 1),
            ('ana.support', 'ana.support@empresa.com', 1)
        ]
        
        for username, email, is_dev in example_users:
            cursor.execute('''
                INSERT OR IGNORE INTO users (username, email, is_developer) 
                VALUES (?, ?, ?)
            ''', (username, email, is_dev))
        
        conn.commit()
        conn.close()
        print("✅ Base de datos inicializada")

    def init_google_drive(self):
        """Inicializa la conexión con Google Drive"""
        try:
            self.drive_manager = init_google_drive()
            if self.drive_manager and self.drive_manager.authenticated:
                print("✅ Google Drive conectado exitosamente")
                # Sincronizar al inicio (opcional)
                threading.Thread(target=self.sync_from_drive, daemon=True).start()
            else:
                print("⚠️ Google Drive no se pudo autenticar")
        except Exception as e:
            print(f"❌ Error inicializando Google Drive: {e}")
            self.drive_manager = None

    def start_auto_sync(self):
        """Inicia la sincronización automática en background"""
        if self.drive_manager and self.drive_manager.authenticated:
            def auto_sync_worker():
                while True:
                    try:
                        time.sleep(AUTO_SYNC_INTERVAL)
                        print("🔄 Ejecutando sincronización automática...")
                        self.sync_to_drive()
                    except Exception as e:
                        print(f"❌ Error en sincronización automática: {e}")
            
            self.sync_thread = threading.Thread(target=auto_sync_worker, daemon=True)
            self.sync_thread.start()
            print(f"🔄 Sincronización automática iniciada (cada {AUTO_SYNC_INTERVAL//60} minutos)")

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    def sync_to_drive(self):
        """Sincroniza datos locales a Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            try:
                success = self.drive_manager.sync_tickets_to_drive()
                if success:
                    print("☁️ Sincronización a Drive exitosa")
                return success
            except Exception as e:
                print(f"❌ Error sincronizando a Drive: {e}")
                return False
        return False

    def sync_from_drive(self):
        """Sincroniza datos desde Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            try:
                success = self.drive_manager.sync_tickets_from_drive()
                if success:
                    print("☁️ Sincronización desde Drive exitosa")
                return success
            except Exception as e:
                print(f"❌ Error sincronizando desde Drive: {e}")
                return False
        return False

    def create_ticket(self, title, description, category, priority, user_id, attachments=None):
        """Crea un nuevo ticket"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Inicializar listas para attachments
        local_attachments = attachments or []
        drive_attachments = []
        
        # Subir archivos a Google Drive si está disponible
        if self.drive_manager and self.drive_manager.authenticated and attachments:
            for attachment in attachments:
                file_path = os.path.join(UPLOAD_FOLDER, attachment)
                if os.path.exists(file_path):
                    drive_info = self.drive_manager.upload_attachment(file_path, 0)  # ID temporal
                    if drive_info:
                        drive_attachments.append(drive_info)
        
        # Insertar ticket
        cursor.execute('''
            INSERT INTO tickets (title, description, category, priority, user_id, attachments, drive_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, category, priority, user_id, 
              json.dumps(local_attachments) if local_attachments else None,
              json.dumps(drive_attachments) if drive_attachments else None))
        
        ticket_id = cursor.lastrowid
        
        # Actualizar drive_attachments con el ID real del ticket
        if drive_attachments:
            for i, attachment in enumerate(drive_attachments):
                # Re-subir con ID correcto (opcional, o mantener como está)
                pass
        
        conn.commit()
        conn.close()
        
        # Notificación
        self.log_notification(ticket_id, 'new', title)
        
        # Sincronizar a Drive en background
        if self.drive_manager:
            threading.Thread(target=self.sync_to_drive, daemon=True).start()
        
        print(f"✅ Ticket #{ticket_id} creado: {title}")
        return ticket_id

    def get_tickets(self, user_id=None, is_developer=False):
        """Obtiene tickets según el tipo de usuario"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        if is_developer:
            # Desarrolladores ven todos los tickets
            cursor.execute('''
                SELECT t.*, u.username as user_name, d.username as developer_name
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN users d ON t.assigned_to = d.id
                ORDER BY 
                    CASE t.status 
                        WHEN 'Abierto' THEN 1
                        WHEN 'En Progreso' THEN 2
                        WHEN 'Resuelto' THEN 3
                        ELSE 4
                    END,
                    CASE t.priority
                        WHEN 'Critical' THEN 1
                        WHEN 'High' THEN 2
                        WHEN 'Medium' THEN 3
                        WHEN 'Low' THEN 4
                        ELSE 5
                    END,
                    t.created_at DESC
            ''')
        else:
            # Usuarios normales solo ven sus tickets
            cursor.execute('''
                SELECT t.*, u.username as user_name, d.username as developer_name
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN users d ON t.assigned_to = d.id
                WHERE t.user_id = ?
                ORDER BY t.created_at DESC
            ''', (user_id,))
        
        tickets = cursor.fetchall()
        conn.close()
        
        return tickets

    def update_ticket_status(self, ticket_id, status, assigned_to=None, comment=None):
        """Actualiza el estado de un ticket"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        if status == 'Resuelto':
            cursor.execute('''
                UPDATE tickets 
                SET status = ?, assigned_to = ?, updated_at = CURRENT_TIMESTAMP, resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, assigned_to, ticket_id))
        else:
            cursor.execute('''
                UPDATE tickets 
                SET status = ?, assigned_to = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, assigned_to, ticket_id))
        
        # Agregar comentario si se proporciona
        if comment and assigned_to:
            cursor.execute('''
                INSERT INTO comments (ticket_id, user_id, comment)
                VALUES (?, ?, ?)
            ''', (ticket_id, assigned_to, comment))
        
        conn.commit()
        conn.close()
        
        # Notificación
        self.log_notification(ticket_id, 'update', f"Estado cambiado a: {status}")
        
        # Sincronizar a Drive en background
        if self.drive_manager:
            threading.Thread(target=self.sync_to_drive, daemon=True).start()
        
        print(f"✅ Ticket #{ticket_id} actualizado a: {status}")

    def log_notification(self, ticket_id, action, details):
        """Registra notificaciones en lugar de enviar emails"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] TICKET #{ticket_id} - {action.upper()}: {details}"
        
        # Escribir a archivo de log
        try:
            with open('notifications.log', 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f"Error escribiendo log: {e}")
        
        # Mostrar en consola
        print(f"📧 NOTIFICACIÓN: {log_message}")

    def get_statistics(self):
        """Obtiene estadísticas del sistema"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Estadísticas básicas
        cursor.execute('SELECT COUNT(*) FROM tickets')
        total_tickets = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Abierto'")
        open_tickets = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'En Progreso'")
        in_progress_tickets = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resuelto'")
        resolved_tickets = cursor.fetchone()[0]
        
        # Estadísticas por categoría
        cursor.execute('''
            SELECT category, COUNT(*) 
            FROM tickets 
            GROUP BY category 
            ORDER BY COUNT(*) DESC
        ''')
        tickets_by_category = cursor.fetchall()
        
        # Estadísticas por prioridad
        cursor.execute('''
            SELECT priority, COUNT(*) 
            FROM tickets 
            GROUP BY priority 
            ORDER BY 
                CASE priority
                    WHEN 'Critical' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Medium' THEN 3
                    WHEN 'Low' THEN 4
                END
        ''')
        tickets_by_priority = cursor.fetchall()
        
        # Tiempo promedio de resolución
        cursor.execute('''
            SELECT AVG(
                (julianday(resolved_at) - julianday(created_at)) * 24
            ) as avg_hours
            FROM tickets 
            WHERE resolved_at IS NOT NULL
        ''')
        avg_resolution_time = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'in_progress_tickets': in_progress_tickets,
            'resolved_tickets': resolved_tickets,
            'tickets_by_category': tickets_by_category,
            'tickets_by_priority': tickets_by_priority,
            'avg_resolution_hours': round(avg_resolution_time or 0, 1)
        }

    def get_system_status(self):
        """Obtiene el estado del sistema"""
        status = {
            'database': 'OK',
            'google_drive': 'No configurado',
            'email': 'Modo Log (notifications.log)',
            'auto_sync': 'Deshabilitado'
        }
        
        if self.drive_manager:
            drive_status = self.drive_manager.get_drive_status()
            status['google_drive'] = drive_status.get('status', 'Error')
            status['drive_details'] = drive_status
            
            if self.sync_thread and self.sync_thread.is_alive():
                status['auto_sync'] = 'Activo'
        
        return status

    def get_recent_notifications(self, limit=10):
        """Obtiene las notificaciones recientes del log"""
        try:
            if os.path.exists('notifications.log'):
                with open('notifications.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    return lines[-limit:] if len(lines) > limit else lines
            return []
        except Exception as e:
            print(f"Error leyendo notificaciones: {e}")
            return []

    def manual_sync_to_drive(self):
        """Sincronización manual a Google Drive"""
        return self.sync_to_drive()

    def manual_sync_from_drive(self):
        """Sincronización manual desde Google Drive"""
        return self.sync_from_drive()

# Instancia global del sistema
ticket_system = TicketSystemWithDrive()

# Agregar filtro personalizado para JSON
@app.template_filter('from_json')
def from_json_filter(value):
    """Filtro para convertir string JSON a lista/dict"""
    if value:
        try:
            return json.loads(value)
        except:
            return []
    return []

# Rutas de la aplicación Flask
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['is_developer'] = user[4]
        flash(f'Bienvenido {user[1]}!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Usuario no encontrado o inactivo', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    username = session.get('username', 'Usuario')
    session.clear()
    flash(f'Hasta luego {username}!', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Debes iniciar sesión primero', 'warning')
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    is_developer = session['is_developer']
    
    tickets = ticket_system.get_tickets(user_id, is_developer)
    stats = ticket_system.get_statistics()
    system_status = ticket_system.get_system_status()
    recent_notifications = ticket_system.get_recent_notifications(5)
    
    return render_template('dashboard.html', 
                         tickets=tickets, 
                         stats=stats,
                         system_status=system_status,
                         notifications=recent_notifications,
                         user={'id': user_id, 'username': session['username'], 'is_developer': is_developer})

@app.route('/new_ticket')
def new_ticket():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    return render_template('new_ticket.html', user_id=session['user_id'])

@app.route('/create_ticket', methods=['POST'])
def create_ticket():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    title = request.form['title']
    description = request.form['description']
    category = request.form['category']
    priority = request.form['priority']
    
    # Obtener información del usuario para notificaciones
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    username = cursor.fetchone()[0]
    conn.close()
    
    # Manejar archivos adjuntos
    attachments = []
    if 'attachments' in request.files:
        files = request.files.getlist('attachments')
        for file in files:
            if file and ticket_system.allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                attachments.append(filename)
    
    ticket_id = ticket_system.create_ticket(title, description, category, priority, user_id, attachments)
    
    # Enviar notificación a desarrolladores
    notify_new_ticket_async(ticket_id, title, username, priority, category)
    
    flash(f'Ticket #{ticket_id} creado exitosamente: {title}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/update_ticket', methods=['POST'])
def update_ticket():
    if 'user_id' not in session or not session['is_developer']:
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('dashboard'))
    
    ticket_id = int(request.form['ticket_id'])
    status = request.form['status']
    comment = request.form.get('comment', '')
    
    ticket_system.update_ticket_status(ticket_id, status, session['user_id'], comment)
    
    flash(f'Ticket #{ticket_id} actualizado a: {status}', 'success')
    return redirect(url_for('dashboard'))

# NUEVAS RUTAS PARA GOOGLE DRIVE
@app.route('/sync_drive', methods=['POST'])
def sync_drive():
    """Endpoint para sincronización manual con Google Drive"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    direction = request.json.get('direction', 'up')
    
    try:
        if direction == 'up':
            success = ticket_system.manual_sync_to_drive()
            message = 'Sincronización a Drive ' + ('exitosa' if success else 'fallida')
        elif direction == 'down':
            success = ticket_system.manual_sync_from_drive()
            message = 'Sincronización desde Drive ' + ('exitosa' if success else 'fallida')
        else:
            success = False
            message = 'Dirección de sincronización inválida'
        
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/drive_status')
def drive_status():
    """Endpoint para obtener estado de Google Drive"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'error': 'Sin permisos'}), 403
    
    if ticket_system.drive_manager:
        status = ticket_system.drive_manager.get_drive_status()
        return jsonify(status)
    else:
        return jsonify({'status': 'No configurado'})

@app.route('/api/stats')
def api_stats():
    """API endpoint para estadísticas en tiempo real"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    stats = ticket_system.get_statistics()
    system_status = ticket_system.get_system_status()
    
    return jsonify({
        'stats': stats,
        'system_status': system_status
    })

@app.route('/download_attachment/<int:ticket_id>/<filename>')
def download_attachment(ticket_id, filename):
    """Descarga archivos adjuntos"""
    if 'user_id' not in session:
        flash('Debes iniciar sesión para descargar archivos', 'error')
        return redirect(url_for('index'))
    
    # Verificar que el usuario tenga acceso al ticket
    user_id = session['user_id']
    is_developer = session['is_developer']
    
    # Obtener información del ticket
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, attachments FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    conn.close()
    
    if not ticket:
        flash('Ticket no encontrado', 'error')
        return redirect(url_for('dashboard'))
    
    # Verificar permisos
    if not is_developer and ticket[0] != user_id:
        flash('No tienes permisos para descargar este archivo', 'error')
        return redirect(url_for('dashboard'))
    
    # Buscar el archivo
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(file_path):
        flash('Archivo no encontrado', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        from flask import send_file
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'Error descargando archivo: {e}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/view_ticket/<int:ticket_id>')
def view_ticket(ticket_id):
    """Vista detallada de un ticket"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    is_developer = session['is_developer']
    
    # Obtener ticket completo
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.*, u.username as user_name, u.email as user_email, 
               d.username as developer_name, d.email as developer_email
        FROM tickets t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN users d ON t.assigned_to = d.id
        WHERE t.id = ?
    ''', (ticket_id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        flash('Ticket no encontrado', 'error')
        return redirect(url_for('dashboard'))
    
    # Verificar permisos
    if not is_developer and ticket[6] != user_id:
        flash('No tienes permisos para ver este ticket', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener comentarios
    cursor.execute('''
        SELECT c.*, u.username
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.ticket_id = ?
        ORDER BY c.created_at ASC
    ''', (ticket_id,))
    
    comments = cursor.fetchall()
    
    # Obtener lista de desarrolladores para asignación
    cursor.execute('SELECT id, username FROM users WHERE is_developer = 1 AND is_active = 1')
    developers = cursor.fetchall()
    
    conn.close()
    
    # Procesar archivos adjuntos
    attachments = []
    if ticket[11]:  # ticket[11] es la columna attachments
        try:
            attachment_list = json.loads(ticket[11])
            for filename in attachment_list:
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file_exists = os.path.exists(file_path)
                file_size = 0
                if file_exists:
                    file_size = os.path.getsize(file_path)
                
                attachments.append({
                    'filename': filename,
                    'original_name': filename.split('_', 2)[-1] if '_' in filename else filename,
                    'exists': file_exists,
                    'size': file_size,
                    'download_url': url_for('download_attachment', ticket_id=ticket_id, filename=filename)
                })
        except json.JSONDecodeError:
            pass
    
    return render_template('view_ticket.html', 
                         ticket=ticket, 
                         comments=comments,
                         developers=developers,
                         attachments=attachments,
                         user={'id': user_id, 'username': session['username'], 'is_developer': is_developer})

@app.route('/add_comment', methods=['POST'])
def add_comment():
    """Agregar comentario a un ticket"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    ticket_id = int(request.form['ticket_id'])
    comment_text = request.form['comment'].strip()
    
    if not comment_text:
        flash('El comentario no puede estar vacío', 'error')
        return redirect(url_for('view_ticket', ticket_id=ticket_id))
    
    # Agregar comentario
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO comments (ticket_id, user_id, comment)
        VALUES (?, ?, ?)
    ''', (ticket_id, session['user_id'], comment_text))
    
    # Actualizar timestamp del ticket
    cursor.execute('''
        UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
    ''', (ticket_id,))
    
    conn.commit()
    conn.close()
    
    # Log de notificación
    ticket_system.log_notification(ticket_id, 'comment', f'Comentario agregado por {session["username"]}')
    
    # Sincronizar a Drive en background
    if ticket_system.drive_manager:
        threading.Thread(target=ticket_system.sync_to_drive, daemon=True).start()
    
    flash('Comentario agregado exitosamente', 'success')
    return redirect(url_for('view_ticket', ticket_id=ticket_id))

@app.route('/assign_ticket', methods=['POST'])
def assign_ticket():
    """Asignar ticket a un desarrollador"""
    if 'user_id' not in session or not session['is_developer']:
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('dashboard'))
    
    ticket_id = int(request.form['ticket_id'])
    assigned_to = int(request.form['assigned_to']) if request.form['assigned_to'] else None
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tickets 
        SET assigned_to = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (assigned_to, ticket_id))
    conn.commit()
    conn.close()
    
    if assigned_to:
        cursor = sqlite3.connect(DATABASE).cursor()
        cursor.execute('SELECT username FROM users WHERE id = ?', (assigned_to,))
        dev_name = cursor.fetchone()[0]
        ticket_system.log_notification(ticket_id, 'assign', f'Ticket asignado a {dev_name}')
        flash(f'Ticket asignado a {dev_name}', 'success')
    else:
        ticket_system.log_notification(ticket_id, 'unassign', 'Ticket sin asignar')
        flash('Asignación removida del ticket', 'info')
    
    # Sincronizar a Drive en background
    if ticket_system.drive_manager:
        threading.Thread(target=ticket_system.sync_to_drive, daemon=True).start()
    
    return redirect(url_for('view_ticket', ticket_id=ticket_id))

@app.route('/notifications')
def notifications():
    """Página para ver todas las notificaciones"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    all_notifications = ticket_system.get_recent_notifications(50)
    return render_template('notifications.html', notifications=all_notifications)

@app.route('/admin')
def admin_panel():
    """Panel de administración - solo para admin"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Verificar que sea admin
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT username, is_developer FROM users WHERE id = ? AND is_active = 1', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or user[0] != 'admin':
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener lista de usuarios
    cursor.execute('''
        SELECT id, username, email, is_active, is_developer, created_at, full_name
        FROM users 
        ORDER BY is_active DESC, is_developer DESC, username
    ''')
    users = cursor.fetchall()
    
    conn.close()
    
    # Obtener configuración de notificaciones
    notification_config = get_notification_config()
    
    return render_template('admin_panel.html', 
                         users=users, 
                         notification_config=notification_config,
                         user={'username': session['username']})

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    """Agregar nuevo usuario"""
    if 'user_id' not in session or session.get('username') != 'admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    username = request.form['username'].strip()
    email = request.form['email'].strip()
    full_name = request.form.get('full_name', '').strip()
    is_developer = 'is_developer' in request.form
    
    if not username or not email:
        flash('Usuario y email son obligatorios', 'error')
        return redirect(url_for('admin_panel'))
    
    # Validar formato de username
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        flash('El nombre de usuario solo puede contener letras, números, puntos, guiones y guiones bajos', 'error')
        return redirect(url_for('admin_panel'))
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        # Verificar que no exista el usuario
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash(f'El usuario {username} ya existe', 'error')
            return redirect(url_for('admin_panel'))
        
        # Agregar tabla full_name si no existe
        cursor.execute('PRAGMA table_info(users)')
        columns = [row[1] for row in cursor.fetchall()]
        if 'full_name' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN full_name TEXT')
        
        # Insertar usuario
        cursor.execute('''
            INSERT INTO users (username, email, full_name, is_developer, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (username, email, full_name, is_developer))
        
        conn.commit()
        flash(f'Usuario {username} creado exitosamente', 'success')
        
    except sqlite3.IntegrityError:
        flash(f'Error: El usuario {username} ya existe', 'error')
    except Exception as e:
        flash(f'Error creando usuario: {e}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_user', methods=['POST'])
def admin_toggle_user():
    """Activar/desactivar usuario"""
    if 'user_id' not in session or session.get('username') != 'admin':
        return jsonify({'success': False, 'message': 'Acceso denegado'})
    
    data = request.get_json()
    user_id = data.get('user_id')
    is_active = data.get('is_active')
    
    if not user_id:
        return jsonify({'success': False, 'message': 'ID de usuario requerido'})
    
    # No permitir desactivar admin
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if user and user[0] == 'admin':
        return jsonify({'success': False, 'message': 'No se puede desactivar el usuario admin'})
    
    try:
        cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (is_active, user_id))
        conn.commit()
        
        action = 'activado' if is_active else 'desactivado'
        return jsonify({'success': True, 'message': f'Usuario {action} exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        conn.close()

@app.route('/admin/update_notifications', methods=['POST'])
def admin_update_notifications():
    """Actualizar configuración de notificaciones"""
    if 'user_id' not in session or session.get('username') != 'admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    method = request.form.get('notification_method', 'none')
    
    # Configurar según método
    if method == 'telegram':
        telegram_token = request.form.get('telegram_token', '').strip()
        telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
        
        if not telegram_token or not telegram_chat_id:
            flash('Token y Chat ID de Telegram son obligatorios', 'error')
            return redirect(url_for('admin_panel'))
        
        success = configure_notifications(
            method='telegram',
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id
        )
        
    elif method == 'email':
        smtp_email = request.form.get('smtp_email', '').strip()
        smtp_password = request.form.get('smtp_password', '').strip()
        
        if not smtp_email or not smtp_password:
            flash('Email y contraseña SMTP son obligatorios', 'error')
            return redirect(url_for('admin_panel'))
        
        success = configure_notifications(
            method='email',
            smtp_email=smtp_email,
            smtp_password=smtp_password
        )
        
    else:
        success = configure_notifications(method='none')
    
    if success:
        flash('Configuración de notificaciones actualizada exitosamente', 'success')
    else:
        flash('Error actualizando configuración de notificaciones', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/test_telegram', methods=['POST'])
def admin_test_telegram():
    """Probar conexión con Telegram"""
    if 'user_id' not in session or session.get('username') != 'admin':
        return jsonify({'success': False, 'message': 'Acceso denegado'})
    
    # Probar conexión
    success, message = test_telegram_bot()
    
    if success:
        # Enviar mensaje de prueba
        test_success, test_message = send_telegram_test()
        return jsonify({
            'success': test_success,
            'message': test_message if test_success else f'Conexión OK pero error enviando mensaje: {test_message}'
        })
    else:
        return jsonify({'success': False, 'message': message})


# ==================== RUTAS DE ADMINISTRACIÓN ====================

@app.route('/admin')
def admin_panel():
    """Panel de administración - solo para admin"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Verificar que sea admin
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ? AND is_active = 1', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or user[0] != 'admin':
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener lista de usuarios
    cursor.execute('''
        SELECT id, username, email, is_active, is_developer, created_at
        FROM users 
        ORDER BY is_active DESC, is_developer DESC, username
    ''')
    users = cursor.fetchall()
    conn.close()
    
    # Obtener configuración de notificaciones
    notification_config = get_notification_config()
    
    return render_template('admin_panel.html', 
                         users=users, 
                         notification_config=notification_config,
                         user={'username': session['username']})

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    """Agregar nuevo usuario"""
    if 'user_id' not in session or session.get('username') != 'admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    username = request.form['username'].strip()
    email = request.form['email'].strip()
    is_developer = 'is_developer' in request.form
    
    if not username or not email:
        flash('Usuario y email son obligatorios', 'error')
        return redirect(url_for('admin_panel'))
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (username, email, is_developer, is_active)
            VALUES (?, ?, ?, 1)
        ''', (username, email, is_developer))
        
        conn.commit()
        flash(f'Usuario {username} creado exitosamente', 'success')
        
    except sqlite3.IntegrityError:
        flash(f'Error: El usuario {username} ya existe', 'error')
    except Exception as e:
        flash(f'Error creando usuario: {e}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_notifications', methods=['POST'])
def admin_update_notifications():
    """Actualizar configuración de notificaciones"""
    if 'user_id' not in session or session.get('username') != 'admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('dashboard'))
    
    method = request.form.get('notification_method', 'none')
    
    if method == 'telegram':
        telegram_token = request.form.get('telegram_token', '').strip()
        telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
        
        success = configure_notifications(
            method='telegram',
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id
        )
    else:
        success = configure_notifications(method='none')
    
    if success:
        flash('Configuración actualizada exitosamente', 'success')
    else:
        flash('Error actualizando configuración', 'error')
    
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    print("🎫 SISTEMA DE TICKETS CON GOOGLE DRIVE")
    print("=" * 50)
    print(f"📂 Base de datos: {DATABASE}")
    print(f"📁 Archivos temporales: {UPLOAD_FOLDER}")
    print(f"☁️ Google Drive: {'Habilitado' if GOOGLE_DRIVE_AVAILABLE else 'Deshabilitado'}")
    print(f"📧 Notificaciones: notifications.log")
    print(f"🔄 Auto-sync: {'Habilitado' if ticket_system.drive_manager else 'Deshabilitado'}")
    print("=" * 50)
    print("🌐 Accede a: http://localhost:5000")
    print("👤 Usuarios disponibles:")
    print("   - admin (desarrollador)")
    print("   - juan.perez (usuario)")
    print("   - maria.garcia (usuario)")
    print("   - carlos.dev (desarrollador)")
    print("=" * 50)
    
    try:
        app.run(debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Sistema detenido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando el sistema: {e}")