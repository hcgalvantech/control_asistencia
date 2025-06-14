import datetime
import os
import pandas as pd
import streamlit as st
from supabase import create_client

# Obtener cliente Supabase
def get_supabase_client():
    try:
        # Intentar obtener de secrets primero
        if hasattr(st, 'secrets') and 'SUPABASE_URL' in st.secrets:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
        else:
            # Usar variables de entorno
            from dotenv import load_dotenv
            load_dotenv()
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                st.error("No se encontraron credenciales de Supabase")
                return None
        
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Error connecting to Supabase: {str(e)}")
        return None

def load_students():
    """Cargar datos de estudiantes desde Supabase"""
    supabase = get_supabase_client()
    if not supabase:
        return pd.DataFrame()
        
    response = supabase.table('students').select('*').execute()
    df = pd.DataFrame(response.data)
    
    # No convertimos nombres de columnas para mantener consistencia con la DB
    return df

def load_attendance():
    """Cargar registros de asistencia desde Supabase"""
    supabase = get_supabase_client()
    if not supabase:
        return pd.DataFrame()
        
    response = supabase.table('attendance').select('*').execute()
    return pd.DataFrame(response.data)

def load_schedule():
    """Cargar horarios desde Supabase"""
    supabase = get_supabase_client()
    if not supabase:
        return pd.DataFrame()
        
    response = supabase.table('schedule').select('*').execute()
    return pd.DataFrame(response.data)

def save_attendance(dni, name, subject, commission, date, time, device, ip, device_id):
    """Guardar registro de asistencia"""
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    # Asegurar formato de fecha para Supabase
    if isinstance(date, str) and '/' in date:
        # Convertir dd/mm/yyyy a formato ISO
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
    
    try:
        # Intentar insertar en la tabla de asistencia
        supabase.table('attendance').insert(data).execute()
        
        try:
            # Intentar insertar en device_usage
            device_data = {
                'DEVICE_ID': device_id,
                'DNI': dni,
                'MATERIA': subject,
                'FECHA': date,
                'TIMESTAMP': datetime.datetime.now().isoformat()
            }
            supabase.table('device_usage').insert(device_data).execute()
            return True
        except Exception as device_error:
            error_str = str(device_error)
            if "23505" in error_str:  # Código de error para violación de clave única
                st.warning("Este dispositivo ya ha sido utilizado para registrar asistencia en esta materia hoy.")
                # Ya tenemos la asistencia registrada, así que podríamos considerarlo un éxito
                return True
            else:
                # Otros errores relacionados con device_usage
                st.error(f"Error al registrar uso del dispositivo: {error_str}")
                # Revertir la entrada de asistencia ya que el registro de dispositivo falló
                supabase.table('attendance').delete().eq('DNI', dni).eq('MATERIA', subject).eq('FECHA', date).execute()
                return False
    except Exception as e:
        st.error(f"Error al guardar asistencia: {str(e)}")
        return False

def is_attendance_registered(dni, subject, date):
    """Verificar si la asistencia ya está registrada"""
    supabase = get_supabase_client()
    if not supabase:
        return False
        
    # Asegurar formato de fecha para Supabase
    if isinstance(date, datetime.date):
        date = date.strftime('%Y-%m-%d')
    
    response = supabase.table('attendance').select('*')\
        .eq('DNI', dni)\
        .eq('MATERIA', subject)\
        .eq('FECHA', date)\
        .execute()
    
    return len(response.data) > 0

def load_admin_config():
    """Cargar configuración de administración"""
    supabase = get_supabase_client()
    if not supabase:
        return {}
        
    response = supabase.table('admin_config').select('*').execute()
    
    if not response.data:
        # Configuración predeterminada
        default_config = {
            "allowed_ip_ranges": ["192.168.1.0/24"],
            "admin_username": "admin",
            "admin_password": "admin123"
        }
        supabase.table('admin_config').insert(default_config).execute()
        return default_config
    
    return response.data[0]

def update_admin_config(config_data):
    """Actualizar configuración de administración"""
    supabase = get_supabase_client()
    if not supabase:
        return False
        
    response = supabase.table('admin_config').select('id').execute()
    if response.data:
        config_id = response.data[0]['id']
        supabase.table('admin_config').update(config_data).eq('id', config_id).execute()
    else:
        supabase.table('admin_config').insert(config_data).execute()
    return True

def save_verification_code(dni, phone, code):
    """Guardar código de verificación"""
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    from network import get_argentina_datetime
    
    argentina_now, _, _ = get_argentina_datetime()
    argentina_timestamp = argentina_now.isoformat()
    
    response = supabase.table('verification_codes').select('*').eq('DNI', str(dni)).execute()
    
    if response.data:
        supabase.table('verification_codes').update({
            'CODE': code,
            'TIMESTAMP': argentina_timestamp,
            'VERIFIED': False
        }).eq('DNI', str(dni)).execute()
    else:
        new_record = {
            'DNI': str(dni),
            'PHONE': phone,
            'CODE': code,
            'TIMESTAMP': argentina_timestamp,
            'VERIFIED': False
        }
        supabase.table('verification_codes').insert(new_record).execute()
    
    return True

def save_classroom_code(code, subject, commission, expiry_time):
    """Guardar código de clase"""
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    # Eliminar códigos expirados
    now = datetime.datetime.now().isoformat()
    try:
        supabase.table('classroom_codes').delete().lt('EXPIRY_TIME', now).execute()
        
        # Insertar nuevo código
        data = {
            'CODE': code,
            'SUBJECT': subject,
            'COMMISSION': commission,
            'EXPIRY_TIME': expiry_time
        }
        supabase.table('classroom_codes').insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar código de clase: {str(e)}")
        return False

def verify_classroom_code(code, subject, commission):
    """Verificar código de clase"""
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    now = datetime.datetime.now().isoformat()
    response = supabase.table('classroom_codes')\
        .select('*')\
        .eq('CODE', code)\
        .eq('SUBJECT', subject)\
        .eq('COMMISSION', commission)\
        .gt('EXPIRY_TIME', now)\
        .execute()
    
    return len(response.data) > 0

# En database.py - Modifica esta función:
def validate_device_for_subject(device_id, dni, subject, date):
    """
    Verificar si el dispositivo ya fue usado por OTRO estudiante para esta materia y fecha
    Permitir que el mismo estudiante use el mismo dispositivo
    """
    supabase = get_supabase_client()
    if not supabase:
        return True
    
    # Buscar si este dispositivo fue usado por OTRO DNI en esta materia/fecha
    response = supabase.table('device_usage')\
        .select('*')\
        .eq('DEVICE_ID', device_id)\
        .eq('MATERIA', subject)\
        .eq('FECHA', date)\
        .neq('DNI', dni)\
        .execute()  # Solo rechazar si es OTRO estudiante
    
    return len(response.data) == 0

##########################
def save_admin_config(config):
    """Save admin configuration to Supabase"""
    supabase = get_supabase_client()
    # Delete existing config and insert new one
    supabase.table('admin_config').delete().neq('id', 0).execute()
    supabase.table('admin_config').insert(config).execute()
    return True

def get_unique_subjects():
    """Get list of unique subjects from student data"""
    supabase = get_supabase_client()
    response = supabase.table('students').select('materia').execute()
    df = pd.DataFrame(response.data)
    return sorted(df['materia'].unique().tolist())

def get_commissions_by_subject(subject):
    """Get commissions available for a specific subject"""
    supabase = get_supabase_client()
    response = supabase.table('students').select('comision').eq('materia', subject).execute()
    df = pd.DataFrame(response.data)
    return sorted(df['comision'].unique().tolist())

def get_attendance_report(date=None, subject=None, commission=None):
    """Generate an attendance report with filters"""
    supabase = get_supabase_client()
    query = supabase.table('attendance').select('*')
    
    if date:
        query = query.eq('FECHA', date)
    
    if subject:
        query = query.eq('MATERIA', subject)
    
    if commission:
        query = query.eq('COMISION', commission)
    
    response = query.execute()
    return pd.DataFrame(response.data)

def get_schedule_by_date(date):
    """Get schedule for a specific date"""
    supabase = get_supabase_client()
    
    # Handle date format conversion if needed
    if isinstance(date, datetime.date):
        date_str = date.strftime('%d/%m/%Y')
    else:
        date_str = date
    
    response = supabase.table('schedule').select('*').eq('FECHA', date_str).execute()
    return pd.DataFrame(response.data)