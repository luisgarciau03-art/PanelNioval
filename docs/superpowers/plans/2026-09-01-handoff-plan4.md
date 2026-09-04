# Handoff — Plan 4, sesión nueva

**Fecha:** 2026-09-01 · **Estado:** Plan 4 en 5/12 · **PR #43 abierto, CI verde**

Mensaje listo para pegar al arrancar la sesión siguiente. Todo lo de aquí está
verificado en disco el 2026-09-01, no copiado de documentos previos.

---

```
Continua los planes de trabajo de PanelNioval. Toca el Plan 4, tarea T4.5.

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
   Su seccion 0 de validacion MANDA sobre los numeros de linea del resto,
   pero OJO: la §0 tambien se equivoco midiendo (ver abajo).
4. docs/adr/2026-08-31-direccion-visual-panel.md  <- la direccion ya esta
   decidida y la paleta accesible calculada. No la vuelvas a abrir.
5. docs/diseno/2026-08-31-auditoria-y-adn-marca.md  <- el estado de partida
   medido, con los contrastes reales.
6. docs/superpowers/plans/2026-08-27-indice-tanda.md  <- marcador global (S6),
   gates del owner (S7.1), decisiones resueltas (S7.2) y pendientes (S8).
7. Memoria: claude-mem (mem-search) y el MEMORY.md del proyecto.

=== ESTADO AL 2026-09-01 ===

MARCADOR GLOBAL: 38/53 tareas (72 %). 4 de 6 planes cerrados.

  Plan 3 - Bug de conteo y pantallas de carga   10/10 OK  PR #36  ae0e1c9
  Plan 0 - Integracion continua                   4/4 OK  PR #40  c10d063
  Plan 2 - Gasto de Google Places                 9/9 OK  PR #38  4e06e64
  Plan 1 - Relevancia de ciudades               10/10 OK  PR #42  SIN MERGEAR
  Plan 4 - Rediseno del panel                    5/12     <- ESTE
  Plan 5 - Endurecimiento                         0/8

Plan 4, hecho:
  T4.0 evidencia del antes          b5ff47d
  T4.1 auditoria y ADN de marca     b5ff47d
  T4.2 direccion visual + ADR       1c3665d   (metodo: skill council)
  T4.3 HTML fuera de app.py         d86323f   app.py 6,368 -> 3,133 lineas
  T4.4 tokens y componentes         211a70e + 43ba0e8

Plan 4, pendiente:
  T4.5 esqueletos de carga     <- SIGUIENTE
  T4.6 sistema de movimiento
  T4.7 rediseno del dashboard
  T4.8 rediseno del formulario
  T4.9 rediseno del importador
  T4.10 accesibilidad, responsive y rendimiento
  T4.11 cierre

*** DOS PRs ABIERTOS Y APILADOS ***

PR #43 (feat/rediseno-panel -> main): el Plan 4. MERGEABLE/CLEAN, CI verde.
PR #42 (feat/relevancia-ciudades-nacional -> main): el Plan 1, terminado.

#43 SALE DE la rama de #42, no de main, asi que ARRASTRA sus 8 commits.
Mergear el Plan 4 mergea tambien el Plan 1. Fue decision del owner el
2026-08-31, y por un motivo concreto: el Plan 1 toca 164 lineas DENTRO de
los dos literales HTML que la T4.3 saco de app.py, y git no puede
automergear un movimiento de archivo contra una edicion del mismo texto.

NO mergees ninguno por tu cuenta: el criterio CE10 del Plan 1 es un gate
humano del owner que sigue abierto, y main auto-despliega a produccion.

=== BASELINE, Y ES POR RAMA ===

  main                                388 passed, 1 skipped
  feat/relevancia-ciudades-nacional   482 passed, 1 skipped
  feat/rediseno-panel (esta)          564 passed, 1 skipped   <- tu gate

Comando oficial: python -m pytest tests/    <- SIN -q
pytest.ini ya trae addopts=-q; el segundo lo vuelve -qq y SUPRIME la linea
del resumen: se ven los puntos y exit 0, pero nunca el numero.

Compara contra 564, que es el baseline de ESTA rama. Un gate escrito con
el numero de main es inalcanzable aqui.

Nota: importar app.py en frio tarda 1-5 minutos. No es un cuelgue.

=== LO QUE YA ESTA DECIDIDO: NO LO REABRAS ===

Direccion visual (ADR 2026-08-31): editorial/Swiss disciplinado, UN solo
sistema con TRES registros:
  - /formulario  denso y quieto. La velocidad de captura manda sobre la
                 estetica; se usa hora tras hora. Movimiento minimo.
  - /            jerarquico. Contraste de escala fuerte.
  - /importador  narrativo. El movimiento cuenta el avance de la corrida.

Se descartaron bento (distorsiona 14 tablas densas) y profundidad real
(repaints con 606 chips contra el gate duro de CLS < 0.1).

Regla heredada del voto del Critico, que la T4.5 tiene que aplicar:
la celebracion (confeti, verde de exito, marcas de verificacion) queda
RESERVADA a estados verificados de forma explicita. Un estado que solo
puede afirmar "no recibi datos" no se viste de exito.

Tipografia: pila de sistema, sin fuente web, pero con cifras tabulares,
pila mono declarada y escala con saltos reales.

Paleta accesible ya calculada y en static/css/tokens.css.

=== EL SISTEMA DE DISENO YA EXISTE: USALO, NO LO REHAGAS ===

  static/css/tokens.css       unico sitio donde puede haber un color literal
  static/css/base.css         reset, tipografia, foco visible, .solo-lectores
  static/css/componentes.css  btn, tarjeta, chip, stat, insignia, campo,
                              tabla, progreso, consola - con sus 4 estados
  templates/{dashboard,formulario,importador}.html
  static/css/*.css y static/js/*.js por superficie

Convencion de color que NO puedes romper:
  --exito       pasa AA en los dos sentidos (4.54:1). Botones y texto.
  --exito-vivo  el #00CC47 de marca. Da 2.16:1. SOLO decoracion sin texto.
  Igual con --aviso/--aviso-vivo y --error/--error-vivo.

tests/test_plan4_tokens.py (57 tests) lo vigila: CE3 por archivo, ratios
declarados, pares color+fondo reales, tokens fantasma, colisiones de
nombre con el sistema, orden de la cascada y el anillo de foco.

=== DEUDA QUE LA T4.4 DEJA ANOTADA (no la ocultes, resuelvela) ===

1. Los componentes accesibles de componentes.css NO los usa ninguna
   plantilla todavia: cada superficie mantiene su version paralela. Los
   selectores [aria-invalid], [aria-pressed] y [aria-sort] que traen no
   alcanzan nada hasta que T4.7-T4.9 migren el marcado.
2. Chart.js anima por <canvas>, FUERA de la cascada CSS, asi que
   prefers-reduced-motion no lo toca. Hace falta matchMedia en JS: es T4.6.
   Son 6 instanciaciones new Chart(...) en static/js/dashboard.js.
3. CE3 queda en 31 literales, todos en static/js/dashboard.js y todos de
   las DOS paletas de datos: las series de Chart.js y el selector de color
   de fila del operador. Es el punto 3 de la T4.7.
4. Chart.js se carga desde jsdelivr SIN integrity (SRI). Preexistente.
   Deuda del Plan 5.

=== LO QUE T4.10 TIENE QUE ARREGLAR (medido, no estimado) ===

  12 div.nav-item con onclick   no alcanzables por teclado (SC 2.1.1)
  ~14 campos y 5+ select        sin nombre accesible (SC 1.3.1, 4.1.2)
  0 aria-live / role=status     el progreso y el guardado cambian en
                                silencio para un lector (SC 4.1.3)
  10 modales                    sin role=dialog, sin trampa de foco, solo
                                uno cierra con Escape
  input de subir comprobante    display:none lo saca del orden de tabulacion

=== CORRECCION AL PROPIO PLAN: MIDIO MAL ===

El plan dice que las tres superficies suman 5,067 lineas. Son 3,228. Midio
"del inicio de una constante al inicio de la siguiente", contando como HTML
el Python de en medio: 1,839 lineas de error.

Consecuencia viva: tras la T4.3 app.py quedo en 3,133 lineas, no en 1,031.
Ni CE1 (<800) ni su supuesto de rescate D1-A (<1,100) eran alcanzables
extrayendo solo HTML.

DECISION D6, ABIERTA, esperando al owner:
  A) (recomendada) mantener el alcance y reescribir CE1 como "app.py baja
     al menos un 45 % y ningun archivo nuevo supera 800 lineas".
  B) ampliar la T4.3 con el troceo del Python en modulos y conservar <800.
  Mientras no responda, se asume A.

=== GATES DEL OWNER ABIERTOS (reportalos, NO los intentes) ===

 1. Validar el top-20 de ciudades y decidir mercado-vs-cosecha (CE10 del
    Plan 1). Bloquea el merge de #42 y por tanto el de #43.
 2. Decidir D6 (arriba).
 3. Verificar la imagen Docker CONSTRUIDA de verdad. Docker no esta
    instalado en la maquina de desarrollo; solo se pudo afirmar que
    .dockerignore no excluye templates/ ni static/.
 4. Recorrido funcional en navegador: guardar una respuesta del formulario,
    ordenar una tabla del dashboard, arrancar una busqueda del importador.
 5. Activar la proteccion de rama en main. Sin ella el check de CI informa
    pero NO impide el merge.
 6. Rotar TELEGRAM_TOKEN, expuesto en el historial git (~14 copias). Es el
    riesgo abierto mas grande.
 7. Apagar el despliegue de Railway, vivo sin PANEL_DASHBOARD_TOKEN.
 8. Anadir a .env.example los nombres de las 5 variables de Places (bloque
    exacto en el indice, S7.1). El entorno bloquea escribir archivos .env*.
 9. Consumo por SKU de Places en la consola de Google Cloud.
10. Verificacion con gunicorn real en el VPS (no corre en Windows: fcntl).
11. Revisar el 2026-09-18 si el barrido de secretos pasa a --estricto (E1).
    ANTES hay que calibrarlo: ver trampa 8.

=== TRAMPAS QUE YA COSTARON TIEMPO ===

 1. Los archivos estan en CRLF EN DISCO, tambien los .py, asi que un
    reemplazo por patron escrito con \n NO CASA y devuelve el texto igual,
    SIN ERROR. Pero en GIT los blobs son 100 % LF, que es lo que reciben el
    runner de CI y el VPS. No confundas las dos cosas. Ya hay .gitattributes
    con `* text=auto` para que deje de depender de la config local.
 2. Los heredocs de bash fallan con contenido largo y se comen los escapes.
    Para escribir archivos usa Write; para parchear, Edit. Si usas python
    con heredoc, evita \n literales: usa chr(10).
 3. .gitignore cubre *.json y deja archivos de datos fuera del repo EN
    SILENCIO. Si anades uno, excepcion por ruta exacta y comprobar con
    `git check-ignore -v` en LAS DOS direcciones.
 4. `git add docs/` arrastra archivos de otro proyecto. Anade por ruta.
 5. Un test que pasa con y sin el arreglo no vale nada. Desactiva el guarda
    y confirma el rojo, SIEMPRE.
 6. NUNCA uses `git checkout <archivo>` para restaurar durante una prueba
    destructiva: revierte a HEAD y BORRA lo que aun no este commiteado. Me
    destruyo la migracion entera de importador.css. Haz la prueba sobre una
    COPIA.
 7. Medir en el momento equivocado da veredictos falsos. Corri la suite
    ANTES del `git add` y reporte verde; el guarda de PII solo mira archivos
    versionados, asi que todavia no podia verse a si mismo y estaba en rojo.
 8. Sustituir un color por prefijo rompe CSS en silencio: `#fff` es PREFIJO
    de `#fff3cd`, y quedo `background:var(--superficie)3cd`, que el parser
    descarta entero. Ningun test lo veia porque buscaban literales que
    empiezan por `#`. Ya hay guarda.
 9. El contraste depende del FONDO. --texto-suave da 4.76:1 sobre blanco y
    4.34:1 sobre --gris-100: el token estaba bien y el par estaba mal.
    Comprueba pares reales, no tokens sueltos.
10. Un anillo de foco de UN color no sirve: --azul daba 7.57:1 sobre blanco
    y 1.43:1 sobre el azul de la barra lateral. Ya es de dos tonos.
11. Un sistema que se aplica sobre marcado existente NO puede imponer color
    a un elemento que ya lo recibia del contexto. Fijar color en h1-h4 y en
    `a` dejo ilegibles el titulo de cabecera y los botones de Herramientas.
12. El barrido de secretos del Plan 0 solo ve telefonos con DIGITOS
    CONTIGUOS: la forma pegada si, pero las separadas por espacios, guiones
    o parentesis NO. Y el formato con espacios es el que usa la hoja.
    Ademas no distingue una fixture de una fuga: deja 13 falsos positivos
    fijos. Calibrarlo antes del --estricto del 2026-09-18.
13. El panel cae a un .json de credencial en la raiz si falta
    GOOGLE_CREDENTIALS_JSON. Para correrlo SIN datos hay que cortar las DOS
    vias y COMPROBAR que get_gs_client() lanza excepcion. Ya lo hace
    tools/capturar_superficies.py; usalo, no improvises.
14. No edites app.py ni el CSS mientras un reviewer los esta leyendo.

=== HERRAMIENTAS UTILES QUE YA EXISTEN ===

  python tools/capturar_superficies.py docs/diseno/<destino>
      levanta el panel y captura las 3 superficies en 320/768/1440,
      SIN credenciales (aborta si logra autenticarse).
  python tools/comparar_capturas.py <dir_antes> <dir_despues>
      comparacion pixel a pixel, con % de diferencia.
  python tools/barrer_secretos.py   (recibe un diff por stdin)

  Capturas del antes, versionadas: docs/diseno/antes/*.png (9)
  Capturas intermedias, en el respaldo fechado, NO versionadas:
    docs/auditoria/respaldos/2026-08-31/verificacion-t4{3,4}-capturas/

=== REGLAS ===

- Herramientas de la tabla de asignacion de cada tarea del plan (S4).
  python-reviewer ADEMAS de code-reviewer, nunca en su lugar. El Plan 4 es
  frontend: usa tambien a11y-architect, accessibility-tester, ui-designer y
  las skills de UI del catalogo. En esta tanda los reviewers encontraron 6
  defectos reales que la verificacion propia no vio: usalos de verdad.
- TDD donde el plan lo marque: tests primero, en rojo, comprobados en las
  dos direcciones.
- Respaldo ANTES del cambio, confirmado en disco con tamano > 0.
- Nada se borra: se aparta al respaldo fechado.
- Datos de clientes enmascarados (+52...XXXX). Credenciales por nombre de
  variable y archivo:linea, NUNCA por valor.
- Commits convencionales en espanol, en ASCII, terminando con:
  Co-authored-by: LUIS V <luisht3g@gmail.com>

=== AL CERRAR ===

Actualiza la tabla PROGRESO del plan (S8) y el marcador global del indice
(S6) con evidencia (commit/test/PR) y fecha. El PR #43 YA EXISTE: empuja a
la rama y se actualiza solo. NO abras otro. Mergea con --squash SOLO si los
gates estan verdes y el owner lo autorizo.
```
