# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app_simple.py'],  # Tu archivo principal integrado
    pathex=[],
    binaries=[],
    datas=[
        # ARCHIVOS ESENCIALES PARA FUNCIONAMIENTO
        ('templates', 'templates'),              # Templates de Flask
        ('credentials.json', '.'),               # Google Drive API (si existe)
        ('temp_uploads', 'temp_uploads'),        # Carpeta para archivos subidos
        # Agrega estos archivos solo si existen en tu directorio:
        # ('walmart.ico', '.'),                  # Icono (si existe)
        # ('home.png', '.'),                     # Splash screen (si existe)
    ],
    hiddenimports=[
        # IMPORTACIONES PARA FLASK/TICKETS
        'flask',
        'flask.json',
        'flask.helpers',
        'flask.templating',
        'werkzeug.serving',
        'werkzeug.middleware.proxy_fix',
        'werkzeug.utils',
        'jinja2',
        'jinja2.loaders',
        'markupsafe',
        'itsdangerous',
        'click',
        'sqlite3',
        'threading',
        'logging',
        
        # IMPORTACIONES PARA GOOGLE DRIVE (si usas)
        'google.auth',
        'google.auth.transport.requests',
        'google_auth_oauthlib',
        'googleapiclient.discovery',
        
        # IMPORTACIONES BÁSICAS DE PYTHON
        'psutil',
        'requests',
        'json',
        'datetime',
        'os',
        'sys',
        'time',
        'shutil',
        'subprocess',
        'hashlib',
        'base64',
        
        # OTRAS DEPENDENCIAS QUE PODRÍAS TENER
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SistemaTickets',                       # Nombre del ejecutable final
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                                # True para ver errores durante desarrollo
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='walmart.ico'                         # Descomenta si tienes el archivo de icono
)