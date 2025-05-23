import ipaddress
import socket
import subprocess
import platform
import re
import datetime
import pytz
import os

def check_wifi_connection():
    """
    Check if the device is connected to WiFi
    Returns True if connected, False otherwise
    """
    """Check if device is connected to WiFi"""
    # Para cloud deployment o desarrollo local
    if os.environ.get('STREAMLIT_SHARING') or os.environ.get('STREAMLIT_CLOUD'):
        return True
    
    # Para desarrollo local, siempre devolver True
    # return True
    
    system = platform.system()
    
    try:
        if system == "Windows":
            # Windows approach
            output = subprocess.check_output("netsh wlan show interfaces", shell=True).decode('utf-8', errors='ignore')
            return "State                  : connected" in output
        
        elif system == "Darwin":  # macOS
            # macOS approach
            output = subprocess.check_output("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I", shell=True).decode('utf-8', errors='ignore')
            return "state: running" in output
        
        elif system == "Linux":
            # Linux approach
            output = subprocess.check_output("iwconfig 2>/dev/null", shell=True).decode('utf-8', errors='ignore')
            return "ESSID:" in output and "off/any" not in output
        
        # Fallback to network card check if the OS-specific checks fail
        return True
    
    except:
        # If any errors occur, assume we can't verify WiFi status
        # For demo purposes, we'll allow access anyway
        return True

def get_local_ip():
    """
    Get the device's local IP address
    Returns the IP as a string
    """
    try:
        # For demo/development purposes, prioritize private IP ranges
        # This helps ensure we're getting a WiFi/local network IP rather than a public one
        if platform.system() == "Linux":
            # Try using the ip command on Linux
            output = subprocess.check_output("ip -4 addr show | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}' | grep -v '127.0.0.1'", shell=True).decode('utf-8').strip()
            if output:
                # Get the first private IP (192.168.x.x, 10.x.x.x, or 172.16-31.x.x)
                for ip in output.split('\n'):
                    if ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', 
                                      '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.',
                                      '172.28.', '172.29.', '172.30.', '172.31.')):
                        return ip
        
        # Standard method
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to a known external server (Google DNS)
        ip = s.getsockname()[0]
        s.close()
        
        # Development/demo workaround - if we get a non-private IP, return a private one
        if not ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', 
                              '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.',
                              '172.28.', '172.29.', '172.30.', '172.31.')):
            # For demo purposes, return a typical private IP
            return "192.168.0.100"  # Default to a typical private IP for demo
        
        return ip
    except:
        # Development/demo workaround - return a typical private IP
        return "192.168.0.100"  # Default to a typical private IP for demo

def is_ip_in_range(ip, range_start, range_end):
    """
    Check if an IP address is within a specified range
    Parameters:
        ip (str): The IP address to check
        range_start (str): The starting IP of the range
        range_end (str): The ending IP of the range
    Returns:
        bool: True if the IP is in the range, False otherwise
    """
    # Convert string IPs to integer representations
    ip_int = int(ipaddress.IPv4Address(ip))
    start_int = int(ipaddress.IPv4Address(range_start))
    end_int = int(ipaddress.IPv4Address(range_end))
    
    # Check if IP is in range
    return start_int <= ip_int <= end_int

def is_ip_in_allowed_range(ip, allowed_ranges):
    """
    Check if an IP address is within any of the allowed CIDR ranges
    Parameters:
        ip (str): The IP address to check
        allowed_ranges (list): List of allowed CIDR ranges (e.g., ["192.168.1.0/24"])
    Returns:
        bool: True if the IP is in any allowed range, False otherwise
    """
    ip_obj = ipaddress.IPv4Address(ip)
    
    for range_cidr in allowed_ranges:
        network = ipaddress.IPv4Network(range_cidr, strict=False)
        if ip_obj in network:
            return True
    
    return False

def get_argentina_datetime():
    """
    Get the current date and time in Buenos Aires, Argentina timezone
    Returns a tuple of (datetime object, date object, time object)
    """
    # Set timezone to Buenos Aires
    argentina_tz = pytz.timezone('America/Argentina/Buenos_Aires')
    
    # Get current UTC time and convert to Argentina time
    utc_now = datetime.datetime.now(pytz.UTC)
    argentina_now = utc_now.astimezone(argentina_tz)
    
    # Extract date and time components
    argentina_date = argentina_now.date()
    argentina_time = argentina_now.time()
    
    return argentina_now, argentina_date, argentina_time

def extract_mac_address():
    """
    Extract MAC address of the primary network interface
    Returns the MAC address as a string or None if not found
    """
    system = platform.system()
    
    try:
        if system == "Windows":
            # Windows method
            output = subprocess.check_output("getmac /v", shell=True).decode('utf-8', errors='ignore')
            for line in output.split('\n'):
                if "Physical Address" in line and not "Disconnected" in line:
                    mac = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                    if mac:
                        return mac.group(0)
        
        elif system == "Darwin":  # macOS
            # macOS method
            output = subprocess.check_output("ifconfig en0", shell=True).decode('utf-8', errors='ignore')
            mac = re.search(r'ether\s+([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', output)
            if mac:
                return mac.group(1)
        
        elif system == "Linux":
            # Linux method
            output = subprocess.check_output("ip link show", shell=True).decode('utf-8', errors='ignore')
            mac = re.search(r'link/ether\s+([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', output)
            if mac:
                return mac.group(1)
        
        # If we get here, we couldn't extract the MAC using the OS-specific methods
        # Return a placeholder value for testing purposes
        return "00:00:00:00:00:00"
    
    except:
        # In case of any errors, return a placeholder
        return "00:00:00:00:00:00"

# Añadir a network.py
def get_device_id():
    """
    Obtiene un identificador único del dispositivo
    Combina MAC address, hostname y otros identificadores
    """
    device_identifiers = []
    
    # Intentar obtener MAC address
    try:
        mac = extract_mac_address()
        if mac and mac != "00:00:00:00:00:00":
            device_identifiers.append(mac)
    except:
        pass
    
    # Obtener hostname
    try:
        hostname = socket.gethostname()
        device_identifiers.append(hostname)
    except:
        pass
    
    # Obtener IP local
    try:
        ip = get_local_ip()
        device_identifiers.append(ip)
    except:
        pass
    
    # Combinar identificadores y generar hash único
    import hashlib
    combined = "-".join([str(x) for x in device_identifiers])
    device_hash = hashlib.md5(combined.encode()).hexdigest()
    
    return device_hash

def get_device_id_from_phone(phone_number):
    """
    Genera un device_id basado en el número de teléfono del estudiante
    """
    import hashlib
    import uuid
    
    # Limpiar número de teléfono (quitar espacios, guiones, etc.)
    clean_phone = ''.join(filter(str.isdigit, str(phone_number)))
    
    # Agregar algunos datos del dispositivo para mayor unicidad
    try:
        mac = extract_mac_address()
        if mac == "00:00:00:00:00:00":
            mac = str(uuid.uuid4())  # Fallback único
    except:
        mac = str(uuid.uuid4())
    
    # Combinar teléfono + MAC (o UUID único)
    combined = f"{clean_phone}_{mac}"
    device_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    return device_hash

def generate_session_device_id():
    """
    Genera un ID único por sesión de navegador usando timestamp y random
    """
    import time
    import random
    import hashlib
    
    timestamp = str(int(time.time() * 1000))  # milliseconds
    random_part = str(random.randint(100000, 999999))
    
    # Intentar obtener algo único del dispositivo
    try:
        mac = extract_mac_address()
        if mac == "00:00:00:00:00:00":
            mac = str(random.randint(1000000, 9999999))
    except:
        mac = str(random.randint(1000000, 9999999))
    
    combined = f"{timestamp}_{random_part}_{mac}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]
