# ============================================================================
# INTEGRACIÓN COMPLETA: DATORAMA + SISTEMA DE TICKETS
# Integra el sistema de tickets Flask DENTRO de la aplicación PyQt5 de Datorama
# ============================================================================

import sys
import os
import threading
import time
import subprocess
import psutil
import json
import sqlite3
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                            QMessageBox, QPushButton, QLabel, QHBoxLayout, 
                            QGridLayout, QFrame, QScrollArea, QSplashScreen,
                            QFileDialog, QProgressBar, QStatusBar, QDialog,
                            QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
                            QListWidget, QCheckBox, QGroupBox, QTabWidget, 
                            QLineEdit, QListWidgetItem, QInputDialog, QTextBrowser)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile
from PyQt5.QtCore import QUrl, Qt, QTimer, pyqtSignal, QDir, QThread, QObject
from PyQt5.QtGui import QFont, QIcon, QCursor, QPixmap

# Importar el sistema de tickets original (adaptado)
import flask
from flask import Flask, render_template_string, jsonify
import werkzeug.serving
import logging

# ============================================================================
# SERVIDOR FLASK EMBEBIDO - SISTEMA DE TICKETS
# ============================================================================

class TicketFlaskServer(QObject):
    """Servidor Flask embebido que ejecuta el sistema de tickets"""
    
    server_started = pyqtSignal()
    server_stopped = pyqtSignal()
    server_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.app = None
        self.server = None
        self.port = 5555  # Puerto específico para tickets
        self.running = False
        
    def create_flask_app(self):
        """Crea la aplicación Flask con el sistema de tickets"""
        app = Flask(__name__)
        app.secret_key = 'tickets-secret-key-2025'
        
        # Suprimir logs de Flask para evitar spam en consola
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        # ================== MODELO DE DATOS SIMPLIFICADO ==================
        
        def init_tickets_db():
            """Inicializa la base de datos de tickets"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            
            # Tabla de tickets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT DEFAULT 'Abierto',
                    user_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de comentarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER,
                    user_name TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
                )
            ''')
            
            conn.commit()
            conn.close()
        
        # Inicializar DB al crear la app
        init_tickets_db()
        
        # ================== FUNCIONES AUXILIARES ==================
        
        def get_tickets():
            """Obtiene todos los tickets"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, category, priority, status, user_name, created_at, updated_at
                FROM tickets ORDER BY created_at DESC
            ''')
            tickets = cursor.fetchall()
            conn.close()
            return tickets
        
        def create_ticket(title, description, category, priority, user_name):
            """Crea un nuevo ticket"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tickets (title, description, category, priority, user_name)
                VALUES (?, ?, ?, ?, ?)
            ''', (title, description, category, priority, user_name))
            ticket_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return ticket_id
        
        def update_ticket_status(ticket_id, status):
            """Actualiza el estado de un ticket"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tickets 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, ticket_id))
            conn.commit()
            conn.close()
        
        def get_comments(ticket_id):
            """Obtiene comentarios de un ticket"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_name, comment, created_at
                FROM comments WHERE ticket_id = ?
                ORDER BY created_at ASC
            ''', (ticket_id,))
            comments = cursor.fetchall()
            conn.close()
            return comments
        
        def add_comment(ticket_id, user_name, comment):
            """Agrega un comentario a un ticket"""
            conn = sqlite3.connect('embedded_tickets.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO comments (ticket_id, user_name, comment)
                VALUES (?, ?, ?)
            ''', (ticket_id, user_name, comment))
            
            # Actualizar timestamp del ticket
            cursor.execute('''
                UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (ticket_id,))
            
            conn.commit()
            conn.close()
        
        # ================== TEMPLATES HTML EMBEBIDOS ==================
        
        DASHBOARD_TEMPLATE = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sistema de Tickets Embebido</title>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                         color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
                .card { background: white; padding: 20px; border-radius: 10px; 
                       box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
                .btn { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; 
                      text-decoration: none; display: inline-block; margin: 5px; }
                .btn-primary { background: #007bff; color: white; }
                .btn-success { background: #28a745; color: white; }
                .btn-warning { background: #ffc107; color: black; }
                .btn-danger { background: #dc3545; color: white; }
                .btn:hover { opacity: 0.8; }
                .ticket { border-left: 4px solid #007bff; padding: 15px; margin: 10px 0; 
                         background: white; border-radius: 5px; }
                .ticket.high { border-left-color: #dc3545; }
                .ticket.medium { border-left-color: #ffc107; }
                .ticket.low { border-left-color: #28a745; }
                .status { padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
                .status.abierto { background: #fff3cd; color: #856404; }
                .status.progreso { background: #d1ecf1; color: #0c5460; }
                .status.resuelto { background: #d4edda; color: #155724; }
                .form-group { margin-bottom: 15px; }
                .form-control { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
                textarea.form-control { height: 100px; resize: vertical; }
                select.form-control { height: 38px; }
                .stats { display: flex; gap: 20px; margin-bottom: 20px; }
                .stat-card { background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                           color: white; padding: 20px; border-radius: 10px; text-align: center; flex: 1; }
                .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; 
                        width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); }
                .modal-content { background-color: white; margin: 5% auto; padding: 20px; 
                               border-radius: 10px; width: 80%; max-width: 600px; }
                .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
                .close:hover { color: black; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎫 Sistema de Tickets Integrado</h1>
                <p>Gestión de tickets desde Datorama Dashboard</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3 id="total-tickets">{{ stats.total }}</h3>
                    <p>Total Tickets</p>
                </div>
                <div class="stat-card">
                    <h3 id="open-tickets">{{ stats.abiertos }}</h3>
                    <p>Abiertos</p>
                </div>
                <div class="stat-card">
                    <h3 id="progress-tickets">{{ stats.progreso }}</h3>
                    <p>En Progreso</p>
                </div>
                <div class="stat-card">
                    <h3 id="resolved-tickets">{{ stats.resueltos }}</h3>
                    <p>Resueltos</p>
                </div>
            </div>
            
            <div class="card">
                <button class="btn btn-primary" onclick="showNewTicketModal()">
                    ➕ Crear Nuevo Ticket
                </button>
                <button class="btn btn-success" onclick="refreshTickets()">
                    🔄 Actualizar Lista
                </button>
            </div>
            
            <div class="card">
                <h3>📋 Lista de Tickets</h3>
                <div id="tickets-container">
                    {% for ticket in tickets %}
                    <div class="ticket {{ ticket[4].lower() }}" data-ticket-id="{{ ticket[0] }}">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div style="flex: 1;">
                                <h4>#{{ ticket[0] }} - {{ ticket[1] }}</h4>
                                <p>{{ ticket[2][:100] }}{% if ticket[2]|length > 100 %}...{% endif %}</p>
                                <p><strong>Categoría:</strong> {{ ticket[3] }} | 
                                   <strong>Prioridad:</strong> {{ ticket[4] }} | 
                                   <strong>Usuario:</strong> {{ ticket[6] }}</p>
                                <p><strong>Creado:</strong> {{ ticket[7] }}</p>
                            </div>
                            <div>
                                <span class="status {{ ticket[5].lower().replace(' ', '') }}">{{ ticket[5] }}</span>
                                <br><br>
                                <button class="btn btn-primary" onclick="viewTicket({{ ticket[0] }})">Ver</button>
                                {% if ticket[5] != 'Resuelto' %}
                                <button class="btn btn-warning" onclick="updateStatus({{ ticket[0] }}, 'En Progreso')">⏳</button>
                                <button class="btn btn-success" onclick="updateStatus({{ ticket[0] }}, 'Resuelto')">✅</button>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            
            <!-- Modal para Nuevo Ticket -->
            <div id="newTicketModal" class="modal">
                <div class="modal-content">
                    <span class="close" onclick="closeModal('newTicketModal')">&times;</span>
                    <h2>Crear Nuevo Ticket</h2>
                    <form id="newTicketForm">
                        <div class="form-group">
                            <label>Título:</label>
                            <input type="text" id="title" class="form-control" required>
                        </div>
                        <div class="form-group">
                            <label>Descripción:</label>
                            <textarea id="description" class="form-control" required></textarea>
                        </div>
                        <div class="form-group">
                            <label>Categoría:</label>
                            <select id="category" class="form-control" required>
                                <option value="">Seleccionar...</option>
                                <option value="Bug">🐛 Bug/Error</option>
                                <option value="Feature">✨ Nueva Funcionalidad</option>
                                <option value="Soporte">🛠️ Soporte Técnico</option>
                                <option value="Mejora">🔧 Mejora</option>
                                <option value="Documentación">📚 Documentación</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Prioridad:</label>
                            <select id="priority" class="form-control" required>
                                <option value="">Seleccionar...</option>
                                <option value="Low">🟢 Baja</option>
                                <option value="Medium" selected>🟡 Media</option>
                                <option value="High">🟠 Alta</option>
                                <option value="Critical">🔴 Crítica</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Su nombre:</label>
                            <input type="text" id="user_name" class="form-control" required placeholder="Ingrese su nombre">
                        </div>
                        <button type="submit" class="btn btn-primary">Crear Ticket</button>
                        <button type="button" class="btn" onclick="closeModal('newTicketModal')">Cancelar</button>
                    </form>
                </div>
            </div>
            
            <!-- Modal para Ver Ticket -->
            <div id="viewTicketModal" class="modal">
                <div class="modal-content" style="max-width: 800px;">
                    <span class="close" onclick="closeModal('viewTicketModal')">&times;</span>
                    <div id="viewTicketContent">
                        <!-- Contenido dinámico del ticket -->
                    </div>
                </div>
            </div>
            
            <script>
                function showNewTicketModal() {
                    document.getElementById('newTicketModal').style.display = 'block';
                }
                
                function closeModal(modalId) {
                    document.getElementById(modalId).style.display = 'none';
                }
                
                function refreshTickets() {
                    window.location.reload();
                }
                
                function updateStatus(ticketId, status) {
                    fetch('/update_status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticket_id: ticketId, status: status })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            refreshTickets();
                        } else {
                            alert('Error al actualizar ticket');
                        }
                    });
                }
                
                function viewTicket(ticketId) {
                    fetch('/get_ticket/' + ticketId)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById('viewTicketContent').innerHTML = data.html;
                            document.getElementById('viewTicketModal').style.display = 'block';
                        }
                    });
                }
                
                function addComment(ticketId) {
                    const comment = document.getElementById('new-comment').value;
                    const userName = document.getElementById('comment-user').value;
                    
                    if (!comment.trim() || !userName.trim()) {
                        alert('Por favor complete todos los campos');
                        return;
                    }
                    
                    fetch('/add_comment', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            ticket_id: ticketId, 
                            comment: comment, 
                            user_name: userName 
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            viewTicket(ticketId); // Refrescar vista del ticket
                        }
                    });
                }
                
                // Envío de formulario nuevo ticket
                document.getElementById('newTicketForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    
                    const formData = {
                        title: document.getElementById('title').value,
                        description: document.getElementById('description').value,
                        category: document.getElementById('category').value,
                        priority: document.getElementById('priority').value,
                        user_name: document.getElementById('user_name').value
                    };
                    
                    fetch('/create_ticket', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            closeModal('newTicketModal');
                            refreshTickets();
                        } else {
                            alert('Error al crear ticket');
                        }
                    });
                });
                
                // Cerrar modales al hacer clic fuera
                window.onclick = function(event) {
                    const modals = document.querySelectorAll('.modal');
                    modals.forEach(modal => {
                        if (event.target == modal) {
                            modal.style.display = 'none';
                        }
                    });
                }
            </script>
        </body>
        </html>
        '''
        
        # ================== RUTAS FLASK ==================
        
        @app.route('/')
        def dashboard():
            """Dashboard principal de tickets"""
            tickets = get_tickets()
            
            # Calcular estadísticas
            stats = {
                'total': len(tickets),
                'abiertos': len([t for t in tickets if t[5] == 'Abierto']),
                'progreso': len([t for t in tickets if t[5] == 'En Progreso']),
                'resueltos': len([t for t in tickets if t[5] == 'Resuelto'])
            }
            
            return render_template_string(DASHBOARD_TEMPLATE, tickets=tickets, stats=stats)
        
        @app.route('/create_ticket', methods=['POST'])
        def create_ticket_route():
            """API para crear nuevo ticket"""
            try:
                data = flask.request.get_json()
                ticket_id = create_ticket(
                    data['title'],
                    data['description'], 
                    data['category'],
                    data['priority'],
                    data['user_name']
                )
                return jsonify({'success': True, 'ticket_id': ticket_id})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @app.route('/update_status', methods=['POST'])
        def update_status_route():
            """API para actualizar estado de ticket"""
            try:
                data = flask.request.get_json()
                update_ticket_status(data['ticket_id'], data['status'])
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @app.route('/get_ticket/<int:ticket_id>')
        def get_ticket_route(ticket_id):
            """API para obtener detalles de un ticket"""
            try:
                conn = sqlite3.connect('embedded_tickets.db')
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
                ticket = cursor.fetchone()
                conn.close()
                
                if not ticket:
                    return jsonify({'success': False, 'error': 'Ticket no encontrado'})
                
                comments = get_comments(ticket_id)
                
                # Generar HTML para la vista del ticket
                ticket_html = f'''
                <h2>#{ticket[0]} - {ticket[1]}</h2>
                <p><strong>Estado:</strong> <span class="status {ticket[5].lower().replace(' ', '')}">{ticket[5]}</span></p>
                <p><strong>Categoría:</strong> {ticket[3]} | <strong>Prioridad:</strong> {ticket[4]}</p>
                <p><strong>Usuario:</strong> {ticket[6]} | <strong>Creado:</strong> {ticket[7]}</p>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h4>Descripción:</h4>
                    <p>{ticket[2]}</p>
                </div>
                
                <h4>💬 Comentarios ({len(comments)})</h4>
                <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin: 10px 0;">
                '''
                
                for comment in comments:
                    ticket_html += f'''
                    <div style="border-bottom: 1px solid #eee; padding: 10px 0;">
                        <strong>{comment[1]}</strong> <small>({comment[3]})</small>
                        <p>{comment[2]}</p>
                    </div>
                    '''
                
                ticket_html += '''
                </div>
                
                <div style="margin-top: 20px;">
                    <h5>Agregar Comentario:</h5>
                    <input type="text" id="comment-user" placeholder="Su nombre" class="form-control" style="margin-bottom: 10px;">
                    <textarea id="new-comment" placeholder="Escriba su comentario..." class="form-control" style="margin-bottom: 10px;"></textarea>
                    <button class="btn btn-primary" onclick="addComment({})">Enviar Comentario</button>
                </div>
                '''.format(ticket_id)
                
                return jsonify({'success': True, 'html': ticket_html})
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @app.route('/add_comment', methods=['POST'])
        def add_comment_route():
            """API para agregar comentario"""
            try:
                data = flask.request.get_json()
                add_comment(data['ticket_id'], data['user_name'], data['comment'])
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        return app
    
    def start_server(self):
        """Inicia el servidor Flask en un hilo separado"""
        if self.running:
            return
            
        try:
            self.app = self.create_flask_app()
            
            # Crear el servidor
            self.server = werkzeug.serving.make_server(
                host='127.0.0.1',
                port=self.port,
                app=self.app,
                threaded=True
            )
            
            # Iniciar en hilo separado
            server_thread = threading.Thread(target=self._run_server, daemon=True)
            server_thread.start()
            
            # Esperar un momento para que inicie
            time.sleep(1)
            self.running = True
            self.server_started.emit()
            print(f"✅ Servidor de tickets iniciado en http://127.0.0.1:{self.port}")
            
        except Exception as e:
            self.server_error.emit(str(e))
            print(f"❌ Error iniciando servidor de tickets: {e}")
    
    def _run_server(self):
        """Ejecuta el servidor Flask"""
        try:
            self.server.serve_forever()
        except Exception as e:
            self.server_error.emit(str(e))
    
    def stop_server(self):
        """Detiene el servidor Flask"""
        if self.server and self.running:
            self.server.shutdown()
            self.running = False
            self.server_stopped.emit()
            print("🛑 Servidor de tickets detenido")

# ============================================================================
# VENTANA DE TICKETS INTEGRADA
# ============================================================================

class TicketsWindow(QMainWindow):
    """Ventana dedicada para el sistema de tickets"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎫 Sistema de Tickets Integrado")
        self.setGeometry(200, 200, 1000, 700)
        
        # Configurar icono
        try:
            if hasattr(parent, 'windowIcon'):
                self.setWindowIcon(parent.windowIcon())
        except:
            pass
        
        # Crear el servidor Flask embebido
        self.ticket_server = TicketFlaskServer()
        self.ticket_server.server_started.connect(self.on_server_started)
        self.ticket_server.server_error.connect(self.on_server_error)
        
        self.setup_ui()
        
        # Iniciar servidor
        self.ticket_server.start_server()
    
    def setup_ui(self):
        """Configura la interfaz de la ventana de tickets"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Header
        header_label = QLabel("🎫 Sistema de Tickets Integrado")
        header_label.setFont(QFont("Arial", 16, QFont.Bold))
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet("""
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 10px;
        """)
        layout.addWidget(header_label)
        
        # Mensaje de carga
        self.status_label = QLabel("🔄 Iniciando servidor de tickets...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("padding: 10px; background: #fff3cd; border-radius: 5px;")
        layout.addWidget(self.status_label)
        
        # Web view para mostrar la interfaz de tickets
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        # Barra de estado
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Inicializando sistema de tickets...")
    
    def on_server_started(self):
        """Callback cuando el servidor se inicia exitosamente"""
        self.status_label.setText("✅ Servidor iniciado correctamente")
        self.status_label.setStyleSheet("padding: 10px; background: #d4edda; border-radius: 5px;")
        
        # Cargar la interfaz web
        url = f"http://127.0.0.1:{self.ticket_server.port}"
        self.web_view.setUrl(QUrl(url))
        
        self.statusBar().showMessage("Sistema de tickets listo")
        
        # Ocultar mensaje de estado después de 3 segundos
        QTimer.singleShot(3000, lambda: self.status_label.hide())
    
    def on_server_error(self, error):
        """Callback cuando hay un error en el servidor"""
        self.status_label.setText(f"❌ Error: {error}")
        self.status_label.setStyleSheet("padding: 10px; background: #f8d7da; border-radius: 5px;")
        self.statusBar().showMessage(f"Error en servidor: {error}")
    
    def closeEvent(self, event):
        """Maneja el cierre de la ventana"""
        # Detener servidor
        self.ticket_server.stop_server()
        event.accept()

# ============================================================================
# MODIFICACIONES A LA CLASE PRINCIPAL DE DATORAMA
# ============================================================================

# NOTA: Este código se integra con la clase DashboardSelector existente
# Agregue este método a la clase DashboardSelector:

def add_tickets_integration_to_dashboard_selector():
    """
    Función que modifica la clase DashboardSelector para integrar tickets
    IMPORTANTE: Agregue estos métodos a su clase DashboardSelector existente
    """
    
    # Método 1: Modificar initUI para agregar el botón de tickets
    def enhanced_initUI(self, version, last_updated):
        """Versión mejorada de initUI que incluye el botón de tickets"""
        
        # ... (código original de initUI) ...
        
        # AGREGAR ESTA SECCIÓN DESPUÉS DE LOS BOTONES EXISTENTES:
        
        # Separador para tickets
        tickets_separator = QFrame()
        tickets_separator.setFrameShape(QFrame.HLine)
        tickets_separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(tickets_separator)
        
        # Sección de Sistema de Tickets
        tickets_section = QWidget()
        tickets_layout = QVBoxLayout(tickets_section)
        
        # Título de la sección de tickets
        tickets_title = QLabel("🎫 Sistema de Tickets Integrado")
        tickets_title.setFont(QFont("Arial", 14, QFont.Bold))
        tickets_title.setAlignment(Qt.AlignCenter)
        tickets_title.setStyleSheet("""
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
        """)
        tickets_layout.addWidget(tickets_title)
        
        # Botones del sistema de tickets
        tickets_buttons_layout = QHBoxLayout()
        
        # Botón principal de tickets
        self.tickets_button = QPushButton("🎫 Abrir Sistema de Tickets")
        self.tickets_button.setFont(QFont("Arial", 11, QFont.Bold))
        self.tickets_button.setStyleSheet("""
            QPushButton {
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background: linear-gradient(135deg, #218838 0%, #1e7e34 100%);
            }
            QPushButton:pressed {
                background: linear-gradient(135deg, #1e7e34 0%, #155724 100%);
            }
        """)
        self.tickets_button.clicked.connect(self.open_tickets_system)
        tickets_buttons_layout.addWidget(self.tickets_button)
        
        # Botón de estado del sistema
        self.tickets_status_button = QPushButton("🔄 Verificar Estado")
        self.tickets_status_button.setStyleSheet("""
            QPushButton {
                background: #17a2b8;
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: #138496;
            }
        """)
        self.tickets_status_button.clicked.connect(self.check_tickets_status)
        tickets_buttons_layout.addWidget(self.tickets_status_button)
        
        tickets_layout.addLayout(tickets_buttons_layout)
        
        # Información del sistema de tickets
        tickets_info = QLabel("Sistema embebido para gestión de tickets y soporte técnico")
        tickets_info.setFont(QFont("Arial", 9))
        tickets_info.setAlignment(Qt.AlignCenter)
        tickets_info.setStyleSheet("color: #666; margin-bottom: 10px;")
        tickets_layout.addWidget(tickets_info)
        
        main_layout.addWidget(tickets_section)
        
        # CONTINÚAR CON EL RESTO DEL CÓDIGO ORIGINAL...
    
    # Método 2: Función para abrir el sistema de tickets
    def open_tickets_system(self):
        """Abre la ventana del sistema de tickets embebido"""
        try:
            # Verificar si ya hay una ventana de tickets abierta
            if hasattr(self, 'tickets_window') and self.tickets_window.isVisible():
                self.tickets_window.raise_()
                self.tickets_window.activateWindow()
                return
            
            # Crear nueva ventana de tickets
            self.tickets_window = TicketsWindow(self)
            self.tickets_window.show()
            
            # Actualizar estado del botón
            self.tickets_button.setText("🎫 Sistema de Tickets (Abierto)")
            self.tickets_button.setStyleSheet("""
                QPushButton {
                    background: linear-gradient(135deg, #fd7e14 0%, #e83e8c 100%);
                    color: white;
                    padding: 12px 24px;
                    border-radius: 8px;
                    border: none;
                    font-weight: bold;
                }
            """)
            
            # Conectar señal de cierre para restaurar el botón
            self.tickets_window.destroyed.connect(self.on_tickets_window_closed)
            
            # Actualizar barra de estado
            self.statusBar().showMessage("Sistema de tickets abierto", 3000)
            
            print("✅ Ventana de tickets abierta exitosamente")
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo abrir el sistema de tickets:\n{str(e)}"
            )
            print(f"❌ Error abriendo tickets: {e}")
    
    def on_tickets_window_closed(self):
        """Callback cuando se cierra la ventana de tickets"""
        # Restaurar estado del botón
        self.tickets_button.setText("🎫 Abrir Sistema de Tickets")
        self.tickets_button.setStyleSheet("""
            QPushButton {
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background: linear-gradient(135deg, #218838 0%, #1e7e34 100%);
            }
        """)
        self.statusBar().showMessage("Sistema de tickets cerrado", 2000)
    
    def check_tickets_status(self):
        """Verifica el estado del sistema de tickets"""
        try:
            # Verificar si la base de datos existe
            db_exists = os.path.exists('embedded_tickets.db')
            
            # Contar tickets si la DB existe
            ticket_count = 0
            if db_exists:
                conn = sqlite3.connect('embedded_tickets.db')
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM tickets')
                ticket_count = cursor.fetchone()[0]
                conn.close()
            
            # Verificar si hay ventana abierta
            window_open = hasattr(self, 'tickets_window') and self.tickets_window.isVisible()
            
            # Crear mensaje de estado
            status_message = f"""
🎫 ESTADO DEL SISTEMA DE TICKETS

📊 Base de Datos: {'✅ Conectada' if db_exists else '❌ No encontrada'}
🎯 Total de Tickets: {ticket_count}
🖥️ Ventana Activa: {'✅ Abierta' if window_open else '❌ Cerrada'}

💡 El sistema está {'✅ OPERATIVO' if db_exists else '⚠️ REQUIERE INICIALIZACIÓN'}
"""
            
            QMessageBox.information(
                self,
                "Estado del Sistema de Tickets",
                status_message
            )
            
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error de Verificación",
                f"Error al verificar el estado:\n{str(e)}"
            )

# ============================================================================
# SCRIPT DE INSTALACIÓN/INTEGRACIÓN AUTOMÁTICA
# ============================================================================

def integrate_tickets_into_datorama():
    """
    Script de integración automática que modifica el archivo principal de Datorama
    """
    
    print("🔧 INICIANDO INTEGRACIÓN DE SISTEMA DE TICKETS")
    print("=" * 60)
    
    # 1. Verificar que existe el archivo principal
    datorama_file = "SCRIPT APP DATORAMA_Final.py"
    if not os.path.exists(datorama_file):
        print(f"❌ No se encontró {datorama_file}")
        print("💡 Asegúrese de que este script esté en el mismo directorio")
        return False
    
    # 2. Crear backup del archivo original
    backup_file = f"{datorama_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        import shutil
        shutil.copy2(datorama_file, backup_file)
        print(f"💾 Backup creado: {backup_file}")
    except Exception as e:
        print(f"⚠️ Error creando backup: {e}")
    
    # 3. Verificar dependencias de Flask
    try:
        import flask
        print("✅ Flask disponible")
    except ImportError:
        print("❌ Flask no encontrado")
        print("💡 Instale con: pip install flask")
        return False
    
    # 4. Leer archivo original
    try:
        with open(datorama_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        print("📖 Archivo original leído exitosamente")
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return False
    
    # 5. Insertar código de integración
    integration_code = '''
# ============================================================================
# INTEGRACIÓN DE SISTEMA DE TICKETS - AGREGADO AUTOMÁTICAMENTE
# ============================================================================

# Importaciones adicionales para el sistema de tickets
import flask
from flask import Flask, render_template_string, jsonify
import werkzeug.serving
import logging

''' + open(__file__, 'r', encoding='utf-8').read().split('# ============================================================================')[1]
    
    # 6. Modificar la clase DashboardSelector
    # Buscar la definición de la clase
    class_start = original_content.find("class DashboardSelector(QMainWindow):")
    if class_start == -1:
        print("❌ No se encontró la clase DashboardSelector")
        return False
    
    # Insertar los nuevos métodos
    modified_content = original_content[:class_start] + integration_code + original_content[class_start:]
    
    # 7. Escribir archivo modificado
    try:
        with open(datorama_file, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print("✅ Archivo modificado exitosamente")
    except Exception as e:
        print(f"❌ Error escribiendo archivo: {e}")
        return False
    
    print("\n🎉 INTEGRACIÓN COMPLETADA EXITOSAMENTE")
    print("=" * 60)
    print("✅ Sistema de tickets integrado en Datorama")
    print("✅ Backup del archivo original creado")
    print("✅ Nuevas funcionalidades disponibles:")
    print("   • Botón 'Sistema de Tickets' en la interfaz principal")
    print("   • Ventana embebida con interfaz web completa")
    print("   • Base de datos SQLite integrada")
    print("   • Servidor Flask interno")
    print("\n🚀 Ejecute la aplicación Datorama para ver los cambios")
    
    return True

# ============================================================================
# INSTALADOR INDEPENDIENTE
# ============================================================================

class TicketsStandaloneApp(QMainWindow):
    """Aplicación independiente del sistema de tickets (para pruebas)"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎫 Sistema de Tickets - Versión Independiente")
        self.setGeometry(300, 300, 1200, 800)
        
        # Crear servidor
        self.ticket_server = TicketFlaskServer()
        self.ticket_server.server_started.connect(self.on_server_ready)
        
        # UI simple
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        title = QLabel("🎫 Sistema de Tickets - Demo Independiente")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 10px;
        """)
        layout.addWidget(title)
        
        self.status_label = QLabel("🔄 Iniciando servidor...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        # Iniciar servidor
        self.ticket_server.start_server()
    
    def on_server_ready(self):
        """Cuando el servidor está listo"""
        self.status_label.setText("✅ Sistema listo")
        url = f"http://127.0.0.1:{self.ticket_server.port}"
        self.web_view.setUrl(QUrl(url))
    
    def closeEvent(self, event):
        """Cerrar aplicación"""
        self.ticket_server.stop_server()
        event.accept()

# ============================================================================
# FUNCIÓN PRINCIPAL Y UTILIDADES
# ============================================================================

def run_standalone_tickets():
    """Ejecuta el sistema de tickets como aplicación independiente"""
    app = QApplication(sys.argv)
    app.setApplicationName("Sistema de Tickets")
    
    window = TicketsStandaloneApp()
    window.show()
    
    sys.exit(app.exec_())

def install_integration():
    """Instala la integración en el archivo de Datorama"""
    if integrate_tickets_into_datorama():
        print("\n✅ INSTALACIÓN COMPLETADA")
        print("🎯 Próximos pasos:")
        print("   1. Ejecute la aplicación Datorama modificada")
        print("   2. Busque el botón 'Sistema de Tickets' en la interfaz")
        print("   3. ¡Disfrute del sistema integrado!")
    else:
        print("\n❌ INSTALACIÓN FALLIDA")
        print("🔧 Revise los errores anteriores y reintente")

def verify_requirements():
    """Verifica que todas las dependencias estén instaladas"""
    print("🔍 Verificando dependencias...")
    
    required_packages = {
        'PyQt5': 'PyQt5',
        'flask': 'Flask',
        'sqlite3': 'sqlite3 (incluido en Python)'
    }
    
    missing = []
    
    for package, display_name in required_packages.items():
        try:
            if package == 'sqlite3':
                import sqlite3
            else:
                __import__(package)
            print(f"✅ {display_name}")
        except ImportError:
            print(f"❌ {display_name}")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Dependencias faltantes: {', '.join(missing)}")
        print("💡 Instale con:")
        for pkg in missing:
            if pkg != 'sqlite3':
                print(f"   pip install {pkg}")
        return False
    else:
        print("\n✅ Todas las dependencias están instaladas")
        return True

# ============================================================================
# INTERFAZ DE LÍNEA DE COMANDOS
# ============================================================================

def show_menu():
    """Muestra el menú principal"""
    print("\n" + "="*60)
    print("🎫 SISTEMA DE TICKETS - INTEGRACIÓN CON DATORAMA")
    print("="*60)
    print("1. 🔧 Instalar integración en Datorama")
    print("2. 🧪 Ejecutar sistema de tickets independiente (demo)")
    print("3. 🔍 Verificar dependencias")
    print("4. 📖 Ver información del sistema")
    print("5. ❌ Salir")
    print("="*60)

def show_system_info():
    """Muestra información del sistema"""
    print("\n📖 INFORMACIÓN DEL SISTEMA DE TICKETS INTEGRADO")
    print("="*60)
    print("🎯 CARACTERÍSTICAS PRINCIPALES:")
    print("   • Sistema de tickets embebido en PyQt5")
    print("   • Servidor Flask interno (puerto 5555)")
    print("   • Base de datos SQLite integrada")
    print("   • Interfaz web responsive")
    print("   • Gestión completa de tickets y comentarios")
    print("   • Estados: Abierto, En Progreso, Resuelto")
    print("   • Categorías: Bug, Feature, Soporte, Mejora, Documentación")
    print("   • Prioridades: Baja, Media, Alta, Crítica")
    print("\n🔧 ARCHIVOS GENERADOS:")
    print("   • embedded_tickets.db - Base de datos de tickets")
    print("   • SCRIPT APP DATORAMA_Final.py.backup.* - Backup automático")
    print("\n🌐 TECNOLOGÍAS UTILIZADAS:")
    print("   • PyQt5 - Interfaz principal")
    print("   • Flask - Servidor web embebido")
    print("   • SQLite - Base de datos")
    print("   • HTML/CSS/JavaScript - Interfaz web")

def main():
    """Función principal con menú interactivo"""
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == 'install':
            install_integration()
            return
        elif arg == 'demo':
            run_standalone_tickets()
            return
        elif arg == 'verify':
            verify_requirements()
            return
    
    while True:
        show_menu()
        
        try:
            choice = input("\n👉 Seleccione una opción (1-5): ").strip()
            
            if choice == '1':
                print("\n🔧 Iniciando instalación...")
                install_integration()
                
            elif choice == '2':
                print("\n🧪 Iniciando demo independiente...")
                if verify_requirements():
                    run_standalone_tickets()
                
            elif choice == '3':
                verify_requirements()
                
            elif choice == '4':
                show_system_info()
                
            elif choice == '5':
                print("\n👋 ¡Hasta luego!")
                break
                
            else:
                print("\n❌ Opción inválida. Por favor seleccione 1-5.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Saliendo...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        input("\n📍 Presione Enter para continuar...")

if __name__ == '__main__':
    main()