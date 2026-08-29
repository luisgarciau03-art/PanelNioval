# ADR — Modelo de puntuación de relevancia de ciudades

**Fecha:** 2026-08-28 · **Estado:** ACEPTADO · **Tarea:** Plan 1 · T1.3
**Rama:** `feat/relevancia-ciudades-nacional`
**Sustituye a:** la fórmula endógena de `app.py:913-919` (que se conserva por compatibilidad
hasta el retiro documentado en T1.6)
**Insumos:** `docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md` (T1.2) ·
`docs/investigacion/2026-08-28-contexto-previo-importador.md` (T1.1)

---

## 1. Contexto

El importador ordena las ciudades con una fórmula cuyos **tres términos son endógenos**:
salen del historial de llamadas de NIOVAL. Una ciudad donde nunca han trabajado puntúa
exactamente 0 y queda ordenada por el orden de escritura de un array hecho a mano. El
ranking es circular: recomienda donde ya se trabajó, así que solo se trabaja ahí.

El orden decide **a qué ciudad se le dedica dinero real**: cada corrida cuesta del orden de
80 llamadas de Place Details a Google Places.

## 2. Decisión

```
prioridad = potencial_mercado × factor_nioval
```

### 2.1 `potencial_mercado` — exógeno, 0-100, escala logarítmica

| Componente | Peso | Fuente | Forma |
|---|---|---|---|
| Ferreterías y tlapalerías (SCIAN 467111) | **50 %** | DENUE 05_2026 | `log(1+x)` normalizado al máximo |
| **Tamaño medio** del establecimiento (personal ocupado ÷ ferreterías) | **10 %** | DENUE 05_2026 | lineal normalizado |
| Mayoreo de materiales de construcción (6 códigos 4342\*) | **15 %** | DENUE 05_2026 | `log(1+x)` normalizado |
| Empresas de construcción (sector 23) | **10 %** | DENUE 05_2026 | `log(1+x)` normalizado |
| Población municipal | **15 %** | Censo 2020 (ITER) | `log(1+x)` normalizado |

**Rango obtenido sobre los municipios candidatos: mínimo 34.6, mediana 51.2, máximo 91.4.
Cero ciudades por debajo de 5 puntos, cero ciudades en 0.** La restricción no negociable del
plan se cumple por construcción, no por un piso artificial.

### 2.2 `factor_nioval` — endógeno, acotado a **[0.60, 1.25]**, neutro en **1.00**

Es **multiplicativo** y tiene dos componentes que se multiplican entre sí:

```python
# Desempeño, con encogimiento por tamaño de muestra
tasa  = aprobados / llamados          if llamados else P0
peso  = llamados / (llamados + 20)    # confianza: 0 sin llamadas, 0.5 a las 20
f_desempeno = clamp(1 + 0.25 * peso * (tasa - P0) / P0, 0.75, 1.25)

# Saturación: lo que ya se cosechó deja de ser oportunidad
f_saturacion = 1 - 0.35 * min(1, contactos_en_hoja / unidades_ferreteras)

factor_nioval = clamp(f_desempeno * f_saturacion, 0.60, 1.25)
```

`P0` es la tasa de interés global de NIOVAL, calculada de los propios datos, no una constante
inventada.

**Comportamiento verificado con datos reales de la hoja:**

| Caso | `factor_nioval` |
|---|---|
| Ciudad virgen, sin historial | **1.000** (neutro — no se penaliza no haber ido) |
| Pueblo con 1 aprobado de 3 llamadas | **0.961** |
| Puebla (425 contactos de 1,357 ferreterías) | 0.890 |
| Chihuahua (448 contactos de 651 ferreterías) | **0.741** |

## 3. Los tres candidatos y por qué se descartaron dos

Los tres se **calcularon de verdad** sobre los 589 municipios con ≥20 ferreterías. No es una
comparación de sobremesa.

| Candidato | Resultado medido | Veredicto |
|---|---|---|
| **A — Lineal** (normalizar dividiendo por el máximo) | Mediana 3.0. **399 de 589 ciudades por debajo de 5 puntos.** | ❌ **Descartado.** La distribución es de cola pesada: el primer municipio vale **185 veces la mediana**. Normalizar linealmente deja 2 de cada 3 ciudades apretadas en una banda de 4 puntos, que es **el empate arbitrario del problema original con otro nombre**. Salvarlo exigiría un piso artificial: reinventar peor lo que el logaritmo hace gratis. |
| **B — Logarítmico** | Mínimo 36.9, mediana 53.9, máximo 98.5. **Cero ciudades bajo 5.** | ✅ **Elegido**, con las tres correcciones del consejo (§4). |
| **C — Geométrico de dos ejes** (ramo × contexto) | Mediana 2.8. **407 ciudades por debajo de 5.** | ❌ **Descartado.** Hereda el defecto de A y además **penaliza dos veces el desbalance**: un municipio con muchas ferreterías y poca obra se hunde por la media geométrica, cuando para un mayorista es exactamente un buen cliente — muchos puntos de venta que reponer. |

## 4. Qué cambió el consejo, y es lo más valioso de esta tarea

Se convocó un consejo de cuatro voces (Arquitecto, Escéptico, Pragmático, Crítico). Las tres
voces externas coincidieron en **B**, así que la elección de modelo no se movió. **Lo que sí
cambió el diseño fueron tres objeciones**, y las tres se comprobaron con medición antes de
aceptarlas:

### 4.1 El Escéptico: *"los cinco indicadores son uno solo con cinco disfraces"*

**Tenía razón a medias, y la mitad correcta cambió el modelo.** Matriz de correlación de
Pearson sobre `log(1+x)`, 589 municipios:

| | ferreterías | ocupados | mayoreo | construcción | población |
|---|---|---|---|---|---|
| **ferreterías** | 1.00 | **0.97** | 0.92 | 0.82 | 0.83 |

`personal ocupado` en crudo es **colineal con el conteo (r = 0.971)**: pesaba 20 % y no
aportaba casi nada. **Reexpresado como tamaño medio (`ocupados / ferreterías`) la
correlación cae a r = 0.152** — el mismo dato deja de duplicar el conteo y empieza a decir
algo propio: si la plaza es de ferreterías de mostrador (3.0 personas) o de bodega (15.1).
**Se cambió la forma del indicador y su peso bajó de 20 % a 10 %.**

Donde el Escéptico **no** tenía razón: sostuvo que los pesos son teatro porque el top no se
mueve. Medido — cinco indicadores contra solo el conteo, mismo modelo logarítmico:

- Top-20: **18 de 20 coinciden**, pero **entran y salen Hermosillo, San Luis Potosí,
  Naucalpan y Chimalhuacán**.
- Desplazamiento medio en el top-100: **10 puestos**.
- Top-50: **16 de 50 cambian**.

No es teatro, pero tampoco es dramático, y decirlo así es más honesto que defender los pesos
como si fueran sagrados.

### 4.2 El Crítico: *"ninguno de los tres modela el agotamiento"* — **objeción aceptada**

Places devuelve del orden de 60 resultados por búsqueda. Una plaza ya cosechada rinde
duplicados y sigue siendo #1 para siempre. **El potencial útil es lo que queda por cosechar,
no lo que existe.**

Comprobado contra la hoja de producción: NIOVAL ya trabajó **116 ciudades** y tiene
**448 contactos en Chihuahua** (que solo tiene 651 ferreterías: **69 % cosechado**) y
**425 en Puebla**. Puebla es #1 en los tres modelos candidatos **y ya está a un tercio de
agotarse**.

**Por eso `f_saturacion` existe.** Es una corrección que no estaba en ninguno de los tres
candidatos ni en el plan original, y sale directamente de esta objeción.

### 4.3 El Crítico y el Escéptico: el número comprimido engaña al operador

Con logaritmo, León (1,137 ferreterías) y Querétaro (824) quedan a pocos puntos. Un `86.7`
frente a un `89.8` **no significa lo que el operador va a leer que significa**.

**Decisión de presentación, obligatoria para T1.7:** el chip muestra **posición y conteo
crudo de ferreterías**, nunca el decimal del puntaje. El puntaje ordena; el conteo explica.
La `explicacion` que el backend ya va a mandar es lo que hace auditable la posición.

### 4.4 El Pragmático: multiplicador, no suma — **aceptado**, con su rango

Con historial cero el factor es **1.0** y la ciudad nueva no se penaliza. Con suma habría que
decidir *cuántos puntos vale "sin datos"*, y **ese número no existe**. Además el multiplicador
es **una sola perilla** para reajustar tras el gate del owner sin tocar los cinco pesos.

Se adoptó su rango acotado (**cerca de 1.0**) en lugar del `0.5-1.5` del plan original: con
0.5-1.5 el factor endógeno movería el potencial ±50 % y volvería a dominar, que es justo lo
que este ADR viene a impedir.

### 4.5 El Crítico: *"el ranking no es el gasto; el string sí"* — **aceptado y escalado**

`"Benito Juárez"` como nombre canónico cuesta ~80 Place Details en la alcaldía equivocada.
Coincide con el hallazgo §4.4a de T1.2. **Se eleva a criterio de cierre de T1.4:** el
`nombre` canónico es el **comercial**, el nombre INEGI viaja como alias, y **ninguna entrada
del catálogo se da por buena sin que su nombre de búsqueda esté resuelto**.

## 5. Decisiones de agrupación

### 5.1 La Zona Metropolitana del Valle de México **no se fusiona en el dato**

Seis de las diez primeras plazas son ZMVM contadas por separado. El Pragmático propuso
agruparlas. **Se acepta la intención y se rechaza el mecanismo**: agrupar en el **dato**
destruiría la clave INEGI, que es el identificador que hace posible deduplicar y regenerar
el catálogo. Los municipios se conservan íntegros; **la agrupación, si se hace, es de
presentación y va al Plan 4**, que es el que rediseña la UI.

Queda registrado como **riesgo abierto**: mientras no se agrupe, el operador puede gastar
seis corridas sobre rutas de reparto solapadas. `f_saturacion` lo amortigua —cada corrida
baja la prioridad de la siguiente— pero no lo resuelve.

### 5.2 Corte del catálogo: **≥ 20 ferreterías → 589 municipios**

Cae dentro del rango 400-600 de la opción **A** de la decisión D3, cubre las **32
entidades**, y sale de un dato medido y no de una estimación. El corte alternativo (≥30 → 443
municipios) también cumple; se elige el más inclusivo porque **excluir una plaza del catálogo
es irreversible para el operador**, mientras que una plaza mal rankeada solo aparece abajo.

## 6. Consecuencias

**A favor**
- Una ciudad virgen con mercado real rankea por encima de un pueblo con un aprobado de tres
  llamadas. Verificado: factor 1.000 contra 0.961.
- El ranking deja de ser circular: el término dominante es exógeno y nacional.
- Cada posición es explicable con un conteo de establecimientos que cualquiera puede
  verificar en el DENUE.
- Regenerable: cuando INEGI publique una edición nueva, se vuelve a correr el generador.

**En contra, y se dice**
- El potencial es una **foto de mayo de 2026** (DENUE) y de **2020** (población). Envejece.
- El logaritmo comprime: sin el conteo crudo al lado, el número engaña. Mitigado en §4.3.
- `f_saturacion` usa los contactos ya escritos en la hoja como proxy de cosecha. La hoja
  tiene **nombres de ciudad sucios —116 valores distintos, algunos son estados
  ("Chiapas", "Guerrero", "Guanajuato")—**, así que el proxy es imperfecto. La reconciliación
  de T1.5 lo mejora, y lo que no case va a `"Sin clasificar"` **visible**.

## 7. Criterio de desempate

A igualdad de `prioridad` (redondeada a un decimal), ordena **descendente por número de
ferreterías (467111)**; si persiste, **ascendente por clave INEGI**. Es determinista y
reproducible: la misma entrada da el mismo orden en cualquier máquina, que es lo que hoy
**no** ocurre con el `sort` estable sobre una lista de ceros.

## 8. Qué invalidaría esta decisión

- **El gate del owner (T1.8):** si no reconoce el top-20 como las plazas relevantes de su
  ramo, se vuelve aquí y se reajustan pesos. El ADR se enmienda; no se sustituye en silencio.
- Que DENUE deje de publicar la descarga masiva por URL directa y solo quede la API con token.
- Que NIOVAL cambie de ramo o de cobertura geográfica.
