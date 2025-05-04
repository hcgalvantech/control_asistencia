import pandas as pd
import datetime
import os

def parse_time(time_str):
    """Parse time string to datetime.time object"""
    if isinstance(time_str, str):
        try:
            # Try HH:MM:SS format
            time_parts = time_str.split(':')
            if len(time_parts) == 3:
                hour, minute, second = map(int, time_parts)
                return datetime.time(hour, minute, second)
            elif len(time_parts) == 2:
                hour, minute = map(int, time_parts)
                return datetime.time(hour, minute)
        except ValueError:
            return None
    return time_str

def parse_date(date_str):
    """Parse date string to datetime.date object"""
    if isinstance(date_str, str):
        try:
            # Try different date formats
            if '-' in date_str:  # YYYY-MM-DD format
                year, month, day = map(int, date_str.split('-'))
                return datetime.date(year, month, day)
            elif '/' in date_str:  # DD/MM/YYYY format
                day, month, year = map(int, date_str.split('/'))
                return datetime.date(year, month, day)
        except (ValueError, IndexError):
            return None
    return date_str

def validate_time_for_subject(current_date, current_time, schedule_date, start_time, end_time):
    """
    Check if current date and time are within the allowed range for a subject
    Parameters:
        current_date (datetime.date): Current date in Argentina timezone
        current_time (datetime.time): Current time in Argentina timezone
        schedule_date (str): Date when the class is scheduled (YYYY-MM-DD or DD/MM/YYYY format)
        start_time (str): Start time of the class
        end_time (str): End time of the class
    Returns:
        bool: True if current date and time are valid for this class, False otherwise
    """
    """Verificación mejorada de fecha y horario"""
    """
    Verificación mejorada de fecha y horario
    Maneja correctamente los formatos de fecha DD/MM/YYYY y YYYY-MM-DD
    """
    # Debug info - descomentar para diagnosticar
    # print(f"Validando: Fecha actual: {current_date}, Hora actual: {current_time}")
    # print(f"Contra horario: Fecha: {schedule_date}, Inicio: {start_time}, Fin: {end_time}")
    
    # Parseo de tiempos
    if isinstance(start_time, str):
        parts = start_time.split(':')
        if len(parts) >= 2:
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2]) if len(parts) > 2 else 0
                start_time = datetime.time(hour, minute, second)
            except ValueError:
                return False
    
    if isinstance(end_time, str):
        parts = end_time.split(':')
        if len(parts) >= 2:
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2]) if len(parts) > 2 else 0
                end_time = datetime.time(hour, minute, second)
            except ValueError:
                return False
    
    if not isinstance(start_time, datetime.time) or not isinstance(end_time, datetime.time):
        return False
    
    # Parseo de fecha del horario
    schedule_date_obj = None
    if isinstance(schedule_date, str):
        try:
            if '/' in schedule_date:  # formato DD/MM/YYYY
                day, month, year = map(int, schedule_date.split('/'))
                schedule_date_obj = datetime.date(year, month, day)
            elif '-' in schedule_date:  # formato YYYY-MM-DD
                year, month, day = map(int, schedule_date.split('-'))
                schedule_date_obj = datetime.date(year, month, day)
        except (ValueError, TypeError):
            return False
    
    if not isinstance(schedule_date_obj, datetime.date):
        return False
        
    # Convertir current_date a datetime.date si es string
    if isinstance(current_date, str):
        try:
            if '/' in current_date:
                day, month, year = map(int, current_date.split('/'))
                current_date = datetime.date(year, month, day)
            elif '-' in current_date:
                year, month, day = map(int, current_date.split('-'))
                current_date = datetime.date(year, month, day)
        except (ValueError, TypeError):
            return False
    
    # Verificar si es el día de la clase
    if current_date != schedule_date_obj:
        return False
    
    # Convertir horas a minutos para comparación
    def time_to_minutes(t):
        return t.hour * 60 + t.minute
    
    current_minutes = time_to_minutes(current_time)
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    
    # Verificar si estamos dentro del rango horario
    # Agregamos 15 minutos de tolerancia al final
    return start_minutes <= current_minutes <= (end_minutes + 15)

def is_attendance_registered(attendance_df, dni, subject, date):
    """Check if attendance is already registered for this subject and date"""
    # Convert date to string for comparison if it's not already
    if isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    else:
        date_str = str(date)
    
    # Filter attendance records
    matching_records = attendance_df[
        (attendance_df['DNI'].astype(str) == str(dni)) & 
        (attendance_df['MATERIA'] == subject) & 
        (attendance_df['FECHA'] == date_str)
    ]
    
    return not matching_records.empty

# Mejora para utils.py - validate_device_for_subject
def validate_device_for_subject(device_id, subject, date_str):
    """
    Verifica si un dispositivo ya fue utilizado para registrar asistencia
    en una materia específica y fecha
    """
    device_usage_path = 'data/device_usage.csv'
    if not os.path.exists(device_usage_path):
        # Si no existe archivo, crear uno vacío
        pd.DataFrame(columns=['DEVICE_ID', 'DNI', 'MATERIA', 'FECHA', 'TIMESTAMP']).to_csv(device_usage_path, index=False)
        return True
        
    device_df = pd.read_csv(device_usage_path)
    
    # Normalizar formato de fecha para comparación
    if '/' in date_str:  # Si es DD/MM/YYYY
        day, month, year = map(int, date_str.split('/'))
        date_normalized = f"{year}-{month:02d}-{day:02d}"
    else:
        date_normalized = date_str
        
    # Verificar si el dispositivo ya se usó para esta materia y fecha
    matching_records = device_df[
        (device_df['DEVICE_ID'] == device_id) & 
        (device_df['MATERIA'] == subject) & 
        (device_df['FECHA'] == date_normalized)
    ]
    
    return matching_records.empty

def save_attendance(dni, name, subject, commission, date, time, device, ip, device_id=None):
    """Save attendance record to CSV file and register device usage"""
    from network import get_argentina_datetime
    
    # Obtener fecha y hora actual de Argentina
    argentina_now, _, _ = get_argentina_datetime()
    
    """Save attendance record to CSV file and register device usage"""
    new_record = {
        'DNI': dni,
        'APELLIDO Y NOMBRE': name,
        'MATERIA': subject,
        'COMISION': commission,
        'FECHA': date,
        'HORA': time,
        'DISPOSITIVO': device,
        'IP': ip
    }
    
    # Read existing attendance data
    attendance_path = 'data/attendance.csv'
    if os.path.exists(attendance_path):
        attendance_df = pd.read_csv(attendance_path)
    else:
        attendance_df = pd.DataFrame(columns=list(new_record.keys()))
    
    # Append new record
    attendance_df = pd.concat([attendance_df, pd.DataFrame([new_record])], ignore_index=True)
    
    # Save back to CSV
    attendance_df.to_csv(attendance_path, index=False)
    
    # Also record device usage to prevent reuse
    if device_id:
        device_usage_path = 'data/device_usage.csv'
        
        if os.path.exists(device_usage_path):
            device_df = pd.read_csv(device_usage_path)
        else:
            device_df = pd.DataFrame(columns=['DEVICE_ID', 'DNI', 'MATERIA', 'FECHA', 'TIMESTAMP'])
        
        # Record device usage
        device_record = {
            'DEVICE_ID': device_id,
            'DNI': dni,
            'MATERIA': subject,
            'FECHA': date,
            'TIMESTAMP': argentina_now.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        device_df = pd.concat([device_df, pd.DataFrame([device_record])], ignore_index=True)
        device_df.to_csv(device_usage_path, index=False)
    
    return True

def check_schedule_conflicts():
    """
    Check if there are any conflicts in the schedule (same subject at overlapping times)
    Returns a list of conflict dictionaries
    """
    """
    Verificación mejorada de conflictos en horarios
    Considera fecha + comisión + horarios
    """
    """
    Verificación mejorada de conflictos en horarios
    Considera fecha + comisión + horarios
    """
    from database import load_schedule
    schedule_df = load_schedule()
    conflicts = []
    
    # Convertir strings de tiempo a objetos datetime.time
    def convert_time(time_str):
        if isinstance(time_str, str):
            try:
                hour, minute, second = map(int, time_str.split(':'))
                return datetime.time(hour, minute, second)
            except ValueError:
                return None
        return time_str
    
    # Convertir strings de fecha a objetos datetime.date
    def convert_date(date_str):
        if isinstance(date_str, str):
            try:
                if '/' in date_str:  # DD/MM/YYYY
                    day, month, year = map(int, date_str.split('/'))
                    return datetime.date(year, month, day)
                elif '-' in date_str:  # YYYY-MM-DD
                    year, month, day = map(int, date_str.split('-'))
                    return datetime.date(year, month, day)
            except ValueError:
                return None
        return date_str
    
    # Aplicar conversiones
    schedule_df['INICIO_OBJ'] = schedule_df['INICIO'].apply(convert_time)
    schedule_df['FINAL_OBJ'] = schedule_df['FINAL'].apply(convert_time)
    schedule_df['FECHA_OBJ'] = schedule_df['FECHA'].apply(convert_date)
    
    # Verificar cada par de horarios
    for i, row1 in schedule_df.iterrows():
        for j, row2 in schedule_df.iterrows():
            if i < j:  # Verificar cada par solo una vez
                # Verificar si las fechas son iguales
                if row1['FECHA_OBJ'] == row2['FECHA_OBJ']:
                    # Verificar comisiones iguales
                    same_commission = row1['COMISION'] == row2['COMISION']
                    
                    if same_commission:
                        # Verificar superposición de horarios
                        row1_start = row1['INICIO_OBJ'] 
                        row1_end = row1['FINAL_OBJ']
                        row2_start = row2['INICIO_OBJ']
                        row2_end = row2['FINAL_OBJ']
                        
                        if (row1_start <= row2_end and row1_end >= row2_start):
                            conflicts.append({
                                'materia1': row1['MATERIA'],
                                'comision1': row1['COMISION'],
                                'fecha1': row1['FECHA'],
                                'inicio1': row1['INICIO'],
                                'final1': row1['FINAL'],
                                'materia2': row2['MATERIA'],
                                'comision2': row2['COMISION'],
                                'fecha2': row2['FECHA'],
                                'inicio2': row2['INICIO'],
                                'final2': row2['FINAL']
                            })
    return conflicts

# Añadir a utils.py
def detect_mobile_device():
    """
    Detecta si el dispositivo actual es un teléfono móvil
    usando características del navegador
    """
    import streamlit as st
    
    # Código JavaScript para detectar dispositivo móvil
    mobile_detect_js = """
    <script>
    function detectMobile() {
        const userAgent = navigator.userAgent || navigator.vendor || window.opera;
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent);
        const screenWidth = window.innerWidth;
        // Considerar dispositivos con pantalla pequeña como móviles
        window.parent.postMessage({
            type: "IS_MOBILE",
            isMobile: isMobile || screenWidth < 768
        }, "*");
    }
    detectMobile();
    </script>
    """
    
    # Para desarrollo, mantener la opción de simulación
    is_mobile = st.checkbox("¿Está usando un dispositivo móvil?", value=True, key="mobile_simulator")
    
    # En producción, descomenta estas líneas:
    # st.components.v1.html(mobile_detect_js, height=0)
    # is_mobile = st.session_state.get("detected_mobile", False)
    
    return is_mobile

# Añadir esta función a utils.py
def generate_persistent_token(dni):
    """Genera un token único persistente para el estudiante"""
    import hashlib
    import time
    import secrets
    
    # Generar token único
    seed = f"{dni}-{time.time()}-{secrets.token_hex(16)}"
    token = hashlib.sha256(seed.encode()).hexdigest()
    
    # Guardar en base de datos
    token_path = 'data/student_tokens.csv'
    if not os.path.exists(token_path):
        pd.DataFrame(columns=['DNI', 'TOKEN', 'CREATED_AT']).to_csv(token_path, index=False)
    
    tokens_df = pd.read_csv(token_path)
    
    # Verificar si ya existe token
    if dni in tokens_df['DNI'].astype(str).values:
        # Actualizar token existente
        tokens_df.loc[tokens_df['DNI'].astype(str) == str(dni), 'TOKEN'] = token
        tokens_df.loc[tokens_df['DNI'].astype(str) == str(dni), 'CREATED_AT'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        # Crear nuevo registro
        new_record = {
            'DNI': dni,
            'TOKEN': token,
            'CREATED_AT': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        tokens_df = pd.concat([tokens_df, pd.DataFrame([new_record])], ignore_index=True)
    
    tokens_df.to_csv(token_path, index=False)
    return token
