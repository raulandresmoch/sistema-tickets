"""
Sistema de Tickets con Google Drive - Versión Completa
Incluye sincronización automática, emails y gestión de archivos adjuntos
"""

import os
import json
import sqlite3
import smtplib
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from email.mime.base import MimeBase
from email import encoders

# Importar módulo de Google Drive
try:
    from google_drive_api import GoogleDriveManager, init_google_drive
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    print("⚠️ Google Drive API no disponible. Funcionando solo en modo local.")
    GOOGLE_DRIVE_AVAILABLE = False

# Configuración de la aplicación
app = Flask(__name__)
app.secret_key = 'tu-clave-secreta-super-segura-cambiar-en-produccion'

# Configuración
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'docx'}
DATABASE = 'tickets.db'
AUTO_SYNC_INTERVAL = 300  # 5 minutos

# Configuración de email
EMAIL_CONFIG = {
    'enabled': True,  # Cambiar a True cuando configures el email
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'email': 'tu-email@gmail.com',  # Cambiar por tu email
    'password': 'tu-app-password',  # Cambiar por tu app password
    'developers': [
        'dev1@empresa.com',
        'dev2@empresa.com'
    ]
}

# Crear carpetas necesarias
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class TicketSystemComplete:
    def __init__(self):
        self.init_database()
        self.drive_manager = None
        self.sync_thread = None
        
        # Inicializar Google Drive si está disponible
        if GOOGLE_DRIVE_AVAILABLE:
            self.init_google_drive()
        
        # Iniciar sincronización automática
        self.start_auto_sync()
        
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

    def init_google_drive(self):
        """Inicializa la conexión con Google Drive"""
        try:
            self.drive_manager = init_google_drive()
            if self.drive_manager and self.drive_manager.authenticated:
                print("✅ Google Drive inicializado correctamente")
                # Sincronizar al inicio
                self.sync_from_drive()
            else:
                print("⚠️ Google Drive no pudo autenticarse")
        except Exception as e:
            print(f"❌ Error inicializando Google Drive: {e}")

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

    def create_ticket(self, title, description, category, priority, user_id, attachments=None):
        """Crea un nuevo ticket"""
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Insertar ticket
        cursor.execute('''
            INSERT INTO tickets (title, description, category, priority, user_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, description, category, priority, user_id))
        
        ticket_id = cursor.lastrowid
        
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
                        drive_info = self.drive_manager.upload_attachment(file_path, ticket_id)
                        if drive_info:
                            drive_attachments.append(drive_info)
        
        # Actualizar ticket con información de adjuntos
        cursor.execute('''
            UPDATE tickets 
            SET attachments = ?, drive_attachments = ?
            WHERE id = ?
        ''', (
            json.dumps(local_attachments) if local_attachments else None,
            json.dumps(drive_attachments) if drive_attachments else None,
            ticket_id
        ))
        
        conn.commit()
        conn.close()
        
        # Enviar notificación por email
        self.send_email_notification(ticket_id, 'new')
        
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
        
        # Enviar notificación
        self.send_email_notification(ticket_id, 'update')
        
        # Sincronizar a Drive
        if self.drive_manager:
            threading.Thread(target=self.sync_to_drive, daemon=True).start()
        
        print(f"✅ Ticket #{ticket_id} actualizado a: {status}")

    def send_email_notification(self, ticket_id, action):
        """Envía notificaciones por email"""
        if not EMAIL_CONFIG['enabled']:
            print(f"📧 Email deshabilitado - Notificación para ticket {ticket_id}: {action}")
            return
        
        try:
            # Obtener información del ticket
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.*, u.username, u.email, d.username as dev_name, d.email as dev_email
                FROM tickets t
                JOIN users u ON t.user_id = u.id
                LEFT JOIN users d ON t.assigned_to = d.id
                WHERE t.id = ?
            ''', (ticket_id,))
            ticket = cursor.fetchone()
            conn.close()
            
            if not ticket:
                return
            
            # Configurar mensaje
            msg = MimeMultipart()
            msg['From'] = EMAIL_CONFIG['email']
            
            if action == 'new':
                msg['To'] = ', '.join(EMAIL_CONFIG['developers'])
                msg['Subject'] = f'[NUEVO TICKET #{ticket_id}] {ticket[1]}'
                
                body = f"""
🎫 NUEVO TICKET CREADO

Ticket #: {ticket_id}
Título: {ticket[1]}
Usuario: {ticket[12]} ({ticket[13]})
Categoría: {ticket[3]}
Prioridad: {ticket[4]}

Descripción:
{ticket[2]}

Estado: {ticket[5]}
Fecha de creación: {ticket[8]}

🔗 Accede al sistema para ver más detalles y asignar el ticket.
                """
            
            elif action == 'update':
                # Notificar al usuario original
                msg['To'] = ticket[13]  # Email del usuario
                if ticket[15]:  # Si hay desarrollador asignado, incluirlo
                    msg['Cc'] = ticket[15]
                
                msg['Subject'] = f'[ACTUALIZACIÓN TICKET #{ticket_id}] {ticket[1]}'
                
                body = f"""
🔄 TICKET ACTUALIZADO

Ticket #: {ticket_id}
Título: {ticket[1]}
Estado actual: {ticket[5]}
Desarrollador asignado: {ticket[14] or 'Sin asignar'}

Última actualización: {ticket[9]}
{f'Resuelto el: {ticket[10]}' if ticket[10] else ''}

🔗 Accede al sistema para ver todos los detalles.
                """
            
            msg.attach(MimeText(body, 'plain'))
            
            # Enviar email
            server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
            server.starttls()
            server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
            
            recipients = msg['To'].split(', ')
            if 'Cc' in msg:
                recipients.extend(msg['Cc'].split(', '))
            
            text = msg.as_string()
            server.sendmail(EMAIL_CONFIG['email'], recipients, text)
            server.quit()
            
            print(f"📧 Email enviado para ticket {ticket_id} - {action}")
            
        except Exception as e:
            print(f"❌ Error enviando email para ticket {ticket_id}: {e}")

    def sync_to_drive(self):
        """Sincroniza datos locales a Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            success = self.drive_manager.sync_tickets_to_drive()
            if success:
                print("☁️ Sincronización a Drive exitosa")
            return success
        return False

    def sync_from_drive(self):
        """Sincroniza datos desde Google Drive"""
        if self.drive_manager and self.drive_manager.authenticated:
            success = self.drive_manager.sync_tickets_from_drive()
            if success:
                print("☁️ Sincronización desde Drive exitosa")
            return success
        return False

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
            'google_drive': 'Desconectado',
            'email': 'Configurado' if EMAIL_CONFIG['enabled'] else 'Deshabilitado',
            'auto_sync': 'Activo' if self.sync_thread and self.sync_thread.is_alive() else 'Inactivo'
        }
        
        if self.drive_manager:
            drive_status = self.drive_manager.get_drive_status()
            status['google_drive'] = drive_status.get('status', 'Error')
            status['drive_details'] = drive_status
        
        return status

# Instancia global del sistema
ticket_system = TicketSystemComplete()

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
        return redirect(url_for('dashboard'))
    else:
        flash('Usuario no encontrado o inactivo', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada exitosamente', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    is_developer = session['is_developer']
    
    tickets = ticket_system.get_tickets(user_id, is_developer)
    stats = ticket_system.get_statistics()
    system_status = ticket_system.get_system_status()
    
    return render_template('dashboard.html', 
                         tickets=tickets, 
                         stats=stats,
                         system_status=system_status,
                         user={'id': user_id, 'is_developer': is_developer})

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
    
    flash(f'Ticket #{ticket_id} creado exitosamente', 'success')
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
    
    flash('Ticket actualizado exitosamente', 'success')
    return redirect(url_for('dashboard'))

@app.route('/sync_drive', methods=['POST'])
def sync_drive():
    if 'user_id' not in session or not session['is_developer']:
        return jsonify({'success': False, 'message': 'Sin permisos'})
    
    direction = request.json.get('direction', 'up')
    
    if direction == 'up':
        success = ticket_system.sync_to_drive()
        message = 'Sincronización a Drive ' + ('exitosa' if success else 'fallida')
    elif direction == 'down':
        success = ticket_system.sync_from_drive()
        message = 'Sincronización desde Drive ' + ('exitosa' if success else 'fallida')
    else:
        success = False
        message = 'Dirección de sincronización inválida'
    
    return jsonify({'success': success, 'message': message})

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

if __name__ == '__main__':
    print("🎫 Sistema de Tickets Completo v2.0")
    print("=" * 50)
    print(f"📂 Base de datos: {DATABASE}")
    print(f"📁 Archivos temporales: {UPLOAD_FOLDER}")
    print(f"☁️ Google Drive: {'Habilitado' if GOOGLE_DRIVE_AVAILABLE else 'Deshabilitado'}")
    print(f"📧 Email: {'Habilitado' if EMAIL_CONFIG['enabled'] else 'Deshabilitado'}")
    print("=" * 50)
    print("🌐 Accede a: http://localhost:5000")
    print("👤 Usuarios de prueba: admin, juan.perez, maria.garcia, carlos.dev")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)