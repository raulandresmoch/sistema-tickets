"""
Sistema de Notificaciones por Telegram para Sistema de Tickets
Versión completa con todas las funciones necesarias
"""

import json
import sqlite3
from datetime import datetime
import threading
import ssl
import urllib3
urllib3.disable_warnings()

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
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('SELECT key, value FROM notification_config WHERE key IN (?, ?, ?)', 
                          ('notification_method', 'telegram_token', 'telegram_chat_id'))
            config = dict(cursor.fetchall())
            
            if config.get('notification_method') == 'telegram':
                self.bot_token = config.get('telegram_token')
                self.chat_id = config.get('telegram_chat_id')
                self.enabled = bool(self.bot_token and self.chat_id)
                
                if self.enabled:
                    print("✅ Notificaciones Telegram habilitadas")
                else:
                    print("⚠️ Telegram configurado pero falta token o chat_id")
            else:
                print("ℹ️ Notificaciones Telegram deshabilitadas")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error cargando configuración Telegram: {e}")
            self.enabled = False
    
    def save_config(self, method, telegram_token=None, telegram_chat_id=None):
        """Guardar configuración de notificaciones"""
        try:
            conn = sqlite3.connect('tickets.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                VALUES ('notification_method', ?, CURRENT_TIMESTAMP)
            ''', (method,))
            
            if method == 'telegram' and telegram_token and telegram_chat_id:
                cursor.execute('''
                    INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                    VALUES ('telegram_token', ?, CURRENT_TIMESTAMP)
                ''', (telegram_token,))
                
                cursor.execute('''
                    INSERT OR REPLACE INTO notification_config (key, value, updated_at)
                    VALUES ('telegram_chat_id', ?, CURRENT_TIMESTAMP)
                ''', (telegram_chat_id,))
                
                self.bot_token = telegram_token
                self.chat_id = telegram_chat_id
                self.enabled = True
            elif method == 'none':
                self.enabled = False
            
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
        except Exception as e:
            print(f"❌ Error obteniendo configuración: {e}")
            return {}
    
    def send_message(self, message):
        """Enviar mensaje a Telegram usando urllib3"""
        if not self.enabled:
            return False
        
        try:
            import urllib3
            import json
            
            # Crear pool manager sin verificación SSL
            http = urllib3.PoolManager(
                cert_reqs='CERT_NONE',
                ca_certs=None,
                ssl_version=None
            )
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            # Enviar petición
            response = http.request(
                'POST',
                url,
                body=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status == 200:
                data = json.loads(response.data.decode('utf-8'))
                if data['ok']:
                    print(f"📱 Mensaje Telegram enviado exitosamente")
                    return True
                else:
                    print(f"❌ Error API Telegram: {data.get('description', 'Unknown')}")
                    return False
            else:
                print(f"❌ Error HTTP Telegram: {response.status}")
                return False
                
        except Exception as e:
            print(f"❌ Error enviando mensaje Telegram: {e}")
            return False
    
    def notify_new_ticket(self, ticket_id, title, username, priority, category):
        """Notificar nuevo ticket"""
        if not self.enabled:
            return False
        
        # Emojis por prioridad
        priority_emoji = {
            'Critical': '🔴',
            'High': '🟠', 
            'Medium': '🟡',
            'Low': '🟢'
        }
        
        # Emojis por categoría
        category_emoji = {
            'Bug': '🐛',
            'Feature': '✨',
            'Soporte': '🛠️',
            'Mejora': '🔧',
            'Documentación': '📚',
            'Seguridad': '🔒'
        }
        
        emoji_priority = priority_emoji.get(priority, '📋')
        emoji_category = category_emoji.get(category, '📋')
        
        message = f"""🎫 <b>NUEVO TICKET</b>

{emoji_priority} <b>Ticket #{ticket_id}</b>
📝 <b>Título:</b> {title}
👤 <b>Usuario:</b> {username}
{emoji_category} <b>Categoría:</b> {category}
⚡ <b>Prioridad:</b> {priority}

🕒 <b>Creado:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}

💡 <i>Accede al sistema para gestionar este ticket</i>"""
        
        return self.send_message(message)
    
    def notify_ticket_update(self, ticket_id, title, old_status, new_status, assigned_to=None):
        """Notificar actualización de ticket"""
        if not self.enabled:
            return False
        
        # Emojis por estado
        status_emoji = {
            'Abierto': '🆕',
            'En Progreso': '⚙️',
            'Resuelto': '✅'
        }
        
        emoji_old = status_emoji.get(old_status, '📋')
        emoji_new = status_emoji.get(new_status, '📋')
        
        message = f"""🔄 <b>TICKET ACTUALIZADO</b>

📋 <b>Ticket #{ticket_id}</b>
📝 <b>Título:</b> {title}

{emoji_old} ➡️ {emoji_new} <b>Estado:</b> {old_status} → {new_status}"""
        
        if assigned_to:
            message += f"\n👤 <b>Asignado a:</b> {assigned_to}"
        
        message += f"\n\n🕒 <b>Actualizado:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        
        return self.send_message(message)
    
    def notify_ticket_comment(self, ticket_id, title, comment_author):
        """Notificar nuevo comentario"""
        if not self.enabled:
            return False
        
        message = f"""💬 <b>NUEVO COMENTARIO</b>

📋 <b>Ticket #{ticket_id}</b>
📝 <b>Título:</b> {title}
👤 <b>Comentario de:</b> {comment_author}

🕒 <b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}

💡 <i>Revisa el ticket para ver el comentario completo</i>"""
        
        return self.send_message(message)
    
    def test_telegram_connection(self):
        """Probar conexión con Telegram usando urllib3"""
        if not self.enabled:
            return False, "Telegram no configurado"
        
        try:
            import urllib3
            import json
            
            # Crear pool manager sin verificación SSL
            http = urllib3.PoolManager(
                cert_reqs='CERT_NONE',
                ca_certs=None,
                ssl_version=None
            )
            
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            
            response = http.request('GET', url, timeout=10)
            
            if response.status == 200:
                data = json.loads(response.data.decode('utf-8'))
                if data['ok']:
                    bot_info = data['result']
                    return True, f"Bot conectado: @{bot_info.get('username', 'Unknown')}"
                else:
                    return False, f"Error API: {data.get('description', 'Unknown')}"
            else:
                return False, f"HTTP Error: {response.status}"
                
        except Exception as e:
            return False, f"Error: {e}"
    
    def send_test_message(self):
        """Enviar mensaje de prueba"""
        if not self.enabled:
            return False, "Telegram no configurado"
        
        test_message = f"""✅ <b>PRUEBA DE CONEXIÓN</b>

🎫 Sistema de Tickets conectado correctamente

🕒 <b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}
🤖 <b>Bot Token:</b> Configurado ✓
💬 <b>Chat ID:</b> Configurado ✓

💡 <i>Las notificaciones están funcionando correctamente</i>"""
        
        success = self.send_message(test_message)
        
        if success:
            return True, "Mensaje de prueba enviado exitosamente"
        else:
            return False, "Error enviando mensaje de prueba"

# Función de ayuda para enviar notificaciones en background
def send_notification_async(notification_func, *args, **kwargs):
    """Enviar notificación en background thread para no bloquear la app"""
    def worker():
        try:
            notification_func(*args, **kwargs)
        except Exception as e:
            print(f"❌ Error en notificación background: {e}")
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

# Instancia global del notificador
telegram_notifier = TelegramNotifier()

# Funciones de conveniencia para usar en app_simple.py
def notify_new_ticket_async(ticket_id, title, username, priority, category):
    """Enviar notificación de nuevo ticket en background"""
    send_notification_async(
        telegram_notifier.notify_new_ticket,
        ticket_id, title, username, priority, category
    )

def notify_ticket_update_async(ticket_id, title, old_status, new_status, assigned_to=None):
    """Enviar notificación de actualización en background"""
    send_notification_async(
        telegram_notifier.notify_ticket_update,
        ticket_id, title, old_status, new_status, assigned_to
    )

def notify_ticket_comment_async(ticket_id, title, comment_author):
    """Enviar notificación de comentario en background"""
    send_notification_async(
        telegram_notifier.notify_ticket_comment,
        ticket_id, title, comment_author
    )

# Funciones para configurar notificaciones (usar en admin panel)
def configure_notifications(method, **kwargs):
    """Configurar sistema de notificaciones"""
    return telegram_notifier.save_config(method, **kwargs)

def get_notification_config():
    """Obtener configuración actual"""
    return telegram_notifier.get_config()

def test_telegram_bot():
    """Probar bot de Telegram"""
    return telegram_notifier.test_telegram_connection()

def send_telegram_test():
    """Enviar mensaje de prueba"""
    return telegram_notifier.send_test_message()

# Función de compatibilidad para app_simple.py
def send_telegram_notification(message):
    """Función de compatibilidad - envía mensaje directo"""
    return telegram_notifier.send_message(message)

if __name__ == "__main__":
    print("🧪 PROBANDO SISTEMA DE NOTIFICACIONES TELEGRAM")
    print("=" * 50)
    
    # Probar configuración
    config = telegram_notifier.get_config()
    print(f"📋 Configuración actual: {config}")
    
    if telegram_notifier.enabled:
        print("✅ Telegram habilitado")
        
        # Probar conexión
        success, message = telegram_notifier.test_telegram_connection()
        print(f"🔍 Test conexión: {message}")
        
        if success:
            # Enviar mensaje de prueba
            test_success, test_message = telegram_notifier.send_test_message()
            print(f"📱 Test mensaje: {test_message}")
        
    else:
        print("⚠️ Telegram no configurado")
        print("💡 Configura el bot desde el panel de administración")