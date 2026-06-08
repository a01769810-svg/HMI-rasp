# Flujo real: editar y subir el HMI a la pantalla Schneider

> Documento basado **exactamente** en la tooling que ya existe (`scripts/`), extraída de
> `RaspberryPiGIT`. No reescribe ni reinventa el HMI: describe el flujo verificado
> `VML → edición → validación → subida → reboot`. Donde algo vive fuera de esta máquina
> (en la Raspberry Pi) se indica con la ruta real.

---

## 1. Qué es el "HMI" aquí

- **Panel:** Schneider **Harmony HMIST6400** (según los comentarios/pcap de la tooling).
- **Software de autoría:** **EcoStruxure Operator Terminal Expert (OTE) 3.2**.
- **Paquete del proyecto = `.VML`** (`package.vml`). **No es `.bml`.** Es un contenedor
  binario con bloques; dentro lleva, entre otros:
  - `application/Screens/Panel0.luac` — la **pantalla del operador compilada** (Lua → luac5.1 `-s armhf`).
  - `application/xfile` — **manifest CSV** con `,ruta,tamaño,md5` por archivo (debe ser coherente).
  - `application/project.xml` — metadata (incluye `<BuildDate>`).
  - fonts, idiomas, `NetworkSettings.ini`, DBs (`Alarm.db`, `Recipe.db`), etc.

> ⚠️ Los **binarios** (`package.vml`, `Panel0*.luac`, `xfile`, firmware `.SYS`, DBs) **no están
> en este repo**: viven en la Raspberry, bajo `/home/admin1/ote_analysis/…`. Este repo guarda la
> **tooling** (`scripts/`) que los construye y los sube.

---

## 2. Cómo se EDITA la pantalla

El flujo no edita el `.VML` "a mano": se reemplaza la pantalla compilada dentro del paquete.

1. Se edita/compila la pantalla a `Panel0.luac` (variantes vistas: `Panel0_green.luac`,
   `Panel0_chanti.luac`) — compilada con `luac5.1 -s armhf`.
2. **`scripts/build_vml_green.py`** toma `package.vml` + el `Panel0_*.luac` nuevo y:
   - localiza el bloque `application/Screens/Panel0.luac` (parser de bloques del VML),
   - lo reemplaza por el nuevo (recalcula el **MD5**),
   - **actualiza la línea del manifest `xfile`** (tamaño + md5) — si no la encuentra, avisa
     que el VML podría no validar,
   - escribe `package_green.vml` y re-parsea para verificar.
   - Rutas (en la Pi): `VML_IN`, `PANEL0_GREEN`, `VML_OUT` al inicio del script.

> Editar otros campos (p. ej. `<BuildDate>` de `project.xml`) lo hace `deploy_green.py` al vuelo.

---

## 3. Protocolo de comunicación con el HMI (`scripts/hmi_protocol.py`)

Reverse-engineered de un pcap del upload real de OTE 3.2 → HMIST6400.

- **Puertos TCP:** `3320` = state broadcast (banner XML) · `3321` = control XML · `8050` = transfer de archivos.
- **Prerrequisito imprescindible:** en el menú del HMI, habilitar **"Ethernet Download"**.
  Sin eso, **los puertos TCP están cerrados** y nada conecta.
- **Mensajes:** length-prefix de **5 dígitos ASCII** + cuerpo XML envuelto en `<TSM>…</TSM>`;
  el cliente usa `Owner="Target"` / `Purpose="Request"`, el HMI responde `Result="1"`/`true`.
- `HmiClient` implementa el handshake básico (CheckFct, Identification, CheckBrand, etc.).

---

## 4. Cómo se SUBE (`scripts/hmi_uploader.py`) — 6 fases

`HmiUploader` replica el Transfer de OTE en 6 fases:

1. **Handshake** (3321): `RT_VERSION_FORMAT_2`, `Identification`, `CheckBrand`, `CheckProjectID`, `PasswordEnabled`, `FileInfo xfile`, `UPLOAD_V2`.
2. **Download manifest** (abre `8050`, recibe el `xfile` actual del HMI).
3. **Metadata** (DatabaseVersion, ExportData, PartitionInfo).
4. **PrepareUpdate + DelFile** — ⚠️ **DESTRUCTIVO**: apaga la UI y limpia el proyecto.
5. **Transfer file-by-file**: por archivo manda `<Transfer>` por 3321 y el contenido en
   **chunks de 8187 B** length-prefix por una conexión `8050`, con **ACK `<TSM> Result="1"`** por archivo.
6. **Deployment + FinalizeUpdate** → **reboot** del HMI.

CRC por archivo = `md5 + "\r\n"`. Helper `update_xfile_entry()` actualiza tamaño/md5 en el manifest.

**Modo seguro:** ejecutar `hmi_uploader.py <IP>` corre **solo Fases 1–3** (no modifica el HMI).

---

## 5. Entradas de deploy (`scripts/deploy_*.py`)

| Script | Qué hace | Destructivo | Cómo |
|---|---|---|---|
| `deploy_green.py` | Sube la pantalla custom (`Panel0_green.luac`) + meta reutilizada del pcap | Sí (con `--confirm`) | `--dry-run` = Fases 1–3; `--confirm` = deploy completo |
| `deploy_green_v2.py` | Igual, pero conexión **one-shot por comando** (el proyecto nuevo del usuario es "stateless" en 3321); construye un `xfile` mínimo | Sí | `--confirm` |
| `deploy_recovery.py` | **Recuperación**: sube un proyecto sample COMPLETO (Alarm/ScreenList/Panel0/Panel1/level.conf) con `xfile` coherente | Sí | `--confirm` |
| `deploy_demo.py` | **Recuperación**: sube el proyecto **DEMO** de Schneider (40 archivos) para revivir el HMI | Sí | `--confirm` |
| `deploy_firmware.py` | **Reflasheo de firmware** (target A2): BOOTLD0E.SYS (bootloader) + BOOTOS0E.SYS (kernel) | Sí (firmware) | `--confirm` |
| `deploy_fw_split.py` | Firmware en **2 fases separadas** (bootloader → reboot → kernel), con polling de 3321 | Sí (firmware) | `python deploy_fw_split.py A` luego `… B` |

Todos toman la IP del HMI (default **`192.168.1.51`**) y leen los binarios de la Pi (`/home/admin1/ote_analysis/…`).

---

## 6. Validación (antes de subir)

- Correr primero en **dry-run** (no modifica el HMI):
  - `python scripts/hmi_uploader.py <HMI_IP>` (Fases 1–3), o
  - `python scripts/deploy_green.py --host <HMI_IP> --dry-run`.
- `build_vml_green.py` re-parsea el VML y confirma bloques + que la línea de `Panel0` quedó en el manifest.
- Confirmar que el handshake responde `Result="true"` y que `download_manifest()` trae el `xfile` actual.

## 7. Backup

- **Antes de cualquier `--confirm`**, conservar copia del `package.vml` actual y del proyecto OTE.
- Existe ruta de recuperación si algo sale mal (ver §8).
- En este repo no se incluyen binarios; el backup vive en la Pi/OTE del usuario.

## 8. Errores comunes / aprendizaje de deploys previos

- **Puertos cerrados / no conecta** → falta habilitar **"Ethernet Download"** en el HMI.
- **`xfile` inconsistente** (md5/size que no cuadran, o falta la línea de `Panel0`) → el HMI **no valida** el proyecto.
- **Fase 4 deja el HMI sin UI** (es destructiva): si el Transfer/Deployment falla a la mitad, el HMI puede quedar **sin proyecto** → usar `deploy_recovery.py` o `deploy_demo.py` para revivirlo.
- **Proyecto "stateless" en 3321** (el HMI cierra la conexión rápido) → usar `deploy_green_v2.py` (one-shot por comando) en vez de la conexión persistente.
- **Brick a nivel firmware** (peor caso) → `deploy_firmware.py` / `deploy_fw_split.py` reflashean bootloader+kernel (target A2). Tras firmware: esperar 5–10 min antes de power-cycle.
- Throttle de 5 ms entre chunks (`time.sleep(0.005)`) para no saturar el recovery del HMI.

## 9. IP / red

- IP del HMI por defecto en los scripts: **`192.168.1.51`** (LAN privada). Es configurable por
  argumento (`--host` / primer argumento), p. ej. `HMI_IP=192.168.1.51`.
- Puertos: 3320 / 3321 / 8050 (TCP) hacia el HMI.

## 10. Pendientes

- Los **binarios del proyecto** (`package.vml`, `Panel0*.luac`, `xfile`, firmware, DBs) no están
  versionados aquí — definir si se suben (¿LFS?) o se mantienen solo en la Pi/OTE.
- La pantalla del operador documentada en `FUNCIONAMIENTO_HMI.md` + `OperatorHMI_RemachadoCell.svg`
  es el **diseño**; el `Panel0.luac` compilado es el artefacto real (su fuente Lua/OTE vive aparte).
