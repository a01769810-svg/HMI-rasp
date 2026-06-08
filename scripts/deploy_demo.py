#!/usr/bin/env python3
"""
Deploy del proyecto DEMO completo de Schneider (extraído de /RunTime/Application/)
al HMI HMIST6400 para recuperarlo.

Usa:
  - xfile manifest ORIGINAL del proyecto demo (sin reconstruir)
  - 40 archivos del demo project (application/...)
  - 4 DBs con paths ajustados de Windows ("C:/ProgramData/...") a Linux
    ("/mnt/data/data/SharedBT/")
  - project.xml DEL DEMO (GUID c76b314e-..., no el del pcap)
  - NetworkSettings.ini, readme y boot_data.img del pcap
"""

import os
import sys
import re
import time
from pathlib import Path

from hmi_uploader import HmiUploader, md5_hex


RT_ROOT = Path("/home/admin1/ote_analysis/runtime_app/"
                "EcoStruxure Operator Terminal Expert 3.2/RunTime/Application")
EXTRACTED = Path("/home/admin1/ote_analysis/extracted_files")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.51"

    # Leer xfile original del demo
    xfile_orig = (RT_ROOT / "xfile").read_text()

    # Sustituir paths Windows por paths Linux para las DBs
    xfile_text = re.sub(
        r"C:/ProgramData/Schneider Electric/EcoStruxure_OTE Runtime/data/SharedBT/",
        "/mnt/data/data/SharedBT/",
        xfile_orig,
    )

    # Recalcular MD5/size de las DBs porque vamos a reutilizar las del pcap
    # (las del demo son distintas tamaño/contenido)
    db_subs = {
        "/mnt/data/data/SharedBT/Alarm.db": EXTRACTED / "Alarm.db",
        "/mnt/data/data/SharedBT/Recipe.db": EXTRACTED / "Recipe.db",
    }
    new_lines = []
    for line in xfile_text.split("\n"):
        replaced = False
        for path, real_file in db_subs.items():
            if f",{path}," in line:
                content = real_file.read_bytes()
                parts = line.split(",")
                parts[2] = str(len(content))
                parts[3] = md5_hex(content)
                new_lines.append(",".join(parts))
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    xfile_text = "\n".join(new_lines)
    xfile_bytes = xfile_text.encode("ascii")

    # Construir lista de archivos a transferir
    files: list[tuple[str, bytes]] = []

    # Meta del HMI (del pcap)
    files.append(("application/NetworkSettings.ini",
                   (EXTRACTED / "NetworkSettings.ini").read_bytes()))

    # project.xml del demo (NO el del pcap)
    files.append(("application/project.xml",
                   (RT_ROOT / "project.xml").read_bytes()))

    # Todos los .luac y archivos del demo (orden alfabetico para ser consistente)
    demo_paths = [
        ("Alarm.luac", "application/Alarm.luac"),
        ("AlarmExport.luac", "application/AlarmExport.luac"),
        ("DriverConfig.luac", "application/DriverConfig.luac"),
        ("level.conf", "application/level.conf"),
        ("OperationLog.luac", "application/OperationLog.luac"),
        ("Project1.Accessories.dat", "application/Project1.Accessories.dat"),
        ("Project1.DataLocation.dat", "application/Project1.DataLocation.dat"),
        ("Project1.Target1.dat", "application/Project1.Target1.dat"),
        ("Project1.Target1.simxml", "application/Project1.Target1.simxml"),
        ("RecipeControls.luac", "application/RecipeControls.luac"),
        ("ScreenList.luac", "application/ScreenList.luac"),
        ("SystemKeypad.luac", "application/SystemKeypad.luac"),
        ("TargetConfigData.luac", "application/TargetConfigData.luac"),
        ("Variables.luac", "application/Variables.luac"),
        ("fonts/88591_VerdureSans.mbf", "application/fonts/88591_VerdureSans.mbf"),
        ("fonts/ja_MobileGothic.mbf", "application/fonts/ja_MobileGothic.mbf"),
        ("fonts/ja_MobileGothic_V.mbf", "application/fonts/ja_MobileGothic_V.mbf"),
        ("image/1.png", "application/image/1.png"),
        ("Languages/Language1/Settings.luac", "application/Languages/Language1/Settings.luac"),
        ("Languages/Language1/Texts.luac", "application/Languages/Language1/Texts.luac"),
        ("Languages/Language2/Settings.luac", "application/Languages/Language2/Settings.luac"),
        ("Languages/Language2/Texts.luac", "application/Languages/Language2/Texts.luac"),
        ("Screens/Panel0.luac", "application/Screens/Panel0.luac"),
        ("Screens/Panel1.luac", "application/Screens/Panel1.luac"),
        ("Screens/Panel2.luac", "application/Screens/Panel2.luac"),
        ("Screens/Panel3.luac", "application/Screens/Panel3.luac"),
        ("Screens/Panel4.luac", "application/Screens/Panel4.luac"),
        ("Screens/Panel5.luac", "application/Screens/Panel5.luac"),
        ("webgui/css/user.css", "application/webgui/css/user.css"),
    ]
    for local_rel, hmi_path in demo_paths:
        local = RT_ROOT / local_rel
        if local.exists():
            files.append((hmi_path, local.read_bytes()))

    # DBs (reusar las del pcap, paths Linux)
    files.append(("/mnt/data/data/SharedBT/Alarm.db",
                   (EXTRACTED / "Alarm.db").read_bytes()))
    files.append(("/mnt/data/data/SharedBT/Recipe.db",
                   (EXTRACTED / "Recipe.db").read_bytes()))

    # xfile (con paths Linux + MD5 reales de DBs reusadas)
    files.append(("application/xfile", xfile_bytes))

    # readme + boot_data.img (del pcap, validados)
    files.append(("/tmp/readme", (EXTRACTED / "readme").read_bytes()))
    files.append(("/tmp/boot_data.img", (EXTRACTED / "boot_data.img").read_bytes()))

    total = sum(len(c) for _, c in files)
    print(f"=== Deploy DEMO @ {host} — {len(files)} archivos, {total} bytes ===\n")
    for p, c in files:
        marker = "★" if p.endswith(".db") or p == "application/xfile" else " "
        print(f"  {marker} {p:55s} {len(c):>7d} B")
    print()

    if "--confirm" not in sys.argv:
        print("Re-run con --confirm para subir")
        sys.exit(0)

    client = HmiUploader(host)
    client.connect()
    try:
        print("--- Phase 1 — Handshake ---")
        client.full_handshake()
        print("--- Phase 3 — Metadata (skip P2: HMI sin xfile valido) ---")
        client.query_metadata()
        print(f"\n--- Phase 4 — PrepareUpdate({total}) + DelFile ---")
        if not client.prepare_update(total):
            print("[FATAL] PrepareUpdate falló")
            return
        client.del_file("[clean_projectdata_folder]")
        client.check_transfer_size_0()
        print("\n--- Phase 5 — Transfer files ---")
        if not client.transfer_files(files):
            print("[FATAL] Transfer falló")
            return
        print("\n--- Phase 6 — Deployment + FinalizeUpdate ---")
        client.deployment("/tmp/boot_data.img BOOT-DATA", "/tmp/readme", timer=60)
        resp = client.finalize_update()
        print(f"\n  [P6] {resp}")
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        print("\n[OK] HMI rebooteando — espera 60-90 seg")


if __name__ == "__main__":
    main()
