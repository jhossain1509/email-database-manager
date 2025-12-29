#!/usr/bin/env python3
"""
Standalone SMTP Email Verification Test Script
Run this manually to test SMTP verification without Flask context issues

TWO METHODS:
1. Relay SMTP: Uses your SMTP server (accepts all emails, not accurate)
2. Direct MX: Connects to recipient's mail server (accurate mailbox verification)
"""

import smtplib
import socket
import dns.resolver
from email.mime.text import MIMEText
import sys

def verify_direct_mx(email, from_email='verify@example.com', timeout=15):
    """
    Verify email by connecting DIRECTLY to recipient's MX server.
    This is the ACCURATE method - checks real mailbox existence.
    NO authentication needed.
    """
    if not email or '@' not in email:
        return False, 'INVALID_FORMAT', 'Invalid email format'
    
    domain = email.split('@')[1]
    
    # Step 1: Get MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
        print(f"✓ MX Record found: {mx_host}")
    except Exception as e:
        print(f"✗ No MX records for {domain}: {e}")
        return False, 'NO_MX', f'No MX records: {str(e)}'
    
    # Step 2: Connect to recipient's mail server
    try:
        print(f"\n=== Direct MX Verification (ACCURATE) ===")
        print(f"Connecting to {mx_host}:25...")
        
        server = smtplib.SMTP(timeout=timeout)
        server.set_debuglevel(0)
        server.connect(mx_host, 25)
        server.ehlo()
        print(f"✓ Connected to {mx_host}")
        
        # MAIL FROM
        print(f"Sending MAIL FROM: {from_email}")
        code, msg = server.mail(from_email)
        if code != 250:
            server.quit()
            print(f"✗ MAIL FROM rejected: {code} - {msg.decode()}")
            return False, 'MAIL_FROM_REJECTED', msg.decode()
        
        # RCPT TO - This checks if mailbox exists!
        print(f"Sending RCPT TO: {email}")
        code, msg = server.rcpt(email)
        server.quit()
        
        print(f"RCPT TO response: {code} - {msg.decode()}")
        
        if code == 250:
            print(f"✓ Email VALID - Mailbox exists!")
            return True, None, None
        elif code in [550, 551, 553]:
            print(f"✗ Email INVALID - Mailbox does NOT exist")
            return False, f'INVALID_{code}', msg.decode()
        elif code in [450, 451, 452]:
            print(f"⚠ Greylisted (temp failure) - Likely valid")
            return True, 'GREYLISTED', msg.decode()
        else:
            print(f"✗ Unexpected response: {code}")
            return False, f'CODE_{code}', msg.decode()
    
    except socket.timeout:
        print(f"✗ Connection timeout to {mx_host}")
        return False, 'TIMEOUT', 'Connection timeout'
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return False, 'CONNECTION_ERROR', str(e)


def verify_smtp_relay(email, smtp_host, smtp_port, smtp_username, smtp_password,
                      use_tls=True, use_ssl=False, timeout=30, from_email=None):
def verify_smtp_relay(email, smtp_host, smtp_port, smtp_username, smtp_password,
                      use_tls=True, use_ssl=False, timeout=30, from_email=None):
    """
    Verify via SMTP relay server (INACCURATE for verification).
    Relay servers accept all emails (250 response) - they don't check mailboxes.
    Use this only for testing connectivity, NOT for email validation.
    """
    if not email or '@' not in email:
        return False, 'INVALID_FORMAT', 'Invalid email format'
    
    local_part, domain = email.rsplit('@', 1)
    
    # Check MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
        print(f"✓ MX Record found: {mx_host}")
    except Exception as e:
        print(f"✗ No MX records for {domain}: {e}")
        return False, 'NO_MX', f'No MX records: {str(e)}'
    
    # Test SMTP Relay Connection
    conn = None
    try:
        print(f"\n=== Relay SMTP Verification (INACCURATE) ===")
        print(f"Host: {smtp_host}:{smtp_port}")
        print(f"Use TLS: {use_tls}, Use SSL: {use_ssl}")
        print(f"Username: {smtp_username}")
        print(f"From: {from_email or smtp_username}")
        print(f"⚠ WARNING: Relay servers accept all emails!")
        
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
        
        # 250 or 251 means relay accepted it (NOT mailbox verification!)
        is_valid = code in [250, 251]
        
        if is_valid:
            print(f"⚠ Relay ACCEPTED (but mailbox may not exist!)")
            return True, 'RELAY_ACCEPTED', 'Relay accepted - NOT mailbox verified'
        else:
            print(f"✗ Relay REJECTED: {message}")
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
    print("="*70)
    print("SMTP Email Verification Manual Test")
    print("="*70)
    
    # Test email
    test_email = "njjj222xxxa@gmail.com"  # Obviously fake email for testing
    
    print(f"\n📧 Testing email: {test_email}")
    print(f"This email is OBVIOUSLY FAKE - let's see which method detects it!\n")
    
    # Method 1: Direct MX (ACCURATE)
    print("\n" + "="*70)
    print("METHOD 1: Direct MX Verification (RECOMMENDED)")
    print("="*70)
    is_valid_mx, code_mx, msg_mx = verify_direct_mx(
        test_email,
        from_email='verify@example.com',
        timeout=15
    )
    
    print(f"\n" + "="*70)
    print(f"DIRECT MX RESULT: {'✓ VALID' if is_valid_mx else '✗ INVALID'}")
    if not is_valid_mx:
        print(f"Error: {code_mx} - {msg_mx}")
    print("="*70)
    
    # Method 2: Relay SMTP (INACCURATE) - Optional
    print(f"\n\n{'='*70}")
    print("METHOD 2: Relay SMTP (INACCURATE - FOR COMPARISON ONLY)")
    print("="*70)
    print("Uncomment the code below to test relay SMTP")
    print("It will likely show VALID for fake emails!")
    print("="*70)
    
    """
    # Uncomment to test relay SMTP
    smtp_host = "premium186.web-hosting.com"
    smtp_port = 465
    smtp_username = "your-email@domain.com"  # UPDATE
    smtp_password = "your-password"  # UPDATE
    
    is_valid_relay, code_relay, msg_relay = verify_smtp_relay(
        test_email,
        smtp_host,
        smtp_port,
        smtp_username,
        smtp_password,
        use_ssl=True,
        use_tls=False,
        from_email=smtp_username
    )
    
    print(f"\n" + "="*70)
    print(f"RELAY SMTP RESULT: {'✓ ACCEPTED' if is_valid_relay else '✗ REJECTED'}")
    print(f"Note: {msg_relay}")
    print("="*70)
    """
    
    # Summary
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print("="*70)
    print(f"Email tested: {test_email}")
    print(f"Direct MX (Accurate): {'✓ VALID' if is_valid_mx else '✗ INVALID (Correct!)'}")
    print(f"\n💡 TIP: Use Direct MX method for real email verification!")
    print(f"    Relay SMTP servers accept all emails - NOT accurate!")
    print("="*70)

if __name__ == '__main__':
    main()
