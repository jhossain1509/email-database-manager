#!/usr/bin/env python3
"""
Standalone SMTP Email Verification Test Script
Run this manually to test SMTP verification without Flask context issues
"""

import smtplib
import socket
import dns.resolver
from email.mime.text import MIMEText
import sys

def verify_smtp_manual(email, smtp_host, smtp_port, smtp_username, smtp_password,
                      use_tls=True, use_ssl=False, timeout=30, from_email=None):
    """
    Manual SMTP verification function for testing
    Returns: (is_valid, error_code, error_message)
    """
    if not email or '@' not in email:
        return False, 'INVALID_FORMAT', 'Invalid email format'
    
    local_part, domain = email.rsplit('@', 1)
    
    # Step 1: Check MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
        print(f"✓ MX Record found: {mx_host}")
    except Exception as e:
        print(f"✗ No MX records for {domain}: {e}")
        return False, 'NO_MX', f'No MX records: {str(e)}'
    
    # Step 2: Test SMTP Connection
    conn = None
    try:
        print(f"\n=== Testing SMTP Connection ===")
        print(f"Host: {smtp_host}:{smtp_port}")
        print(f"Use TLS: {use_tls}, Use SSL: {use_ssl}")
        print(f"Username: {smtp_username}")
        print(f"From: {from_email or smtp_username}")
        
        # Create connection
        if use_ssl:
            print(f"Connecting via SSL...")
            conn = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout)
        else:
            print(f"Connecting via plain/TLS...")
            conn = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout)
            conn.ehlo()
            
            if use_tls:
                print(f"Starting TLS...")
                conn.starttls()
                conn.ehlo()
        
        print(f"✓ Connection established")
        
        # Login
        if smtp_username and smtp_password:
            print(f"Logging in as {smtp_username}...")
            conn.login(smtp_username, smtp_password)
            print(f"✓ Login successful")
        
        # Verify email
        sender = from_email or smtp_username
        print(f"\nVerifying email: {email}")
        print(f"From: {sender}")
        
        conn.mail(sender)
        code, message = conn.rcpt(email)
        
        print(f"RCPT TO response: {code} - {message.decode() if isinstance(message, bytes) else message}")
        
        # 250 or 251 means valid
        is_valid = code in [250, 251]
        
        if is_valid:
            print(f"✓ Email is VALID")
            return True, None, None
        else:
            print(f"✗ Email is INVALID: {message}")
            return False, f'SMTP_{code}', message.decode() if isinstance(message, bytes) else str(message)
            
    except smtplib.SMTPAuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
        return False, 'AUTH_ERROR', f'Authentication failed: {str(e)}'
    except smtplib.SMTPConnectError as e:
        print(f"✗ Connection failed: {e}")
        return False, 'CONNECT_ERROR', f'Connection failed: {str(e)}'
    except smtplib.SMTPException as e:
        print(f"✗ SMTP error: {e}")
        return False, 'SMTP_ERROR', str(e)
    except socket.timeout:
        print(f"✗ Connection timeout")
        return False, 'TIMEOUT', 'Connection timeout'
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False, 'ERROR', str(e)
    finally:
        if conn:
            try:
                conn.quit()
                print(f"✓ Connection closed")
            except:
                pass

def main():
    print("="*60)
    print("SMTP Email Verification Manual Test")
    print("="*60)
    
    # Test configuration - UPDATE THESE VALUES
    smtp_host = "premium186.web-hosting.com"
    smtp_port = 465  # Try 587 for TLS or 25 for plain
    smtp_username = "your-email@domain.com"  # UPDATE THIS
    smtp_password = "your-password"  # UPDATE THIS
    use_ssl = True  # True for port 465, False for 587/25
    use_tls = False  # True for port 587, False for 465
    from_email = smtp_username
    
    # Test email
    test_email = "test@gmail.com"  # Email to verify
    
    print(f"\nConfiguration:")
    print(f"  SMTP Server: {smtp_host}:{smtp_port}")
    print(f"  Username: {smtp_username}")
    print(f"  SSL: {use_ssl}, TLS: {use_tls}")
    print(f"  Test Email: {test_email}")
    print(f"\n" + "="*60 + "\n")
    
    # Run test
    is_valid, error_code, error_message = verify_smtp_manual(
        test_email,
        smtp_host,
        smtp_port,
        smtp_username,
        smtp_password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout=30,
        from_email=from_email
    )
    
    print(f"\n" + "="*60)
    print(f"RESULT: {'✓ VALID' if is_valid else '✗ INVALID'}")
    if not is_valid:
        print(f"Error Code: {error_code}")
        print(f"Error Message: {error_message}")
    print("="*60)

if __name__ == '__main__':
    main()
