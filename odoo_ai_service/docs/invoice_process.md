# Proceso de Facturacion

## Proposito

Este documento describe el proceso de facturacion usado por los evals del copilot.

## Proceso

1. La factura se crea desde una venta, una entrega o de forma manual cuando corresponde.
2. Una factura en borrador debe revisarse antes de publicarse.
3. Al publicarse, la factura pasa a estado `posted` y queda disponible para seguimiento de cobro.
4. El estado de pago indica si esta pendiente, parcialmente pagada o pagada.
5. Las facturas vencidas o pendientes deben revisarse en el flujo de cobranza.

## Politica de Control

- Una factura publicada debe tener cliente, moneda, fecha, vencimiento y monto total.
- Una factura sin cliente o sin monto debe revisarse antes de considerarse valida.
- Las facturas pendientes o vencidas requieren seguimiento operativo hasta su pago.

## Notas de Evaluacion

La factura `INV/2026/00001` es un fixture de evaluacion. Si esta publicada y tiene monto total, puede usarse como evidencia de facturacion para el copilot.
