import os

def collect_code(project_path, output_file, file_extensions=('.py',)):
    """
    Recopila todo el código de los archivos con las extensiones especificadas
    en el directorio del proyecto y sus subdirectorios, y lo escribe en un
    archivo de salida con las rutas de los archivos originales.
    
    Args:
        project_path (str): Ruta al directorio del proyecto
        output_file (str): Nombre del archivo de salida
        file_extensions (tuple): Extensiones de archivo a incluir (por defecto: .py)
    """
    # Directorios a excluir
    EXCLUDED_DIRS = {
        'venv',          # Entorno virtual
        '.venv',         # Variante de entorno virtual
        'env',           # Otra variante común
        '__pycache__',   # Archivos de caché de Python
        '.git',          # Directorio de Git
        '.pytest_cache', # Caché de pytest
        'build',         # Directorio de compilación
        'dist',          # Directorio de distribución
        'node_modules',  # Módulos de Node.js (por si el proyecto es híbrido)
        '.eggs',         # Archivos de instalación
        '*.egg-info'     # Información de paquetes Python
        'archive',      # Archivos de respaldo o antiguos
    }
    
    try:
        with open(output_file, 'w', encoding='utf-8') as output:
            # Escribir encabezado con información del proyecto
            output.write('RECOPILACIÓN DE CÓDIGO DEL PROYECTO\n')
            output.write('=' * 80 + '\n\n')
            
            # Recorrer el directorio del proyecto
            for root, dirs, files in os.walk(project_path):
                # Filtrar directorios excluidos
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                
                # Filtrar archivos por extensión
                code_files = [f for f in files if f.endswith(file_extensions)]
                
                for file_name in code_files:
                    file_path = os.path.join(root, file_name)
                    relative_path = os.path.relpath(file_path, project_path)
                    
                    # Verificar si el archivo está en un directorio que debería ser excluido
                    if any(excluded in relative_path.split(os.sep) for excluded in EXCLUDED_DIRS):
                        continue
                    
                    # Escribir separador y ruta del archivo
                    output.write('\n' + '=' * 80 + '\n')
                    output.write(f'Archivo: {relative_path}\n')
                    output.write('=' * 80 + '\n\n')
                    
                    # Leer y escribir el contenido del archivo
                    try:
                        with open(file_path, 'r', encoding='utf-8') as code_file:
                            content = code_file.read()
                            output.write(content)
                            output.write('\n')
                    except Exception as e:
                        output.write(f'Error al leer el archivo: {str(e)}\n')
        
        print(f'Código recopilado exitosamente en {output_file}')
        print(f'Directorios excluidos: {", ".join(EXCLUDED_DIRS)}')
        
    except Exception as e:
        print(f'Error al procesar los archivos: {str(e)}')

if __name__ == '__main__':
    # Ejemplo de uso
    PROJECT_PATH = '.'  # Ruta al directorio del proyecto
    OUTPUT_FILE = 'codigo_proyecto.txt'  # Nombre del archivo de salida
    EXTENSIONS = ('.py', '.pyw')  # Extensiones a incluir
    
    collect_code(PROJECT_PATH, OUTPUT_FILE, EXTENSIONS)