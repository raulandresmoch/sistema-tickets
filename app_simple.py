"""
Sistema de Tickets - Versión Simplificada LIMPIA
Sin rutas duplicadas - Integrado con Google Drive y Telegram
"""

import os
import json
import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename

# Intentar importar Google Drive y Telegram
try:
    from google_drive_api import GoogleDriveManager, init_google_drive
    GOOGLE_DRIVE_AVAILABLE = True
    print("✅ Google Drive API disponible")
except ImportError as e:
    print(f"⚠️ Google Drive API no disponible: {e}")
    GOOGLE_DRIVE_AVAILABLE = False

try:
    from telegram_notifications import send_telegram_notification, notify_new_ticket_async, notify_ticket_update_async
    TELEGRAM_AVAILABLE = True
    print("✅ Telegram API disponible")
except ImportError as e:
    print(f"⚠️ Telegram API no disponible: {e}")
    TELEGRAM_AVAILABLE = False

# Configuración de la aplicación
app = Flask(__name__)
app.secret_key = 'tu-clave-secreta-super-segura-cambiar-en-produccion'

# Configuración
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'docx'}
DATABASE = 'tickets.db'

# Crear carpetas necesarias
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class TicketSystemComplete:
    def __init__(self):
        self.init_database()
        self.drive_manager = None
        
        # Inicializar Google Drive si está disponible
        if GOOGLE_DRIVE_AVAILABLE:
            try:
                self.drive_manager = init_google_drive()
                if self.drive_manager and self.drive_manager.authenticated:
                    print("✅ Google Drive conectado exitosamente")
                    # Sincronizar al inicio
                    self.sync_from_drive()
                else:
                    print("⚠️ Google Drive no se pudo autenticar")
            except Exception as e:
                print(f"❌ Error inicializando Google Drive: {e}")
        
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
        
        # Tabla de tickets - CON drive_attachments
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
        
        # Tabla de configuración del sistema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
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

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    def sync_to_drive(self):
        """Sincroniza datos locales a Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            return self.drive_manager.sync_tickets_to_drive()
        return False

    def sync_from_drive(self):
        """Sincroniza datos desde Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            return self.drive_manager.sync_tickets_from_drive()
        return False

    def create_ticket(self, title, description, category, priority, user_id, attachments=None):
        """Crea un nuevo ticket"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Procesar archivos adjuntos
        drive_attachments = []
        local_attachments = []
        
        if attachments:
            for attachment in attachments:
                # Guardar localmente
                local_attachments.append(attachment)
                
                # Subir a Google Drive si está disponible
                if self.drive_manager and self.drive_manager.authenticated:
                    file_path = os.path.join(UPLOAD_FOLDER, attachment)
                    if os.path.exists(file_path):
                        drive_info = self.drive_manager.upload_attachment(file_path, None)  # ticket_id se agregará después
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
        conn.commit()
        conn.close()
        
        # Notificación simple por log
        self.log_notification(ticket_id, 'new', title)
        
        # Notificación por Telegram
        if TELEGRAM_AVAILABLE:
            try:
                notify_new_ticket_async(ticket_id, title, user_id, priority, category)
            except Exception as e:
                print(f"Error enviando notificación Telegram: {e}")
        
        # Sincronizar a Drive
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
                SELECT t.*, u.username as user_name, u.email as user_email,
                       d.username as developer_name, d.email as developer_email
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
                SELECT t.*, u.username as user_name, u.email as user_email,
                       d.username as developer_name, d.email as developer_email
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
        
        # Obtener estado anterior para Telegram
        cursor.execute('SELECT title, status FROM tickets WHERE id = ?', (ticket_id,))
        ticket_info = cursor.fetchone()
        old_status = ticket_info[1] if ticket_info else 'Desconocido'
        title = ticket_info[0] if ticket_info else 'Ticket sin título'
        
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
        
        # Notificación simple
        self.log_notification(ticket_id, 'update', f"Estado cambiado a: {status}")
        
        # Notificación por Telegram
        if TELEGRAM_AVAILABLE:
            try:
                notify_ticket_update_async(ticket_id, title, old_status, status, assigned_to)
            except Exception as e:
                print(f"Error enviando notificación Telegram: {e}")
        
        # Sincronizar a Drive
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
        
        # Estadísticas adicionales para admin
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_developer = 1 AND is_active = 1')
        total_developers = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM comments')
        total_comments = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'in_progress_tickets': in_progress_tickets,
            'resolved_tickets': resolved_tickets,
            'tickets_by_category': tickets_by_category,
            'tickets_by_priority': tickets_by_priority,
            'avg_resolution_hours': round(avg_resolution_time or 0, 1),
            'total_users': total_users,
            'total_developers': total_developers,
            'total_comments': total_comments
        }

    def get_system_status(self):
        """Obtiene el estado del sistema"""
        status = {
            'database': 'OK',
            'google_drive': 'Desconectado',
            'telegram': 'Desconectado',
            'notifications': 'Archivo Log'
        }
        
        if self.drive_manager and self.drive_manager.authenticated:
            status['google_drive'] = 'Conectado'
        
        if TELEGRAM_AVAILABLE:
            status['telegram'] = 'Disponible'
        
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

# Instancia global del sistema
ticket_system = TicketSystemComplete()

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

# ==================== RUTAS PRINCIPALES ====================

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
    
    return redirect(url_for('view_ticket', ticket_id=ticket_id))

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
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'Error descargando archivo: {e}', 'error')
        return redirect(url_for('dashboard'))

# ==================== RUTAS DE ADMINISTRACIÓN ====================

@app.route('/admin')
def admin_panel():
    """Panel de administración - Solo para desarrolladores"""
    if 'user_id' not in session or not session['is_developer']:
        flash('No tienes permisos para acceder al panel de administración', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener estadísticas completas
    stats = ticket_system.get_statistics()
    system_status = ticket_system.get_system_status()
    
    # Obtener usuarios
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, is_active, is_developer, created_at FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    
    # Obtener notificaciones recientes
    recent_notifications = ticket_system.get_recent_notifications(20)
    
    # Información del sistema
    import platform
    import psutil
    
    system_info = {
        'python_version': platform.python_version(),
        'os': platform.system() + ' ' + platform.release(),
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('.').percent
    }
    
    conn.close()
    
    return render_template('admin_panel.html',
                         stats=stats,
                         system_status=system_status,
                         users=users,
                         notifications=recent_notifications,
                         system_info=system_info,
                         user={'id': session['user_id'], 'username': session['username'], 'is_developer': True})

@app.route('/admin/sync_drive', methods=['POST'])
def admin_sync_drive():
    """Sincronización manual con Google Drive"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    direction = request.json.get('direction', 'up')
    
    try:
        if direction == 'up':
            success = ticket_system.sync_to_drive()
            message = 'Sincronización a Drive ' + ('exitosa' if success else 'fallida')
        elif direction == 'down':
            success = ticket_system.sync_from_drive()
            message = 'Sincronización desde Drive ' + ('exitosa' if success else 'fallida')
        else:
            success = False
            message = 'Dirección de sincronización inválida'
    except Exception as e:
        success = False
        message = f'Error en sincronización: {str(e)}'
    
    return jsonify({'success': success, 'message': message})

@app.route('/admin/toggle_user/<int:user_id>', methods=['POST'])
def admin_toggle_user(user_id):
    """Activar/desactivar usuario"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    # No permitir desactivar al admin actual
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'No puedes desactivarte a ti mismo'})
    
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Obtener estado actual
        cursor.execute('SELECT is_active, username FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})
        
        # Cambiar estado
        new_status = not user[0]
        cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
        conn.commit()
        conn.close()
        
        action = 'activado' if new_status else 'desactivado'
        return jsonify({'success': True, 'message': f'Usuario {user[1]} {action} exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/admin/create_user', methods=['POST'])
def admin_create_user():
    """Crear nuevo usuario"""
    if 'user_id' not in session or not session['is_developer']:
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('admin_panel'))
    
    username = request.form['username'].strip()
    email = request.form['email'].strip()
    is_developer = 'is_developer' in request.form
    
    if not username or not email:
        flash('Nombre de usuario y email son requeridos', 'error')
        return redirect(url_for('admin_panel'))
    
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, email, is_developer, is_active)
            VALUES (?, ?, ?, 1)
        ''', (username, email, is_developer))
        conn.commit()
        conn.close()
        
        role = 'desarrollador' if is_developer else 'usuario'
        flash(f'Usuario {username} creado exitosamente como {role}', 'success')
        
    except sqlite3.IntegrityError:
        flash(f'El usuario {username} ya existe', 'error')
    except Exception as e:
        flash(f'Error creando usuario: {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/fix_telegram_db', methods=['POST'])
def admin_fix_telegram_db():
    """Crear tabla de configuración de Telegram"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Crear tabla de configuración
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Tabla de configuración creada exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/admin/test_telegram', methods=['POST'])
def admin_test_telegram():
    """Probar notificaciones de Telegram"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    if not TELEGRAM_AVAILABLE:
        return jsonify({'success': False, 'message': 'Telegram no está disponible'})
    
    try:
        # Enviar mensaje de prueba
        from telegram_notifications import send_telegram_notification
        message = f"🧪 Mensaje de prueba desde Sistema de Tickets\n\nUsuario: {session['username']}\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        success = send_telegram_notification(message)
        
        if success:
            return jsonify({'success': True, 'message': 'Mensaje de prueba enviado exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Error enviando mensaje de prueba'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/admin/configure_telegram', methods=['POST'])
def admin_configure_telegram():
    """Configurar Telegram desde el panel admin"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        chat_id = data.get('chat_id', '').strip()
        enabled = data.get('enabled', False)
        
        if enabled and (not token or not chat_id):
            return jsonify({'success': False, 'message': 'Token y Chat ID son requeridos'})
        
        # Configurar usando las funciones de telegram_notifications
        from telegram_notifications import configure_notifications
        
        if enabled:
            success = configure_notifications('telegram', telegram_token=token, telegram_chat_id=chat_id)
        else:
            success = configure_notifications('none')
        
        if success:
            status = 'habilitado' if enabled else 'deshabilitado'
            return jsonify({'success': True, 'message': f'Telegram {status} exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Error configurando Telegram'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# ==================== RUTAS API ====================

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

@app.route('/api/system_info')
def api_system_info():
    """API endpoint para información del sistema"""
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        import platform
        import psutil
        
        info = {
            'python_version': platform.python_version(),
            'os': platform.system() + ' ' + platform.release(),
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('.').percent,
            'uptime': time.time() - psutil.boot_time()
        }
        
        return jsonify({'success': True, 'data': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== MANEJO DE ERRORES ====================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', 
                         error_code=404, 
                         error_message='Página no encontrada'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
                         error_code=500, 
                         error_message='Error interno del servidor'), 500

# ==================== EJECUTAR APLICACIÓN ====================

if __name__ == '__main__':
    print("🎫 SISTEMA DE TICKETS - VERSIÓN COMPLETA LIMPIA")
    print("=" * 60)
    print(f"📂 Base de datos: {DATABASE}")
    print(f"📁 Archivos temporales: {UPLOAD_FOLDER}")
    print(f"☁️ Google Drive: {'✅ Conectado' if GOOGLE_DRIVE_AVAILABLE and ticket_system.drive_manager and ticket_system.drive_manager.authenticated else '❌ Desconectado'}")
    print(f"📧 Telegram: {'✅ Disponible' if TELEGRAM_AVAILABLE else '❌ No disponible'}")
    print(f"📝 Notificaciones: notifications.log")
    print("=" * 60)
    print("🌐 Accede a: http://localhost:5000")
    print("👤 Usuarios disponibles:")
    print("   - admin (desarrollador) - Panel admin en /admin")
    print("   - juan.perez (usuario)")
    print("   - maria.garcia (usuario)")
    print("   - carlos.dev (desarrollador)")
    print("   - ana.support (desarrollador)")
    print("=" * 60)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Sistema detenido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando el sistema: {e}")