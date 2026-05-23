AVAILABLE_BANKS = [
    "Banco de Venezuela",
    "BBVA Provincial",
    "Mercantil",
    "DELSUR",
    "BNC",
    "Banesco",
    "BDT",
    "Banco Exterior",
    "Banco del Tesoro",
    "Provincial",
    "Banco Bicentenario",
    "Banco de la Fuerza Armada Nacional Bolivariana (BFA)",
    "Banco Venezolano de Crédito",
    "Banco Plaza",
    "Banco Activo",
    "Banco Fondo Común",
    "BOD",
    "Banco Caroní",
    "Banco Sofitasa",
    "Banco Agrícola de Venezuela",
    "Banco del Caribe",
    "Banco del Pueblo Soberano",
    "BANDEs",
    "Desconocido"
]

SUD_BANK_CODES = {
    "0102": "Banco de Venezuela",
    "0134": "Banesco",
    "0157": "DELSUR",
    "0172": "Banco del Tesoro",
    "0404": "Banco Bicentenario",
    "0114": "BOD",
    "0412": "Banco Exterior",
    "0262": "Mercantil",
    "0174": "Banco Caroní",
    "0173": "Banco Activo",
    "0115": "Banco Venezolano de Crédito",
    "0171": "Banco Plaza",
    "0177": "Banco Fondo Común",
    "0199": "BANDEs",
    "0105": "BBVA Provincial",
}


def get_available_banks():
    return list(AVAILABLE_BANKS)


def get_bank_by_sudeban_code(code):
    if not code:
        return "Desconocido"
    normalized = str(code).strip()
    return SUD_BANK_CODES.get(normalized, "Desconocido")
