import os
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import TypedDict

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

import models

getcontext().prec = 9

class TasaBCV(TypedDict):
    tasa: Decimal
    origen: str
    fecha: datetime

class ConversionResult(TypedDict):
    monto_bs: Decimal
    tasa_bcv: Decimal
    monto_usd: Decimal
    origen: str
    fecha: datetime


class TasaNoDisponibleError(Exception):
    """Ocurre cuando no se puede obtener ninguna tasa del BCV."""


async def fetch_tasa_api() -> TasaBCV:
    """Nivel 1: usar una API externa asíncrona mediante httpx."""
    urls = []
    configured_url = os.getenv("TASA_BCV_API_URL")
    if configured_url:
        urls.append(configured_url)

    # URLs de respaldo conocidas
    urls.extend([
        "https://pydolarve.org/api/v1/bcv",
        "https://s3.amazonaws.com/dolartoday/data.json",
        "https://api.exchangerate.host/latest?base=VES&symbols=USD",
    ])

    skip_ssl = str(os.getenv("TASA_BCV_SKIP_TLS_VERIFY", "false")).strip().lower() in ("1", "true", "yes")

    last_error = None
    async with httpx.AsyncClient(timeout=10.0, verify=not skip_ssl, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for url in urls:
            if not url:
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, dict):
                    raise TasaNoDisponibleError("Respuesta de API no es JSON válido")

                # Ajustar según el contrato de API de pydolarve o exchangerate.host u otras APIs similares
                # Ejemplo: {'tasa': 95.5, ...} o {'base':'VES','rates': {'USD': 0.000021}} u {'base':'USD','rates':{'VES':95.5}}
                if "tasa" in data and data["tasa"]:
                    raw = Decimal(str(data["tasa"]))
                    if raw <= 0:
                        raise TasaNoDisponibleError("Tasa de API debe ser mayor que cero")
                    return {"tasa": raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "origen": "API", "fecha": datetime.utcnow()}

                if "rates" in data and isinstance(data["rates"], dict):
                    rates = data["rates"]

                    if "USD" in rates and rates["USD"]:
                        rate = Decimal(str(rates["USD"]))
                        if rate <= 0:
                            raise TasaNoDisponibleError("Tasa de API rates USD debe ser mayor que cero")
                        tasa_valor = (Decimal("1") / rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                        return {"tasa": tasa_valor, "origen": "API", "fecha": datetime.utcnow()}

                    if "VES" in rates and rates["VES"]:
                        rate = Decimal(str(rates["VES"]))
                        if rate <= 0:
                            raise TasaNoDisponibleError("Tasa de API rates VES debe ser mayor que cero")
                        return {"tasa": rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "origen": "API", "fecha": datetime.utcnow()}

                # Manejo específico para exchangerate.host (error de access_key)
                if data.get("success") is False and data.get("error"):
                    raise TasaNoDisponibleError(f"Error de API exchange: {data.get('error')}")

                # Si no pudimos parsear ninguna estructura válida, lanzamos error y probamos siguiente URL
                raise TasaNoDisponibleError("No se encontró campo 'tasa' ni 'rates' válido en respuesta de API")

            except Exception as e:
                last_error = e
                continue

    raise TasaNoDisponibleError(f"No se pudo obtener tasa por API en ninguna fuente: {last_error}")

    if not isinstance(data, dict):
        raise TasaNoDisponibleError("Respuesta de API no es JSON válido")

    # Ajustar según el contrato de API de pydolarve o exchangerate.host u otras APIs similares
    # Ejemplo: {'tasa': 95.5, ...} o {'base':'VES','rates': {'USD': 0.000021}} u {'base':'USD','rates':{'VES':95.5}}
    if "tasa" in data and data["tasa"]:
        try:
            raw = Decimal(str(data["tasa"]))
        except Exception as exc:
            raise TasaNoDisponibleError(f"Tasa inválida en API: {exc}")

        if raw <= 0:
            raise TasaNoDisponibleError("Tasa de API debe ser mayor que cero")

        return {"tasa": raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "origen": "API", "fecha": datetime.utcnow()}

    if "rates" in data and isinstance(data["rates"], dict):
        rates = data["rates"]

        if "USD" in rates and rates["USD"]:
            try:
                rate = Decimal(str(rates["USD"]))
            except Exception as exc:
                raise TasaNoDisponibleError(f"Tasa inválida en rates USD: {exc}")

            if rate <= 0:
                raise TasaNoDisponibleError("Tasa de API rates USD debe ser mayor que cero")

            # Si la base está en VES convertimos a VES/USD (1 USD = 1 / (USD/VES))
            if data.get("base", "").upper() == "VES":
                tasa_valor = (Decimal("1") / rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            else:
                # Si la base es USD u otra, y el precio es USD por algo, invertimos para obtener VES/USD
                tasa_valor = (Decimal("1") / rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            return {"tasa": tasa_valor, "origen": "API", "fecha": datetime.utcnow()}

        if "VES" in rates and rates["VES"]:
            try:
                rate = Decimal(str(rates["VES"]))
            except Exception as exc:
                raise TasaNoDisponibleError(f"Tasa inválida en rates VES: {exc}")

            if rate <= 0:
                raise TasaNoDisponibleError("Tasa de API rates VES debe ser mayor que cero")

            return {"tasa": rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "origen": "API", "fecha": datetime.utcnow()}

    raise TasaNoDisponibleError("No se encontró campo 'tasa' ni 'rates' válido en respuesta de API")


async def fetch_tasa_scraping() -> TasaBCV:
    """Nivel 2: scraping directo del portal del BCV usando BeautifulSoup."""
    url = os.getenv("TASA_BCV_SCRAPING_URL", "https://www.bcv.org.ve")
    skip_ssl = str(os.getenv("TASA_BCV_SKIP_TLS_VERIFY", "false")).strip().lower() in ("1", "true", "yes")

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=not skip_ssl, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as e:
        if not skip_ssl:
            # Mlveria para entornos con CA desactualizada: reintentar sin verificación SSL
            async with httpx.AsyncClient(timeout=10.0, verify=False, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        else:
            raise

    soup = BeautifulSoup(html, "html.parser")

    # Intentamos seleccionar la tasa del BCV según su estructura actual.
    node = soup.select_one(".exchange-rate, .field-content .value, span.rate, .field--name-field-valor")
    tasa_text = None

    if node is not None:
        tasa_text = node.get_text(" ", strip=True)

    if not tasa_text:
        # Buscamos en el texto libre todo el bloque de USD
        all_text = soup.get_text(" ", strip=True)
        match = re.search(r"USD\s*[:\-]?\s*([0-9]{1,3}(?:[\.,][0-9]+)?)", all_text)
        if match:
            tasa_text = match.group(1)

    if not tasa_text:
        # Otra alternativa: obtén cualquier número cercano a "Bs/USD" o "Tasas Informativas"
        all_text = soup.get_text(" ", strip=True)
        match = re.search(r"Bs\s*[/]USD\D*([0-9]{1,3}(?:[\.,][0-9]+)?)", all_text)
        if match:
            tasa_text = match.group(1)

    if not tasa_text:
        raise TasaNoDisponibleError("No se pudo encontrar la tasa BCV en el HTML de BCV")

    tasa_text = tasa_text.replace("Bs.", "").replace("Bs", "").replace("%", "").strip()
    tasa_text = tasa_text.replace(".", "").replace(",", ".")

    try:
        tasa = Decimal(tasa_text)
    except Exception as exc:
        raise TasaNoDisponibleError(f"No se pudo analizar la tasa scraped: {exc}")

    if tasa <= 0:
        raise TasaNoDisponibleError("Tasa scrapeada inválida")

    return {"tasa": tasa.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "origen": "SCRAPING", "fecha": datetime.utcnow()}


def fetch_tasa_db(db: Session) -> TasaBCV:
    """Nivel 3: último valor persistido en la base de datos."""
    tasa_db = db.query(models.TasaCambio).order_by(models.TasaCambio.fecha_actualizacion.desc()).first()
    if tasa_db and tasa_db.monto_tasa and Decimal(str(tasa_db.monto_tasa)) > 0:
        return {
            "tasa": Decimal(str(tasa_db.monto_tasa)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            "origen": "DB",
            "fecha": tasa_db.fecha_actualizacion or datetime.utcnow(),
        }
    raise TasaNoDisponibleError("No hay tasa BCV en la base de datos")


def persist_tasa(db: Session, tasa: Decimal, origen: str) -> None:
    """Actualiza el registro de tasa en la base de datos cada vez que hay valor exitoso."""
    tasa_db = db.query(models.TasaCambio).filter(models.TasaCambio.proveedor == "BCV").first()
    if not tasa_db:
        tasa_db = models.TasaCambio(proveedor="BCV", monto_tasa=tasa, fecha_actualizacion=datetime.utcnow())
        db.add(tasa_db)
    else:
        tasa_db.monto_tasa = tasa
        tasa_db.fecha_actualizacion = datetime.utcnow()

    db.commit()


def decimal_usd(monto_bs: float, tasa_bcv: Decimal) -> Decimal:
    """Convierte bolívares a dólares con precisión financiera."""
    if tasa_bcv <= 0:
        raise ValueError("La tasa BCV debe ser mayor que cero")
    monto_bs_dec = Decimal(str(monto_bs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    monto_usd = (monto_bs_dec / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return monto_usd


async def get_tasa_bcv(db: Session) -> TasaBCV:
    """Cadena de redundancia: API -> Scraping -> DB -> DEFAULT env."""
    try:
        res = await fetch_tasa_api()
        persist_tasa(db, res["tasa"], res["origen"])
        return res
    except Exception as e:
        # Retener logs en main.py
        pass

    try:
        res = await fetch_tasa_scraping()
        persist_tasa(db, res["tasa"], res["origen"])
        return res
    except Exception:
        pass

    try:
        return fetch_tasa_db(db)
    except Exception:
        pass

    # última defensa: env var o 1.0
    tasa_defecto = Decimal(str(os.getenv("DEFAULT_TASA_BCV", "1.0"))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if tasa_defecto <= 0:
        raise TasaNoDisponibleError("No hay tasa disponible en ningún nivel")

    persist_tasa(db, tasa_defecto, "ENV")
    return {"tasa": tasa_defecto, "origen": "ENV", "fecha": datetime.utcnow()}


async def convertir_payments(db: Session, monto_bs: float) -> ConversionResult:
    tasa = await get_tasa_bcv(db)
    usd = decimal_usd(monto_bs, tasa["tasa"])
    return {
        "monto_bs": Decimal(str(monto_bs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "tasa_bcv": tasa["tasa"],
        "monto_usd": usd,
        "origen": tasa["origen"],
        "fecha": datetime.utcnow(),
    }
