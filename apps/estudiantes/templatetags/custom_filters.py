from django import template

register = template.Library()

@register.filter
def formato_cedula(value):
    if not value:
        return value
    
    s_val = str(value).strip().upper()
    prefix = 'V-'
    
    if s_val.startswith('V-'):
        prefix = 'V-'
        s_val = s_val[2:]
    elif s_val.startswith('E-'):
        prefix = 'E-'
        s_val = s_val[2:]
    elif s_val.startswith('P-'):
        prefix = 'P-'
        s_val = s_val[2:]
    elif s_val.startswith('V'):
        prefix = 'V-'
        s_val = s_val[1:]
    elif s_val.startswith('E'):
        prefix = 'E-'
        s_val = s_val[1:]
        
    import re
    digits = re.sub(r'\D', '', s_val)
    if not digits:
        return value

    try:
        formatted = f"{int(digits):,}".replace(",", ".")
        return f"{prefix}{formatted}"
    except ValueError:
        return value

@register.filter
def formato_telefono(value):
    if not value:
        return value
    import re
    digits = re.sub(r'\D', '', str(value))
    if len(digits) == 11:
        return f"{digits[:4]}-{digits[4:]}"
    elif len(digits) == 10:
        return f"0{digits[:3]}-{digits[3:]}"
    return value

@register.filter
def whatsapp_phone(value):
    if not value:
        return ""
    import re
    digits = re.sub(r'\D', '', str(value))
    if digits.startswith('0'):
        digits = digits[1:]
    return digits

