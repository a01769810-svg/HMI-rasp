# Librerías para la HMI exacta + Comunicación Modbus TCP

> Investigación técnica para trabajar el HMI real de la celda y comunicarlo por
> Modbus TCP. Aterrizado en el panel exacto del proyecto y en la tooling de este repo.
> (Fuentes al final.)

---

## PARTE A — El HMI exacto: Schneider Harmony **HMIST6400**

### A.1 Especificaciones del panel (modelo de la tooling de deploy / pcap)
| | |
|---|---|
| Familia | **Harmony ST6** (HMIST6400) |
| Pantalla | **7" Wide, 800 × 480 px (WVGA)**, 16M colores, táctil **resistiva** (single-touch) |
| CPU / Memoria | ARM **Cortex-A8 @ 800 MHz** · 1 GB device · 128 MB user data · 512 KB backup |
| Comunicaciones | **2× Ethernet**, **COM1 (RS-232C)**, **COM2 (RS-485)**, USB 2.0 host (Type A) + device (Micro-B) |
| Alimentación | 24 V DC ±20% |
| Software de autoría | **EcoStruxure Operator Terminal Expert (OTE)** |

> ⚠️ **Discrepancia de modelo a confirmar:** la tooling/pcap de deploy apunta a **HMIST6400 (7", 800×480)**, pero la maqueta `OperatorHMI_RemachadoCell.svg` se dimensionó a **480×272 (HMIST6200, 4.3" wide)**. Verificar cuál es el panel físico real y ajustar la maqueta a su resolución nativa (la HMI escala, pero conviene 1:1).

### A.2 "Librerías" / entorno para programar la HMI
El HMI **no** se programa con librerías open-source tipo npm/pip: se programa con la
herramienta propietaria **EcoStruxure Operator Terminal Expert (OTE)** en Windows, y la
pantalla se compone con sus widgets + scripts. Lo "programable" es:

1. **Lenguajes de script de OTE** (para lógica en pantalla / eventos):
   - **Block Script** (editor por bloques de Schneider),
   - **JavaScript**,
   - **LUA Plus** (Lua extendido). → El paquete del proyecto guarda las pantallas
     **compiladas como `Panel0.luac`** (Lua 5.1 compilado, `luac5.1 -s armhf`). O sea el
     runtime de la HMI ejecuta **Lua**.
   - Variables/tags se asocian a los objetos (switches, lamps, data displays). El ID de
     pantalla activa se lee/escribe con `$Target.Target01.Preferences.ScreenID` (útil para
     que el PLC cambie de pantalla o sepa cuál está activa).
2. **Lua 5.1 (estándar)** dentro de los scripts: librerías base de Lua (`string`, `table`,
   `math`, etc.) según lo que exponga el sandbox de OTE.
3. **Tooling de build/upload de ESTE repo** (Python 3, para automatizar sin la GUI):
   - `scripts/build_vml_green.py` — reemplaza `Panel0.luac` dentro del `.VML` + recalcula md5 + actualiza el manifest `xfile`.
   - `scripts/hmi_protocol.py` + `scripts/hmi_uploader.py` — protocolo OTE↔HMI (puertos **3320/3321/8050**, 6 fases) reverse-engineered del pcap. Sin dependencias raras (socket/hashlib/struct).
   - Ver `docs/FLUJO_SUBIDA_HMI_REAL.md`.

### A.3 Formato del paquete `.VML` (no `.bml`)
Contenedor binario por bloques. Dentro: `application/Screens/Panel0.luac` (pantalla),
`application/xfile` (manifest CSV `,ruta,size,md5`), `application/project.xml`, fonts,
idiomas, `NetworkSettings.ini`, DBs. El parser está en `build_vml_green.py`.

### A.4 Cómo el HMI obtiene los datos (drivers)
OTE conecta a PLCs/equipos con **drivers de comunicación** configurables (no requiere
escribir el protocolo a mano). Para el digital twin hay 2 caminos:
- **A)** El HMI lee **directo** del PLC/gateway por su **driver Modbus TCP Master** (ver Parte B.4).
- **B)** El **gateway RPi** hace de puente (lee el cobot/PLC por Modbus y publica), y el HMI
  consume del PLC. (Hoy el twin web usa el gateway RPi por WebSocket; el HMI físico usaría su
  driver nativo Modbus contra el PLC de la celda.)

---

## PARTE B — Comunicación Modbus TCP

### B.1 El protocolo (resumen operativo)
- **Transporte:** TCP, puerto **502** (estándar). *El cobot Lexium del proyecto está en `10.5.5.100:6502`.*
- **MBAP header (7 bytes)** + PDU:
  - `Transaction ID` (2B), `Protocol ID` (2B, =0), `Length` (2B), `Unit ID` (1B) + `Function Code` (1B) + datos.
- **Modelo de datos** (4 espacios):
  | Tipo | Acceso | Tamaño | Función lectura | Función escritura |
  |---|---|---|---|---|
  | Coils | R/W | 1 bit | FC01 | FC05 (single) / FC15 (multi) |
  | Discrete Inputs | R | 1 bit | FC02 | — |
  | Holding Registers | R/W | 16 bit | **FC03** | FC06 (single) / **FC16** (multi) |
  | Input Registers | R | 16 bit | **FC04** | — |
- **Function codes clave:** FC01 read coils · FC02 read discrete inputs · **FC03 read holding** · **FC04 read input** · FC05 write coil · FC06 write register · FC15 write coils · **FC16 write multiple registers** · FC23 read/write múltiple.
- **Direccionamiento:** la notación "4xxxx" (p.ej. 40001) es 1-based de documentación; en código casi todas las librerías usan **0-based** (40001 → address 0). Cuidado con el offset ±1.
- **Excepciones:** 0x01 Illegal Function, 0x02 Illegal Data Address, 0x03 Illegal Data Value, 0x04 Slave Device Failure, etc.

### B.2 Librería recomendada en Python (gateway RPi): **pymodbus 3.x**
Es la que ya usa el gateway (`cobot_reader.py`). API moderna y mantenida.

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("10.5.5.100", port=6502)   # host, puerto
client.connect()

# Leer 10 INPUT registers (FC04) desde la dirección 0, unidad/slave 1
rr = client.read_input_registers(address=0, count=10, slave=1)
if not rr.isError():
    print(rr.registers)        # lista de enteros 16-bit

# Leer HOLDING registers (FC03)
hr = client.read_holding_registers(address=454, count=8, slave=1)

# Escribir (si el equipo lo permite)
client.write_register(address=0, value=1234, slave=1)          # FC06
client.write_registers(address=10, values=[100, 200, 300], slave=1)  # FC16

client.close()
```
- `slave=` es el **Unit ID**. `result.registers` = lista de valores. Siempre validar `if not result.isError():`.
- Notación: pymodbus es **0-based** (holding 40001 → `address=0`).
- **Async** (para no bloquear el loop FastAPI): `from pymodbus.client import AsyncModbusTcpClient` + `await client.read_input_registers(...)`.
- **INT32 / floats:** muchos valores ocupan 2 registros → reconstruir con el orden de words/bytes correcto (big/little-endian); pymodbus trae helpers de decodificación. El cobot, por ejemplo, manda `motion_errcode` como INT32 (2 regs).
- **Alternativas Python:** `pyModbusTCP` (más liviana), `minimalmodbus` (RTU/serial).

### B.3 Otros lenguajes (referencia)
- **Node.js:** `modbus-serial` (TCP + RTU), `jsmodbus`.
- **C/C++:** `libmodbus`.
- **Diagnóstico:** `modpoll`, QModMaster, el `modbus_check.py` de este ecosistema.

### B.4 Modbus TCP **nativo del HMI** (EcoStruxure Operator Terminal Expert)
El HMIST6400 puede ser **maestro Modbus TCP** sin escribir código: se configura un driver.
Pasos en OTE 3.x:
1. En **Project Explorer → System Architecture → Target01 → Driver**, clic en **`+Driver`**.
2. En "Add Driver": **Manufacturer = Schneider Electric**, **Driver = Modbus TCP Master** → OK.
3. Aparece un equipo `SchneiderModbusTCPIPEquipment1`; en **Properties → Basic → Equipment Settings** pones la **IP del dispositivo** (PLC / gateway) y el puerto.
4. Creas **variables** y las mapeas a direcciones Modbus del equipo (coils/registers); luego las asocias a switches, lamparas, data displays, etc.
5. **Persistent vs Triggered requests:** el driver puede pollear continuamente (persistent) o solo bajo evento (triggered) — elegir según carga de red.
- Se pueden agregar **varios equipos** bajo un mismo driver Modbus TCP (límite según versión/SP).
- Alternativa Schneider: protocolo transparente **Machine Expert** (publicando símbolos en el PLC) en vez de Modbus directo.

### B.5 Mapa Modbus real del cobot (del gateway, `cobot_reader.py` / `CONTEXT_DIGITAL_TWIN.md`)
- Host **`10.5.5.100`**, puerto **`6502`**, **Unit ID 1**, lectura por **FC04 (input registers)**, read-only.
- Bloques leídos (rangos de registro aproximados, ver el código para el mapa exacto):
  - `status` (protective_stop, emergency_stop, power_on, robot_enabled, on_soft_limit, inpos, motion_mode, reduction_level) ≈ regs **454–461**.
  - `motion_errcode` (INT32), `speed_magnification_pct`, `controller` (temp/power/current).
  - `joint_states` (×6), `joint_positions_deg` (×6), `joint_speeds_deg_s` (×6), `joint_temperatures_c` (×6).
  - `tcp_position`, `tcp_speed`, `end_effector` (fuerza/par) ≈ regs **370–381**.
- Para **escribir comandos** al cobot, Schneider expone el control por su **SDK / OPC UA (EcoStruxure Cobot)**, no por estos registros FC04 (que son de monitoreo). Ver la API propuesta en `CONTEXT_DIGITAL_TWIN.md`.

---

## PARTE C — Cómo encaja con la celda (arquitectura)

```
PLC / I/O de celda ──Modbus TCP──┐
Cobot Lexium (10.5.5.100:6502) ──┤
                                 ├── (A) HMI Harmony lee DIRECTO por su Driver Modbus TCP Master
                                 │
                                 └── (B) Gateway RPi (pymodbus) ── WS/REST ── Web Digital Twin (SCADA / Cobot en Vivo)
```
- **Señales finales del HMI** (I_*/O_*, ver `docs/FUNCIONAMIENTO_HMI.md`) ↔ se mapean a coils/registers del PLC en el driver Modbus del HMI, o al bloque `telemetry.io` que publica el gateway (ver `PROMPT_RASP_SCADA_IO.md` en el repo web).
- **Lecturas** (sensores, limit switches, fixtures) → Input Registers/Discrete Inputs (FC04/FC02).
- **Comandos** (conveyor, gripper, mesa) → Holding Registers/Coils (FC16/FC05) — solo si el PLC los expone como escribibles.
- **Seguridad (importante):** Modbus TCP **no tiene autenticación** por diseño → depende 100% de **segmentación de red**. El E-stop debe ser **hardware/PLC**, nunca por Modbus/HMI. (Ver la revisión de seguridad del proyecto.)

---

## Recomendaciones rápidas
- **Editar la pantalla:** OTE en Windows (Block Script / JS / Lua) → exportar `.VML`, o usar la tooling de este repo (`build_vml_green.py` + `hmi_uploader.py`) para sustituir `Panel0.luac` y subir.
- **Gateway/puente:** Python + **pymodbus 3.x** (async para FastAPI).
- **HMI ↔ PLC:** driver **Modbus TCP Master** nativo de OTE (sin código).
- Confirmar el **modelo real** (HMIST6400 7" vs HMIST6200 4.3") y la **resolución** para la pantalla.

---

## Fuentes
- Schneider HMIST6400 (specs): https://www.se.com/us/en/faqs/FA308478/ · ficha en distribuidores (DM Supply, RS, iQelectro).
- OTE — lenguajes de script (Block/JavaScript/LUA Plus) y variables: catálogo OTE (manuals.plus / cloudfront 118827_en.pdf) · https://www.se.com/us/en/faqs/FAQ000264718/ (ScreenID en script).
- OTE — driver Modbus TCP Master (pasos): https://www.se.com/us/en/faqs/FA405185/ · persistent vs triggered https://www.se.com/us/en/faqs/FAQ000270974/ · nº de equipos https://www.se.com/us/en/faqs/FAQ000227595/
- Modbus function codes / MBAP: https://docs.chipkin.com/articles/modbus-function-code-deep-dive-fc01-fc06-fc15-fc16-fc23/ · https://controllerstech.com/modbus-tcp-protocol-explained/ · https://modbus.app/modbus-function-codes.html
- pymodbus 3.x: https://www.pymodbus.org/docs/quick-start · https://www.pymodbus.org/docs/reading-registers · pyModbusTCP: https://pymodbustcp.readthedocs.io/
- Mapa Modbus del cobot: `cobot_reader.py` + `CONTEXT_DIGITAL_TWIN.md` (repo RaspberryPiGIT).
