import streamlit as st
import pandas as pd
import datetime
import os
import socket
from pathlib import Path
from utils import validate_time_for_subject, is_attendance_registered, save_attendance
from network import check_wifi_connection, is_ip_in_allowed_range, get_local_ip, get_argentina_datetime
from database import load_students, load_attendance, load_schedule, load_admin_config

# Set page config
st.set_page_config(
    page_title="Sistema de Asistencia",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state variables
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'student_data' not in st.session_state:
    st.session_state.student_data = None
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False

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
    schedule_data.to_csv('data/schedule.csv', index=False)

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

# Network validation function
def validate_network():
    admin_config = load_admin_config()
    allowed_ranges = admin_config.get("allowed_ip_ranges", ["192.168.1.0/24"])
    
    if not check_wifi_connection():
        st.error("❌ Debe estar conectado a una red WiFi para utilizar el sistema")
        return False
    
    # Use our improved function to get the local IP address
    client_ip = get_local_ip()
    
    if not is_ip_in_allowed_range(client_ip, allowed_ranges):
        st.error(f"❌ Su dirección IP ({client_ip}) está fuera del rango permitido")
        return False
    
    return True

# Student authentication
def student_login():
    st.title("Sistema de Registro de Asistencia")
    
    # Network validation
    if not validate_network():
        return
    
    students_df = load_students()
    
    # Date and time validation using Argentina timezone
    _, current_date, current_time = get_argentina_datetime()
    
    st.subheader("Registro de Asistencia")
    st.info(f"Fecha actual: {current_date.strftime('%d/%m/%Y')} - Hora: {current_time.strftime('%H:%M:%S')} (Hora de Buenos Aires)")
    
    # Create a list of all DNIs for the dropdown
    dni_list = [""] + sorted(students_df["DNI"].astype(str).unique().tolist())
    selected_dni = st.selectbox("Seleccione su DNI:", dni_list)
    
    if selected_dni:
        # Get student data
        student_data = students_df[students_df["DNI"].astype(str) == selected_dni].to_dict('records')
        
        if student_data:
            student_data = student_data[0]
            st.session_state.student_data = student_data
            
            st.info(f"Estudiante: {student_data['APELLIDO Y NOMBRE']}")
            st.info(f"Tecnicatura: {student_data['TECNICATURA']}")
            
            # Get available subjects for this student
            student_subjects = students_df[students_df["DNI"].astype(str) == selected_dni]["MATERIA"].unique().tolist()
            
            # Check which subjects are available at current time
            schedule_df = load_schedule()
            available_subjects = []
            
            for subject in student_subjects:
                subject_schedule = schedule_df[schedule_df["MATERIA"] == subject]
                if not subject_schedule.empty:
                    for _, row in subject_schedule.iterrows():
                        if validate_time_for_subject(current_date, current_time, row["FECHA"], row["INICIO"], row["FINAL"]):
                            available_subjects.append(subject)
            
            if available_subjects:
                selected_subject = st.selectbox("Materia disponible:", available_subjects)
                
                # Check if attendance was already registered for this subject today
                attendance_df = load_attendance()
                if is_attendance_registered(attendance_df, selected_dni, selected_subject, current_date):
                    st.warning("Ya registró su asistencia para esta materia hoy.")
                else:
                    if st.button("Registrar Asistencia"):
                        # Get current device information
                        device_info = {
                            "ip": get_local_ip(),
                            "hostname": socket.gethostname()
                        }
                        
                        # Get commission for this subject
                        commission = students_df[(students_df["DNI"].astype(str) == selected_dni) & 
                                               (students_df["MATERIA"] == selected_subject)]["COMISION"].iloc[0]
                        
                        # Save attendance
                        save_attendance(
                            selected_dni,
                            student_data['APELLIDO Y NOMBRE'],
                            selected_subject,
                            commission,
                            str(current_date),
                            str(current_time),
                            device_info["hostname"],
                            device_info["ip"]
                        )
                        
                        st.success(f"Asistencia registrada para {selected_subject} a las {current_time.strftime('%H:%M:%S')}")
            else:
                st.warning("No hay materias disponibles en este horario.")
        else:
            st.error("DNI no encontrado en el sistema.")

# Main app
def main():
    sidebar()
    
    # Show admin login if requested
    if not st.session_state.admin_mode and hasattr(st.session_state, 'temp_show_admin') and st.session_state.temp_show_admin:
        admin_login()
        return
    
    # Regular student view
    if not st.session_state.admin_mode:
        student_login()

if __name__ == "__main__":
    main()
