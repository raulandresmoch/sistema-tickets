#!/usr/bin/env python3
"""
Script para compilar la aplicación de Datorama con sistema de tickets integrado
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def create_build_structure():
    """Crea la estructura de directorios necesaria"""
    print("📁 Creando estructura de directorios...")
    
    # Directorios necesarios
    dirs = [
        "build_temp",
        "build_temp/ticket_system",
        "build_temp/ticket_system/templates",
        "dist_final"
    ]
    
    try:
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            print(f"   ✅ {dir_path}")
        return True
    except Exception as e:
        print(f"   ❌ Error creando directorios: {e}")
        return False

def copy_ticket_system():
    """Copia los archivos del sistema de tickets"""
    print("\n📋 Copiando sistema de tickets...")
    
    try:
        ticket_files = [
            "app_simple.py",
            "google_drive_api.py", 
            "telegram_notifications.py"
        ]
        
        files_found = 0
        for file in ticket_files:
            if os.path.exists(file):
                shutil.copy2(file, "build_temp/ticket_system/")
                print(f"   ✅ {file}")
                files_found += 1
            else:
                print(f"   ❌ {file} - No encontrado")
        
        if files_found == 0:
            print("   ❌ No se encontraron archivos del sistema de tickets")
            return False
        
        # Copiar templates
        if os.path.exists("templates"):
            print("   📄 Copiando templates...")
            for template in os.listdir("templates"):
                if template.endswith(".html"):
                    shutil.copy2(f"templates/{template}", "build_temp/ticket_system/templates/")
                    print(f"      ✅ templates/{template}")
        else:
            print("   ⚠️ Carpeta templates/ no encontrada")
        
        # Crear carpeta temp_uploads si no existe
        temp_uploads_path = "build_temp/ticket_system/temp_uploads"
        Path(temp_uploads_path).mkdir(parents=True, exist_ok=True)
        print(f"   ✅ temp_uploads/ creada")
        
        # Copiar credentials.json si existe (para Google Drive)
        if os.path.exists("credentials.json"):
            shutil.copy2("credentials.json", "build_temp/ticket_system/")
            print(f"   ✅ credentials.json")
        else:
            print(f"   ⚠️ credentials.json - No encontrado (opcional)")
        
        # Copiar archivos de configuración adicionales si existen
        optional_files = ["token.pickle", "tickets.db"]
        for file in optional_files:
            if os.path.exists(file):
                shutil.copy2(file, "build_temp/ticket_system/")
                print(f"   ✅ {file}")
            else:
                print(f"   ⚠️ {file} - No encontrado (se creará automáticamente)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error copiando sistema de tickets: {e}")
        return False

def copy_resources():
    """Copia recursos como iconos e imágenes"""
    print("\n🖼️ Copiando recursos...")
    
    try:
        resources = ["walmart.ico", "home.png"]
        resources_found = 0
        
        for resource in resources:
            if os.path.exists(resource):
                shutil.copy2(resource, "build_temp/")
                print(f"   ✅ {resource}")
                resources_found += 1
            else:
                print(f"   ❌ {resource} - No encontrado")
        
        # Si no existe walmart.ico, crear uno básico
        if not os.path.exists("walmart.ico") and not os.path.exists("build_temp/walmart.ico"):
            print("   🔧 Creando icono placeholder...")
            create_placeholder_icon("build_temp/walmart.ico")
        
        # Al menos uno de los recursos debe existir para continuar
        if resources_found == 0:
            print("   ⚠️ No se encontraron recursos, usando placeholders...")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error copiando recursos: {e}")
        return False

def create_placeholder_icon(icon_path):
    """Crea un icono placeholder básico"""
    try:
        # Crear un icono simple usando PIL si está disponible
        try:
            from PIL import Image, ImageDraw
            
            # Crear una imagen de 32x32 con fondo azul
            img = Image.new('RGBA', (32, 32), (0, 123, 255, 255))
            draw = ImageDraw.Draw(img)
            
            # Dibujar una "T" simple para "Tickets"
            draw.rectangle([12, 8, 20, 10], fill=(255, 255, 255, 255))  # Barra horizontal
            draw.rectangle([15, 8, 17, 24], fill=(255, 255, 255, 255))  # Barra vertical
            
            # Guardar como ICO
            img.save(icon_path, format='ICO', sizes=[(32, 32)])
            print(f"      ✅ Icono placeholder creado: {icon_path}")
            return True
            
        except ImportError:
            # Si no hay PIL, crear un archivo básico
            with open(icon_path, 'w') as f:
                f.write("")  # Archivo vacío
            print(f"      ⚠️ Icono placeholder vacío creado: {icon_path}")
            return True
            
    except Exception as e:
        print(f"      ❌ Error creando icono placeholder: {e}")
        return False

def create_spec_file():
    """Crea el archivo .spec para PyInstaller"""
    print("\n📝 Creando archivo de configuración...")
    
    try:
        # Verificar qué archivos existen para incluir en datas
        datas = []
        
        # Verificar recursos
        if os.path.exists("walmart.ico"):
            datas.append("('walmart.ico', '.')")
        if os.path.exists("home.png"):
            datas.append("('home.png', '.')")
        
        # Siempre incluir el sistema de tickets
        datas.append("('ticket_system', 'ticket_system')")
        
        # Verificar carpetas del sistema de tickets
        if os.path.exists("ticket_system/templates"):
            datas.append("('ticket_system/templates', 'ticket_system/templates')")
        if os.path.exists("ticket_system/temp_uploads"):
            datas.append("('ticket_system/temp_uploads', 'ticket_system/temp_uploads')")
        
        # Convertir la lista a string para el .spec
        datas_str = ",\n        ".join(datas)
        
        # Determinar el icono a usar
        icon_line = ""
        if os.path.exists("walmart.ico"):
            icon_line = "icon='walmart.ico',"
        
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['SCRIPT_APP_DATORAMA_MODIFIED.py'],
    pathex=[],
    binaries=[],
    datas=[
        {datas_str}
    ],
    hiddenimports=[
        # PyQt5 para la interfaz principal
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebChannel',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        
        # Sistema de tickets - Flask y dependencias
        'flask',
        'flask.templating',
        'werkzeug',
        'werkzeug.utils',
        'jinja2',
        'jinja2.ext',
        'sqlite3',
        
        # Google Drive API
        'google.auth',
        'google.auth.transport.requests',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient.discovery',
        'googleapiclient.http',
        'googleapiclient.errors',
        
        # Módulos personalizados del sistema de tickets
        'telegram_notifications',
        'google_drive_api',
        
        # Utilidades del sistema
        'psutil',
        'threading',
        'webbrowser',
        'json',
        'datetime',
        'pickle',
        'io',
        'os',
        'sys',
        'subprocess',
        'time',
        'glob',
        'shutil',
        
        # Dependencias adicionales
        'urllib3',
        'ssl',
        'socket',
        'ipaddress',
        're',
        'functools',
    ],
    hookspath=[],
    hooksconfig={{}},
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
    name='Tableros_Datorama_con_Tickets',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_line}
)
'''
        
        with open("build_temp/app_datorama.spec", "w", encoding="utf-8") as f:
            f.write(spec_content)
        
        print("   ✅ app_datorama.spec creado dinámicamente")
        print(f"   📁 Archivos incluidos: {len(datas)} elementos")
        return True
        
    except Exception as e:
        print(f"   ❌ Error creando archivo .spec: {e}")
        return False

def copy_main_script():
    """Copia el script principal modificado"""
    print("\n📜 Copiando script principal...")
    
    try:
        if os.path.exists("SCRIPT_APP_DATORAMA_MODIFIED.py"):
            shutil.copy2("SCRIPT_APP_DATORAMA_MODIFIED.py", "build_temp/")
            print("   ✅ Script principal copiado")
            return True
        else:
            print("   ❌ SCRIPT_APP_DATORAMA_MODIFIED.py no encontrado")
            print("   💡 Asegúrate de guardar el script modificado con este nombre")
            return False
    except Exception as e:
        print(f"   ❌ Error copiando script principal: {e}")
        return False

def build_executable():
    """Compila el ejecutable usando PyInstaller"""
    print("\n🔨 Compilando ejecutable...")
    
    # Cambiar al directorio de build
    original_dir = os.getcwd()
    
    try:
        os.chdir("build_temp")
        
        # Ejecutar PyInstaller
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            "app_datorama.spec"
        ]
        
        print(f"   🔄 Ejecutando: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("   ✅ Compilación exitosa")
            return True
        else:
            print("   ❌ Error en compilación:")
            print("   STDOUT:", result.stdout)
            print("   STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"   ❌ Error durante compilación: {e}")
        return False
    finally:
        os.chdir(original_dir)

def finalize_build():
    """Mueve el ejecutable final y limpia archivos temporales"""
    print("\n📦 Finalizando build...")
    
    try:
        # Mover el directorio compilado
        source_dist = "build_temp/dist/Tableros_Datorama_con_Tickets.exe"
        target_dist = "dist_final/Tableros_Datorama_con_Tickets.exe"
        
        if os.path.exists(source_dist):
            # Asegurar que el directorio de destino existe
            os.makedirs("dist_final", exist_ok=True)
            
            # Mover el ejecutable
            shutil.move(source_dist, target_dist)
            print(f"   ✅ Ejecutable movido a: {target_dist}")
            
            # Crear un README
            readme_content = """# Tableros de Información Corporativa con Sistema de Tickets

## Ejecución
Ejecuta: `Tableros_Datorama_con_Tickets.exe`

## Características
- ✅ Visualización de dashboards de Datorama
- ✅ Sistema integrado de tickets para reportar problemas
- ✅ Descarga de archivos desde dashboards
- ✅ Múltiples instancias por dashboard (máximo 2)

## Sistema de Tickets
- Accede desde el botón "🎫 Sistema de Tickets" en la barra de herramientas
- Se abre automáticamente en tu navegador en http://localhost:5000
- Usuarios de prueba: admin, juan.perez, maria.garcia

## Soporte
Para problemas técnicos, usa el propio sistema de tickets integrado.
"""
            
            with open("dist_final/README.txt", "w", encoding="utf-8") as f:
                f.write(readme_content)
            
            print("   ✅ README.txt creado")
            return True
        else:
            print("   ❌ No se encontró el ejecutable compilado")
            print(f"   🔍 Buscando en: {source_dist}")
            
            # Buscar archivos en build_temp/dist
            if os.path.exists("build_temp/dist"):
                print("   📁 Contenido de build_temp/dist:")
                for item in os.listdir("build_temp/dist"):
                    print(f"      - {item}")
            
            return False
            
    except Exception as e:
        print(f"   ❌ Error finalizando build: {e}")
        return False

def cleanup():
    """Limpia archivos temporales"""
    print("\n🧹 Limpiando archivos temporales...")
    
    if os.path.exists("build_temp"):
        shutil.rmtree("build_temp")
        print("   ✅ build_temp eliminado")

def main():
    """Función principal del script de build"""
    print("🚀 INICIANDO BUILD DE APLICACIÓN DATORAMA + TICKETS")
    print("=" * 60)
    
    # Verificar dependencias
    try:
        import PyInstaller
        print("✅ PyInstaller disponible")
    except ImportError:
        print("❌ PyInstaller no encontrado. Instálalo con: pip install pyinstaller")
        return False
    
    # Ejecutar pasos del build
    steps = [
        create_build_structure,
        copy_main_script,
        copy_ticket_system,
        copy_resources,
        create_spec_file,
        build_executable,
        finalize_build
    ]
    
    for step in steps:
        if not step():
            print(f"\n❌ Error en el paso: {step.__name__}")
            return False
    
    print("\n🎉 BUILD COMPLETADO EXITOSAMENTE!")
    print("=" * 60)
    print("📁 Ejecutable disponible en: dist_final/Tableros_Datorama_con_Tickets/")
    print("🚀 Para ejecutar: dist_final/Tableros_Datorama_con_Tickets/Tableros_Datorama_con_Tickets.exe")
    
    # Preguntar si limpiar archivos temporales
    cleanup_response = input("\n¿Limpiar archivos temporales? (y/n): ").lower()
    if cleanup_response in ['y', 'yes', 's', 'si']:
        cleanup()
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        input("\nPresiona Enter para salir...")
        sys.exit(1)