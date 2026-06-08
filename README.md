# HMI-rasp — HMI real de la Celda de Remachado (Schneider Harmony)

Repositorio con la **tooling y documentación del HMI real** de la celda de remachado
(Equipo 3 · ITESM × Schneider). No es un HMI nuevo: aquí se versiona **lo que ya se hizo**
para construir y subir el proyecto del panel Schneider.

> **Panel:** Harmony **HMIST6400** · autoría con **EcoStruxure Operator Terminal Expert (OTE) 3.2**
> · paquete **`.VML`** (contiene `Panel0.luac` + manifest `xfile`).

## Estructura

```
HMI-rasp/
├── README.md                 ← este índice
├── scripts/                  ← tooling REAL (de RaspberryPiGIT) para construir/subir el VML
│   ├── build_vml_green.py     reemplaza Panel0.luac dentro del package.vml + actualiza el manifest
│   ├── hmi_protocol.py        protocolo OTE↔HMI (puertos 3320/3321/8050, length-prefix XML <TSM>)
│   ├── hmi_uploader.py        uploader de 6 fases (handshake→…→deploy+reboot)
│   ├── deploy_green.py        deploy de la pantalla custom (--dry-run / --confirm)
│   ├── deploy_green_v2.py     variante one-shot (proyecto "stateless" en 3321)
│   ├── deploy_recovery.py     recuperación: sube proyecto sample completo
│   ├── deploy_demo.py         recuperación: sube el proyecto DEMO de Schneider
│   ├── deploy_firmware.py     reflasheo de firmware A2 (bootloader + kernel)
│   └── deploy_fw_split.py     firmware en 2 fases (bootloader → kernel)
└── docs/
    ├── FLUJO_SUBIDA_HMI_REAL.md      ← cómo se edita el VML y se sube al HMI (paso a paso, puertos, fases, errores, recovery)
    ├── FUNCIONAMIENTO_HMI.md         ← qué muestra/hace la pantalla del operador (botones, indicadores, señales, contadores)
    └── OperatorHMI_RemachadoCell.svg ← maqueta vectorial del diseño de la pantalla del operador
```

## Por dónde empezar
1. **`docs/FLUJO_SUBIDA_HMI_REAL.md`** — el flujo `VML → edición → validación → subida → reboot`.
2. **`docs/FUNCIONAMIENTO_HMI.md`** — señales (I/O), botones e indicadores del operador.
3. `scripts/` — la tooling Python que ejecuta ese flujo.

## Notas importantes
- **Los binarios del proyecto NO están aquí** (`package.vml`, `Panel0*.luac`, `xfile`, firmware `.SYS`, DBs):
  viven en la Raspberry, bajo `/home/admin1/ote_analysis/…`. Este repo guarda la **tooling + docs**.
- **Prerrequisito** para subir: habilitar **"Ethernet Download"** en el menú del HMI.
- **IP del HMI:** default `192.168.1.51` (LAN), configurable por argumento (`--host` / primer arg). No hay credenciales en el repo.
- **La Fase 4 del upload es destructiva** (limpia el proyecto). Correr siempre primero en **`--dry-run`**.
  Si el HMI se queda sin proyecto: `deploy_recovery.py` / `deploy_demo.py`; si se brickea el firmware: `deploy_firmware.py` / `deploy_fw_split.py`.
- No se modificó la tooling: se versionó **tal cual** de RaspberryPiGIT.
