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
        # Get the public suffix
        public_suffix = psl.get_public_suffix(domain)
        if not public_suffix:
            return False, None
        
        # Get TLD (last part)
        tld = '.' + public_suffix
        
        # Check if it's a generic TLD
        generic_tlds = current_app.config.get('GENERIC_TLDS', [])
        if tld in generic_tlds:
            return False, tld
        
        # Check for multi-level public suffixes (like .co.uk, .com.au)
        # These are ccTLDs
        parts = public_suffix.split('.')
        if len(parts) > 1:
            return True, tld
        
        # Check if last part is 2 characters (typical ccTLD)
        last_part = parts[-1]
        if len(last_part) == 2:
            return True, '.' + last_part
        
        # Otherwise, assume it's a generic/new gTLD
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
