# Handoff — Plan 4 cerrado, siguiente el Plan 5

**Fecha:** 2026-09-03 · **Estado:** Plan 4 en **12/12** · **PR #43 abierto, CI verde**

Mensaje listo para pegar al arrancar la sesión siguiente. Todo lo de aquí está verificado en
disco el 2026-09-03, no copiado de documentos previos.

---

```
Continua los planes de trabajo de PanelNioval. Toca el Plan 5, tarea T5.0.

PROYECTO: C:\Users\PC 1\PanelNioval
RAMA ACTUAL: feat/rediseno-panel (Plan 4, TERMINADO). El Plan 5 abre RAMA NUEVA.
NUNCA main: Railway y Vultr auto-despliegan desde ahi.

LEE EN ESTE ORDEN ANTES DE TOCAR CODIGO:
1. C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md  <- 653 herramientas
   (229 agentes + 424 skills), 6 fuentes. Confirma que la leiste citando el
   total. Superpowers aporta 14 de 653: si el plan usa solo Superpowers, esta
   mal disenado por definicion.
2. C:\Users\PC 1\PanelNioval\CLAUDE.md
3. docs/superpowers/plans/2026-08-28-plan5-endurecimiento-panel.md
   Su seccion 1 trae los cinco huecos CON EVIDENCIA MEDIDA. Empieza por ahi.
4. docs/diseno/sistema.md  <- NUEVO. El sistema de diseno del panel: tokens,
   componentes, los cuatro estados, movimiento, accesibilidad, rendimiento y
   las OCHO herramientas de verificacion. Leelo aunque el Plan 5 sea de
   backend: si tocas una plantilla, las reglas de ahi aplican.
5. docs/superpowers/plans/2026-08-27-indice-tanda.md  <- marcador global (S6),
   gates del owner (S7.1), decisiones resueltas (S7.2) y pendientes (S8).
6. Memoria del proyecto: MEMORY.md de
   C:\Users\PC 1\.claude\projects\c--Users-PC-1-PanelNioval\memory\
   (10 entradas; las tres ultimas son del Plan 4 y cada una evita un error
   que ya costo tiempo).

=== ESTADO AL 2026-09-03 ===

MARCADOR GLOBAL: 45/53 tareas (85 %). 5 de 6 planes cerrados.

  Plan 3 - Bug de conteo y pantallas de carga   10/10 OK  PR #36  ae0e1c9
  Plan 0 - Integracion continua                   4/4 OK  PR #40  c10d063
  Plan 2 - Gasto de Google Places                 9/9 OK  PR #38  4e06e64
  Plan 1 - Relevancia de ciudades               10/10 OK  PR #42  SIN MERGEAR
  Plan 4 - Rediseno del panel                   12/12 OK  PR #43  SIN MERGEAR
  Plan 5 - Endurecimiento                         0/8     <- ESTE

Plan 5, las ocho tareas:
  T5.0 rama, respaldo y baseline (bloquea todo)
  T5.1 rate limiting en todas las rutas          (M5)
  T5.2 escapado de formulas al escribir en Sheets (M14)
  T5.3 zona horaria explicita                     (M2)
  T5.4 healthcheck del contenedor                 (M9)
  T5.5 cierre ordenado del hilo del importador    (M3)
  T5.6 verificacion integral
  T5.7 cierre

*** DOS PRs ABIERTOS Y APILADOS ***

PR #43 (feat/rediseno-panel -> main): el Plan 4. CI verde.
PR #42 (feat/relevancia-ciudades-nacional -> main): el Plan 1.

#43 SALE DE la rama de #42, asi que ARRASTRA sus commits. Mergear el Plan 4
mergea tambien el Plan 1. Fue decision del owner el 2026-08-31.

NO mergees ninguno por tu cuenta: el criterio CE10 del Plan 1 es un gate humano
del owner que sigue abierto, y main auto-despliega a produccion.

DE DONDE SALE LA RAMA DEL PLAN 5: decidelo con el owner. El Plan 5 toca app.py
(rate limiting, escapado, zona horaria) y el Dockerfile, no las superficies, asi
que sale limpio de main; pero si sale de main, su baseline es 388 y no 900. Ver
el bloque de baseline.

=== BASELINE, Y ES POR RAMA ===

  main                                388 passed, 1 skipped
  feat/relevancia-ciudades-nacional   482 passed, 1 skipped
  feat/rediseno-panel (Plan 4)        900 passed, 2 skipped   <- hoy

Comando oficial: python -m pytest tests/    <- SIN -q
pytest.ini ya trae addopts=-q; el segundo lo vuelve -qq y SUPRIME la linea del
resumen: se ven los puntos y exit 0, pero nunca el numero.

Un gate escrito como ">= 900" es inalcanzable desde una rama basada en main.
Compara SIEMPRE contra el baseline de tu rama base.

Nota: importar app.py en frio tarda 1-5 minutos. No es un cuelgue.

=== LAS OCHO HERRAMIENTAS DE VERIFICACION — USALAS ===

Ninguna es opcional y todas estan comprobadas EN LAS DOS DIRECCIONES: se
reintroduce el defecto y se ve salir. Corre las que toque tu tarea ANTES de dar
nada por terminado.

  python tools/verificar_accesibilidad.py [--detalle]  contraste efectivo,
        teclado, foco, etiquetas, landmarks, dialogos, objetivos y desborde en
        5 anchos, RECORRIENDO los estados (14 secciones + 7 dialogos)
  python tools/verificar_estados.py       5 comprobaciones
  python tools/verificar_movimiento.py   13 comprobaciones
  python tools/verificar_tablero.py      24 comprobaciones
  python tools/verificar_formulario.py   12 comprobaciones
  python tools/verificar_importador.py   45 comprobaciones
  python tools/medir_cls.py [--detalle]  CLS de las 3 superficies, red lenta
  python tools/medir_presupuesto.py      bytes por tipo, terceros, LCP
  python tools/capturar_superficies.py <dir> [--sinteticos]   5 anchos
  python tools/capturar_estados.py <dir> · capturar_importador.py <dir>
  python tools/comparar_capturas.py <antes> <despues>
  python tools/barrer_secretos.py   (recibe un diff por stdin)

Todos arrancan la app SIN credenciales de Google y lo COMPRUEBAN en la direccion
util (que el cliente falla). Ninguno llama a APIs de pago.

=== LO QUE EL PLAN 4 DEJO Y NO HAY QUE DESHACER ===

El sistema de diseno esta documentado en docs/diseno/sistema.md. Lo esencial:

  static/css/tokens.css       UNICO sitio con un color literal. CE3 = 0.
  static/css/base.css         reset, tipografia, foco de dos tonos, [hidden]
  static/css/componentes.css  btn, tarjeta, chip, stat, insignia, campo, tabla,
                              progreso, consola + los 4 estados + movimiento
  static/js/estados.js        Estados.esqueleto/vacio/error/parcial/escapar
  static/js/dialogo.js        foco, retencion y Escape de los 7 dialogos
  static/js/vendor/           Chart.js auto-hospedado (venia de un CDN que
                              tardo 15.1 s en responder al medirlo)

Tres reglas que ningun grep detecta y que ya han mordido:

  1. La OPACIDAD rompe el contraste sin tocar el color. Un token valido con
     opacity:.55 da 2.97:1 y pasa el guarda de "cero colores literales".
     Cuatro veces en el Plan 4.
  2. Un par que pasa sobre BLANCO puede no pasar sobre un TINTE. --exito da
     4.54:1 sobre blanco y 4.13:1 sobre --azul-tenue-2, que es el fondo de la
     mitad de las filas de todas las tablas.
  3. Un test que busca el patron prohibido en el ARCHIVO ENTERO lo encuentra en
     el comentario que explica por que se retiro. Ocho veces en esta tanda.

=== GATES DEL OWNER ABIERTOS (reportalos, NO los intentes) ===

 1. Validar el top-20 de ciudades y decidir mercado-vs-cosecha (CE10 del
    Plan 1). Bloquea el merge de #42 y por tanto el de #43.
 2. Decidir D6: CE1 pedia app.py < 800 lineas y son 3,170. Opcion A
    (recomendada): reescribir CE1 como "app.py baja al menos un 45 % y ningun
    archivo NUEVO supera 800 lineas" — que se cumple. Opcion B: trocear el
    Python en modulos. Afecta tambien a dashboard.js (1,920) e importador.js
    (948).
 3. Recorrido funcional en navegador por parte del owner sobre datos reales.
 4. Recorrido con LECTOR DE PANTALLA real (NVDA/JAWS/VoiceOver). La lista de
    que escuchar y donde esta en
    docs/diseno/2026-09-03-accesibilidad-responsive-t410.md, seccion 8.
    Ninguna herramienta automatica cierra esto.
 5. Verificar la imagen Docker CONSTRUIDA de verdad (Docker no esta instalado
    en la maquina de desarrollo).
 6. Activar la proteccion de rama en main. Sin ella el check de CI informa pero
    NO impide el merge.
 7. Rotar TELEGRAM_TOKEN, expuesto en el historial git. Es el riesgo abierto
    mas grande, y el Plan 5 T5.3 lo toca.
 8. Apagar el despliegue de Railway, vivo sin PANEL_DASHBOARD_TOKEN.
 9. Anadir a .env.example los nombres de las 5 variables de Places (bloque
    exacto en el indice, S7.1). El entorno bloquea escribir archivos .env*.
10. Consumo por SKU de Places en la consola de Google Cloud.
11. Verificacion con gunicorn real en el VPS (no corre en Windows: fcntl).
12. Revisar el 2026-09-18 si el barrido de secretos pasa a --estricto (E1).

=== TRAMPAS QUE YA COSTARON TIEMPO ===

 1. Los archivos estan en CRLF EN DISCO, tambien los .py, asi que un reemplazo
    por patron escrito con \n NO CASA y devuelve el texto igual, SIN ERROR. En
    GIT los blobs son LF. No confundas las dos cosas.
 2. read_bytes().decode() seguido de write_text() DUPLICA los retornos de carro
    (\r\r\n). Usa read_text+write_text (traducen en los dos sentidos) o
    read_bytes+write_bytes (no traducen en ninguno), nunca uno de cada. Y
    comprueba contando bytes, no de vista.
 3. Los heredocs de bash se comen los escapes. Para escribir archivos usa Write;
    para parchear, Edit o un script con read_text/write_text que AFIRME que el
    patron caso. Un replace que no casa devuelve el texto igual y no se queja.
 4. Un caracter de control escrito literal en el fuente vuelve el archivo
    "binario" para grep, que entonces SUPRIME coincidencias sin avisar — o sea
    invisible para tools/barrer_secretos.py. Los escapes van como escapes.
    Hay guarda en tests/test_plan4_importador.py.
 5. Un test que busca el patron prohibido en el archivo ENTERO lo encuentra en
    su propio comentario. Quita comentarios antes de afirmar "no queda ninguno".
 6. .gitignore cubre *.json y docs/auditoria/respaldos/. Comprueba con
    `git check-ignore -v` en LAS DOS direcciones.
 7. `git add docs/` arrastra archivos de otro proyecto. Anade por ruta.
 8. Un test que pasa con y sin el arreglo no vale nada. Desactiva el guarda y
    confirma el rojo, SIEMPRE. Vale igual para los arneses.
 9. NUNCA uses `git checkout <archivo>` para restaurar durante una prueba
    destructiva: revierte a HEAD y BORRA lo no commiteado. Copia al scratchpad
    y restaura desde ahi, verificando por hash.
10. En este entorno `git diff` abre un pager y CUELGA a los subagentes. Usa
    `git --no-pager diff`, y vuelca el diff a un archivo para que el reviewer
    lo lea con Read.
11. Playwright evalua las rutas de la ULTIMA a la primera. Registra la generica
    ANTES y la especifica DESPUES.
12. getBoundingClientRect() incluye la transformacion; para el ancho de LAYOUT
    usa offsetWidth.
13. Comprobar una CLASE no prueba que el arbol del DOM este bien. Comprueba
    tambien parentElement y offsetParent.
14. El barrido de secretos solo ve telefonos con DIGITOS CONTIGUOS. Si
    necesitas un numero de prueba, usa la marca `barrido-ok: <motivo>` que el
    proyecto define — NO compongas la cadena para esquivar el regex.
15. El panel cae a un .json de credencial en la raiz si falta
    GOOGLE_CREDENTIALS_JSON. Para correrlo SIN datos hay que cortar las DOS
    vias y COMPROBAR que get_gs_client() lanza excepcion.
16. La consola de Windows es cp1252 y revienta al imprimir caracteres que no
    existen ahi — y se lleva por delante lo que fuera despues, como escribir un
    JSON. En los scripts:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace").
17. No edites archivos mientras un reviewer los esta leyendo.
18. Un arnes que audita UN SOLO ESTADO da un cero falso. El de accesibilidad
    daba 0 mirando la seccion inicial; recorriendo las 14 secciones y los 7
    dialogos aparecieron 36 hallazgos. Si anades una pantalla o un modal,
    asegurate de que el auditor lo visita.

=== REGLAS ===

- Herramientas de la tabla de asignacion de cada tarea del plan (S4). En el
  Plan 5 manda `security-reviewer`, y va SIEMPRE junto a `code-reviewer` y
  `python-reviewer`, nunca en su lugar.
- Respaldo ANTES del cambio, en docs/auditoria/respaldos/<fecha>/, confirmado en
  disco con tamano > 0.
- Nada se borra: se aparta al respaldo fechado.
- Datos de clientes enmascarados. Credenciales por nombre de variable y
  archivo:linea, NUNCA por valor.
- Commits convencionales en espanol, en ASCII, terminando con:
  Co-authored-by: LUIS V <luisht3g@gmail.com>

=== AL CERRAR ===

Actualiza la tabla PROGRESO del plan, el marcador global del indice (S6) y el
baseline de CLAUDE.md, con evidencia (commit/test/PR) y fecha. Escribe la
evidencia en docs/. Abre PR con `gh pr create --base main`. Mergea con --squash
SOLO si los gates estan verdes y el owner lo autorizo.
```
