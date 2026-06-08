#!/usr/bin/env python3
"""
Deploy de la pantalla verde al HMI Schneider HMIST6400.

Toma:
  - Panel0_green.luac (compilado previamente con luac5.1 -s armhf)
  - El xfile manifest extraído del pcap 604 como base
  - project.xml extraído del pcap como base

Y produce:
  - xfile con MD5/size de Panel0.luac actualizados
  - project.xml con nuevo BuildDate

Luego ejecuta las 6 fases del Transfer.
"""

import argparse
import hashlib
import os
import sys
import time
import uuid

from hmi_uploader import HmiUploader, update_xfile_entry, md5_hex


SAMPLES = "/home/admin1/ote_analysis/samples"
EXTRACTED = "/home/admin1/ote_analysis/extracted_files"

# Archivos del pcap que reutilizamos tal cual
REUSE = {
    "application/NetworkSettings.ini": f"{EXTRACTED}/NetworkSettings.ini",
    "/mnt/data/data/SharedBT/Alarm.db": f"{EXTRACTED}/Alarm.db",
    "/mnt/data/data/SharedBT/Recipe.db": f"{EXTRACTED}/Recipe.db",
    "/tmp/readme": f"{EXTRACTED}/readme",
    "/tmp/boot_data.img": f"{EXTRACTED}/boot_data.img",
}


def build_files(panel0_path: str) -> list[tuple[str, bytes]]:
    """Devuelve la lista (path_en_hmi, content_bytes) para transferir."""
    panel0 = open(panel0_path, "rb").read()
    panel0_md5 = md5_hex(panel0)
    print(f"  Panel0_green.luac: {len(panel0)} B, MD5={panel0_md5}")

    # 1) xfile actualizado
    xfile_orig = open(f"{EXTRACTED}/xfile", "rb").read().decode("ascii")
    xfile_new_text = update_xfile_entry(
        xfile_orig, "application/Screens/Panel0.luac", panel0
    )
    xfile_new = xfile_new_text.encode("ascii")
    print(f"  xfile (nuevo):     {len(xfile_new)} B, MD5={md5_hex(xfile_new)}")

    # 2) project.xml con nuevo BuildDate (mantenemos el GUID original)
    project_orig = open(f"{EXTRACTED}/project.xml", "rb").read().decode("ascii")
    new_build = time.strftime("%m/%d/%Y %H:%M:%S")
    # Reemplazar la línea <BuildDate>...</BuildDate>
    import re
    project_new_text = re.sub(
        r"<BuildDate>[^<]+</BuildDate>",
        f"<BuildDate>{new_build}</BuildDate>",
        project_orig,
    )
    project_new = project_new_text.encode("ascii")
    print(f"  project.xml:       {len(project_new)} B, MD5={md5_hex(project_new)}")

    # Lista de archivos a transferir en el orden del pcap
    files = [
        ("application/NetworkSettings.ini", open(REUSE["application/NetworkSettings.ini"], "rb").read()),
        ("application/project.xml", project_new),
        ("/mnt/data/data/SharedBT/Alarm.db", open(REUSE["/mnt/data/data/SharedBT/Alarm.db"], "rb").read()),
        ("/mnt/data/data/SharedBT/Recipe.db", open(REUSE["/mnt/data/data/SharedBT/Recipe.db"], "rb").read()),
        ("application/Screens/Panel0.luac", panel0),
        ("application/xfile", xfile_new),
        ("/tmp/readme", open(REUSE["/tmp/readme"], "rb").read()),
        ("/tmp/boot_data.img", open(REUSE["/tmp/boot_data.img"], "rb").read()),
    ]
    return files


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="192.168.1.51")
    p.add_argument("--panel0", default=f"{SAMPLES}/Panel0_green.luac")
    p.add_argument("--dry-run", action="store_true",
                   help="Phases 1-3 only, NO destructive")
    p.add_argument("--confirm", action="store_true",
                   help="Ejecuta Phase 4+5+6 (apaga UI + reboot)")
    args = p.parse_args()

    print(f"=== Deploy GREEN to {args.host} ===\n")
    print("[*] Preparando archivos...")
    files = build_files(args.panel0)
    total_bytes = sum(len(c) for _, c in files)
    print(f"\n  Total transfer size: {total_bytes} bytes")
    print(f"  Archivos a transferir: {len(files)}\n")

    if not (args.dry_run or args.confirm):
        print("ERROR: necesitas --dry-run o --confirm")
        print("  --dry-run  → solo Phases 1-3 (NO modifica HMI)")
        print("  --confirm  → ejecuta el deploy COMPLETO (apaga UI + reboot)")
        sys.exit(1)

    client = HmiUploader(args.host)
    client.connect()
    try:
        print("--- Phase 1 — Handshake ---")
        client.full_handshake()

        print("\n--- Phase 2 — Download manifest ---")
        manifest = client.download_manifest()
        print(f"  HMI tiene manifest de {len(manifest)} bytes")

        print("\n--- Phase 3 — Metadata ---")
        client.query_metadata()

        if args.dry_run:
            print("\n[DRY-RUN] HMI no modificado. Saliendo.")
            return

        print("\n--- Phase 4 — PrepareUpdate + DelFile ---")
        if not client.prepare_update(total_bytes):
            print("[FATAL] PrepareUpdate falló")
            return
        if not client.del_file("[clean_projectdata_folder]"):
            print("[FATAL] DelFile falló")
            return
        client.check_transfer_size_0()

        print("\n--- Phase 5 — Transfer files ---")
        if not client.transfer_files(files):
            print("[FATAL] Transfer falló")
            return

        print("\n--- Phase 6 — Deployment + FinalizeUpdate ---")
        if not client.deployment(
            "/tmp/boot_data.img BOOT-DATA", "/tmp/readme", timer=60
        ):
            print("[WARN] Deployment falló — el HMI puede no completar el update")
        finalize_resp = client.finalize_update()
        print(f"\n  [P6] El HMI debería rebootear ahora.")
        print(f"  Resp: {finalize_resp}")

    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        print("\n[OK] Disconnect limpio")


if __name__ == "__main__":
    main()
