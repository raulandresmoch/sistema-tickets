"""
Script para integrar todas las nuevas funcionalidades:
- Panel de administración
- Sistema de notificaciones Telegram
- Login limpio sin usuarios visibles
"""

import os
import shutil
from datetime import datetime

def backup_files():
    """Crear backup de archivos actuales"""
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = ['app_simple.py', 'templates/login.html']
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            shutil.copy2(file_path, backup_dir)
            print(f"✅ Backup creado: {backup_dir}/{os.path.basename(file_path)}")
    
    return backup_dir

def create_telegram_notifications():
    """Crear archivo telegram_notifications.py"""
    telegram_content = '''"""
Sistema de Notificaciones por Telegram para Sistema de Tickets
"""

import requests
import json
import sqlite3
from datetime import datetime
import threading

class TelegramNotifier:
    def __init__(self):
        self.enabled = False
        self.bot_token = None
        self.chat_id = None
        self.load_config()
    
    def load_config(self):
        """Cargar configuración de notificaciones desde base de datos"""
        try:
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            
            cursor.execute(\'\'\'
                CREATE TABLE IF NOT EXISTS notification_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            \'\'\')
            
            cursor.execute('SELECT key, value FROM notification_config WHERE key IN (?, ?, ?)', 
                          ('notification_method', 'telegram_token', 'telegram_chat_id'))
            config = dict(cursor.fetchall())
            
            if config.get('notification_method') == 'telegram':
                self.bot_token = config.get('telegram_token')
                self.chat_id = config.get('telegram_chat_id')
                self.enabled = bool(self.bot_token and self.chat_id)
                
                if self.enabled:
                    print("✅ Notificaciones Telegram habilitadas")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error cargando configuración Telegram: {e}")
            self.enabled = False
    
    def save_config(self, method, telegram_token=None, telegram_chat_id=None):
        """Guardar configuración de notificaciones"""
        try:
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            
            cursor.execute(\'\'\'
                INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                VALUES ('notification_method', ?, CURRENT_TIMESTAMP)
            \'\'\', (method,))
            
            if method == 'telegram' and telegram_token and telegram_chat_id:
                cursor.execute(\'\'\'
                    INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                    VALUES ('telegram_token', ?, CURRENT_TIMESTAMP)
                \'\'\', (telegram_token,))
                
                cursor.execute(\'\'\'
                    INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                    VALUES ('telegram_chat_id', ?, CURRENT_TIMESTAMP)
                \'\'\', (telegram_chat_id,))
                
                self.bot_token = telegram_token
                self.chat_id = telegram_chat_id
                self.enabled = True
            
            conn.commit()
            conn.close()
            self.load_config()
            return True
            
        except Exception as e:
            print(f"❌ Error guardando configuración: {e}")
            return False
    
    def get_config(self):
        """Obtener configuración actual"""
        try:
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM notification_config')
            config = dict(cursor.fetchall())
            conn.close()
            return config
        except:
            return {}
    
    def send_message(self, message):
        """Enviar mensaje a Telegram"""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ Error enviando mensaje Telegram: {e}")
            return False
    
    def notify_new_ticket(self, ticket_id, title, username, priority, category):
        """Notificar nuevo ticket"""
        if not self.enabled:
            return False
        
        priority_emoji = {'Critical': '🔴', 'High': '🟠', 'Medium': '🟡', 'Low': '🟢'}
        category_emoji = {'Bug': '🐛', 'Feature': '✨', 'Soporte': '🛠️', 'Mejora': '🔧'}
        
        message = f"""🎫 <b>NUEVO TICKET</b>

{priority_emoji.get(priority, '📋')} <b>Ticket #{ticket_id}</b>
📝 <b>Título:</b> {title}
👤 <b>Usuario:</b> {username}
{category_emoji.get(category, '📋')} <b>Categoría:</b> {category}
⚡ <b>Prioridad:</b> {priority}

🕒 <b>Creado:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}"""
        
        return self.send_message(message)
    
    def notify_ticket_update(self, ticket_id, title, old_status, new_status, assigned_to=None):
        """Notificar actualización de ticket"""
        if not self.enabled:
            return False
        
        status_emoji = {'Abierto': '🆕', 'En Progreso': '⚙️', 'Resuelto': '✅'}
        
        message = f"""🔄 <b>TICKET ACTUALIZADO</b>

📋 <b>Ticket #{ticket_id}</b>
📝 <b>Título:</b> {title}
{status_emoji.get(old_status, '📋')} ➡️ {status_emoji.get(new_status, '📋')} <b>Estado:</b> {old_status} → {new_status}"""
        
        if assigned_to:
            message += f"\\n👤 <b>Asignado a:</b> {assigned_to}"
        
        return self.send_message(message)

# Funciones de conveniencia
def send_notification_async(notification_func, *args, **kwargs):
    """Enviar notificación en background"""
    def worker():
        try:
            notification_func(*args, **kwargs)
        except:
            pass
    threading.Thread(target=worker, daemon=True).start()

# Instancia global
telegram_notifier = TelegramNotifier()

def notify_new_ticket_async(ticket_id, title, username, priority, category):
    send_notification_async(telegram_notifier.notify_new_ticket, ticket_id, title, username, priority, category)

def notify_ticket_update_async(ticket_id, title, old_status, new_status, assigned_to=None):
    send_notification_async(telegram_notifier.notify_ticket_update, ticket_id, title, old_status, new_status, assigned_to)

def configure_notifications(method, **kwargs):
    return telegram_notifier.save_config(method, **kwargs)

def get_notification_config():
    return telegram_notifier.get_config()
'''
    
    with open('telegram_notifications.py', 'w', encoding='utf-8') as f:
        f.write(telegram_content)
    
    print("✅ Archivo telegram_notifications.py creado")

def update_app_simple():
    """Actualizar app_simple.py con nuevas funcionalidades"""
    
    # Leer archivo actual
    with open('app_simple.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Agregar importación de telegram
    if 'from telegram_notifications import' not in content:
        import_line = """
# Importar sistema de notificaciones Telegram
try:
    from telegram_notifications import (
        notify_new_ticket_async, notify_ticket_update_async, 
        configure_notifications, get_notification_config
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    def notify_new_ticket_async(*args, **kwargs): pass
    def notify_ticket_update_async(*args, **kwargs): pass
    def configure_notifications(*args, **kwargs): return True
    def get_notification_config(): return {}
"""
        
        # Agregar después de las importaciones existentes
        content = content.replace(
            'from werkzeug.utils import secure_filename',
            'from werkzeug.utils import secure_filename' + import_line
        )
    
    # Modificar función create_ticket para agregar notificaciones
    old_create_ticket = '''def create_ticket():
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
    return redirect(url_for('dashboard'))'''
    
    new_create_ticket = '''def create_ticket():
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
    return redirect(url_for('dashboard'))'''
    
    content = content.replace(old_create_ticket, new_create_ticket)
    
    # Agregar ruta de admin antes del if __name__ == '__main__':
    admin_routes = '''
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
    cursor.execute(\'\'\'
        SELECT id, username, email, is_active, is_developer, created_at
        FROM users 
        ORDER BY is_active DESC, is_developer DESC, username
    \'\'\')
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
        cursor.execute(\'\'\'
            INSERT INTO users (username, email, is_developer, is_active)
            VALUES (?, ?, ?, 1)
        \'\'\', (username, email, is_developer))
        
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

'''
    
    # Agregar antes del if __name__ == '__main__':
    content = content.replace(
        "if __name__ == '__main__':",
        admin_routes + "\nif __name__ == '__main__':"
    )
    
    # Escribir archivo actualizado
    with open('app_simple.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ app_simple.py actualizado con nuevas funcionalidades")

def create_admin_template():
    """Crear template admin_panel.html simplificado"""
    admin_template = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Administración</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/dashboard">
                <i class="fas fa-ticket-alt"></i> Sistema de Tickets
            </a>
            <span class="navbar-text">
                <i class="fas fa-user-shield"></i> {{ user.username }} (Admin)
            </span>
        </div>
    </nav>

    <div class="container mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else 'success' }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="row">
            <!-- Agregar Usuario -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h5><i class="fas fa-user-plus"></i> Agregar Usuario</h5>
                    </div>
                    <div class="card-body">
                        <form method="POST" action="/admin/add_user">
                            <div class="mb-3">
                                <label class="form-label">Usuario *</label>
                                <input type="text" class="form-control" name="username" required 
                                       placeholder="juan.perez">
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Email *</label>
                                <input type="email" class="form-control" name="email" required 
                                       placeholder="juan.perez@empresa.com">
                            </div>
                            <div class="form-check mb-3">
                                <input type="checkbox" class="form-check-input" name="is_developer">
                                <label class="form-check-label">Es Desarrollador</label>
                            </div>
                            <button type="submit" class="btn btn-primary">
                                <i class="fas fa-plus"></i> Agregar Usuario
                            </button>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Configurar Notificaciones -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header bg-success text-white">
                        <h5><i class="fas fa-bell"></i> Notificaciones Telegram</h5>
                    </div>
                    <div class="card-body">
                        <form method="POST" action="/admin/update_notifications">
                            <div class="form-check mb-3">
                                <input type="radio" class="form-check-input" name="notification_method" value="none" 
                                       {% if not notification_config.notification_method or notification_config.notification_method == 'none' %}checked{% endif %}>
                                <label class="form-check-label">Sin notificaciones</label>
                            </div>
                            <div class="form-check mb-3">
                                <input type="radio" class="form-check-input" name="notification_method" value="telegram"
                                       {% if notification_config.notification_method == 'telegram' %}checked{% endif %}>
                                <label class="form-check-label">Telegram Bot</label>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Bot Token</label>
                                <input type="text" class="form-control" name="telegram_token" 
                                       placeholder="123456:ABC-DEF..." 
                                       value="{{ notification_config.telegram_token or '' }}">
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Chat ID</label>
                                <input type="text" class="form-control" name="telegram_chat_id" 
                                       placeholder="-1001234567890"
                                       value="{{ notification_config.telegram_chat_id or '' }}">
                            </div>
                            
                            <button type="submit" class="btn btn-success">
                                <i class="fas fa-save"></i> Guardar
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>

        <!-- Lista de Usuarios -->
        <div class="card mt-4">
            <div class="card-header">
                <h5><i class="fas fa-users"></i> Usuarios ({{ users|length }})</h5>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Usuario</th>
                                <th>Email</th>
                                <th>Tipo</th>
                                <th>Estado</th>
                                <th>Creado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user in users %}
                            <tr>
                                <td>{{ user[1] }}</td>
                                <td>{{ user[2] }}</td>
                                <td>
                                    {% if user[4] %}
                                        <span class="badge bg-success">Desarrollador</span>
                                    {% else %}
                                        <span class="badge bg-primary">Usuario</span>
                                    {% endif %}
                                </td>
                                <td>
                                    {% if user[3] %}
                                        <span class="badge bg-success">Activo</span>
                                    {% else %}
                                        <span class="badge bg-danger">Inactivo</span>
                                    {% endif %}
                                </td>
                                <td>{{ user[5][:16] }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    with open('templates/admin_panel.html', 'w', encoding='utf-8') as f:
        f.write(admin_template)
    
    print("✅ Template admin_panel.html creado")

def update_login_template():
    """Actualizar login.html para versión limpia"""
    login_clean = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Sistema de Tickets</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
        }
        .login-card {
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
        }
        .login-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px 15px 0 0;
            color: white;
            padding: 2rem;
            text-align: center;
        }
        .logo-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        .btn-login {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 10px;
            padding: 12px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="row justify-content-center mb-3">
                    <div class="col-md-6">
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else 'success' }} alert-dismissible fade show">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    </div>
                </div>
            {% endif %}
        {% endwith %}

        <div class="row justify-content-center">
            <div class="col-md-6 col-lg-4">
                <div class="card login-card">
                    <div class="login-header">
                        <div class="logo-icon">
                            <i class="fas fa-ticket-alt"></i>
                        </div>
                        <h3 class="mb-0">Sistema de Tickets</h3>
                        <p class="mb-0 opacity-75">Gestión Integral de Soporte</p>
                    </div>
                    
                    <div class="card-body p-4">
                        <form method="POST" action="/login">
                            <div class="form-floating mb-3">
                                <input type="text" class="form-control" id="username" name="username" 
                                       placeholder="Usuario" required autofocus>
                                <label for="username">
                                    <i class="fas fa-user me-2"></i>Usuario
                                </label>
                            </div>
                            
                            <button type="submit" class="btn btn-primary btn-login w-100">
                                <i class="fas fa-sign-in-alt me-2"></i>
                                Iniciar Sesión
                            </button>
                        </form>
                        
                        <div class="text-center mt-3">
                            <small class="text-muted">
                                ¿No tienes cuenta? Contacta al administrador
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write(login_clean)
    
    print("✅ Login actualizado (sin usuarios visibles)")

def add_admin_link_to_dashboard():
    """Agregar enlace al panel de admin en el dashboard"""
    dashboard_path = 'templates/dashboard.html'
    
    if os.path.exists(dashboard_path):
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar el navbar y agregar enlace de admin
        old_navbar = '''<div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">
                    <i class="fas fa-user"></i> {{ user.username }}
                    {% if user.is_developer %}
                        <span class="badge bg-success ms-1">Desarrollador</span>
                    {% endif %}
                </span>
                <a class="nav-link" href="/logout">
                    <i class="fas fa-sign-out-alt"></i> Salir
                </a>
            </div>'''
        
        new_navbar = '''<div class="navbar-nav ms-auto">
                {% if user.username == 'admin' %}
                    <a class="nav-link me-3" href="/admin">
                        <i class="fas fa-cogs"></i> Admin
                    </a>
                {% endif %}
                <span class="navbar-text me-3">
                    <i class="fas fa-user"></i> {{ user.username }}
                    {% if user.is_developer %}
                        <span class="badge bg-success ms-1">Desarrollador</span>
                    {% endif %}
                </span>
                <a class="nav-link" href="/logout">
                    <i class="fas fa-sign-out-alt"></i> Salir
                </a>
            </div>'''
        
        content = content.replace(old_navbar, new_navbar)
        
        with open(dashboard_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Dashboard actualizado con enlace al panel de admin")

def main():
    """Función principal de integración"""
    print("🚀 INICIANDO INTEGRACIÓN DE FUNCIONALIDADES")
    print("=" * 60)
    
    # Verificar que estamos en el directorio correcto
    if not os.path.exists('app_simple.py'):
        print("❌ Error: No se encontró app_simple.py")
        print("   Ejecuta este script desde el directorio del proyecto")
        return
    
    if not os.path.exists('templates'):
        print("❌ Error: No se encontró el directorio templates")
        return
    
    try:
        # 1. Crear backup
        print("\n1. Creando backup de archivos...")
        backup_dir = backup_files()
        
        # 2. Crear sistema de notificaciones Telegram
        print("\n2. Creando sistema de notificaciones Telegram...")
        create_telegram_notifications()
        
        # 3. Actualizar app_simple.py
        print("\n3. Actualizando app_simple.py...")
        update_app_simple()
        
        # 4. Crear template de admin
        print("\n4. Creando template del panel de administración...")
        create_admin_template()
        
        # 5. Actualizar login
        print("\n5. Actualizando login (sin usuarios visibles)...")
        update_login_template()
        
        # 6. Actualizar dashboard
        print("\n6. Actualizando dashboard...")
        add_admin_link_to_dashboard()
        
        print("\n" + "=" * 60)
        print("🎉 ¡INTEGRACIÓN COMPLETADA EXITOSAMENTE!")
        print("=" * 60)
        
        print(f"📁 Backup creado en: {backup_dir}")
        print("\n✅ Funcionalidades agregadas:")
        print("   • Panel de administración (/admin)")
        print("   • Sistema de notificaciones Telegram")
        print("   • Login limpio sin usuarios visibles")
        print("   • Gestión de usuarios desde admin panel")
        
        print("\n🔄 Para probar:")
        print("   1. python app_simple.py")
        print("   2. Login como 'admin'")
        print("   3. Click en 'Admin' en el navbar")
        print("   4. Configurar Telegram Bot")
        print("   5. Agregar usuarios")
        
        print("\n📱 Para configurar Telegram:")
        print("   1. Crear bot con @BotFather en Telegram")
        print("   2. Obtener token del bot")
        print("   3. Agregar bot a un grupo")
        print("   4. Obtener Chat ID del grupo")
        print("   5. Configurar en panel de admin")
        
    except Exception as e:
        print(f"\n❌ Error durante la integración: {e}")
        print("💡 Revisa que todos los archivos estén presentes y tengas permisos de escritura")

if __name__ == "__main__":
    main()