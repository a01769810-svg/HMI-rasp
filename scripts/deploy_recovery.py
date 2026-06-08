#!/usr/bin/env python3
"""
Recuperación de emergencia del HMI: sube el proyecto sample COMPLETO de
backup_app/a2 (Alarm, ScreenList, Panel0, Panel1, level.conf) construyendo
un xfile manifest coherente con los MD5/size reales.
"""

import hashlib
import os
import sys
import time

from hmi_uploader import HmiUploader, md5_hex


BACKUP = "/home/admin1/ote_analysis/backup_app"
EXTRACTED = "/home/admin1/ote_analysis/extracted_files"


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.51"

    # Archivos del proyecto sample (todos van a "application/...")
    project_files = [
        ("application/Alarm.luac", open(f"{BACKUP}/Alarm.luac", "rb").read()),
        ("application/level.conf", open(f"{BACKUP}/level.conf", "rb").read()),
        ("application/ScreenList.luac", open(f"{BACKUP}/ScreenList.luac", "rb").read()),
        ("application/Screens/Panel0.luac", open(f"{BACKUP}/Panel0.luac", "rb").read()),
        ("application/Screens/Panel1.luac", open(f"{BACKUP}/Panel1.luac", "rb").read()),
    ]

    # Construir xfile manifest con MD5/size REALES de cada archivo
    total_size = sum(len(c) for _, c in project_files)
    xfile_lines = [
        f"{total_size},32768,./",  # primera línea: total + alguna info
        "0,0,",
        "0,0,",
        "",
    ]
    for path, content in project_files:
        xfile_lines.append(f",{path},{len(content)},{md5_hex(content)}")
    xfile_text = "\r\n".join(xfile_lines) + "\r\n"
    xfile_content = xfile_text.encode("ascii")

    # project.xml con BuildDate nuevo
    project_xml = open(f"{EXTRACTED}/project.xml", "rb").read()

    # Lista completa a transferir: proyecto sample + meta + readme + boot_data.img
    files = [
        ("application/NetworkSettings.ini", open(f"{EXTRACTED}/NetworkSettings.ini", "rb").read()),
        ("application/project.xml", project_xml),
        ("application/Alarm.luac", project_files[0][1]),
        ("application/level.conf", project_files[1][1]),
        ("application/ScreenList.luac", project_files[2][1]),
        ("application/Screens/Panel0.luac", project_files[3][1]),
        ("application/Screens/Panel1.luac", project_files[4][1]),
        ("application/xfile", xfile_content),
        ("/tmp/readme", open(f"{EXTRACTED}/readme", "rb").read()),
        ("/tmp/boot_data.img", open(f"{EXTRACTED}/boot_data.img", "rb").read()),
    ]

    total_bytes = sum(len(c) for _, c in files)
    print(f"=== RECOVERY: subir {len(files)} archivos = {total_bytes} bytes ===\n")
    for p, c in files:
        print(f"  {p:50s} {len(c):>7d} B  md5={md5_hex(c)[:10]}")
    print()

    if "--confirm" not in sys.argv:
        print("Re-run con --confirm para ejecutar")
        sys.exit(0)

    client = HmiUploader(host)
    client.connect()
    try:
        print("--- Phase 1 — Handshake ---")
        client.full_handshake()

        print("\n--- Phase 2 — Skip (HMI sin xfile válido) ---")
        # Saltamos Phase 2 porque el HMI puede no tener xfile

        print("--- Phase 3 — Metadata ---")
        client.query_metadata()

        print("\n--- Phase 4 — PrepareUpdate + DelFile ---")
        if not client.prepare_update(total_bytes):
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
        print(f"  [P6] {resp}")

    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        print("\n[OK] HMI rebooteando — esperar 60-90 seg")


if __name__ == "__main__":
    main()
