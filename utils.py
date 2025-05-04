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

def validate_time_for_subject(current_date, current_time, schedule_date, start_time, end_time):
    """
    Check if current date and time are within the allowed range for a subject
    
    Parameters:
        current_date (datetime.date): Current date in Argentina timezone
        current_time (datetime.time): Current time in Argentina timezone
        schedule_date (str): Date when the class is scheduled (YYYY-MM-DD format)
        start_time (str): Start time of the class
        end_time (str): End time of the class
    
    Returns:
        bool: True if current date and time are valid for this class, False otherwise
    """
    # Parse times if they are strings
    start_time = parse_time(start_time)
    end_time = parse_time(end_time)
    
    # Check if any of the times is None (invalid)
    if start_time is None or end_time is None:
        return False
    
    # Convert schedule_date string to datetime.date
    try:
        if isinstance(schedule_date, str):
            schedule_date = datetime.datetime.strptime(schedule_date, '%Y-%m-%d').date()
    except ValueError:
        return False
    
    # First check if today is the day of the class
    if current_date != schedule_date:
        return False
    
    # Convert datetime.time to minutes for easier comparison
    def time_to_minutes(t):
        return t.hour * 60 + t.minute
    
    current_minutes = time_to_minutes(current_time)
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    
    # Check if current time is within range
    return start_minutes <= current_minutes <= end_minutes

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

def save_attendance(dni, name, subject, commission, date, time, device, ip):
    """Save attendance record to CSV file"""
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
    attendance_df = attendance_df._append(new_record, ignore_index=True)
    
    # Save back to CSV
    attendance_df.to_csv(attendance_path, index=False)
    
    return True

def check_schedule_conflicts():
    """
    Check if there are any conflicts in the schedule (same subject at overlapping times)
    Returns a list of conflict dictionaries
    """
    from database import load_schedule
    
    schedule_df = load_schedule()
    conflicts = []
    
    # Convert time strings to datetime.time objects for comparison
    schedule_df['INICIO'] = schedule_df['INICIO'].apply(parse_time)
    schedule_df['FINAL'] = schedule_df['FINAL'].apply(parse_time)
    
    # Check each pair of schedules for conflicts
    for i, row1 in schedule_df.iterrows():
        for j, row2 in schedule_df.iterrows():
            if i < j:  # Only check each pair once
                # Check for time overlap
                row1_start = row1['INICIO']
                row1_end = row1['FINAL']
                row2_start = row2['INICIO']
                row2_end = row2['FINAL']
                
                # Check for overlap
                if (row1_start <= row2_end and row1_end >= row2_start):
                    conflicts.append({
                        'materia1': row1['MATERIA'],
                        'comision1': row1['COMISION'],
                        'inicio1': row1_start.strftime('%H:%M:%S'),
                        'final1': row1_end.strftime('%H:%M:%S'),
                        'materia2': row2['MATERIA'],
                        'comision2': row2['COMISION'],
                        'inicio2': row2_start.strftime('%H:%M:%S'),
                        'final2': row2_end.strftime('%H:%M:%S')
                    })
    
    return conflicts
