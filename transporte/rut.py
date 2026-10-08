import re


def normalizar(texto):
    """'12.345.678-5' -> '12345678-5'. Si no parece un RUT, devuelve el texto limpio."""
    s = re.sub(r"[^0-9kK]", "", str(texto)).upper()
    cuerpo = s[:-1]
    if len(s) < 2 or not cuerpo.isdigit():
        return s
    return f"{int(cuerpo)}-{s[-1]}"


def digito_verificador(cuerpo):
    suma, m = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * m
        m = m + 1 if m < 7 else 2
    r = 11 - suma % 11
    return "0" if r == 11 else "K" if r == 10 else str(r)


def es_valido(rut):
    if not re.fullmatch(r"\d{7,8}-[\dK]", rut):
        return False
    cuerpo, dv = rut.split("-")
    return digito_verificador(cuerpo) == dv


def formatear(rut):
    """'12345678-5' -> '12.345.678-5'"""
    cuerpo, dv = rut.split("-")
    return f"{int(cuerpo):,}".replace(",", ".") + "-" + dv
