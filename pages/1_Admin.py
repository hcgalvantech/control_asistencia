import streamlit as st
import pandas as pd
import datetime
from io import BytesIO
import socket
from pathlib import Path
import sys
import os
import ipaddress

# Add parent directory to path to import from parent modules
sys.path.append(str(Path(__file__).parent.parent))

from database import (
    load_students, load_attendance, load_schedule, load_admin_config,
    save_admin_config, get_unique_subjects, get_commissions_by_subject,
    get_attendance_report
)
from utils import check_schedule_conflicts
from network import is_ip_in_allowed_range, get_local_ip

# Set page config
st.set_page_config(
    page_title="Panel de Administración",
    page_icon="🔐",
    layout="wide"
)

# Initialize session state variables if not exist
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False

# Check if admin is logged in
if not st.session_state.admin_mode:
    st.warning("Debe iniciar sesión como administrador para acceder a esta página")
    st.stop()

# Admin Panel
st.title("Panel de Administración")

# Sidebar for admin navigation
with st.sidebar:
    st.title("Menú de Administración")
    admin_option = st.radio(
        "Seleccione una opción:",
        ["Generar Informes", "Verificar Conflictos", "Configuración del Sistema"]
    )
    
    if st.button("Volver a Página Principal"):
        st.switch_page("app.py")

# Main content based on selected option
if admin_option == "Generar Informes":
    st.header("Generar Informes de Asistencia")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date selection for report
        report_date = st.date_input(
            "Seleccione fecha para el informe",
            datetime.datetime.now().date()
        )
        
        # Convert to string format
        report_date_str = report_date.strftime('%Y-%m-%d')
        
        # Subject selection
        subjects = ["Todos"] + get_unique_subjects()
        selected_subject = st.selectbox("Seleccione materia:", subjects)
        
        # Commission selection (depends on subject)
        if selected_subject != "Todos":
            commissions = ["Todos"] + get_commissions_by_subject(selected_subject)
            selected_commission = st.selectbox("Seleccione comisión:", commissions)
        else:
            selected_commission = "Todos"
    
    with col2:
        # Show report configuration summary
        st.subheader("Resumen de configuración")
        st.write(f"**Fecha:** {report_date_str}")
        st.write(f"**Materia:** {selected_subject}")
        if selected_subject != "Todos":
            st.write(f"**Comisión:** {selected_commission}")
    
    # Generate report button
    if st.button("Generar Informe"):
        # Apply filters for the report
        if selected_subject == "Todos":
            subject_filter = None
        else:
            subject_filter = selected_subject
            
        if selected_commission == "Todos":
            commission_filter = None
        else:
            commission_filter = selected_commission
        
        # Get filtered attendance data
        attendance_data = get_attendance_report(
            date=report_date_str,
            subject=subject_filter,
            commission=commission_filter
        )
        
        if attendance_data.empty:
            st.warning(f"No hay registros de asistencia para la fecha {report_date_str} con los filtros seleccionados.")
        else:
            # Display the report
            st.subheader(f"Informe de Asistencia - {report_date_str}")
            st.dataframe(attendance_data)
            
            # Export to Excel
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                attendance_data.to_excel(writer, index=False, sheet_name="Asistencia")
            
            excel_data = excel_buffer.getvalue()
            
            # Create download button
            report_filename = f"asistencia_{report_date_str}"
            if subject_filter:
                report_filename += f"_{subject_filter}"
            if commission_filter:
                report_filename += f"_{commission_filter}"
            report_filename += ".xlsx"
            
            st.download_button(
                label="Descargar Informe Excel",
                data=excel_data,
                file_name=report_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    # Also add a section to view all historical attendance
    st.header("Historial Completo de Asistencia")
    attendance_df = load_attendance()
    
    if attendance_df.empty:
        st.info("No hay registros de asistencia en el sistema.")
    else:
        # Add a download button for all attendance
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            attendance_df.to_excel(writer, index=False, sheet_name="Asistencia")
        
        excel_data = excel_buffer.getvalue()
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(attendance_df)
        with col2:
            st.download_button(
                label="Descargar Historial Completo",
                data=excel_data,
                file_name="historial_asistencia_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

elif admin_option == "Verificar Conflictos":
    st.header("Verificación de Conflictos en Horarios")
    
    # Check for conflicts in the schedule
    conflicts = check_schedule_conflicts()
    
    if conflicts:
        st.error(f"Se encontraron {len(conflicts)} conflictos en los horarios de las materias:")
        
        for i, conflict in enumerate(conflicts, 1):
            st.warning(
                f"**Conflicto {i}:** \n"
                f"- Materia 1: {conflict['materia1']} ({conflict['comision1']}) "
                f"de {conflict['inicio1']} a {conflict['final1']}\n"
                f"- Materia 2: {conflict['materia2']} ({conflict['comision2']}) "
                f"de {conflict['inicio2']} a {conflict['final2']}"
            )
    else:
        st.success("No se detectaron conflictos en los horarios de las materias.")
    
    # Show current schedule
    st.subheader("Horarios Actuales")
    schedule_df = load_schedule()
    st.dataframe(schedule_df)
    
    # Option to modify schedule
    st.subheader("Modificar Horarios")
    st.info("Esta funcionalidad permitiría modificar los horarios de las materias.")
    
    # For simplicity, we'll just show a placeholder for this functionality
    if st.button("Editar Horarios (No implementado)"):
        st.warning("Funcionalidad no implementada en esta versión del sistema.")

elif admin_option == "Configuración del Sistema":
    st.header("Configuración del Sistema")
    
    admin_config = load_admin_config()
    
    # IP Range Configuration
    st.subheader("Configuración de Rango de IP")
    
    current_ip = get_local_ip()
    st.info(f"Su dirección IP actual es: {current_ip}")
    
    ip_ranges = admin_config.get("allowed_ip_ranges", ["192.168.1.0/24"])
    
    # Display current IP ranges
    st.write("Rangos de IP permitidos actualmente:")
    for i, ip_range in enumerate(ip_ranges):
        st.code(ip_range)
    
    # Add new IP range
    new_ip_range = st.text_input("Nuevo rango de IP (formato CIDR, ejemplo: 192.168.1.0/24):")
    
    if st.button("Agregar Rango de IP"):
        if new_ip_range:
            try:
                # Validate CIDR notation
                ipaddress.IPv4Network(new_ip_range, strict=False)
                
                if new_ip_range not in ip_ranges:
                    ip_ranges.append(new_ip_range)
                    admin_config["allowed_ip_ranges"] = ip_ranges
                    save_admin_config(admin_config)
                    st.success(f"Rango de IP {new_ip_range} agregado correctamente.")
                    st.rerun()
                else:
                    st.warning("Este rango de IP ya está en la lista.")
            except ValueError:
                st.error("Formato de CIDR inválido. Use el formato correcto (ejemplo: 192.168.1.0/24).")
    
    # Administrator credentials
    st.subheader("Credenciales de Administrador")
    
    admin_username = st.text_input("Nombre de usuario:", admin_config.get("admin_username", "admin"))
    admin_password = st.text_input("Contraseña:", admin_config.get("admin_password", ""), type="password")
    
    if st.button("Actualizar Credenciales"):
        admin_config["admin_username"] = admin_username
        if admin_password:  # Only update if a new password is provided
            admin_config["admin_password"] = admin_password
        
        save_admin_config(admin_config)
        st.success("Credenciales de administrador actualizadas.")
