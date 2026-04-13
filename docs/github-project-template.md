# GitHub Project sugerido — Odoo AI Copilot

Este documento deja armado el diseño del GitHub Project para organizar el trabajo del repo.

Como referencia, el Project puede llamarse:

**Odoo AI Copilot — Hardening & Productization**

---

## Vista sugerida: Board

### Columnas

1. **Backlog**
2. **Ready**
3. **In Progress**
4. **Review**
5. **Done**

---

## Campos sugeridos del Project

### 1) Prioridad
Opciones:
- Alta
- Media
- Baja

### 2) Estimación
Opciones:
- S
- M
- L

### 3) Área
Opciones:
- Backend
- Frontend
- Seguridad
- Memoria
- Observabilidad
- UX
- Documentación
- Producto

### 4) Sprint
Opciones:
- Sprint 1
- Sprint 2
- Sprint 3
- Sprint 4

### 5) Estado funcional
Opciones:
- Definición
- Implementación
- Validación
- Demo

---

## Swimlanes o agrupación recomendada

Agrupar por **Prioridad** o por **Sprint**.

Si quieres una vista operativa más clara, agrupa por **Sprint** y ordena dentro de cada columna por **Prioridad**.

---

## Issues recomendadas para cargar al Project

### Sprint 1

#### Alta
1. **Formalizar los modos de respuesta del agente**
   - Área: Backend
   - Estimación: M
   - Labels: `backend`, `agent`, `high-priority`

2. **Estandarizar el contrato de respuesta entre backend y frontend**
   - Área: Backend / Frontend
   - Estimación: M
   - Labels: `backend`, `frontend`, `api`, `high-priority`

3. **Implementar allowlist de modelos y campos permitidos**
   - Área: Seguridad
   - Estimación: M
   - Labels: `security`, `backend`, `high-priority`

4. **Asegurar el scope por usuario, compañía y contexto activo**
   - Área: Seguridad / Contexto
   - Estimación: M
   - Labels: `security`, `backend`, `context`, `high-priority`

---

### Sprint 2

#### Alta
5. **Endurecer la comunicación entre Odoo y FastAPI**
   - Área: Seguridad / Backend
   - Estimación: S/M
   - Labels: `security`, `backend`, `api`

6. **Separar memoria en contexto activo, memoria corta y preferencias**
   - Área: Memoria
   - Estimación: M
   - Labels: `memory`, `backend`, `agent`

7. **Implementar TTL y reglas de reinicio de memoria**
   - Área: Memoria / Contexto
   - Estimación: S/M
   - Labels: `memory`, `backend`, `context`

8. **Implementar logging estructurado por request**
   - Área: Observabilidad
   - Estimación: S/M
   - Labels: `observability`, `backend`, `high-priority`

---

### Sprint 3

#### Alta
9. **Reducir el uso del LLM en consultas de negocio determinísticas**
   - Área: Backend / Performance
   - Estimación: M
   - Labels: `backend`, `agent`, `performance`

10. **Mejorar la resolución de follow-ups relacionales**
    - Área: Memoria / Agente
    - Estimación: M
    - Labels: `memory`, `agent`, `tests`

11. **Crear benchmark funcional del copiloto**
    - Área: Calidad / Observabilidad
    - Estimación: M
    - Labels: `tests`, `observability`, `quality`

12. **Agregar tests unitarios e integración para componentes críticos**
    - Área: Calidad
    - Estimación: M/L
    - Labels: `tests`, `backend`, `quality`

---

### Sprint 4

#### Media/Alta
13. **Adaptar el frontend a respuestas estructuradas**
    - Área: Frontend / UX
    - Estimación: M
    - Labels: `frontend`, `ux`, `chat`

14. **Mostrar contexto activo y tipo de respuesta en la interfaz**
    - Área: Frontend / UX
    - Estimación: S/M
    - Labels: `frontend`, `ux`

15. **Agregar acciones rápidas contextuales en las respuestas**
    - Área: Frontend / Producto
    - Estimación: M
    - Labels: `frontend`, `ux`, `product`

16. **Mejorar README técnico y de producto**
    - Área: Documentación / Producto
    - Estimación: S
    - Labels: `documentation`, `product`

17. **Documentar variables de entorno y configuración**
    - Área: Documentación / DevOps
    - Estimación: S
    - Labels: `documentation`, `devops`

18. **Crear demo guiada por casos de uso**
    - Área: Producto / Demo
    - Estimación: S/M
    - Labels: `product`, `demo`

---

## Vista sugerida: Tabla

Crear una segunda vista tipo tabla con estas columnas visibles:

- Título
- Estado
- Prioridad
- Estimación
- Área
- Sprint
- Labels

Esta vista sirve para priorizar rápido sin mover tarjetas.

---

## Reglas operativas sugeridas

### Cuándo pasa una tarjeta a Ready
- Tiene alcance claro
- Tiene criterios de aceptación
- No depende de otra tarea bloqueante sin identificar

### Cuándo pasa a In Progress
- Ya se empezó a implementar
- Hay una persona responsable
- Ya existe enfoque técnico definido

### Cuándo pasa a Review
- La implementación principal está hecha
- Falta validación funcional, revisión o prueba

### Cuándo pasa a Done
- Cumple criterios de aceptación
- No rompe flujo actual
- Tiene validación mínima
- Si aplica, quedó documentado

---

## Issues críticas para abrir primero

Si no quieres cargar todo el Project de golpe, empieza solo con estas 8:

1. Formalizar los modos de respuesta del agente
2. Estandarizar el contrato de respuesta entre backend y frontend
3. Implementar allowlist de modelos y campos permitidos
4. Asegurar el scope por usuario, compañía y contexto activo
5. Separar memoria en contexto activo, memoria corta y preferencias
6. Implementar TTL y reglas de reinicio de memoria
7. Implementar logging estructurado por request
8. Crear benchmark funcional del copiloto

---

## Labels recomendados

- `backend`
- `frontend`
- `agent`
- `memory`
- `security`
- `context`
- `tests`
- `observability`
- `ux`
- `product`
- `documentation`
- `api`
- `performance`
- `high-priority`

---

## Cómo montarlo manualmente en GitHub

1. Ir a la pestaña **Projects** en GitHub
2. Crear un nuevo proyecto tipo **Board**
3. Nombrarlo: **Odoo AI Copilot — Hardening & Productization**
4. Crear columnas:
   - Backlog
   - Ready
   - In Progress
   - Review
   - Done
5. Crear campos personalizados:
   - Prioridad
   - Estimación
   - Área
   - Sprint
   - Estado funcional
6. Crear o importar las issues del backlog
7. Asignarlas al sprint correspondiente
8. Ordenarlas por prioridad

---

## Recomendación final

No empieces con 18 tareas activas. Mantén **máximo 3 a 4 tarjetas en In Progress**.

Si abres todo al mismo tiempo, el Project se verá muy bonito, pero va a producir exactamente cero features. GitHub también sabe decorar cementerios.
