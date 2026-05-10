# Proceso de Ventas

## Proposito

Este documento describe el proceso de ventas, aprobacion y confirmacion de pedidos de venta en Odoo usado por los evals del copilot.

## Proceso

1. El vendedor crea una cotizacion con cliente, productos, cantidades, precios y condiciones comerciales.
2. La cotizacion se revisa antes de confirmarla como pedido de venta.
3. Si el pedido cumple las condiciones comerciales aprobadas, puede confirmarse y pasar a estado `sale`.
4. Un pedido confirmado en estado `sale` se considera aprobado comercialmente.
5. Luego del pedido confirmado pueden generarse entregas, facturas o tareas operativas segun la configuracion.

## Politica de Aprobacion

- Las ventas confirmadas deben tener cliente identificado, monto total y productos definidos.
- Una venta en estado `sale` indica que ya fue confirmada por el flujo comercial.
- Si una venta tiene condiciones excepcionales, descuentos no autorizados o falta de cliente, debe revisarse antes de considerarse conforme.

## Notas de Evaluacion

La venta `DCN 0426-0039` es un fixture de evaluacion. Si esta en estado `sale` y tiene cliente y monto, puede tratarse como conforme con la politica comercial basica.
