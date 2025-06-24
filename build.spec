# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app_simple.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('credentials.json', '.'),
        ('temp_uploads', 'temp_uploads'),
    ],
    hiddenimports=[
        'google.auth',
        'google.auth.transport.requests',
        'google_auth_oauthlib',
        'googleapiclient.discovery',
        'sqlite3',
        'flask',
        'werkzeug',
        'jinja2',
        'telegram_notifications',
        'google_drive_api',
        'psutil'
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
    name='SistemaTickets',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)