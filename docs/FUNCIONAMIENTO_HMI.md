# Operator HMI — Celda de Remachado · I/O y funcionamiento

> Documento que explica **cómo funcionaría** la pantalla `OperatorHMI_RemachadoCell.svg`
> con la lista FINAL de señales. **Solo 14 inputs + 8 outputs.** No hay señales extra,
> no hay sensor fotoeléctrico de cámara, no se inventan tags.

---

## 1. Panel destino

- **Schneider Harmony ST6 · HMIST6200 · 4.3" Wide · 480 × 272 px** (resolución nativa).
- El SVG usa `viewBox="0 0 480 272"` 1:1 con el panel; `#screen_outline` es el contorno del área activa.

---

## 2. Estructura del SVG (para el integrador)

- **Elementos sueltos** (sin grupo contenedor): `#bg`, `#screen_outline`, `#title`, `#title_divider`, `#panel_inputs`/`#title_inputs`, `#panel_outputs`/`#title_outputs`.
- **Cada botón** = un grupo `#btn_*` (rect + texto). **Cada señal** = un grupo `#di_*` / `#do_*` (LED + etiqueta).
- Atributos de binding por elemento:

| Atributo | En | Significado |
|---|---|---|
| `data-element` | todos | `button` · `led-input` · `led-output` |
| `data-tag` | todos | tag PLC (`I_*`, `O_*`, `HMI.*`) para mapear a la señal real |
| `data-event` | botones | evento de operador que dispara (`START`, `STOP`, …) |
| `data-state` | LEDs | estado inicial mostrado (`on`/`off`) |
| `data-on-color` | LEDs | color cuando la señal está ACTIVA |

**Cómo se enciende/apaga un LED:** el motor del HMI cambia el `fill` del círculo `#<id>_led`:
- **OFF** → `#40566F` (gris azulado).
- **ON** → el valor de `data-on-color` de ese LED.

**Cómo cambia un botón:** cambiar el `fill` del `#btn_*_rect` (p. ej. resaltar el botón activo).

---

## 3. DIGITAL INPUTS booleanos (7 LEDs) — lo que la celda LEE

Los inputs booleanos se muestran como **LEDs** (recompactados a la izquierda). La cámara NO es LED: va en el apartado de texto (§3b).

| # | Tag (`data-tag`) | id grupo | Etiqueta | Qué indica | Fuente | ON cuando |
|---|---|---|---|---|---|---|
| 1 | `I_CONVEYOR_PHOTOEYE` | `di_conveyor_photoeye` | Conveyor | Hay CAFI en la posición de pick del conveyor | PLC/Gateway | sensor fotoeléctrico bloqueado |
| 2 | `I_FIXTURE_1_PRESENT` | `di_fixture_1_present` | Fixture 1 | CAFI dentro del fixture 1 de la mesa | PLC (limit switch) | pieza presente |
| 3 | `I_FIXTURE_2_PRESENT` | `di_fixture_2_present` | Fixture 2 | CAFI dentro del fixture 2 de la mesa | PLC (limit switch) | pieza presente |
| 4 | `I_COBOT_MOVING` | `di_cobot_moving` | Cobot Mov | Cobot en movimiento | **Cobot (WS)** | algún joint con velocidad |
| 5 | `I_COBOT_READY` | `di_cobot_ready` | Cobot Rdy | Cobot listo | **Cobot (WS)** | robot habilitado/inpos |
| 6 | `I_GRIPPER_OPEN` | `di_gripper_open` | Grip Open | Confirma gripper abierto | PLC (sensor) | gripper abierto |
| 7 | `I_GRIPPER_CLOSED` | `di_gripper_closed` | Grip Clsd | Confirma gripper cerrado | PLC (sensor) | gripper cerrado |

> **Table HOME/WORK quitados de la pantalla:** `I_TABLE_HOME_LIMIT` y `I_TABLE_WORK_LIMIT`
> **siguen siendo señales reales** que usa la lógica (posición de la mesa, faults), pero **no se
> muestran** en esta pantalla de operador (se quitaron para limpiar el panel; la actividad del
> disco se ve con el output **Disco**).
>
> **No incluido a propósito:** sensor fotoeléctrico de cámara, presión de aire,
> E-stop/Stop como inputs del bloque. (E-stop sigue siendo seguridad del PLC físico.)

## 3b. CÁMARA — apartado de TEXTO (no es indicador LED)

La cámara **envía un texto/resultado**, así que en el HMI va como un **apartado "CAMERA:"**
con el estado en texto, NO como LEDs. Elemento: `#camera_status` (`data-element="text-readout"`,
`data-tag="CAMERA_STATUS"`); el valor se escribe en `#camera_status_value`.

| Estado (texto) | Equivale a | Significado | Color sugerido del texto |
|---|---|---|---|
| `READY` | I_CAMERA_READY | Cámara lista para inspeccionar | azul `#6FA8FF` |
| `PASS` | I_CAMERA_PASS | CAFI aceptado | verde `#22FF66` |
| `FAIL` | I_CAMERA_FAIL | CAFI rechazado | rojo `#FF5566` |
| `NO_READ` | I_CAMERA_NO_READ | No dio resultado válido | ámbar `#FBBF24` |
| `ERROR` | I_CAMERA_ERROR | Error de cámara/comunicación | rojo `#FF5566` |

**Binding:** el motor del HMI escribe en `#camera_status_value` el texto que manda la
cámara (`data-states="READY|PASS|FAIL|NO_READ|ERROR"`) y, si se quiere, cambia su `fill`
según el estado. Mapea a las señales `I_CAMERA_*` (ninguna señal nueva inventada).

---

## 4. DIGITAL OUTPUTS (8) — lo que la celda COMANDA

Los 5 outputs de proceso van como **LEDs**; los 3 `O_STACKLIGHT_*` van como **SEMÁFORO** (§4b).

| # | Tag (`data-tag`) | id grupo | Etiqueta | Qué hace | ON cuando | `data-on-color` |
|---|---|---|---|---|---|---|
| 1 | `O_GRIPPER_OFF` | `do_gripper_off` | Grip Off | Apaga ambas salidas del gripper (válvula off) | gripper desenergizado | verde `#22FF66` |
| 2 | `O_CONVEYOR_MOTOR` | `do_conveyor_motor` | Conv Motor | Enciende/apaga el motor del conveyor | motor encendido | verde `#22FF66` |
| 3 | `O_CAMERA_TRIGGER` | `do_camera_trigger` | Cam Trig | Dispara la inspección de la cámara | pulso de trigger | azul `#3B8BFF` |
| 4 | `O_TABLE_NEMA_MOVING` | `do_table_nema_moving` | Disco | Disco/NEMA en movimiento | mesa indexando | azul `#3B8BFF` |
| 5 | `O_RIVET_ACTIVE` | `do_rivet_active` | Rivet | Remachado activo | remachando (30 s) | naranja `#F97316` |

## 4b. STACKLIGHT — SEMÁFORO (torreta) al costado

Las 3 salidas de la torreta se muestran como un **semáforo vertical** (housing oscuro
`#stacklight_housing` + 3 lámparas), no como LEDs sueltos. Orden estándar: **rojo arriba,
ámbar en medio, verde abajo**. Cada lámpara conserva su grupo y tag:

| Tag (`data-tag`) | id grupo / LED | Luz | ON cuando | `data-on-color` |
|---|---|---|---|---|
| `O_STACKLIGHT_RED` | `do_stacklight_red` / `_led` | 🔴 arriba | FAULT / stop / emergencia | `#FF3B3B` |
| `O_STACKLIGHT_YELLOW` | `do_stacklight_yellow` / `_led` | 🟡 medio | warning / espera / pausa | `#FBBF24` |
| `O_STACKLIGHT_GREEN` | `do_stacklight_green` / `_led` | 🟢 abajo | RUNNING nominal | `#22FF66` |

Normalmente **exclusivas** (una encendida a la vez). Apagadas en gris `#40566F`.

## 4c. CONTADORES DE PRODUCCIÓN (CAFI) — panel "PRODUCCIÓN"

Panel `#panel_counts` (arriba a la derecha, junto al semáforo) con tres contadores. El motor
del HMI escribe el número en el `<text id="*_value">`; el resto es etiqueta fija.

| Contador | id grupo / valor | `data-tag` | Color | Origen |
|---|---|---|---|---|
| **Total** | `count_total` / `#count_total_value` | `COUNT.total` | blanco `#DDEEFF` | aceptados + rechazados |
| **Aceptados** | `count_accepted` / `#count_accepted_value` | `COUNT.accepted` | verde `#22FF66` | CAFIs a bin ACCEPTED (cámara PASS) |
| **Rechazados** | `count_rejected` / `#count_rejected_value` | `COUNT.rejected` | rojo `#FF5566` | CAFIs a bin REJECTED (cámara FAIL) |

- Mapea a los conteos de producción de la celda (`CountsSnapshot.accepted` / `.rejected`; total = suma).
- **RESET** pone los tres a 0; **STOP/PAUSE** los conserva (no se borran).
- Inicial en el SVG = `0 / 0 / 0` (real-only: se llenan con datos del ciclo).

---

## 5. Botones de operador (HMI)

| Tag (`data-tag`) | id grupo | Evento (`data-event`) | Acción |
|---|---|---|---|
| `HMI.START` | `btn_start` | `START` | Arranca el ciclo (RUNNING) |
| `HMI.STOP` | `btn_stop` | `STOP` | Pausa (conserva estado/conteos) |
| `HMI.RESUME` | `btn_resume` | `RESUME` | Reanuda desde pausa |
| `HMI.RESTART` | `btn_restart` | `RESTART` | Reinicio/recuperación |
| `HMI.CONFIRM_CLEAN` | `btn_confirmar_limpieza` | `CONFIRM_CLEAN` | Confirma limpieza manual |
| `HMI.FINALIZE` | `btn_finalizar` | `FINALIZE` | Finaliza: drena → HOME → IDLE |

> **COLOCAR CAFI se eliminó:** la carga de la pieza es **física**; el operador solo
> presiona **START** y la celda alimenta sola. Layout: 2 columnas × 3 filas.
> Los botones son comandos de operador, **no** forman parte de la lista de I/O.

---

## 6. Cómo funcionaría en vivo (flujo de datos)

```
PLC / Gateway (RPi)  ──telemetry.io──►  HMI / SCADA  ──fill del LED──►  pantalla
Cobot (WS)           ──telemetría───►  (I_COBOT_MOVING, I_COBOT_READY)
Operador (touch)     ──data-event──►   comando de ciclo/actuador
```

1. El gateway publica el bloque `io` con **exactamente** estas 14 entradas + 8 salidas.
2. El motor del HMI/SCADA, por cada señal:
   - Busca el LED por su `data-tag`.
   - Si la señal llega y está activa → `fill = data-on-color`; si inactiva → `fill = #40566F`.
3. Los botones, al tocarlos, emiten su `data-event` hacia la lógica de ciclo (FSM/gateway).

### Frescura (igual que SCADA real-only)
- Señal fresca = **REAL** (se muestra con su color).
- Señal que dejó de actualizar (> ~3 s) = **STALE** (recomendado: parpadeo o atenuar).
- Señal que nunca llega = **NOT_CONNECTED** (LED en gris `#40566F`, "no disponible").

### Qué es REAL hoy vs pendiente
- **REAL hoy** (si el cobot está conectado por WS): `I_COBOT_MOVING`, `I_COBOT_READY`.
- **PENDIENTE** (el gateway aún no publica `io`): el resto de inputs PLC/cámara y **todos** los outputs.
  Hasta que el gateway los exponga, esos LEDs van en `NOT_CONNECTED` (gris). En **modo DEMO** se pueden animar, marcados como demo.

---

## 7. Relación con la lógica de la celda (qué enciende cada output)

- `O_CONVEYOR_MOTOR` ON mientras la banda avanza; OFF al detectar CAFI en `I_CONVEYOR_PHOTOEYE` o tras pick (espera ~2 s).
- `O_TABLE_NEMA_MOVING` ON durante el giro HOME↔WORK; OFF al activarse `I_TABLE_HOME_LIMIT` o `I_TABLE_WORK_LIMIT`.
- `O_RIVET_ACTIVE` ON durante el dwell de remachado (**30 s exactos**) con la mesa en WORK; nunca gira la mesa mientras está ON.
- `O_CAMERA_TRIGGER` pulso tras `PLACE_VISION`; el resultado llega por `I_CAMERA_PASS` / `I_CAMERA_FAIL` / `I_CAMERA_NO_READ` (timeout 3 s → no-read/`I_CAMERA_ERROR`).
- `O_GRIPPER_OFF` desenergiza la válvula; los confirmadores son `I_GRIPPER_OPEN` / `I_GRIPPER_CLOSED`.
- **Stacklight**: `O_STACKLIGHT_GREEN` = RUNNING nominal · `O_STACKLIGHT_YELLOW` = warning/pausa · `O_STACKLIGHT_RED` = fault/stop/emergencia (exclusivos entre sí).

---

## 8. Reglas

- **Usar SOLO estas 14 + 8 señales.** No agregar más, no reintroducir el fotoeléctrico de cámara, no inventar tags.
- Los `data-tag` (`I_*` / `O_*`) son el contrato: el gateway debe mandar exactamente esos nombres (o mapearlos).
- Colores **solo para estado**; en reposo todo gris `#40566F`.
- Este documento es de diseño/integración: **no** cambia código de la app (HMI/SCADA/FSM intactos en esta entrega; solo se actualizó el SVG).
