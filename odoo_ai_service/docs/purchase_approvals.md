# Purchase Approval Policy

## Purpose

This document defines the approval flow for purchase orders in Odoo.

## Approval rules

- Purchases up to S/ 10,000 can be confirmed directly by the buyer.
- Purchases above S/ 10,000 require manager approval before confirmation.
- Purchases above S/ 25,000 require finance approval in addition to manager approval.

## Operational notes

- Draft purchase orders should remain in review until the required approval is completed.
- Confirmed purchase orders in state `purchase` are considered approved.
- The policy applies to all local vendors unless a specific contract states otherwise.

## Example

If purchase order `PO00045` has a total amount of S/ 12,500, it should have passed manager approval before confirmation.
