# SKILL: ExtractorPagos_V5
## Instrucciones de Extracción:
1. **banco_origen**: Banco emisor (ej. Venezuela, Mercantil, Banesco).
2. **banco_destino**: Banco receptor. Busca "Destino", "A:", "Cuenta".
3. **monto**: Valor numérico.
   - Busca etiquetas como "Monto", "Importe", "Bs.", "VES", "Total".
   - **Formato Venezuela**: "1.500,00" es mil quinientos. "50,00" es cincuenta.
   - Si ves "1.500,00", conviértelo a `1500.00`.
   - Devuelve un número (float), no un string.
4. **referencia**: Número de operación o referencia. Busca etiquetas como: "Ref", "Referencia", "Nro Operación", "Secuencia", "Documento". Ignora cédulas o teléfonos.

## Formato de Salida (JSON estricto):
{
  "banco_origen": "Nombre o null",
  "banco_destino": "Nombre o null",
  "monto": 0.00,
  "referencia": "123456"
}