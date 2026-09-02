# Handoff — Plan 4, sesión nueva

**Fecha:** 2026-09-02 · **Estado:** Plan 4 en 9/12 · **PR #43 abierto, CI verde**

Mensaje listo para pegar al arrancar la sesión siguiente. Todo lo de aquí está
verificado en disco el 2026-09-02, no copiado de documentos previos.

---

```
Continua los planes de trabajo de PanelNioval. Toca el Plan 4, tarea T4.9.

PROYECTO: C:\Users\PC 1\PanelNioval
RAMA: feat/rediseno-panel  <- YA EXISTE, continua en ella. NO crees otra.
NUNCA main: Railway y Vultr auto-despliegan desde ahi.

LEE EN ESTE ORDEN ANTES DE TOCAR CODIGO:
1. C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md  <- 653 herramientas
   (229 agentes + 424 skills), 6 fuentes. Confirma que la leiste citando el
   total. Superpowers aporta 14 de 653: si el plan usa solo Superpowers,
   esta mal disenado por definicion.
2. C:\Users\PC 1\PanelNioval\CLAUDE.md
3. docs/superpowers/plans/2026-08-27-plan4-rediseno-profesional-panel.md
   Su seccion 0 de validacion MANDA sobre los numeros de linea del resto.
   OJO: los anclajes `app.py:NNNN` de las tareas T4.7-T4.9 son de ANTES de
   la T4.3. Desde entonces NO hay HTML en app.py: las tres superficies
   viven en templates/ y static/. Ignora esos numeros de linea.
4. docs/adr/2026-08-31-direccion-visual-panel.md  <- la direccion ya esta
   decidida y la paleta accesible calculada. No la vuelvas a abrir.
5. Las cuatro evidencias de las tareas ya hechas, que documentan lo que se
   corrigio y por que:
     docs/diseno/2026-09-01-estados-de-carga-t45.md
     docs/diseno/2026-09-01-sistema-de-movimiento-t46.md
     docs/diseno/2026-09-01-rediseno-tablero-t47.md
     docs/diseno/2026-09-02-rediseno-formulario-t48.md
6. docs/superpowers/plans/2026-08-27-indice-tanda.md  <- marcador global (S6),
   gates del owner (S7.1), decisiones resueltas (S7.2) y pendientes (S8).
7. Memoria del proyecto: el MEMORY.md de
   C:\Users\PC 1\.claude\projects\c--Users-PC-1-PanelNioval\memory\
   (7 entradas; la ultima es de esta sesion y evita un error que costo cinco
   rondas).

=== ESTADO AL 2026-09-02 ===

MARCADOR GLOBAL: 42/53 tareas (79 %). 4 de 6 planes cerrados.

  Plan 3 - Bug de conteo y pantallas de carga   10/10 OK  PR #36  ae0e1c9
  Plan 0 - Integracion continua                   4/4 OK  PR #40  c10d063
  Plan 2 - Gasto de Google Places                 9/9 OK  PR #38  4e06e64
  Plan 1 - Relevancia de ciudades               10/10 OK  PR #42  SIN MERGEAR
  Plan 4 - Rediseno del panel                    9/12     <- ESTE
  Plan 5 - Endurecimiento                         0/8

Plan 4, hecho:
  T4.0 evidencia del antes          b5ff47d
  T4.1 auditoria y ADN de marca     b5ff47d
  T4.2 direccion visual + ADR       1c3665d   (metodo: skill council)
  T4.3 HTML fuera de app.py         d86323f   app.py 6,368 -> 3,133 lineas
  T4.4 tokens y componentes         211a70e + 43ba0e8
  T4.5 esqueletos y los 4 estados   798e4c9 + a0bbdbb
  T4.6 sistema de movimiento        465640b
  T4.7 rediseno del tablero         ecdb62c
  T4.8 rediseno del formulario      cd5729c

Plan 4, pendiente:
  T4.9  rediseno del importador   <- SIGUIENTE
  T4.10 accesibilidad, responsive y rendimiento
  T4.11 cierre: sistema documentado, PR, handoff

*** DOS PRs ABIERTOS Y APILADOS ***

PR #43 (feat/rediseno-panel -> main): el Plan 4. MERGEABLE, CI verde.
PR #42 (feat/relevancia-ciudades-nacional -> main): el Plan 1, terminado.

#43 SALE DE la rama de #42, asi que ARRASTRA sus commits. Mergear el Plan 4
mergea tambien el Plan 1. Fue decision del owner el 2026-08-31.

NO mergees ninguno por tu cuenta: el criterio CE10 del Plan 1 es un gate
humano del owner que sigue abierto, y main auto-despliega a produccion.

=== BASELINE, Y ES POR RAMA ===

  main                                388 passed, 1 skipped
  feat/relevancia-ciudades-nacional   482 passed, 1 skipped
  feat/rediseno-panel (esta)          781 passed, 1 skipped   <- tu gate

Comando oficial: python -m pytest tests/    <- SIN -q
pytest.ini ya trae addopts=-q; el segundo lo vuelve -qq y SUPRIME la linea
del resumen: se ven los puntos y exit 0, pero nunca el numero.

Nota: importar app.py en frio tarda 1-5 minutos. No es un cuelgue.

=== HERRAMIENTAS DE VERIFICACION QUE YA EXISTEN — USALAS ===

Esta tanda construyo cuatro arneses de navegador. NO son opcionales: cada uno
encontro al menos un fallo que ninguna lectura de codigo ni test de patron
podia ver. Correlos ANTES de dar nada por terminado, y AMPLIALOS con lo que
toque tu tarea.

  python tools/verificar_estados.py      5 comprobaciones (T4.5)
  python tools/verificar_movimiento.py  13 comprobaciones (T4.6)
  python tools/verificar_tablero.py     24 comprobaciones (T4.7)
  python tools/verificar_formulario.py  12 comprobaciones (T4.8)
  python tools/medir_cls.py [--detalle] CLS de las 3 superficies, red lenta
  python tools/capturar_estados.py <dir>  capturas de los estados
  python tools/capturar_superficies.py <dir>  las 3 superficies en 320/768/1440
  python tools/comparar_capturas.py <antes> <despues>
  python tools/barrer_secretos.py   (recibe un diff por stdin)

Todos arrancan la app SIN credenciales de Google y lo COMPRUEBAN en la
direccion util (que el cliente falla). Ninguno llama a APIs de pago.

Capturas versionadas:
  docs/diseno/antes/*.png                    (9, el estado original)
  docs/diseno/2026-09-01-estados-t45/*.png   (7, los cuatro estados)
  docs/diseno/2026-09-01-tablero-t47/*.png   (9, el tablero rediseñado)

=== LO QUE YA ESTA DECIDIDO: NO LO REABRAS ===

Direccion visual (ADR 2026-08-31): editorial/Swiss disciplinado, UN solo
sistema con TRES registros:
  - /formulario  denso y quieto. NO lleva animacion de entrada, y es
                 decision, no descuido: la velocidad de captura manda.
  - /            jerarquico. Contraste de escala fuerte.
  - /importador  narrativo. El movimiento cuenta el avance de la corrida.
                 <- ES EL REGISTRO DE TU TAREA.

Regla del voto del Critico, ya aplicada en T4.5/T4.7/T4.8 y que la T4.9
tiene que respetar: la celebracion (confeti, verde de exito, marcas de
verificacion) queda RESERVADA a estados verificados de forma explicita. Un
estado que solo puede afirmar "no recibi datos" no se viste de exito.

El sistema de diseno YA EXISTE. Usalo, no lo rehagas:
  static/css/tokens.css       UNICO sitio con un color literal. CE3 = 0 en
                              todo el proyecto desde la T4.7.
  static/css/base.css         reset, tipografia, foco de dos tonos,
                              .solo-lectores, [hidden]{display:none!important}
  static/css/componentes.css  btn, tarjeta, chip, stat, insignia, campo,
                              tabla, progreso, consola + ESTADOS DE CARGA
                              (.esqueleto*, .estado--vacio/error/parcial) +
                              MOVIMIENTO (.fila-entra, .seccion-entra)
  static/js/estados.js        Estados.esqueleto/vacio/error/parcial/escapar
  templates/*.html + static/css|js/*.css|js por superficie

Convenciones que NO puedes romper:
  --exito pasa AA (4.54:1) y va con texto; --exito-vivo (2.16:1) SOLO
  decoracion. Igual con --aviso/--aviso-vivo y --error/--error-vivo.
  Nada de `transition: all` ni de animar width/height/border/top/left.
  Solo transform, opacity y color/background-color.
  Todo lo que venga de la hoja pasa por Estados.escapar antes de innerHTML.

=== LO QUE LA T4.9 TIENE DELANTE (medido, no estimado) ===

El importador es la superficie donde convergen los cuatro planes.

Ya esta hecho y NO hay que rehacerlo:
  - los cuatro contadores del Plan 3 y su rejilla
  - el progreso con denominador ajustable (Plan 3, T3.6)
  - el medidor de gasto del Plan 2 (T2.6) y el estado presupuesto_agotado
  - el escapado de nombres de ciudad (Plan 3, T3.7)
  - el esqueleto de chips y el estado de error del catalogo (T4.5)
  - la barra por transform:scaleX con will-change puesto y retirado (T4.6)
  - el catalogo nacional de 606 municipios y sus macro-regiones (Plan 1)

Lo que la tarea pide encima:
  1. jerarquia de los cuatro contadores: nuevos_en_sheet es el numero grande
  2. dar forma al filtro por macro-region: 606 chips necesitan agrupacion,
     contador por grupo y un buscador que se sienta instantaneo
  3. la consola de log dentro del sistema, conservando su funcion
  4. la etiqueta de fase visible junto al progreso
  5. cancelacion y presupuesto agotado como estados de PRIMERA CLASE,
     no como errores

Y un defecto conocido que sigue vivo: el importador DESBORDA en horizontal a
320 px. La rejilla de contadores ya es adaptativa, pero la caja de chips y la
fila de entrada no. Formalmente es T4.10, pero mide antes de tocar y no lo
empeores.

Gate de la T4.9: code-reviewer + security-reviewer (los chips llevan nombres
de la hoja) + corrida completa con los numeros cuadrando contra la hoja.

=== DEUDA ANOTADA, NO OCULTA ===

1. Chart.js se carga de jsdelivr SIN integrity (SRI) y sin copia local. Si
   ese CDN no responde, las graficas no se dibujan — el estado parcial de la
   T4.5 lo cubre, pero la deuda es del Plan 5.
2. El panel NO es responsive. #sidebar es fixed de 230 px sin media query, asi
   que a 320 px deja menos de 90 px de contenido. Es T4.10 entera.
3. `escalonarFilas` no retira la clase `.fila-entra`. Hoy da igual porque los
   tres llamadores reconstruyen el innerHTML completo; una futura
   actualizacion de fila "in place" reintroduciria el problema.
4. `int(request.args.get('skip', 0))` en /api/formulario/siguiente sigue sin
   validar: `?skip=abc` da un 500 HTML. El formulario ya lo presenta como
   error legible, pero es deuda.
5. Los componentes accesibles de componentes.css se usan ya en los estados,
   pero varias superficies mantienen sus versiones paralelas (.btn-green del
   formulario, .stat-box del importador). Consolidarlos es trabajo de T4.10.

=== GATES DEL OWNER ABIERTOS (reportalos, NO los intentes) ===

 1. Validar el top-20 de ciudades y decidir mercado-vs-cosecha (CE10 del
    Plan 1). Bloquea el merge de #42 y por tanto el de #43.
 2. Decidir D6: CE1 pedia app.py < 800 lineas y quedo en 3,133 porque la
    T4.3 solo saco HTML. Opcion A (recomendada, y la asumida hasta ahora):
    reescribir CE1 como "app.py baja al menos un 45 % y ningun archivo nuevo
    supera 800 lineas". Opcion B: trocear el Python en modulos.
 3. Verificar la imagen Docker CONSTRUIDA de verdad (Docker no esta instalado
    en la maquina de desarrollo).
 4. Recorrido funcional en navegador por parte del owner sobre datos reales.
 5. Activar la proteccion de rama en main. Sin ella el check de CI informa
    pero NO impide el merge.
 6. Rotar TELEGRAM_TOKEN, expuesto en el historial git. Es el riesgo abierto
    mas grande.
 7. Apagar el despliegue de Railway, vivo sin PANEL_DASHBOARD_TOKEN.
 8. Anadir a .env.example los nombres de las 5 variables de Places (bloque
    exacto en el indice, S7.1). El entorno bloquea escribir archivos .env*.
 9. Consumo por SKU de Places en la consola de Google Cloud.
10. Verificacion con gunicorn real en el VPS (no corre en Windows: fcntl).
11. Revisar el 2026-09-18 si el barrido de secretos pasa a --estricto (E1).
    ANTES hay que calibrarlo: ver trampa 12.

=== TRAMPAS QUE YA COSTARON TIEMPO ===

 1. Los archivos estan en CRLF EN DISCO, tambien los .py, asi que un
    reemplazo por patron escrito con \n NO CASA y devuelve el texto igual,
    SIN ERROR. Pero en GIT los blobs son 100 % LF. No confundas las dos cosas.
 2. Los heredocs de bash se comen los escapes. Para escribir archivos usa
    Write; para parchear, Edit. Si necesitas un script Python con regex,
    escribelo con Write y ejecutalo — NO lo pases por heredoc. Esto me mordio
    cuatro veces en la sesion del 2026-09-01/02.
 3. Un test que busca el patron prohibido en el ARCHIVO ENTERO lo encuentra
    en el comentario que explica por que se retiro. Paso CINCO veces:
    `transition: all`, `style.display`, `undefined`, el confeti y
    `var(--nombre)`. Quita comentarios antes de afirmar "no queda ninguno", o
    acota la busqueda a la construccion concreta. Esta en la memoria del
    proyecto.
 4. .gitignore cubre *.json y deja archivos fuera del repo EN SILENCIO.
    Comprueba con `git check-ignore -v` en LAS DOS direcciones.
 5. `git add docs/` arrastra archivos de otro proyecto. Anade por ruta.
 6. Un test que pasa con y sin el arreglo no vale nada. Desactiva el guarda y
    confirma el rojo, SIEMPRE. Vale igual para los arneses de navegador: los
    de esta tanda estan comprobados en las dos direcciones.
 7. NUNCA uses `git checkout <archivo>` para restaurar durante una prueba
    destructiva: revierte a HEAD y BORRA lo no commiteado. Copia el archivo
    al scratchpad y restaura desde ahi.
 8. En este entorno `git diff` abre un pager y CUELGA a los subagentes. Usa
    `git --no-pager diff`, y vuelca el diff a un archivo para que el reviewer
    lo lea con Read. Tres agentes se colgaron por esto.
 9. Playwright evalua las rutas de la ULTIMA a la primera. Registra la
    generica ANTES y la especifica DESPUES. Al reves, un PoC de XSS dio
    NEGATIVO EN FALSO porque no llego a renderizarse nada.
10. `getBoundingClientRect()` incluye la transformacion; para el ancho de
    LAYOUT usa `offsetWidth`. Una comprobacion de la barra de progreso midio
    0 px por esto.
11. Comprobar la CLASE `.section.active` no prueba que el arbol del DOM este
    bien. Un `</div>` de mas dejo 11 de 12 secciones colgando de <body> y la
    verificacion lo dio por bueno. Comprueba tambien `parentElement` y
    `offsetParent`.
12. El barrido de secretos solo ve telefonos con DIGITOS CONTIGUOS y no
    distingue una fixture de una fuga. Si necesitas un numero de prueba, usa
    el literal con la marca `barrido-ok: <motivo>` que el proyecto define —
    NO compongas la cadena para esquivar el regex: funciona, y ese es el
    problema.
13. El panel cae a un .json de credencial en la raiz si falta
    GOOGLE_CREDENTIALS_JSON. Para correrlo SIN datos hay que cortar las DOS
    vias y COMPROBAR que get_gs_client() lanza excepcion. Los cuatro arneses
    ya lo hacen; copialos, no improvises.
14. No edites archivos mientras un reviewer los esta leyendo.

=== REGLAS ===

- Herramientas de la tabla de asignacion de cada tarea del plan (S4).
  security-reviewer ADEMAS de code-reviewer en la T4.9, nunca en su lugar.
  Usa tambien a11y-architect: en esta tanda encontro DOS CRITICAL y TRES HIGH
  que el code-reviewer no vio, y viceversa. Los dos gates juntos, siempre.
- Respaldo ANTES del cambio, en docs/auditoria/respaldos/<fecha>/, confirmado
  en disco con tamano > 0.
- Nada se borra: se aparta al respaldo fechado.
- Datos de clientes enmascarados. Credenciales por nombre de variable y
  archivo:linea, NUNCA por valor.
- Commits convencionales en espanol, en ASCII, terminando con:
  Co-authored-by: LUIS V <luisht3g@gmail.com>

=== AL CERRAR ===

Actualiza la tabla PROGRESO del plan (S8), el marcador global del indice (S6)
y el baseline de CLAUDE.md, con evidencia (commit/test/PR) y fecha. Escribe la
evidencia en docs/diseno/. El PR #43 YA EXISTE: empuja a la rama y se
actualiza solo. NO abras otro. Mergea con --squash SOLO si los gates estan
verdes y el owner lo autorizo.
```
