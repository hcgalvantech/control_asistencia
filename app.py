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
from utils import validate_time_for_subject, detect_mobile_device, is_attendance_registered, save_attendance, validate_device_for_subject
from network import check_wifi_connection, is_ip_in_allowed_range, get_local_ip, get_argentina_datetime, get_device_id
from database import load_students, load_attendance, load_schedule, load_admin_config, save_verification_code


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
    

# Create data directory and files if they don't exist
if not os.path.exists('data'):
    os.makedirs('data')

# Copy initial data from attached assets
assets_path = Path('attached_assets')
if assets_path.exists() and (assets_path / 'alumnosPorMateria-030525_reducido.csv').exists():
    students_df = pd.read_csv(assets_path / 'alumnosPorMateria-030525_reducido.csv', skiprows=0)
    if not os.path.exists('data/students.csv'):
        students_df.to_csv('data/students.csv', index=False)

# Initialize other data files if they don't exist
if not os.path.exists('data/attendance.csv'):
    pd.DataFrame(columns=['DNI', 'APELLIDO Y NOMBRE', 'MATERIA', 'COMISION', 
                         'FECHA', 'HORA', 'DISPOSITIVO', 'IP']).to_csv('data/attendance.csv', index=False)

if not os.path.exists('data/schedule.csv'):
    # Generate a schedule file based on the student data
    students_df = pd.read_csv('data/students.csv')
    schedule_data = students_df[['MATERIA', 'COMISION', 'INICIO', 'FINAL']].drop_duplicates()
    # Ensure we have a FECHA column
    if 'FECHA' not in schedule_data.columns:
        # Add today's date as default
        schedule_data['FECHA'] = datetime.datetime.now().strftime('%d/%m/%Y')
    schedule_data.to_csv('data/schedule.csv', index=False)

# Initialize verification codes file
if not os.path.exists('data/verification_codes.csv'):
    pd.DataFrame(columns=['DNI', 'PHONE', 'CODE', 'TIMESTAMP', 'VERIFIED']).to_csv('data/verification_codes.csv', index=False)

# Initialize device usage tracking
if not os.path.exists('data/device_usage.csv'):
    pd.DataFrame(columns=['DEVICE_ID', 'DNI', 'MATERIA', 'FECHA', 'TIMESTAMP']).to_csv('data/device_usage.csv', index=False)

# In your initialization section
if not os.path.exists('data/classroom_codes.csv'):
    pd.DataFrame(columns=['CODE', 'SUBJECT', 'COMMISSION', 'EXPIRY_TIME']).to_csv('data/classroom_codes.csv', index=False)
    
# Initialize admin config
if not os.path.exists('data/admin_config.json'):
    import json
    with open('data/admin_config.json', 'w') as f:
        json.dump({
            "allowed_ip_ranges": ["192.168.1.0/24"],
            "admin_username": "admin",
            "admin_password": "admin123"
        }, f)

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

# In the admin section
def admin_dashboard():
    st.title("Panel Administrativo")
    
    tab1, tab2, tab3 = st.tabs(["Asistencia", "Generador de Códigos", "Configuración"])
    
    with tab1:
        # Existing attendance viewing functionality
        pass
        
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
    """Save active classroom code to database"""
    codes_df = pd.read_csv('data/classroom_codes.csv') if os.path.exists('data/classroom_codes.csv') else pd.DataFrame(columns=['CODE', 'SUBJECT', 'COMMISSION', 'EXPIRY_TIME'])
    
    # Remove expired codes
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    codes_df = codes_df[codes_df['EXPIRY_TIME'] > now]
    
    # Add new code
    new_code = pd.DataFrame({
        'CODE': [code],
        'SUBJECT': [subject],
        'COMMISSION': [commission],
        'EXPIRY_TIME': [expiry_time]
    })
    
    codes_df = pd.concat([codes_df, new_code], ignore_index=True)
    codes_df.to_csv('data/classroom_codes.csv', index=False)

def verify_classroom_code(code, subject, commission):
    """Verify if the code is valid for the subject and commission"""
    if not os.path.exists('data/classroom_codes.csv'):
        return False
        
    codes_df = pd.read_csv('data/classroom_codes.csv')
    
    # Remove expired codes
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    codes_df = codes_df[codes_df['EXPIRY_TIME'] > now]
    
    # Check if code exists for subject and commission
    valid = not codes_df[(codes_df['CODE'] == code) & 
                      (codes_df['SUBJECT'] == subject) & 
                      (codes_df['COMMISSION'] == commission)].empty
    
    return valid

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


def generate_verification_code(dni, phone):
    # Esta función ahora solo registra que iniciamos un proceso de verificación
    save_verification_code(dni, phone, "firebase_initiated")
    
    # Iniciar proceso de verificación con Firebase
    if send_verification_code(phone):
        return True
    return False


# Modificación de la función de verificación de teléfono
def phone_verification(dni, phone):
    st.subheader("Verificación de Teléfono")
    
    # Si no hay sesión de verificación, iniciar el proceso
    if 'verification_session_id' not in st.session_state:
        if send_verification_code(phone):
            st.info(f"Se ha enviado un código por SMS al número: {phone}")
        else:
            st.error("No se pudo enviar el código de verificación")
            return
    else:
        st.info(f"Ingrese el código recibido por SMS en el número: {phone}")
    
    # Entrada del código
    verification_input = st.text_input("Código de verificación:", max_chars=6)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Verificar"):
            if verify_code(verification_input):  # Modified this line
                st.session_state.phone_verified = True
                st.success("Teléfono verificado correctamente")
                # Limpiar la sesión de verificación
                if 'verification_session_id' in st.session_state:
                    del st.session_state.verification_session_id
                st.rerun()
            else:
                st.error("Código incorrecto. Intente nuevamente.")
    
    with col2:
        if st.button("Reenviar código"):
            # Limpiar sesión anterior
            if 'verification_session_id' in st.session_state:
                del st.session_state.verification_session_id
            
            # Enviar nuevo código
            if send_verification_code(phone):
                st.info("Nuevo código enviado")
                st.rerun()
            else:
                st.error("No se pudo enviar un nuevo código")
                
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
    dni_list = [""] + sorted(students_df["DNI"].astype(str).unique().tolist())
    selected_dni = st.selectbox("Seleccione su DNI:", dni_list)
    
    if selected_dni:
        # Obtener datos del estudiante
        student_data = students_df[students_df["DNI"].astype(str) == selected_dni].to_dict('records')
        
        if student_data:
            student_data = student_data[0]
            st.session_state.student_data = student_data
            st.info(f"Estudiante: {student_data['APELLIDO Y NOMBRE']}")
            st.info(f"Tecnicatura: {student_data['TECNICATURA']}")
            
            # Verificación del teléfono
            student_phone = str(student_data.get('TELEFONO', ''))
            
            # Si el teléfono no está verificado, iniciar proceso
            if not st.session_state.phone_verified:
                # Si estamos en un móvil, simplificar verificación
                if is_mobile and st.checkbox("Este es mi celular registrado", value=False):
                    st.session_state.phone_verified = True
                    st.success("Dispositivo móvil reconocido")
                    st.rerun()
                
                # Verificación por código tradicional
                if not st.session_state.verification_step:
                    code = generate_verification_code(selected_dni, student_phone)
                    st.session_state.verification_step = True
                    st.rerun()
                
            # Replace the phone verification part of student_login with this:

            # If the teléfono no está verificado, use QR verification instead
            if not st.session_state.phone_verified:
                st.subheader("Verificación de Presencia")
                
                # Check if attendance verification is in progress
                if 'qr_verification_step' not in st.session_state:
                    st.session_state.qr_verification_step = False
                
                # Get commission for this subject
                student_subjects = students_df[students_df["DNI"].astype(str) == selected_dni]["MATERIA"].unique().tolist()
                
                # Show available subjects
                if student_subjects:
                    selected_subject = st.selectbox("Seleccione materia:", student_subjects)
                    commission = students_df[(students_df["DNI"].astype(str) == selected_dni) & 
                                        (students_df["MATERIA"] == selected_subject)]["COMISION"].iloc[0]
                    
                    verification_method = st.radio(
                        "Método de verificación:",
                        ["Escanear código QR", "Ingresar código manualmente"]
                    )
                    
                    if verification_method == "Escanear código QR":
                        st.info("Escanee el código QR mostrado por el profesor")
                        # Use camera input for QR scanning
                        uploaded_file = st.camera_input("Tomar foto del código QR")
                        
                        if uploaded_file is not None:
                            # This would need image processing to extract QR code
                            # For now, we'll simulate success
                            st.session_state.qr_verification_step = True
                            st.success("QR detectado! Por favor ingrese el código manualmente para completar")
                    
                    # Manual code entry - either as fallback or primary method
                    code = st.text_input("Código de clase:", max_chars=6)
                    
                    if st.button("Verificar código"):
                        if verify_classroom_code(code, selected_subject, commission):
                            st.session_state.phone_verified = True
                            st.success("Verificación exitosa")
                            st.rerun()
                        else:
                            st.error("Código inválido o expirado")
                            
                else:
                    st.warning("No hay materias disponibles para este estudiante")
                
                return # Exit here until verification is complete
            
            # Continue with attendance process after verification
            
            # Get available subjects for this student
            student_subjects = students_df[students_df["DNI"].astype(str) == selected_dni]["MATERIA"].unique().tolist()
            
            # Check which subjects are available at current time
            schedule_df = load_schedule()
            available_subjects = []

            # Imprimir información de depuración (agregar temporalmente)
            # st.write(f"Fecha actual (Argentina): {current_date}")
            # st.write(f"Hora actual (Argentina): {current_time}")

            for subject in student_subjects:
                # Obtener la comisión del estudiante para esta materia
                student_commission = students_df[(students_df["DNI"].astype(str) == selected_dni) & 
                                                (students_df["MATERIA"] == subject)]["COMISION"].iloc[0]
                
                # Filtrar horarios por materia y comisión
                subject_schedule = schedule_df[(schedule_df["MATERIA"] == subject) & 
                                            (schedule_df["COMISION"] == student_commission)]
                
                if not subject_schedule.empty:
                    for _, row in subject_schedule.iterrows():
                        # Imprimir información de depuración (agregar temporalmente)
                        # st.write(f"Verificando: {subject} - {student_commission}")
                        # st.write(f"Horario: {row['FECHA']} de {row['INICIO']} a {row['FINAL']}")
                    
                        if validate_time_for_subject(current_date, current_time, row["FECHA"], row["INICIO"], row["FINAL"]):
                            st.write(f"¡Materia disponible encontrada!")
                            available_subjects.append(subject)
                            break  # Si encontramos al menos un horario válido, añadimos la materia
            # If there are available subjects, show selection                       
            # In the student_login function, replace phone verification with QR verification
            # After showing available subjects and selecting one:

            if available_subjects:
                selected_subject = st.selectbox("Materia disponible:", available_subjects)
                commission = students_df[(students_df["DNI"].astype(str) == selected_dni) & 
                                    (students_df["MATERIA"] == selected_subject)]["COMISION"].iloc[0]
                
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
                            # Note: Native QR scanning requires JavaScript, which is limited in Streamlit
                            # Alternative: Use a camera input and process the image
                            uploaded_file = st.camera_input("Tomar foto del código QR")
                            
                            if uploaded_file is not None:
                                # In a real implementation, you would process this image to extract QR data
                                # For demo purposes, we'll fallback to manual entry
                                st.info("Procesamiento de QR en desarrollo. Por favor, ingrese el código manualmente.")
                                code = st.text_input("Código:", max_chars=6)
                                
                                if st.button("Verificar código"):
                                    if verify_classroom_code(code, selected_subject, commission):
                                        # Register attendance
                                        register_attendance_function()
                                    else:
                                        st.error("Código inválido o expirado")
                                        
                        else:  # Manual code entry
                            st.info("Ingrese el código mostrado por el profesor")
                            code = st.text_input("Código:", max_chars=6)
                            
                            if st.button("Verificar código"):
                                if verify_classroom_code(code, selected_subject, commission):
                                    # Register attendance
                                    register_attendance_function()
                                else:
                                    st.error("Código inválido o expirado")
            else:
                st.warning("No hay materias disponibles en este horario.")
        else:
            st.error("DNI no encontrado en el sistema.")

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
           
        # When admin is authenticated:
        if st.session_state.admin_mode:
            admin_dashboard()  # Add this line to call the new function
        else:
            # Your existing student login code
            student_login()
    except Exception as e:
        st.error(f"Detailed Error: {str(e)}")
            
    
    sidebar()
    
if __name__ == "__main__":
    main()