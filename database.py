import datetime
import json
import os
import pandas as pd
import streamlit as st

# Get Supabase client - reuse from app.py or initialize here
def get_supabase_client():
    try:
        # Try to get from Streamlit secrets first
        if 'SUPABASE_URL' in st.secrets:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
        else:
            # Fall back to environment variables
            from dotenv import load_dotenv
            load_dotenv()
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
        
        from supabase import create_client
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Error connecting to Supabase: {str(e)}")
        return None

def load_students():
    """Load student data from Supabase"""
    supabase = get_supabase_client()
    response = supabase.table('students').select('*').execute()
    df = pd.DataFrame(response.data)
    
    # Rename columns to match code expectations
    column_mapping = {
        'dni': 'DNI',
        'apellido_nombre': 'APELLIDO Y NOMBRE',
        'telefono': 'TELEFONO',
        'correo': 'CORREO',
        'tecnicatura': 'TECNICATURA',
        'materia': 'MATERIA',
        'comision': 'COMISION'
    }
    
    return df.rename(columns=column_mapping)

def load_attendance():
    """Load attendance records from Supabase"""
    supabase = get_supabase_client()
    response = supabase.table('attendance').select('*').execute()
    return pd.DataFrame(response.data)

def load_schedule():
    """Load class schedule from Supabase"""
    supabase = get_supabase_client()
    response = supabase.table('schedule').select('*').execute()
    return pd.DataFrame(response.data)

def load_admin_config():
    """Load admin configuration from Supabase"""
    supabase = get_supabase_client()
    response = supabase.table('admin_config').select('*').execute()
    
    if not response.data:
        # Default config
        default_config = {
            "allowed_ip_ranges": ["192.168.1.0/24"],
            "admin_username": "admin",
            "admin_password": "admin123"
        }
        # Save default config
        supabase.table('admin_config').insert(default_config).execute()
        return default_config
    
    return response.data[0]

def save_admin_config(config):
    """Save admin configuration to Supabase"""
    supabase = get_supabase_client()
    # Delete existing config and insert new one
    supabase.table('admin_config').delete().neq('id', 0).execute()
    supabase.table('admin_config').insert(config).execute()
    return True

def save_verification_code(dni, phone, code):
    """Save verification code to Supabase"""
    from network import get_argentina_datetime
    
    supabase = get_supabase_client()
    argentina_now, _, _ = get_argentina_datetime()
    argentina_timestamp = argentina_now.isoformat()
    
    # Check if there's already a code for this user
    response = supabase.table('verification_codes').select('*').eq('DNI', str(dni)).execute()
    
    if response.data:
        # Update existing code
        supabase.table('verification_codes').update({
            'CODE': code,
            'TIMESTAMP': argentina_timestamp,
            'VERIFIED': False
        }).eq('DNI', str(dni)).execute()
    else:
        # Add new code
        new_record = {
            'DNI': str(dni),
            'PHONE': phone,
            'CODE': code,
            'TIMESTAMP': argentina_timestamp,
            'VERIFIED': False
        }
        supabase.table('verification_codes').insert(new_record).execute()
    
    return True

def mark_verification_code_verified(dni):
    """Mark a verification code as verified"""
    supabase = get_supabase_client()
    supabase.table('verification_codes').update({'VERIFIED': True}).eq('DNI', str(dni)).execute()
    return True

def get_students_by_subject(subject, commission=None):
    """Get students enrolled in a specific subject and commission"""
    supabase = get_supabase_client()
    
    if commission:
        response = supabase.table('students').select('*').eq('MATERIA', subject).eq('COMISION', commission).execute()
    else:
        response = supabase.table('students').select('*').eq('MATERIA', subject).execute()
    
    return pd.DataFrame(response.data)

def get_attendance_by_date(date):
    """Get attendance records for a specific date"""
    supabase = get_supabase_client()
    response = supabase.table('attendance').select('*').eq('FECHA', date).execute()
    return pd.DataFrame(response.data)

def get_attendance_by_subject_date(subject, date):
    """Get attendance records for a specific subject and date"""
    supabase = get_supabase_client()
    response = supabase.table('attendance').select('*').eq('MATERIA', subject).eq('FECHA', date).execute()
    return pd.DataFrame(response.data)

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