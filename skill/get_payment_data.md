# Skill: Extracción de datos de pagos

## Objetivo
Extraer información estructurada de comprobantes de pago venezolanos a partir del texto sucio generado por OCR.

## Entrada
Un texto plano con el contenido extraído del comprobante.

## Salida esperada
Un objeto JSON con los siguientes campos:
- monto: número decimal, usando punto como separador decimal.
- referencia: texto del número de referencia o comprobante.
- cedula: texto de la cédula o RIF si se detecta, o null si no está presente.
- banco: nombre del banco si se encuentra claramente en el texto, o null si no puede identificarse.

## Reglas
- Responde **solo** con JSON válido. No agregues explicaciones.
- Si un campo no puede extraerse con seguridad, devuélvelo como null.
- Normaliza los montos para que sean valores numéricos, no texto.
- No inventes datos que no estén en el texto.
