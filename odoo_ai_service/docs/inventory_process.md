# Proceso de Inventario

## Proposito

Este documento describe como funciona el proceso de inventario, stock, transferencias y pickings en Odoo para los evals del copilot.

## Proceso

1. Los movimientos de inventario se representan con pickings o transferencias de stock.
2. Un picking agrupa los movimientos necesarios para recibir, entregar o transferir productos internamente.
3. Un picking puede estar en borrador, en espera, listo, hecho o cancelado.
4. Un picking en estado `assigned` o listo tiene stock reservado y puede validarse.
5. Un picking en espera todavia depende de disponibilidad de stock o de una operacion anterior.
6. Cuando todas las cantidades requeridas se procesan, el picking se valida y pasa a estado `done`.
7. El proceso de inventario permite controlar disponibilidad, reservas, recepciones, entregas y transferencias internas.

## Notas de Evaluacion

El copilot debe usar esta documentacion cuando el usuario pregunta como funciona el proceso de inventario, como funciona un picking o como interpretar la validacion de transferencias de stock.
