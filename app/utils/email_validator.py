import re
from email_validator import validate_email as validate_email_lib, EmailNotValidError
import dns.resolver
import publicsuffix2
from flask import current_app

# Initialize public suffix list
psl = publicsuffix2.PublicSuffixList()

def is_valid_email_syntax(email):
    """Check if email has valid syntax"""
    try:
        validate_email_lib(email, check_deliverability=False)
        return True, None
    except EmailNotValidError as e:
        return False, str(e)

def extract_domain(email):
    """Extract domain from email"""
    try:
        parts = email.split('@')
        if len(parts) == 2:
            return parts[1].lower()
    except:
        pass
    return None

def check_dns_mx(domain):
    """Check if domain has MX records"""
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except:
        return False

def is_role_based_email(email):
    """Check if email uses role-based local part"""
    role_prefixes = [
        'admin', 'info', 'support', 'sales', 'contact', 'help',
        'webmaster', 'postmaster', 'noreply', 'no-reply', 'abuse'
    ]
    
    local_part = email.split('@')[0].lower()
    return any(local_part.startswith(prefix) for prefix in role_prefixes)

def get_public_suffix(domain):
    """Get the public suffix of a domain"""
    try:
        return psl.get_public_suffix(domain)
    except:
        return None

def is_cctld(domain):
    """
    Check if domain uses a country-code TLD (ccTLD).
    Returns (is_cctld, tld)
    """
    try:
        # Extract the TLD (last part after final dot)
        domain_lower = domain.lower()
        parts = domain_lower.split('.')
        
        if len(parts) < 2:
            return False, None
        
        # Get TLD
        tld = '.' + parts[-1]
        
        # Check if it's in generic TLDs list
        generic_tlds = current_app.config.get('GENERIC_TLDS', [])
        if tld in generic_tlds:
            return False, tld
        
        # Check for multi-level TLDs like .co.uk, .com.au
        if len(parts) >= 3:
            # Check common multi-level patterns
            second_last = parts[-2]
            multi_level_tld = f'.{second_last}{tld}'
            
            # Known multi-level ccTLDs
            multi_level_cctlds = [
                '.co.uk', '.com.au', '.co.nz', '.co.za', '.com.br',
                '.co.jp', '.co.in', '.co.kr', '.com.cn', '.com.mx',
                '.com.ar', '.com.co', '.ac.uk', '.gov.uk', '.org.uk'
            ]
            
            if multi_level_tld in multi_level_cctlds:
                return True, multi_level_tld
            
            # Check if it ends with .us (multi-level like .co.us is OK)
            if tld == '.us':
                return False, multi_level_tld
        
        # Single-level TLD: check if it's 2 characters (typical ccTLD)
        if len(parts[-1]) == 2:
            return True, tld
        
        # Otherwise treat as generic gTLD
        return False, tld
    except:
        return False, None

def is_policy_suffix(domain):
    """Check if domain ends with blocked policy suffix (.gov, .edu)"""
    blocked_suffixes = current_app.config.get('BLOCKED_POLICY_SUFFIXES', ['.gov', '.edu'])
    domain_lower = domain.lower()
    
    for suffix in blocked_suffixes:
        if domain_lower.endswith(suffix):
            return True, suffix
    
    return False, None

def check_us_only_cctld_policy(email):
    """
    Apply US-only ccTLD policy.
    Returns (allowed, reason)
    
    Rules:
    - Allow all generic TLDs (.com, .net, .org, etc.)
    - For ccTLDs, only allow .us
    - Block policy suffixes (.gov, .edu)
    """
    domain = extract_domain(email)
    if not domain:
        return False, 'Invalid email format'
    
    # Check policy suffixes first
    is_policy, suffix = is_policy_suffix(domain)
    if is_policy:
        return False, f'Policy suffix {suffix} not allowed'
    
    # Check if it's a ccTLD
    is_cc, tld = is_cctld(domain)
    
    if is_cc:
        # Only allow .us ccTLD
        if domain.endswith('.us'):
            return True, None
        else:
            return False, f'Non-US ccTLD {tld} not allowed'
    
    # Generic TLD - allow
    return True, None

def classify_domain(domain):
    """Classify domain into TOP_DOMAINS or 'mixed'"""
    top_domains = current_app.config.get('TOP_DOMAINS', [])
    
    if domain.lower() in [d.lower() for d in top_domains]:
        return domain.lower()
    
    return 'mixed'

def validate_email_full(email, check_dns=False, check_role=False, ignore_domains=None):
    """
    Full email validation with multiple checks.
    Returns (is_valid, error_type, error_message)
    """
    # Syntax check
    is_valid_syntax, syntax_error = is_valid_email_syntax(email)
    if not is_valid_syntax:
        return False, 'invalid_syntax', syntax_error
    
    # Extract domain
    domain = extract_domain(email)
    if not domain:
        return False, 'invalid_format', 'Could not extract domain'
    
    # Check ignore domains
    if ignore_domains and domain.lower() in [d.lower() for d in ignore_domains]:
        return False, 'ignore_domain', f'Domain {domain} is in ignore list'
    
    # Check US-only ccTLD policy
    allowed, reason = check_us_only_cctld_policy(email)
    if not allowed:
        if 'ccTLD' in reason:
            return False, 'cctld_policy', reason
        elif 'Policy suffix' in reason:
            return False, 'policy_suffix', reason
    
    # Check role-based email
    if check_role and is_role_based_email(email):
        return False, 'role_based', 'Role-based email address'
    
    # DNS/MX check
    if check_dns:
        if not check_dns_mx(domain):
            return False, 'no_mx_record', 'No MX record found for domain'
    
    return True, None, None

# Common disposable email domains
DISPOSABLE_DOMAINS = {
    'tempmail.com', '10minutemail.com', 'guerrillamail.com', 'mailinator.com',
    'throwaway.email', 'trashmail.com', 'getnada.com', 'temp-mail.org',
    'yopmail.com', 'fakeinbox.com', 'maildrop.cc', 'getairmail.com',
    'sharklasers.com', 'spam4.me', 'tmpeml.info', 'dispostable.com',
    'mintemail.com', 'emailondeck.com', 'guerrillamail.info', 'guerrillamail.net'
}

def is_disposable_email(email):
    """
    Check if email is from a disposable/temporary email service
    Returns (is_disposable, domain)
    """
    domain = extract_domain(email)
    if not domain:
        return False, None
    
    domain_lower = domain.lower()
    
    # Check against known disposable domains
    if domain_lower in DISPOSABLE_DOMAINS:
        return True, domain_lower
    
    # Check for common disposable patterns
    disposable_patterns = ['temp', 'trash', 'fake', 'throwaway', 'disposable', 'guerrilla']
    for pattern in disposable_patterns:
        if pattern in domain_lower:
            return True, domain_lower
    
    return False, None

def calculate_email_quality_score(email, is_valid=None, has_mx=None, is_role=None, 
                                  is_disposable=None, domain_category=None):
    """
    Calculate email quality score (0-100)
    
    Args:
        email: Email address
        is_valid: Whether email passed validation (True/False/None)
        has_mx: Whether domain has MX record (True/False/None)
        is_role: Whether email is role-based (True/False/None)
        is_disposable: Whether email is from disposable service (True/False/None)
        domain_category: Domain category - should be a TOP domain name (e.g., 'gmail.com')
                        or 'mixed' for other domains. Non-null, non-'mixed' values are 
                        treated as top domains.
    
    Scoring criteria:
    - Valid syntax: +30 (base score)
    - Has MX record: +20
    - Not role-based: +15
    - Not disposable: +15
    - Top domain (not 'mixed'): +10
    - Mixed domain: +5
    - Valid flag: +10
    
    Penalties:
    - No MX: -10
    - Role-based: -5
    - Disposable: -20
    - Invalid: -15
    
    Returns:
        int: Quality score between 0 and 100
    """
    score = 0
    
    # Base score for valid syntax (always given if we're scoring)
    score += 30
    
    # MX record check
    if has_mx is True:
        score += 20
    elif has_mx is False:
        score -= 10
    
    # Role-based check
    if is_role is False:
        score += 15
    elif is_role is True:
        score -= 5
    
    # Disposable check
    if is_disposable is False:
        score += 15
    elif is_disposable is True:
        score -= 20
    
    # Domain category - top domains get +10, mixed get +5
    if domain_category and domain_category != 'mixed':
        score += 10  # Top domain (e.g., 'gmail.com', 'yahoo.com')
    elif domain_category == 'mixed':
        score += 5
    
    # Validation status
    if is_valid is True:
        score += 10
    elif is_valid is False:
        score -= 15
    
    # Ensure score is between 0 and 100
    return max(0, min(100, score))

def validate_email_enhanced(email, check_dns=False, check_smtp=False, check_role=False, 
                           check_disposable=True, ignore_domains=None):
    """
    Enhanced email validation with quality scoring
    Returns (is_valid, error_type, error_message, quality_score, details)
    """
    details = {
        'has_mx': None,
        'is_role': None,
        'is_disposable': None,
        'domain_category': None
    }
    
    # Syntax check
    is_valid_syntax, syntax_error = is_valid_email_syntax(email)
    if not is_valid_syntax:
        quality_score = calculate_email_quality_score(email, is_valid=False)
        return False, 'invalid_syntax', syntax_error, quality_score, details
    
    # Extract domain
    domain = extract_domain(email)
    if not domain:
        quality_score = calculate_email_quality_score(email, is_valid=False)
        return False, 'invalid_format', 'Could not extract domain', quality_score, details
    
    # Domain category
    details['domain_category'] = classify_domain(domain)
    
    # Check ignore domains
    if ignore_domains and domain.lower() in [d.lower() for d in ignore_domains]:
        quality_score = calculate_email_quality_score(email, is_valid=False, 
                                                      domain_category=details['domain_category'])
        return False, 'ignore_domain', f'Domain {domain} is in ignore list', quality_score, details
    
    # Check US-only ccTLD policy
    allowed, reason = check_us_only_cctld_policy(email)
    if not allowed:
        quality_score = calculate_email_quality_score(email, is_valid=False,
                                                      domain_category=details['domain_category'])
        if 'ccTLD' in reason:
            return False, 'cctld_policy', reason, quality_score, details
        elif 'Policy suffix' in reason:
            return False, 'policy_suffix', reason, quality_score, details
    
    # Check disposable email
    if check_disposable:
        is_disp, disp_domain = is_disposable_email(email)
        details['is_disposable'] = is_disp
        if is_disp:
            quality_score = calculate_email_quality_score(email, is_valid=False, 
                                                          is_disposable=True,
                                                          domain_category=details['domain_category'])
            return False, 'disposable_email', f'Disposable email domain: {disp_domain}', quality_score, details
    else:
        details['is_disposable'] = False
    
    # Check role-based email
    details['is_role'] = is_role_based_email(email)
    if check_role and details['is_role']:
        quality_score = calculate_email_quality_score(email, is_valid=False,
                                                      is_role=True,
                                                      is_disposable=details['is_disposable'],
                                                      domain_category=details['domain_category'])
        return False, 'role_based', 'Role-based email address', quality_score, details
    
    # DNS/MX check
    if check_dns:
        details['has_mx'] = check_dns_mx(domain)
        if not details['has_mx']:
            quality_score = calculate_email_quality_score(email, is_valid=False,
                                                          has_mx=False,
                                                          is_role=details['is_role'],
                                                          is_disposable=details['is_disposable'],
                                                          domain_category=details['domain_category'])
            return False, 'no_mx_record', 'No MX record found for domain', quality_score, details
    
    # Calculate final quality score for valid email
    quality_score = calculate_email_quality_score(email, is_valid=True,
                                                  has_mx=details.get('has_mx'),
                                                  is_role=details['is_role'],
                                                  is_disposable=details['is_disposable'],
                                                  domain_category=details['domain_category'])
    
    return True, None, None, quality_score, details


def verify_email_smtp(email, smtp_host, smtp_port, smtp_username, smtp_password, 
                      use_tls=True, use_ssl=False, timeout=30, from_email=None):
    """
    Verify email using SMTP server by attempting RCPT TO command.
    
    Args:
        email: Email address to verify
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        smtp_username: SMTP account username
        smtp_password: SMTP account password
        use_tls: Whether to use STARTTLS
        use_ssl: Whether to use SSL
        timeout: Connection timeout in seconds
        from_email: Email to use in MAIL FROM (defaults to smtp_username)
    
    Returns:
        tuple: (is_valid, error_code, error_message)
    """
    import smtplib
    import socket
    
    if not from_email:
        from_email = smtp_username
    
    try:
        # Connect to SMTP server
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout)
        
        server.set_debuglevel(0)
        
        # Use STARTTLS if specified and not using SSL
        if use_tls and not use_ssl:
            server.starttls()
        
        # Login
        server.login(smtp_username, smtp_password)
        
        # Send MAIL FROM command
        code, message = server.mail(from_email)
        if code != 250:
            server.quit()
            return False, 'smtp_mail_from_failed', f'MAIL FROM failed: {message.decode()}'
        
        # Send RCPT TO command to verify email
        code, message = server.rcpt(email)
        server.quit()
        
        # Check response code
        # 250: Recipient OK
        # 550: User not found / Mailbox unavailable
        # 551: User not local
        # 552: Mailbox full
        # 553: Mailbox name not allowed
        # 450-451: Temporary failure (greylisting)
        
        if code == 250:
            return True, None, None
        elif code in [550, 551, 553]:
            return False, f'smtp_invalid_{code}', f'Email rejected by server: {message.decode()}'
        elif code in [450, 451, 452]:
            # Temporary failure - treat as valid (greylisting)
            return True, None, None
        else:
            return False, f'smtp_code_{code}', f'SMTP verification failed: {message.decode()}'
    
    except smtplib.SMTPAuthenticationError as e:
        return False, 'smtp_auth_error', f'SMTP authentication failed: {str(e)}'
    except smtplib.SMTPException as e:
        return False, 'smtp_error', f'SMTP error: {str(e)}'
    except socket.timeout:
        return False, 'smtp_timeout', 'SMTP connection timed out'
    except Exception as e:
        return False, 'smtp_connection_error', f'Connection error: {str(e)}'
