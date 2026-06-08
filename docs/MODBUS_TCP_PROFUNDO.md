# Modbus TCP — guía profunda (para la celda de remachado)

> Todo lo necesario para comunicar HMI Harmony ↔ PLC/gateway ↔ cobot por Modbus TCP:
> protocolo byte a byte, function codes, encoding de 16/32-bit y floats, **cliente** y
> **servidor** con pymodbus, el **driver nativo del HMI (OTE)**, buenas prácticas, y un
> **mapa Modbus propuesto** para las señales finales de la celda. (Fuentes al final.)

---

## 1. Conceptos base
- **Transporte:** TCP. Puerto **502** (estándar). *El cobot Lexium del proyecto: `10.5.5.100:6502`.*
- **Master/Client ↔ Slave/Server:** el **master** (HMI o gateway) inicia las peticiones; el **slave/server** (PLC, cobot, o el gateway RPi actuando de slave) responde. Un slave se identifica por **Unit ID** (1 byte).
- **Modelo de datos — 4 espacios:**
  | Tabla | Tipo | Acceso | Leer | Escribir |
  |---|---|---|---|---|
  | **Coils** | bit | R/W | FC01 | FC05 (1) / FC15 (N) |
  | **Discrete Inputs** | bit | R | FC02 | — |
  | **Holding Registers** | 16-bit | R/W | **FC03** | FC06 (1) / **FC16** (N) |
  | **Input Registers** | 16-bit | R | **FC04** | — |
- **Límites por petición:** registros **≤ 125** (FC03/FC04), coils **≤ 2000** (FC01/FC02), write multiple ≤ 123 regs / 1968 coils. Si necesitas más, **trocea** en varias peticiones.

## 2. Anatomía del frame (MBAP + PDU)
```
┌──────────────── MBAP (7 bytes) ─────────────────┬──── PDU ────┐
 TransactionID(2) ProtocolID(2)=0  Length(2)  UnitID(1) | FC(1) Data(...)
```
- **TransactionID:** eco para emparejar request/response (permite pipelining).
- **ProtocolID:** siempre `0x0000` para Modbus.
- **Length:** nº de bytes que siguen (UnitID + PDU).
- **UnitID:** slave destino (en TCP puro suele ser 1; relevante con gateways serial).

**Ejemplo real — FC03 leer 2 holding registers en addr 0, unit 1:**
```
Request : 00 01 00 00 00 06 01 03 00 00 00 02
          └TxID┘ └Proto┘ └Len┘ U  FC └addr┘ └qty┘
Response: 00 01 00 00 00 07 01 03 04 00 0A 00 14
                                  BC  └reg0┘└reg1┘   → [10, 20]
```
(BC = byte count = 2·nº regs.)

## 3. Function codes (los que usarás)
| FC | Nombre | Uso típico en la celda |
|---|---|---|
| 0x01 | Read Coils | leer salidas booleanas (estado de actuadores) |
| 0x02 | Read Discrete Inputs | leer **sensores** (photoeye, limits, fixtures) |
| 0x03 | Read Holding Registers | leer/escribir valores 16-bit (setpoints, contadores) |
| 0x04 | Read Input Registers | leer **medidas** read-only (temps, posiciones, contadores) |
| 0x05 | Write Single Coil | comandar una salida (ON=`0xFF00`, OFF=`0x0000`) |
| 0x06 | Write Single Register | escribir un setpoint |
| 0x0F (15) | Write Multiple Coils | comandar varias salidas |
| 0x10 (16) | Write Multiple Registers | escribir varios setpoints de golpe |
| 0x17 (23) | Read/Write Multiple | lectura+escritura atómica |

**Excepciones** (response con FC|0x80 + código): `01` Illegal Function · `02` Illegal Data Address · `03` Illegal Data Value · `04` Slave Device Failure · `0B` Gateway Target Failed To Respond.

## 4. Direccionamiento (¡cuidado con el off-by-one!)
- **Notación Modicon (documentación):** `0xxxx`=coils, `1xxxx`=discrete inputs, `3xxxx`=input regs, `4xxxx`=holding regs. Ej.: `40001` = primer holding register.
- **En código (pymodbus, etc.) es 0-based:** `40001 → address=0`, `40002 → address=1`. La tabla (coil vs holding) la define la **función** que llamas, no el prefijo.
- Errores clásicos: confundir 1-based con 0-based (±1), o leer holding cuando el dato está en input registers.

## 5. Encoding de datos
- **16-bit:** un registro = 1 valor (0..65535 unsigned, o −32768..32767 signed con complemento a 2).
- **32-bit (INT32 / UINT32 / FLOAT32):** ocupa **2 registros** → hay que combinar y respetar **byte order** y **word order**:
  - Modbus es **big-endian** por especificación (byte alto primero).
  - 4 combinaciones posibles (word, byte): **ABCD** (big-big, "FP B"), **CDAB** (word-swap, "FP LB", muy común en PLCs), **BADC**, **DCBA**.
  - **Truco para descubrir el orden:** pide un valor float conocido; si sale un número imposible (exponente raro), cambia el orden.
- **Float decode con pymodbus:**
  ```python
  # pymodbus ≤ 3.6
  from pymodbus.payload import BinaryPayloadDecoder
  from pymodbus.constants import Endian
  rr = client.read_holding_registers(address=0, count=2, slave=1)
  dec = BinaryPayloadDecoder.fromRegisters(rr.registers, byteorder=Endian.BIG, wordorder=Endian.BIG)
  valor = dec.decode_32bit_float()

  # pymodbus ≥ 3.7 (API nueva, recomendada)
  valor = client.convert_from_registers(rr.registers, client.DATATYPE.FLOAT32, word_order="big")
  ```

## 6. CLIENTE Modbus TCP (gateway RPi) — pymodbus 3.x
```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("10.5.5.100", port=6502, timeout=1.0)   # LAN: 0.5–1s
if not client.connect():
    raise RuntimeError("no conecta")

# Leer (FC04 input registers / FC03 holding / FC02 discrete / FC01 coils)
rr = client.read_input_registers(address=454, count=8, slave=1)
if not rr.isError():
    regs = rr.registers          # lista de 16-bit

# Escribir
client.write_register(address=0, value=1234, slave=1)            # FC06
client.write_registers(address=10, values=[1, 0, 1], slave=1)    # FC16
client.write_coil(address=2, value=True, slave=1)                # FC05

client.close()
```
- **Async (recomendado dentro de FastAPI):** `from pymodbus.client import AsyncModbusTcpClient` → `await client.read_input_registers(...)`. Evita bloquear el event loop.
- **Leer > 125 registros:** trocear (`for base in range(0, total, 120): read_input_registers(base, 120)`).
- **Manejo de errores:** siempre `if rr.isError():` antes de `.registers`; reintentar con backoff; reconectar si el socket cae.
- **Alternativas:** `pyModbusTCP` (más liviana), `minimalmodbus` (serial/RTU).

## 7. SERVIDOR Modbus TCP en la RPi (para que el HMI lea la celda) ⭐
Si el **HMI Harmony es el master** y quieres que lea el estado del digital twin / I/O de la
celda, la RPi puede actuar de **slave/server Modbus** exponiendo coils + registros que el HMI
pollea. Patrón con pymodbus 3.x (async):

```python
import asyncio
from pymodbus.datastore import (ModbusServerContext, ModbusSlaveContext, ModbusSequentialDataBlock)
from pymodbus.server import StartAsyncTcpServer

# Bloques: di=discrete inputs, co=coils, hr=holding, ir=input regs
store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 32),    # sensores (FC02)
    co=ModbusSequentialDataBlock(0, [0] * 16),    # salidas/comandos (FC01/05)
    ir=ModbusSequentialDataBlock(0, [0] * 64),    # medidas RO (FC04)
    hr=ModbusSequentialDataBlock(0, [0] * 64),    # setpoints (FC03/16)
)
context = ModbusServerContext(slaves=store, single=True)

async def actualizar(context):
    # function code de escritura interna: 2=discrete inputs, 1=coils, 4=input, 3=holding
    while True:
        io = leer_estado_celda()                  # tu fuente real
        context[0].setValues(2, 0, [int(io.conveyor_photoeye), int(io.fixture_1_present), ...])  # discrete inputs
        context[0].setValues(4, 10, [j1_temp, j2_temp, ...])  # input registers (temps)
        await asyncio.sleep(0.2)                  # 5 Hz

async def main():
    asyncio.create_task(actualizar(context))
    await StartAsyncTcpServer(context, address=("0.0.0.0", 502))

asyncio.run(main())
```
- El HMI configura su **driver Modbus TCP Master** apuntando a la IP de la RPi:502 y lee esas direcciones.
- `setValues(fc, address, values)`: `fc` = el código de la tabla (1 coils, 2 discrete inputs, 3 holding, 4 input). Verifica la firma según tu versión de pymodbus.
- Así el HMI ve la celda **sin** que la RPi tenga que hablar el protocolo OTE: el HMI usa su driver estándar.

## 8. HMI Harmony (OTE) como **Modbus TCP Master** (sin código)
1. Project Explorer → **System Architecture → Target01 → Driver** → **`+Driver`**.
2. Manufacturer = **Schneider Electric**, Driver = **Modbus TCP Master** → OK.
3. En el equipo creado (`SchneiderModbusTCPIPEquipment1`) → Properties → Basic → **Equipment Settings**: IP del slave (PLC o RPi) y puerto.
4. Crea **variables** mapeadas a direcciones Modbus del equipo (coil/register) y asócialas a switches, lamps, data displays.
5. **Persistent vs Triggered:** persistent = polleo continuo; triggered = solo por evento. Elige según carga.
6. Se pueden agregar **varios equipos** por driver (límite según versión/SP).

## 9. Buenas prácticas / tuning
- **Conexión persistente:** NO abras un socket TCP por petición — llena la tabla de conexiones del slave y empieza a responder **RST**. Reusa una conexión.
- **Límite de conexiones del slave:** firmware-dependiente, de **1 a 16** (PLCs simples 4–8). No abras N clientes contra el mismo equipo.
- **Timeouts:** LAN **500–1000 ms**, WAN/VPN **1–2 s**. Regla: (máx. tiempo de respuesta + latencia) × 1.5–2. < 200 ms da fallos intermitentes.
- **Polling por niveles (tiered):** pollea rápido lo que cambia rápido (estados, alarmas) y lento lo lento (contadores, temps). No pollees todo a 50 ms.
- **Lecturas contiguas:** agrupa registros en bloques contiguos y lee de un golpe (1 petición de 50 regs ≪ 50 peticiones de 1).
- **Reconexión:** detecta socket caído y reconecta con backoff; valida `isError()` siempre.

## 10. Mapa Modbus PROPUESTO para la celda (señales finales)
Una forma limpia de exponer las señales del HMI (`docs/FUNCIONAMIENTO_HMI.md`) por Modbus
para que el HMI las lea con su driver. *(Ajustar a tu PLC real; es una propuesta.)*

**Discrete Inputs (FC02) — sensores (read-only):**
| Addr | Señal |
|---|---|
| 0 | I_CONVEYOR_PHOTOEYE |
| 1 | I_FIXTURE_1_PRESENT |
| 2 | I_FIXTURE_2_PRESENT |
| 3 | I_TABLE_HOME_LIMIT |
| 4 | I_TABLE_WORK_LIMIT |
| 5 | I_CAMERA_PASS |
| 6 | I_CAMERA_FAIL |
| 7 | I_CAMERA_READY |
| 8 | I_CAMERA_ERROR |
| 9 | I_CAMERA_NO_READ |
| 10 | I_COBOT_MOVING |
| 11 | I_COBOT_READY |
| 12 | I_GRIPPER_OPEN |
| 13 | I_GRIPPER_CLOSED |

**Coils (FC01 leer / FC05 escribir) — salidas/estado:**
| Addr | Señal |
|---|---|
| 0 | O_GRIPPER_OFF |
| 1 | O_CONVEYOR_MOTOR |
| 2 | O_CAMERA_TRIGGER |
| 3 | O_TABLE_NEMA_MOVING (Disco) |
| 4 | O_RIVET_ACTIVE |
| 5 | O_STACKLIGHT_GREEN |
| 6 | O_STACKLIGHT_YELLOW |
| 7 | O_STACKLIGHT_RED |

**Input Registers (FC04) — numéricos read-only:**
| Addr | Valor |
|---|---|
| 0 | cycle_state (enum: 0 IDLE,1 RUNNING,2 STOPPED,3 FAULT,4 FINISHED,5 CLEANING) |
| 1 | active_cafi_id |
| 2 | cafis_waiting_count |
| 3 | conveyor_on_time_s |
| 4 | table_position (0 HOME,1 WORK,2 MOVING) |
| 10–15 | joint temp J1..J6 (°C) |
| 16 | controller temp (°C) |
| 20 | accepted_count |
| 21 | rejected_count |
| 22 | total_count |

## 11. Diagnóstico
- CLI: **`mbpoll`**, `modpoll`. GUI: **QModMaster**, Modbus Poll. En este repo/ecosistema: `modbus_check.py`.
- Para ver el cobot real: `mbpoll -m tcp -a 1 -t 4 -r 455 -c 8 10.5.5.100 -p 6502` (FC04 desde reg 455).

## 12. Mapa Modbus real del cobot (referencia)
`10.5.5.100:6502`, Unit ID 1, **FC04 input registers**, read-only. Bloques: `status` (≈454–461),
`motion_errcode` (INT32), `controller`, `joint_states/positions/speeds/temps` (×6), `tcp_position/speed`,
`end_effector` (≈370–381). Mapa exacto en `cobot_reader.py` + `CONTEXT_DIGITAL_TWIN.md`. Para
**comandar** el cobot se usa su SDK/OPC UA (EcoStruxure Cobot), no estos registros de monitoreo.

## 13. Seguridad
Modbus **no tiene autenticación ni cifrado** por diseño → la seguridad es **segmentación de red**
(VLAN/firewall; no exponer 502 a internet). El **E-stop debe ser hardware/PLC**, nunca depender de
Modbus/HMI/red. (Ver la revisión de seguridad del proyecto.)

---

## Fuentes
- Function codes / MBAP: https://docs.chipkin.com/articles/modbus-function-code-deep-dive-fc01-fc06-fc15-fc16-fc23/ · https://controllerstech.com/modbus-tcp-protocol-explained/ · https://modbus.app/modbus-function-codes.html
- pymodbus 3.x cliente: https://www.pymodbus.org/docs/quick-start · https://www.pymodbus.org/docs/reading-registers · tipos de dato: https://www.pymodbus.org/docs/data-types
- pymodbus servidor: https://pymodbus.readthedocs.io/en/stable/source/server.html · ejemplo: https://github.com/pymodbus-dev/pymodbus/blob/dev/examples/server_async.py
- Floats/byte-word order: https://store.chipkin.com/articles/how-real-floating-point-and-32-bit-data-is-encoded-in-modbus-rtu-messages
- Buenas prácticas (timeouts/persistente/conexiones): https://flowfuse.com/blog/2026/04/modbus-polling-best-practices/ · https://infoneva.com/en/knowledge/configuring-modbus-tcp-timeouts-best-practices
- Driver Modbus TCP en OTE: https://www.se.com/us/en/faqs/FA405185/
