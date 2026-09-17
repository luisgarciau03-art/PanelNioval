# T3.7 — Verificación en producción · **BLOQUEADA en CE3**

**Plan:** 3 · **Tarea:** T3.7 · **Fecha:** 2026-09-17
**Rama:** `fix/conteo-importador-reincidencia` · **Baseline:** 1,208 passed, 2 skipped
**Evidencia:** `docs/investigacion/estados-produccion-2026-09-17/` (9 capturas)

> El plan es explícito: *«si la corrida real depende del owner, la tarea queda **BLOQUEADA**, no
> "hecha con nota"»*. Queda bloqueada. Abajo está lo que sí se pudo cerrar, y exactamente qué
> falta.

---

## 1. Estado de los criterios

| | Criterio | Estado |
|---|---|---|
| **CE5** | Recorrido de estados contra producción | ✅ **9 / 9 coinciden** |
| **CE3** | `después − antes == nuevos_en_sheet` en la hoja real | 🔴 **BLOQUEADO — owner** |
| — | Telegram dice lo mismo que la UI | ✅ verificado (local, §4) |
| — | Despliegue | ✅ **no hace falta** (§3) |

---

## 2. CE5 · Los estados, contra el front-end desplegado

Se repitió el recorrido de T3.5 contra `https://panelnioval.duckdns.org`, con el panel real
sirviendo su HTML, su CSS y su JS.

| Estado | `nuevos` | `aprobados` | Pantalla | |
|---|---:|---:|---:|---|
| `idle` | 0 | 0 | fila oculta | ✅ |
| `running` | 6 | 6 | 6 | ✅ |
| **`done`** | **10** | **14** | **10** | ✅ |
| `cancelado` | 6 | 6 | 6 | ✅ |
| `interrumpido` | 6 | 6 | 6 | ✅ |
| `error` | 0 | 0 | 0 | ✅ |
| `presupuesto_agotado` | 6 | 6 | 6 | ✅ |
| `done_vacia` | 0 | 0 | 0 | ✅ |
| `recarga_tras_reinicio` | 6 | 6 | 6 | ✅ |

**9 escenarios, 0 afirmaciones falsas.** La captura de `done` enseña el caso que importa:
**«NUEVOS EN LA HOJA 10»** en grande, y **«APROBADOS POR FILTROS 14»** en pequeño y con su
nombre propio. El «20 vs 10» ya no se puede leer mal.

### 2.1 Qué demuestra este recorrido, y qué NO

**Demuestra** que el front-end **que sirve el VPS** saca los mismos veredictos que el local sobre
los mismos datos. No es una inferencia desde el sha256: es la página real, cargada por red,
ejecutando su propio JavaScript.

**No demuestra** que el backend desplegado produzca esos estados. **Los estados no se provocan
contra producción a propósito**: hacerlo costaría llamadas a Places y escribiría filas en
`LISTA DE CONTACTOS`. Eso *es* la corrida real, y es gate del owner.

⚠️ **Y una salvedad de método, para que nadie lea de más en las capturas.** La lista de ciudades
está **interceptada** por el arnés —son datos sintéticos del catálogo público del INEGI más una
ciudad de demo—, así que el «1005» que se ve **no** es lo que sirve producción. Que el VPS sirve
**1,004** ciudades quedó probado aparte, en el Plan 1 · T1.6.

Las 9 capturas no llevan un solo dato de cliente: las ciudades son públicas y los contadores,
inventados.

---

## 3. El paso 1 del plan: no hay nada que desplegar

El plan pide *«PR, gates, merge, despliegue, smoke en verde»*. El despliegue **no aplica**, y no
por criterio sino por medición:

```
git diff main..HEAD --stat -- app.py static/ templates/ Dockerfile requirements.txt despliegue/
    -> vacio
```

**Este plan no cambia una sola línea de lo que el VPS sirve.** Lo que añade son dos herramientas
(`tools/`), sus tests, y documentación. Era previsible desde T3.2 —la causa era de despliegue, no
de código— pero se comprueba en vez de suponerse.

Consecuencia: **el operador no ve ningún cambio**, y no hay riesgo de regresión en producción por
mergear esto. El smoke sigue valiendo lo que valía; no se corre como prueba de nada nuevo.

---

## 4. Telegram dice lo mismo que la UI

Verificado en T3.5 interceptando el `post` del notificador real, no reimplementando el mensaje:

| Estado | Título del aviso | ¿Coincide con la UI? |
|---|---|---|
| `done` / `done_vacia` | 📥 Importador **Completado** | ✅ |
| `cancelado` / `interrumpido` | ⏹ Importador **DETENIDO** | ✅ |
| `error` | ❌ Importador **FALLÓ** | ✅ |
| `presupuesto_agotado` | ⛔ Importador: **TOPE DE GASTO** | ✅ |

Y en los cuatro, `<b>Nuevos en la hoja:</b>` publica **el mismo número** que el titular de la
pantalla. Los dos hallazgos de agosto (#17575, #17826) están cerrados.

**Esto se midió en local.** El aviso lo construye el backend, y el desplegado es el mismo
commit — pero *el mismo commit* es una inferencia, no una medición. Comprobarlo de verdad exige
una corrida real, o sea el mismo gate.

---

## 5. 🔴 CE3 · Lo que falta, y por qué no lo puedo hacer yo

**CE3 es la aritmética:** contar las filas de `LISTA DE CONTACTOS` antes, correr una ciudad,
contarlas después, y comprobar que **la diferencia es exactamente el `nuevos_en_sheet` que
muestra la UI**.

Tres razones por las que esta sesión no puede cerrarlo, y ninguna es de criterio:

1. **No hay credenciales de Google en esta máquina.** `GOOGLE_CREDENTIALS_JSON` ausente, ni
   `credentials.json` ni `.env` en disco (comprobada la **presencia**, nunca el valor).
2. **Una corrida real factura Google Places.** Las reglas del proyecto exigen confirmar el coste
   con el owner antes de gastar.
3. **Escribe filas en la hoja de producción**, sobre datos vivos de clientes. Es una mutación
   difícil de revertir, y **requiere respaldo previo de hojas** — que tampoco se puede hacer sin
   credenciales.

**Lleva bloqueado desde el 2026-08-27.** Es el mismo CE1 que el Plan 3 de agosto dejó abierto, y
este plan entero es la consecuencia de que nadie lo cerrara: el fix se dio por bueno con dobles,
y el operador siguió viendo el bug tres semanas por otra razón —el despliegue— que ninguna
verificación local podía ver.

### 5.1 La receta exacta, para cuando el owner la corra

```bash
# 1. RESPALDO PRIMERO. No es opcional: la corrida escribe en produccion.
python tools/respaldar_hojas.py            # deja XLSX en docs/auditoria/respaldos/<fecha>/

# 2. Contar las filas ANTES
python tools/inspeccionar_contactos.py     # anotar el total

# 3. Correr UNA ciudad pequeña desde el panel, y anotar de la pantalla:
#      nuevos_en_sheet · aprobados · ya estaban · descartados

# 4. Contar DESPUES
python tools/inspeccionar_contactos.py

# 5. La comprobacion, que es una resta:
#      despues - antes  ==  nuevos_en_sheet
```

**Elegir una ciudad pequeña y ya trabajada.** Pequeña acota el gasto; ya trabajada hace que
`nuevos` y `aprobados` **sean distintos**, que es lo único que prueba que se distinguen. Una
ciudad virgen los deja iguales y la comprobación no prueba nada — es el mismo agujero que la
mutación destapó en la auditoría de T3.5.

**Si la resta no cuadra**, T3.6 se reabre con un caso real y el candidato ya está anotado: la
escritura parcial de `app.py:3238`, que devuelve filas **enviadas** y no las que Google confirmó.

---

## 6. Estado de la tarea

| | |
|---|---|
| CE5 | ✅ **9/9 contra producción** |
| Telegram | ✅ coincide con la UI |
| Despliegue | ✅ innecesario, **medido** |
| **CE3** | 🔴 **BLOQUEADO — owner: credenciales, coste de Places y respaldo de hojas** |
| **T3.7** | 🔴 **BLOQUEADA** |

**T3.8 puede cerrarse igual** —es documentación y relevo— pero **el Plan 3 no se marca completo**
mientras CE3 siga rojo. Marcarlo completo sería repetir exactamente el error de agosto: dar por
verificado con dobles lo que sólo la hoja real puede confirmar.
