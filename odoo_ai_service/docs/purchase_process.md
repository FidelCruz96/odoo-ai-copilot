# Proceso de Compras

## Proposito

Este documento describe el proceso de compras en Odoo usado por los evals del copilot.

## Proceso

1. El comprador crea una orden de compra en borrador con proveedor, productos, cantidades, precios y fecha esperada de recepcion.
2. La orden de compra se revisa contra la politica de aprobacion antes de confirmarla.
3. Si el monto total esta dentro del umbral del comprador, el comprador puede confirmar la compra.
4. Si el monto total supera S/ 10,000, se requiere aprobacion de un gerente antes de confirmar.
5. Si el monto total supera S/ 25,000, tambien se requiere aprobacion de finanzas.
6. Una vez confirmada, la orden pasa al estado `purchase` y puede generar recepciones.
7. El estado de recepcion indica si los productos comprados fueron recibidos parcial o totalmente.

## Notas de Evaluacion

La orden de compra `PO-I-10-00026` es un fixture de evaluacion. Como su total supera S/ 25,000, debe tener aprobacion de gerente y finanzas antes de considerarse conforme con la politica.
