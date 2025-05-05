# Leer el archivo y eliminar líneas en blanco
with open('codigo_proyecto.txt', 'r') as archivo:
    lineas = archivo.readlines()
    lineas_limpias = [linea for linea in lineas if linea.strip()]

# Escribir el resultado en el mismo archivo
with open('codigo_proyecto1.txt', 'w') as archivo:
    archivo.writelines(lineas_limpias)