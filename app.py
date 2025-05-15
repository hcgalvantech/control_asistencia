import qrcode
import streamlit as st
import pandas as pd
import datetime
import os
import socket
import random
import string
from io import BytesIO
from pathlib import Path
from PIL import Image
from pyzbar.pyzbar import decode
import io
import numpy as np
import cv2
from utils import validate_time_for_subject, detect_mobile_device, is_attendance_registered, save_attendance, validate_device_for_subject
from network import check_wifi_connection, is_ip_in_allowed_range, get_local_ip, get_argentina_datetime, get_device_id
from database import load_students, load_attendance, load_schedule, load_admin_config, save_verification_code
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Detectar si estamos en Streamlit Cloud
if not os.environ.get('STREAMLIT_SHARING'):
    os.environ['STREAMLIT_SHARING'] = 'true'
    
# Set page config
st.set_page_config(
    page_title="Sistema de Asistencia",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state variables
if 'attendance_registered' not in st.session_state:
    st.session_state.attendance_registered = False
if 'registration_info' not in st.session_state:
    st.session_state.registration_info = {}
# -----------------------    
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'student_data' not in st.session_state:
    st.session_state.student_data = None
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False
if 'verification_step' not in st.session_state:
    st.session_state.verification_step = False
if 'verification_code' not in st.session_state:
    st.session_state.verification_code = None
if 'phone_verified' not in st.session_state:
    st.session_state.phone_verified = False
if 'device_id' not in st.session_state:
    st.session_state.device_id = get_device_id()
    

# Hybrid approach for both local and cloud
def initialize_supabase():
    try:
        # Intentar usar st.secrets primero
        if hasattr(st, 'secrets') and 'SUPABASE_URL' in st.secrets:
            # We're in Streamlit Cloud
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
        else:
            # Intentar con variables de entorno
            load_dotenv()
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            # Si aún no tenemos las credenciales, mostrar mensaje de error claro
            if not supabase_url or not supabase_key:
                st.error("""
                No se encontraron credenciales de Supabase. Por favor:
                
                1. Crea una carpeta .streamlit en el directorio raíz
                2. Crea un archivo secrets.toml dentro con tus credenciales:
                   
                   SUPABASE_URL = "tu_url_de_supabase"
                   SUPABASE_KEY = "tu_key_de_supabase"
                   
                O configura variables de entorno SUPABASE_URL y SUPABASE_KEY
                """)
                return None
                
        # Inicializar cliente de Supabase
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Error al inicializar Supabase: {str(e)}")
        return None

# Inicializar Supabase
supabase = initialize_supabase()

# Funciones adaptadas para usar Supabase
def load_students():
    response = supabase.table('students').select('*').execute()
    return pd.DataFrame(response.data)

def load_attendance():
    response = supabase.table('attendance').select('*').execute()
    return pd.DataFrame(response.data)

def save_attendance(dni, name, subject, commission, date, time, device, ip, device_id):
    # Ensure date is in ISO format for Supabase date type
    if isinstance(date, str) and '/' in date:
        # Convert dd/mm/yyyy to ISO format
        date_parts = date.split('/')
        date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
    
    data = {
        'DNI': dni,
        'APELLIDO Y NOMBRE': name,
        'MATERIA': subject,
        'COMISION': commission,
        'FECHA': date,
        'HORA': time,
        'DISPOSITIVO': device,
        'IP': ip,
        'DEVICE_ID': device_id
    }
    supabase.table('attendance').insert(data).execute()

    # También guardar uso del dispositivo
    device_data = {
        'DEVICE_ID': device_id,
        'DNI': dni,
        'MATERIA': subject,
        'FECHA': date,
        'TIMESTAMP': datetime.datetime.now().isoformat()
    }
    supabase.table('device_usage').insert(device_data).execute()

def save_classroom_code(code, subject, commission, expiry_time):
    # Primero eliminar códigos expirados
    now = datetime.datetime.now().isoformat()
    supabase.table('classroom_codes').delete().lt('EXPIRY_TIME', now).execute()
    
    # Luego insertar el nuevo código
    data = {
        'CODE': code,
        'SUBJECT': subject,
        'COMMISSION': commission,
        'EXPIRY_TIME': expiry_time
    }
    supabase.table('classroom_codes').insert(data).execute()
     
def verify_classroom_code(code, subject, commission):
    now = datetime.datetime.now().isoformat()
    response = supabase.table('classroom_codes')\
        .select('*')\
        .eq('CODE', code)\
        .eq('SUBJECT', subject)\
        .eq('COMMISSION', commission)\
        .gt('EXPIRY_TIME', now)\
        .execute()
    
    return len(response.data) > 0

def is_attendance_registered(attendance_df, dni, subject, date):
    """Check if attendance is already registered for the student in the given subject and date."""
    # Format date if needed
    if isinstance(date, datetime.date):
        date = date.strftime('%Y-%m-%d')
    
    # Filter the attendance dataframe directly instead of querying Supabase again
    result = attendance_df[
        (attendance_df['DNI'] == dni) & 
        (attendance_df['MATERIA'] == subject) & 
        (attendance_df['FECHA'] == date)
    ]
    
    return not result.empty
    
   
# Initialize admin config
# Admin config is now managed in Supabase
# Initialize it when loading if needed (handled by load_admin_config function)

# Sidebar for navigation
def sidebar():
    with st.sidebar:
        st.title("Menú")
        if st.session_state.admin_mode:
            st.info("Modo Administrador Activo")
            if st.button("Cerrar Sesión de Admin"):
                st.session_state.admin_mode = False
                st.rerun()
        else:
            if st.button("Acceso Administrador"):
                st.session_state.temp_show_admin = True
                st.rerun()
        
        if not st.session_state.admin_mode and st.session_state.authenticated:
            if st.button("Cerrar Sesión de Estudiante"):
                st.session_state.authenticated = False
                st.session_state.student_data = None
                st.session_state.verification_step = False
                st.session_state.verification_code = None
                st.session_state.phone_verified = False
                st.rerun()

# Add these functions to handle admin config in Supabase
def load_admin_config():
    response = supabase.table('admin_config').select('*').execute()
    if response.data:
        return response.data[0]
    else:
        # Create default config if none exists
        default_config = {
            "allowed_ip_ranges": ["192.168.1.0/24"],
            "admin_username": "admin",
            "admin_password": "admin123"
        }
        supabase.table('admin_config').insert(default_config).execute()
        return default_config

def update_admin_config(config_data):
    # Get the id of the existing config
    response = supabase.table('admin_config').select('id').execute()
    if response.data:
        config_id = response.data[0]['id']
        supabase.table('admin_config').update(config_data).eq('id', config_id).execute()
    else:
        # Create if doesn't exist
        supabase.table('admin_config').insert(config_data).execute()
        
# Admin login form
def admin_login():
    st.subheader("Acceso Administrador")
    admin_config = load_admin_config()
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    
    if st.button("Ingresar como Admin"):
        if username == admin_config["admin_username"] and password == admin_config["admin_password"]:
            st.session_state.admin_mode = True
            st.session_state.temp_show_admin = False
            st.success("Acceso concedido")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")
    
    if st.button("Cancelar"):
        st.session_state.temp_show_admin = False
        st.rerun()

# In the admin section - FIXED AND COMPLETED
def admin_dashboard():
    st.title("Panel Administrativo")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Asistencia", "Generador de Códigos", "Gestión de Horarios", "Configuración"])
    
    with tab1:
        st.subheader("Control de Asistencia")
        
        # Cargar datos de asistencia
        attendance_df = load_attendance()
        
        if attendance_df.empty:
            st.warning("No hay registros de asistencia disponibles.")
        else:
            # Filtros para la asistencia
            st.write("Filtros:")
            col1, col2 = st.columns(2)
            
            with col1:
                # Filtro por fecha
                if 'FECHA' in attendance_df.columns:
                    fechas = ["Todas"] + sorted(attendance_df["FECHA"].unique().tolist(), reverse=True)
                    fecha_seleccionada = st.selectbox("Fecha:", fechas)
            
            with col2:
                # Filtro por materia
                if 'MATERIA' in attendance_df.columns:
                    materias = ["Todas"] + sorted(attendance_df["MATERIA"].unique().tolist())
                    materia_seleccionada = st.selectbox("Materia:", materias)
            
            # Aplicar filtros
            filtered_df = attendance_df.copy()
            
            if fecha_seleccionada != "Todas":
                filtered_df = filtered_df[filtered_df["FECHA"] == fecha_seleccionada]
                
            if materia_seleccionada != "Todas":
                filtered_df = filtered_df[filtered_df["MATERIA"] == materia_seleccionada]
            
            # Mostrar datos filtrados
            st.write(f"Mostrando {len(filtered_df)} registros de asistencia")
            st.dataframe(filtered_df)
            
            # Exportar datos
            if st.button("Exportar a CSV"):
                export_filename = f"asistencia_{fecha_seleccionada}_{materia_seleccionada}.csv"
                export_filename = export_filename.replace("Todas", "completo")
                
                # Crear archivo CSV para descargar
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="Descargar CSV",
                    data=csv,
                    file_name=export_filename,
                    mime="text/csv"
                )
        
    with tab2:
        st.subheader("Generador de Códigos de Clase")
        
        # Load subjects and commissions
        schedule_df = load_schedule()
        subjects = schedule_df["MATERIA"].unique().tolist()
        
        selected_subject = st.selectbox("Seleccione materia:", subjects)
        
        # Filter commissions for selected subject
        commissions = schedule_df[schedule_df["MATERIA"] == selected_subject]["COMISION"].unique().tolist()
        selected_commission = st.selectbox("Seleccione comisión:", commissions)
        
        # Select code validity time
        validity_minutes = st.slider("Validez del código (minutos):", 5, 120, 30)
        
        if st.button("Generar Código QR"):
            code = generate_classroom_code()
            
            # Calculate expiry time
            now = datetime.datetime.now()
            expiry_time = (now + datetime.timedelta(minutes=validity_minutes)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Save code to database
            save_classroom_code(code, selected_subject, selected_commission, expiry_time)
            
            # Display QR and code
            qr_data = f"{code}|{selected_subject}|{selected_commission}"
            qr_img = create_qr_code(qr_data)
            
            st.success(f"Código generado: {code}")
            st.success(f"Válido hasta: {expiry_time}")
            st.image(qr_img, caption="Código QR para escanear")
            
            # Add download button for QR code
            st.download_button(
                label="Descargar QR",
                data=qr_img,
                file_name=f"qr_{selected_subject}_{selected_commission}_{code}.png",
                mime="image/png"
            )
    with tab3:
        st.subheader("Gestión de Horarios y Alumnos")
        
        # Subtabs para gestionar horarios o alumnos
        horario_tab, alumno_tab = st.tabs(["Gestión de Horarios", "Gestión de Alumnos"])
        
        with horario_tab:
            gestionar_horarios()
            
        with alumno_tab:
            gestionar_alumnos() 
    with tab4:
        st.subheader("Configuración del Sistema")
        
        admin_config = load_admin_config()
        
        # Configuración de acceso
        st.write("### Acceso Administrador")
        
        new_username = st.text_input("Nuevo Usuario", value=admin_config["admin_username"])
        new_password = st.text_input("Nueva Contraseña", type="password")
        confirm_password = st.text_input("Confirmar Contraseña", type="password")
        
        if st.button("Actualizar Credenciales"):
            if new_password == confirm_password:
                updated_config = admin_config.copy()
                updated_config["admin_username"] = new_username
                if new_password:  # Solo actualizar contraseña si se ha introducido una nueva
                    updated_config["admin_password"] = new_password
                
                # Guardar configuración en Supabase
                update_admin_config(updated_config)
                st.success("Credenciales actualizadas correctamente")
            else:
                st.error("Las contraseñas no coinciden")
        
        # Configuración de red
        st.write("### Configuración de Red")
        
        current_ip_ranges = ", ".join(admin_config.get("allowed_ip_ranges", ["192.168.1.0/24"]))
        new_ip_ranges = st.text_input("Rangos IP permitidos (separados por coma)", value=current_ip_ranges)
        
        if st.button("Actualizar Configuración de Red"):
            # Validar formato de IPs
            ip_list = [ip.strip() for ip in new_ip_ranges.split(",")]
            updated_config = admin_config.copy()
            updated_config["allowed_ip_ranges"] = ip_list
            
            # Guardar configuración en Supabase
            update_admin_config(updated_config)
            st.success("Configuración de red actualizada")

# Función para gestionar horarios
def gestionar_horarios():
    st.write("### Horarios de Materias")
    
    # Cargar datos actuales
    schedule_df = load_schedule()
    
    # Mostrar horarios actuales
    if not schedule_df.empty:
        st.write("Horarios Actuales:")
        
        # Filtros para visualizar horarios
        col1, col2 = st.columns(2)
        with col1:
            materias = ["Todas"] + sorted(schedule_df["MATERIA"].unique().tolist())
            materia_filtro = st.selectbox("Filtrar por Materia:", materias, key="materia_horario_filtro")
        
        with col2:
            comisiones = ["Todas"] + sorted(schedule_df["COMISION"].unique().tolist())
            comision_filtro = st.selectbox("Filtrar por Comisión:", comisiones, key="comision_horario_filtro")
        
        # Aplicar filtros
        filtered_df = schedule_df.copy()
        if materia_filtro != "Todas":
            filtered_df = filtered_df[filtered_df["MATERIA"] == materia_filtro]
        if comision_filtro != "Todas":
            filtered_df = filtered_df[filtered_df["COMISION"] == comision_filtro]
        
        # Mostrar datos con opción de editar/eliminar
        st.dataframe(filtered_df)
        
        # Opción para eliminar horario
        if st.checkbox("Eliminar Horario"):
            # Convertir el DataFrame a una lista de diccionarios para facilitar la selección
            horarios_list = filtered_df.to_dict('records')
            
            # Crear una lista de strings para representar cada horario
            opciones_horario = [f"{h['MATERIA']} - {h['COMISION']} - {h['FECHA']} ({h['INICIO']}-{h['FINAL']})" for h in horarios_list]
            
            # Selector de horario a eliminar
            horario_a_eliminar = st.selectbox("Seleccione horario a eliminar:", opciones_horario)
            
            if st.button("Confirmar Eliminación"):
                # Obtener índice del horario seleccionado
                indice = opciones_horario.index(horario_a_eliminar)
                horario = horarios_list[indice]
                
                # Eliminar de Supabase
                supabase.table('schedule').delete().eq('id', horario['id']).execute()
                
                st.success(f"Horario eliminado: {horario_a_eliminar}")
                st.rerun()
        
        # Opción para modificar horario
        if st.checkbox("Modificar Horario"):
            # Similar al anterior, permitir seleccionar un horario
            horarios_list = filtered_df.to_dict('records')
            opciones_horario = [f"{h['MATERIA']} - {h['COMISION']} - {h['FECHA']} ({h['INICIO']}-{h['FINAL']})" for h in horarios_list]
            horario_a_modificar = st.selectbox("Seleccione horario a modificar:", opciones_horario)
            
            # Obtener el horario seleccionado
            indice = opciones_horario.index(horario_a_modificar)
            horario_actual = horarios_list[indice]
            
            # Formulario para modificar
            materia = st.text_input("Materia:", value=horario_actual["MATERIA"])
            comision = st.text_input("Comisión:", value=horario_actual["COMISION"])
            fecha = st.text_input("Fecha (formato: Lunes, Martes, etc.):", value=horario_actual["FECHA"])
            hora_inicio = st.text_input("Hora de inicio (HH:MM):", value=horario_actual["INICIO"])
            hora_fin = st.text_input("Hora de fin (HH:MM):", value=horario_actual["FINAL"])
            
            if st.button("Guardar Cambios"):
                # Actualizar en Supabase
                supabase.table('schedule').update({
                    "MATERIA": materia,
                    "COMISION": comision,
                    "FECHA": fecha,
                    "INICIO": hora_inicio,
                    "FINAL": hora_fin
                }).eq('id', horario_actual['id']).execute()
                
                st.success("Horario actualizado correctamente")
                st.rerun()
    
    # Agregar nuevo horario
    st.write("### Agregar Nuevo Horario")
    
    # Cargar materias y comisiones existentes para selección
    materias_existentes = sorted(schedule_df["MATERIA"].unique().tolist()) if not schedule_df.empty else []
    comisiones_existentes = sorted(schedule_df["COMISION"].unique().tolist()) if not schedule_df.empty else []
    
    # Permitir seleccionar de existentes o crear nuevos
    usar_existente = st.checkbox("Usar materia y comisión existente", value=True)
    
    if usar_existente and materias_existentes and comisiones_existentes:
        materia_nueva = st.selectbox("Materia:", materias_existentes)
        comision_nueva = st.selectbox("Comisión:", comisiones_existentes)
    else:
        materia_nueva = st.text_input("Nueva Materia:")
        comision_nueva = st.text_input("Nueva Comisión:")
    
    # Días de la semana para seleccionar
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dia_seleccionado = st.selectbox("Día de la semana:", dias_semana)
    
    # Horas
    col1, col2 = st.columns(2)
    with col1:
        hora_inicio_nueva = st.time_input("Hora de inicio:", datetime.time(18, 0))
    with col2:
        hora_fin_nueva = st.time_input("Hora de fin:", datetime.time(21, 0))
    
    if st.button("Agregar Horario"):
        if materia_nueva and comision_nueva:
            # Guardar en Supabase
            nuevo_horario = {
                "MATERIA": materia_nueva,
                "COMISION": comision_nueva,
                "FECHA": dia_seleccionado,
                "INICIO": hora_inicio_nueva.strftime("%H:%M"),
                "FINAL": hora_fin_nueva.strftime("%H:%M")
            }
            
            supabase.table('schedule').insert(nuevo_horario).execute()
            
            st.success(f"Horario agregado correctamente para {materia_nueva} - {comision_nueva}")
            st.rerun()
        else:
            st.error("Debe completar todos los campos")

# Función para gestionar alumnos
def gestionar_alumnos():
    st.write("### Gestión de Alumnos")
    
    # Cargar datos de alumnos
    students_df = load_students()
    
    # Mostrar alumnos actuales
    if not students_df.empty:
        st.write("Alumnos Registrados:")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            tecnicaturas = ["Todas"] + sorted(students_df["tecnicatura"].unique().tolist())
            tecnicatura_filtro = st.selectbox("Filtrar por Tecnicatura:", tecnicaturas)
        
        with col2:
            materias = ["Todas"] + sorted(students_df["materia"].unique().tolist())
            materia_filtro = st.selectbox("Filtrar por Materia:", materias)
        
        # Aplicar filtros
        filtered_df = students_df.copy()
        if tecnicatura_filtro != "Todas":
            filtered_df = filtered_df[filtered_df["tecnicatura"] == tecnicatura_filtro]
        if materia_filtro != "Todas":
            filtered_df = filtered_df[filtered_df["materia"] == materia_filtro]
        
        # Mostrar datos
        st.dataframe(filtered_df)
        
        # Búsqueda por DNI para editar/eliminar
        st.write("### Buscar alumno por DNI")
        dni_busqueda = st.text_input("Ingrese DNI:")
        
        if dni_busqueda:
            alumno = students_df[students_df["dni"] == dni_busqueda]
            
            if not alumno.empty:
                st.success(f"Alumno encontrado: {alumno['apellido_nombre'].iloc[0]}")
                
                # Opciones
                accion = st.radio("Acción:", ["Modificar Datos", "Eliminar Alumno", "Modificar Materias"])
                
                if accion == "Modificar Datos":
                    # Formulario con datos actuales
                    apellido_nombre = st.text_input("Apellido y Nombre:", value=alumno["apellido_nombre"].iloc[0])
                    tecnicatura = st.text_input("Tecnicatura:", value=alumno["tecnicatura"].iloc[0])
                    telefono = st.text_input("Teléfono:", value=str(alumno["telefono"].iloc[0]))
                    correo = st.text_input("Correo electrónico:", value=str(alumno["correo"].iloc[0]) if "correo" in alumno.columns and not pd.isna(alumno["correo"].iloc[0]) else "")
                    
                    if st.button("Guardar Cambios"):
                        # Actualizar en Supabase - usamos id para la actualización
                        supabase.table('students').update({
                            "apellido_nombre": apellido_nombre,
                            "tecnicatura": tecnicatura,
                            "telefono": telefono,
                            "correo": correo
                        }).eq('id', alumno['id'].iloc[0]).execute()
                        
                        st.success("Datos actualizados correctamente")
                        st.rerun()
                
                elif accion == "Eliminar Alumno":
                    if st.button("Confirmar Eliminación", type="primary"):
                        # Eliminar de Supabase usando id
                        supabase.table('students').delete().eq('id', alumno['id'].iloc[0]).execute()
                        
                        st.success(f"Alumno {alumno['apellido_nombre'].iloc[0]} eliminado correctamente")
                        st.rerun()
                
                elif accion == "Modificar Materias":
                    # Mostrar materias actuales del alumno seleccionado
                    materias_alumno = students_df[students_df["dni"] == dni_busqueda][["materia", "comision", "id"]]
                    st.write("Materias actuales:")
                    st.dataframe(materias_alumno[["materia", "comision"]])  # No mostrar ID al usuario
                    
                    # Opción para agregar/quitar materias
                    opcion_materia = st.radio("Opción:", ["Agregar Materia", "Quitar Materia"])
                    
                    if opcion_materia == "Agregar Materia":
                        # Cargar lista de materias disponibles
                        schedule_df = load_schedule()
                        materias_disponibles = sorted(schedule_df["MATERIA"].unique().tolist()) if not schedule_df.empty else []
                        
                        if materias_disponibles:
                            # Seleccionar materia
                            nueva_materia = st.selectbox("Seleccione materia:", materias_disponibles)
                            
                            # Filtrar comisiones para esa materia
                            comisiones = schedule_df[schedule_df["MATERIA"] == nueva_materia]["COMISION"].unique().tolist()
                            nueva_comision = st.selectbox("Seleccione comisión:", comisiones)
                            
                            if st.button("Agregar Materia"):
                                # Verificar que no tenga la materia ya asignada
                                if ((materias_alumno["materia"] == nueva_materia) & 
                                    (materias_alumno["comision"] == nueva_comision)).any():
                                    st.error("El alumno ya está inscripto en esta materia y comisión")
                                else:
                                    # Agregar a Supabase - creamos un nuevo registro manteniendo los datos existentes
                                    new_student_entry = {
                                        "dni": dni_busqueda,
                                        "apellido_nombre": alumno["apellido_nombre"].iloc[0],
                                        "tecnicatura": alumno["tecnicatura"].iloc[0],
                                        "telefono": alumno["telefono"].iloc[0],
                                        "correo": alumno["correo"].iloc[0] if "correo" in alumno.columns and not pd.isna(alumno["correo"].iloc[0]) else "",
                                        "materia": nueva_materia,
                                        "comision": nueva_comision
                                    }
                                    supabase.table('students').insert(new_student_entry).execute()
                                    
                                    st.success(f"Materia {nueva_materia} agregada correctamente")
                                    st.rerun()
                        else:
                            st.warning("No hay materias disponibles en el sistema")
                    
                    else:  # Quitar Materia
                        if not materias_alumno.empty:
                            # Opciones de materias para quitar
                            materias_opciones = [f"{row['materia']} - {row['comision']}" for _, row in materias_alumno.iterrows()]
                            materia_a_quitar = st.selectbox("Seleccione materia a quitar:", materias_opciones)
                            
                            if st.button("Quitar Materia"):
                                indice = materias_opciones.index(materia_a_quitar)
                                registro_a_quitar = materias_alumno.iloc[indice]
                                
                                # Eliminar esta combinación específica usando el id
                                supabase.table('students').delete().eq('id', registro_a_quitar['id']).execute()
                                
                                st.success(f"Materia {registro_a_quitar['materia']} quitada correctamente")
                                st.rerun()
                        else:
                            st.warning("El alumno no tiene materias asignadas")
            else:
                st.error("DNI no encontrado")
    
    # Agregar nuevo alumno
    st.write("### Registrar Nuevo Alumno")
    
    nuevo_dni = st.text_input("DNI:", key="nuevo_dni")
    nuevo_nombre = st.text_input("Apellido y Nombre:", key="nuevo_nombre")
    nueva_tecnicatura = st.text_input("Tecnicatura:", key="nueva_tecnicatura")
    nuevo_telefono = st.text_input("Teléfono:", key="nuevo_telefono")
    nuevo_correo = st.text_input("Correo electrónico:", key="nuevo_correo")
    
    # Para asignar materia directamente
    agregar_materia = st.checkbox("Asignar materia ahora")
    
    if agregar_materia:
        schedule_df = load_schedule()
        materias_disponibles = sorted(schedule_df["MATERIA"].unique().tolist()) if not schedule_df.empty else []
        
        if materias_disponibles:
            materia_inicial = st.selectbox("Seleccione materia:", materias_disponibles)
            
            # Filtrar comisiones para esa materia
            comisiones = schedule_df[schedule_df["MATERIA"] == materia_inicial]["COMISION"].unique().tolist()
            comision_inicial = st.selectbox("Seleccione comisión:", comisiones)
        else:
            st.warning("No hay materias disponibles en el sistema")
            materia_inicial = "Sin asignar"
            comision_inicial = "Sin asignar"
    else:
        materia_inicial = "Sin asignar"
        comision_inicial = "Sin asignar"
    
    if st.button("Registrar Alumno"):
        if nuevo_dni and nuevo_nombre and nueva_tecnicatura:
            # Verificar que no exista
            if (students_df["dni"] == nuevo_dni).any():
                st.error("Ya existe un alumno con ese DNI")
            else:
                # Insertar en Supabase
                new_student = {
                    "dni": nuevo_dni,
                    "apellido_nombre": nuevo_nombre,
                    "tecnicatura": nueva_tecnicatura,
                    "telefono": nuevo_telefono,
                    "correo": nuevo_correo,
                    "materia": materia_inicial,
                    "comision": comision_inicial
                }
                supabase.table('students').insert(new_student).execute()
                
                st.success(f"Alumno {nuevo_nombre} registrado correctamente")
                if materia_inicial == "Sin asignar":
                    st.info("Ahora puede buscar al alumno por DNI para asignarle materias")
                st.rerun()
        else:
            st.error("Debe completar DNI, Nombre y Tecnicatura")
            
# Network validation function
def validate_network():
    admin_config = load_admin_config()
    allowed_ranges = admin_config.get("allowed_ip_ranges", ["192.168.1.0/24"])
    
    # Si estamos en desarrollo local (localhost), omitir verificación de red
    client_ip = get_local_ip()
    if client_ip == "127.0.0.1" or client_ip.startswith("localhost"):
        st.info("Ejecutando en modo de desarrollo local")
        return True
        
    if not check_wifi_connection():
        st.error("❌ Debe estar conectado a una red WiFi para utilizar el sistema")
        return False
    
    if not is_ip_in_allowed_range(client_ip, allowed_ranges):
        st.error(f"❌ Su dirección IP ({client_ip}) está fuera del rango permitido")
        return False
        
    return True

def generate_classroom_code():
    """Generate a random 6-character alphanumeric code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

def save_classroom_code(code, subject, commission, expiry_time):
    # First delete expired codes
    now = datetime.datetime.now().isoformat()
    supabase.table('classroom_codes').delete().lt('EXPIRY_TIME', now).execute()
    
    # Then insert the new code
    data = {
        'CODE': code,
        'SUBJECT': subject,
        'COMMISSION': commission,
        'EXPIRY_TIME': expiry_time
    }
    supabase.table('classroom_codes').insert(data).execute()
     
def verify_classroom_code(code, subject, commission):
    now = datetime.datetime.now().isoformat()
    response = supabase.table('classroom_codes')\
        .select('*')\
        .eq('CODE', code)\
        .eq('SUBJECT', subject)\
        .eq('COMMISSION', commission)\
        .gt('EXPIRY_TIME', now)\
        .execute()
    
    return len(response.data) > 0

def create_qr_code(data):
    """Generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes for Streamlit
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return buffered.getvalue()

# Reemplazar la parte del código que maneja la subida de la imagen QR con esto:
def process_qr_code(uploaded_file):
    """Procesa la imagen QR y extrae el código"""
    try:
        # Leer la imagen cargada
        if uploaded_file is None:
            return None
            
        # Convertir el archivo subido a un formato que pyzbar pueda procesar
        image_bytes = uploaded_file.getvalue()
        image = Image.open(io.BytesIO(image_bytes))
        
        # También probar con OpenCV para mejorar la detección
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_cv = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        # Intentar decodificar primero con PIL
        decoded_objects = decode(image)
        
        # Si no funciona con PIL, intentar con OpenCV
        if not decoded_objects:
            # Aplicar umbral adaptativo para mejorar la calidad
            img_cv = cv2.adaptiveThreshold(img_cv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY, 11, 2)
            decoded_objects = decode(Image.fromarray(img_cv))
        
        # Verificar si se encontró algún código
        if decoded_objects:
            # Extraer el primer código QR encontrado
            qr_data = decoded_objects[0].data.decode('utf-8')
            
            # Si es un código de clase, podría tener formato: "CODIGO|MATERIA|COMISION"
            try:
                parts = qr_data.split('|')
                if len(parts) >= 1:
                    # Retornar solo el código (primera parte)
                    return parts[0]
                else:
                    return qr_data
            except:
                # Si hay algún error en el formato, devolver el dato crudo
                return qr_data
        else:
            return None
    except Exception as e:
        st.error(f"Error al procesar el código QR: {str(e)}")
        return None
    
# FIXED: Removed send_verification_code function calls 
def generate_verification_code(dni, phone):
    # Esta función simplemente registra que el usuario ha sido verificado
    save_verification_code(dni, phone, "verification_skipped")
    return True


# FIXED: Removed references to send_verification_code and verify_code
def phone_verification(dni, phone):
    st.subheader("Verificación de Teléfono")
    st.info(f"Nuevo sistema de verificación basado en QR activo.")
    st.session_state.phone_verified = True
    st.success("Verificación completada")
    st.rerun()
                
# Student authentication
def student_login():
    st.title("Sistema de Registro de Asistencia")
    
    # Validación de red
    if not validate_network():
        return
    # Al inicio de la función student_login(), después de validar la red:
    if st.session_state.attendance_registered:
        st.success(f"✅ Asistencia registrada correctamente")
        
        # Panel con información de la asistencia registrada
        st.info(f"""
        **Detalles del registro:**
        - **Estudiante:** {st.session_state.registration_info['student_name']}
        - **Materia:** {st.session_state.registration_info['subject']}
        - **Fecha:** {st.session_state.registration_info['date']}
        - **Hora:** {st.session_state.registration_info['time']}
        """)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("Salir", type="primary"):
                # Limpiar todas las variables de sesión
                st.session_state.authenticated = False
                st.session_state.student_data = None
                st.session_state.verification_step = False
                st.session_state.verification_code = None
                st.session_state.phone_verified = False
                st.session_state.attendance_registered = False
                st.session_state.registration_info = {}
                st.rerun()
        
        with col2:
            if st.button("Registrar otra asistencia"):
                # Mantener algunas variables pero reiniciar el proceso
                st.session_state.attendance_registered = False
                st.session_state.registration_info = {}
                st.rerun()
        
        # Mensaje de redirección automática con contador
        import time
        placeholder = st.empty()
        for i in range(15, 0, -1):
            placeholder.warning(f"Se cerrará automáticamente en {i} segundos...")
            time.sleep(1)
        
        # Después de la cuenta regresiva, limpia todo y regresa al inicio
        st.session_state.authenticated = False
        st.session_state.student_data = None
        st.session_state.verification_step = False
        st.session_state.verification_code = None
        st.session_state.phone_verified = False
        st.session_state.attendance_registered = False
        st.session_state.registration_info = {}
        st.rerun()
        
        # Detener la ejecución aquí para no mostrar el resto del formulario
        return

    ####
    students_df = load_students()
    
    argentina_now, current_date, current_time = get_argentina_datetime()
    
    st.subheader("Registro de Asistencia")
    st.info(f"Fecha actual: {current_date.strftime('%d/%m/%Y')} - Hora: {current_time.strftime('%H:%M:%S')} (Hora de Buenos Aires)")
    
    # Obtener ID del dispositivo
    device_id = st.session_state.device_id
    
    # Detectar si es dispositivo móvil
    is_mobile = detect_mobile_device()
    if not is_mobile:
        st.warning("⚠️ Este sistema está diseñado para utilizarse desde un dispositivo móvil.")
    
    # Lista de DNIs para selección
    dni_list = [""] + sorted(students_df["dni"].astype(str).unique().tolist())
    selected_dni = st.selectbox("Seleccione su DNI:", dni_list)
    
    if selected_dni:
        # Obtener datos del estudiante
        student_data = students_df[students_df["dni"].astype(str) == selected_dni].to_dict('records')
        
        if student_data:
            student_data = student_data[0]
            st.session_state.student_data = student_data
            st.info(f"Estudiante: {student_data['apellido_nombre']}")
            st.info(f"Tecnicatura: {student_data['tecnicatura']}")
            
            # Verificación del teléfono
            student_phone = str(student_data.get('telefono', ''))
            
            # FIXED: Simplified verification process
            # Si el teléfono no está verificado, simplificar proceso
            if not st.session_state.phone_verified:
                # Verificación simplificada para móviles
                if is_mobile and st.checkbox("Este es mi celular registrado", value=False):
                    st.session_state.phone_verified = True
                    st.success("Dispositivo móvil reconocido")
                    st.rerun()
                else:
                    st.subheader("Verificación de Presencia")
                    
                    # Get student subjects
                    student_subjects = students_df[students_df["dni"].astype(str) == selected_dni]["materia"].unique().tolist()
                    
                    # Show available subjects
                    if student_subjects:
                        selected_subject = st.selectbox("Seleccione materia:", student_subjects)
                        commission = students_df[(students_df["dni"].astype(str) == selected_dni) & 
                                            (students_df["materia"] == selected_subject)]["comision"].iloc[0]
                        
                        verification_method = st.radio(
                            "Método de verificación:",
                            ["Escanear código QR", "Ingresar código manualmente"]
                        )
                        
                        if verification_method == "Escanear código QR":
                            st.info("Escanee el código QR mostrado por el profesor")
                            uploaded_file = st.camera_input("Escanear código QR")
                            
                            if uploaded_file is not None:
                                # Procesar el código QR
                                extracted_code = process_qr_code(uploaded_file)
                                
                                if extracted_code:
                                    # Mostrar el código extraído para que el usuario confirme
                                    st.success(f"Código QR detectado: {extracted_code}")
                                    
                                    # Crear una caja de verificación para que el usuario confirme
                                    confirm = st.checkbox("Confirmar que este es el código correcto", value=True)
                                    
                                    # El usuario también puede editar el código si es necesario
                                    code = st.text_input("Código:", value=extracted_code, max_chars=6, key="qr_code_input")
                                    
                                    if st.button("Verificar código", key="verify_qr_code"):
                                        if verify_classroom_code(code, selected_subject, commission):
                                            # Register attendance with proper arguments
                                            device_info = {
                                                "hostname": socket.gethostname(),
                                                "ip": get_local_ip(),
                                                "device_id": device_id
                                            }
                                            
                                            register_attendance_function(
                                                selected_dni,
                                                student_data['apellido_nombre'],
                                                selected_subject,
                                                commission,
                                                current_date,
                                                current_time,
                                                device_info
                                            )
                                        else:
                                            st.error("Código inválido o expirado")
                                else:
                                    st.warning("No se pudo detectar un código QR válido. Por favor, intente de nuevo o ingrese el código manualmente.")
                                    code = st.text_input("Código:", max_chars=6, key="manual_qr_code_input")
                                    
                                    if st.button("Verificar código", key="verify_manual_qr_code"):
                                        if verify_classroom_code(code, selected_subject, commission):
                                            # Register attendance with proper arguments
                                            device_info = {
                                                "hostname": socket.gethostname(),
                                                "ip": get_local_ip(),
                                                "device_id": device_id
                                            }
                                            
                                            register_attendance_function(
                                                selected_dni,
                                                student_data['apellido_nombre'],
                                                selected_subject,
                                                commission,
                                                current_date,
                                                current_time,
                                                device_info
                                            )
                                        else:
                                            st.error("Código inválido o expirado")
                                
                    else:
                        st.warning("No hay materias disponibles para este estudiante")
                
                return # Exit here until verification is complete
            
            # Continue with attendance process after verification
            
            # Get available subjects for this student
            student_subjects = students_df[students_df["dni"].astype(str) == selected_dni]["materia"].unique().tolist()
            
            # Check which subjects are available at current time
            schedule_df = load_schedule()
            available_subjects = []

            for subject in student_subjects:
                # Obtener la comisión del estudiante para esta materia
                student_commission = students_df[(students_df["dni"].astype(str) == selected_dni) & 
                                                (students_df["materia"] == subject)]["comision"].iloc[0]
                
                # Filtrar horarios por materia y comisión
                subject_schedule = schedule_df[(schedule_df["MATERIA"] == subject) & 
                                            (schedule_df["COMISION"] == student_commission)]
                
                if not subject_schedule.empty:
                    for _, row in subject_schedule.iterrows():
                        if validate_time_for_subject(current_date, current_time, row["FECHA"], row["INICIO"], row["FINAL"]):
                            st.write(f"¡Materia disponible encontrada!")
                            available_subjects.append(subject)
                            break  # Si encontramos al menos un horario válido, añadimos la materia

            if available_subjects:
                selected_subject = st.selectbox("Materia disponible:", available_subjects)
                commission = students_df[(students_df["dni"].astype(str) == selected_dni) & 
                                    (students_df["materia"] == selected_subject)]["comision"].iloc[0]
                
                # Check if attendance already registered
                attendance_df = load_attendance()
                if is_attendance_registered(attendance_df, selected_dni, selected_subject, current_date):
                    st.warning("Ya registró su asistencia para esta materia hoy.")
                else:
                    # Check if device valid
                    device_valid = validate_device_for_subject(device_id, selected_subject, current_date.strftime('%Y-%m-%d'))
                    
                    if not device_valid:
                        st.error("Este dispositivo ya fue utilizado para registrar asistencia en esta materia y fecha.")
                    else:
                        # QR code verification - offer two options
                        verification_method = st.radio(
                            "Método de verificación:",
                            ["Escanear código QR", "Ingresar código manualmente"]
                        )
                        
                        if verification_method == "Escanear código QR":
                            st.info("Escanee el código QR mostrado por el profesor")
                            uploaded_file = st.camera_input("Tomar foto del código QR")
                            
                            if uploaded_file is not None:
                                st.info("Procesamiento de QR en desarrollo. Por favor, ingrese el código manualmente.")
                                code = st.text_input("Código:", max_chars=6, key="qr_code_input")
                                
                                if st.button("Verificar código", key="verify_qr_code"):
                                    if verify_classroom_code(code, selected_subject, commission):
                                        # FIXED: Register attendance with proper arguments
                                        device_info = {
                                            "hostname": socket.gethostname(),
                                            "ip": get_local_ip(),
                                            "device_id": device_id
                                        }
                                        
                                        register_attendance_function(
                                            selected_dni,
                                            student_data['apellido_nombre'],
                                            selected_subject,
                                            commission,
                                            current_date,
                                            current_time,
                                            device_info
                                        )
                                    else:
                                        st.error("Código inválido o expirado")
                                        
                        else:  # Manual code entry
                            st.info("Ingrese el código mostrado por el profesor")
                            code = st.text_input("Código:", max_chars=6, key="manual_code_input")
                            
                            if st.button("Verificar código", key="verify_manual_code"):
                                if verify_classroom_code(code, selected_subject, commission):
                                    # FIXED: Register attendance with proper arguments
                                    device_info = {
                                        "hostname": socket.gethostname(),
                                        "ip": get_local_ip(),
                                        "device_id": device_id
                                    }
                                    
                                    register_attendance_function(
                                        selected_dni,
                                        student_data['apellido_nombre'],
                                        selected_subject,
                                        commission,
                                        current_date,
                                        current_time,
                                        device_info
                                    )
                                else:
                                    st.error("Código inválido o expirado")
            else:
                st.warning("No hay materias disponibles en este horario.")
        else:
            st.error("DNI no encontrado en el sistema.")

# FIXED: Function to register attendance with all required parameters
def register_attendance_function(selected_dni, student_name, selected_subject, commission, current_date, current_time, device_info):
    # Guardar asistencia
    save_attendance(
        selected_dni,
        student_name,
        selected_subject,
        commission,
        current_date.strftime('%Y-%m-%d'),
        current_time.strftime('%H:%M:%S'),
        device_info["hostname"],
        device_info["ip"],
        device_info["device_id"]
    )
    
    # En lugar de reiniciar inmediatamente, establecer estado de confirmación
    st.session_state.attendance_registered = True
    st.session_state.registration_info = {
        "student_name": student_name,
        "subject": selected_subject,
        "time": current_time.strftime('%H:%M:%S'),
        "date": current_date.strftime('%d/%m/%Y')
    }
    st.rerun()
    
# Main app
def main():
    try:
        if not st.session_state.admin_mode and hasattr(st.session_state, 'temp_show_admin') and st.session_state.temp_show_admin:
            admin_login()
        
        # When admin is authenticated:
        if st.session_state.admin_mode:
            admin_dashboard()
        else:
            # Your existing student login code
            student_login()
    except Exception as e:
        st.error(f"Detailed Error Message: {str(e)}")
          
    sidebar()
    
if __name__ == "__main__":
    main()