import pandas as pd
import json
import os
import datetime

def load_students():
    """Load student data from CSV"""
    if os.path.exists('data/students.csv'):
        return pd.read_csv('data/students.csv')
    return pd.DataFrame()

def load_attendance():
    """Load attendance records from CSV"""
    if os.path.exists('data/attendance.csv'):
        return pd.read_csv('data/attendance.csv')
    return pd.DataFrame(columns=['DNI', 'APELLIDO Y NOMBRE', 'MATERIA', 'COMISION', 
                                'FECHA', 'HORA', 'DISPOSITIVO', 'IP'])

def load_schedule():
    """Load class schedule from CSV"""
    if os.path.exists('data/schedule.csv'):
        return pd.read_csv('data/schedule.csv')
    return pd.DataFrame()

def load_verification_codes():
    """Load verification codes from CSV"""
    if os.path.exists('data/verification_codes.csv'):
        return pd.read_csv('data/verification_codes.csv')
    return pd.DataFrame(columns=['DNI', 'PHONE', 'CODE', 'TIMESTAMP', 'VERIFIED'])

def load_device_usage():
    """Load device usage tracking from CSV"""
    if os.path.exists('data/device_usage.csv'):
        return pd.read_csv('data/device_usage.csv')
    return pd.DataFrame(columns=['DEVICE_ID', 'DNI', 'MATERIA', 'FECHA', 'TIMESTAMP'])

def load_admin_config():
    """Load admin configuration from JSON"""
    if os.path.exists('data/admin_config.json'):
        with open('data/admin_config.json', 'r') as f:
            return json.load(f)
    
    # Default config
    default_config = {
        "allowed_ip_ranges": ["192.168.1.0/24"],
        "admin_username": "admin",
        "admin_password": "admin123"
    }
    
    # Save default config
    with open('data/admin_config.json', 'w') as f:
        json.dump(default_config, f)
    
    return default_config

def save_admin_config(config):
    """Save admin configuration to JSON"""
    with open('data/admin_config.json', 'w') as f:
        json.dump(config, f)
    return True

def save_verification_code(dni, phone, code):
    """Save verification code to CSV"""
    from network import get_argentina_datetime
    
    verification_path = 'data/verification_codes.csv'
    if os.path.exists(verification_path):
        verification_df = pd.read_csv(verification_path)
    else:
        verification_df = pd.DataFrame(columns=['DNI', 'PHONE', 'CODE', 'TIMESTAMP', 'VERIFIED'])
    
    # Obtener hora de Argentina
    argentina_now, _, _ = get_argentina_datetime()
    argentina_timestamp = argentina_now.strftime('%Y-%m-%d %H:%M:%S')
    
    # Check if there's already a code for this user
    existing = verification_df[verification_df['DNI'].astype(str) == str(dni)]
    if not existing.empty:
        # Update existing code
        verification_df.loc[verification_df['DNI'].astype(str) == str(dni), 'CODE'] = code
        verification_df.loc[verification_df['DNI'].astype(str) == str(dni), 'TIMESTAMP'] = argentina_timestamp
        verification_df.loc[verification_df['DNI'].astype(str) == str(dni), 'VERIFIED'] = False
    else:
        # Add new code
        new_record = {
            'DNI': dni,
            'PHONE': phone,
            'CODE': code,
            'TIMESTAMP': argentina_timestamp,
            'VERIFIED': False
        }
        verification_df = pd.concat([verification_df, pd.DataFrame([new_record])], ignore_index=True)
    
    verification_df.to_csv(verification_path, index=False)
    return True

def mark_verification_code_verified(dni):
    """Mark a verification code as verified"""
    verification_path = 'data/verification_codes.csv'
    
    if os.path.exists(verification_path):
        verification_df = pd.read_csv(verification_path)
        verification_df.loc[verification_df['DNI'].astype(str) == str(dni), 'VERIFIED'] = True
        verification_df.to_csv(verification_path, index=False)
    
    return True

def get_students_by_subject(subject, commission=None):
    """Get students enrolled in a specific subject and commission"""
    students_df = load_students()
    
    if commission:
        filtered_df = students_df[(students_df['MATERIA'] == subject) & 
                                 (students_df['COMISION'] == commission)]
    else:
        filtered_df = students_df[students_df['MATERIA'] == subject]
    
    return filtered_df

def get_attendance_by_date(date):
    """Get attendance records for a specific date"""
    attendance_df = load_attendance()
    return attendance_df[attendance_df['FECHA'] == date]

def get_attendance_by_subject_date(subject, date):
    """Get attendance records for a specific subject and date"""
    attendance_df = load_attendance()
    return attendance_df[(attendance_df['MATERIA'] == subject) & 
                        (attendance_df['FECHA'] == date)]

def get_unique_subjects():
    """Get list of unique subjects from student data"""
    students_df = load_students()
    return sorted(students_df['MATERIA'].unique().tolist())

def get_commissions_by_subject(subject):
    """Get commissions available for a specific subject"""
    students_df = load_students()
    commissions = students_df[students_df['MATERIA'] == subject]['COMISION'].unique()
    return sorted(commissions.tolist())

def get_attendance_report(date=None, subject=None, commission=None):
    """
    Generate an attendance report with filters
    Returns a DataFrame with the filtered attendance data
    """
    attendance_df = load_attendance()
    
    # Apply filters
    if date:
        attendance_df = attendance_df[attendance_df['FECHA'] == date]
    
    if subject:
        attendance_df = attendance_df[attendance_df['MATERIA'] == subject]
    
    if commission:
        attendance_df = attendance_df[attendance_df['COMISION'] == commission]
    
    return attendance_df

def get_schedule_by_date(date):
    """Get schedule for a specific date"""
    schedule_df = load_schedule()
    
    # Handle date format conversion if needed
    if isinstance(date, datetime.date):
        date_str = date.strftime('%d/%m/%Y')
    else:
        date_str = date
    
    # Filter schedule for the specified date
    filtered_df = schedule_df[schedule_df['FECHA'] == date_str]
    return filtered_df
