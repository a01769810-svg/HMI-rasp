#!/usr/bin/env python3
"""
Deploy del firmware del HMIST6400 (target A2) via Ethernet en modo recovery.

Sigue el procedimiento exacto del list de Schneider en /Buildtime/S2I/A2/:
  S2I/A2/kernel/readme        → /tmp/readme        (26684 B)
  S2I/A2/kernel/BOOTLD0E.SYS  → /tmp/BOOTLD0E.SYS  (295340 B)
  Deployment: "/tmp/readme" "/tmp/BOOTLD0E.SYS BOOTLOADER"   ← flashea bootloader
  S2I/A2/kernel/chrootfs.sh   → /tmp/chrootfs.sh   (4794 B)
  S2I/A2/kernel/BOOTOS0E.SYS  → /tmp/BOOTOS0E.SYS  (31098968 B)
  Deployment: "/tmp/chrootfs.sh" "KERNEL 240"               ← flashea kernel
"""

import sys
import time
from pathlib import Path

from hmi_uploader import HmiUploader, md5_hex


A2 = Path("/home/admin1/ote_analysis/recovery_a2")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.51"

    files = [
        ("/tmp/readme",         (A2 / "readme").read_bytes()),
        ("/tmp/BOOTLD0E.SYS",   (A2 / "BOOTLD0E.SYS").read_bytes()),
        ("/tmp/chrootfs.sh",    (A2 / "chrootfs.sh").read_bytes()),
        ("/tmp/BOOTOS0E.SYS",   (A2 / "BOOTOS0E.SYS").read_bytes()),
    ]
    total = sum(len(c) for _, c in files)
    print(f"=== Firmware deploy @ {host} ===")
    for p, c in files:
        print(f"  {p:25s} {len(c):>10d} B  md5={md5_hex(c)[:10]}")
    print(f"  TOTAL: {total} bytes\n")

    if "--confirm" not in sys.argv:
        print("Re-run con --confirm para ejecutar")
        sys.exit(0)

    client = HmiUploader(host)
    client.connect()
    try:
        print("--- Phase 1 — Handshake ---")
        client.full_handshake()

        # En recovery mode no hay project para validar, saltamos Phase 2
        print("\n--- Phase 4 — PrepareUpdate + DelFile ---")
        if not client.prepare_update(total):
            print("[FATAL] PrepareUpdate falló")
            return
        client.del_file("[clean_projectdata_folder]")
        client.check_transfer_size_0()

        print("\n--- Phase 5 — Transfer 4 firmware files ---")
        if not client.transfer_files(files):
            print("[FATAL] Transfer falló")
            return

        print("\n--- Phase 6a — Deploy BOOTLOADER ---")
        ok1 = client.deployment(
            "/tmp/BOOTLD0E.SYS BOOTLOADER",
            "/tmp/readme",
            timer=60,
        )
        print(f"  BOOTLOADER deploy: {'OK' if ok1 else 'FAIL'}")

        print("\n--- Phase 6b — Deploy KERNEL (chrootfs pivot) ---")
        ok2 = client.deployment(
            "KERNEL 240",
            "/tmp/chrootfs.sh",
            timer=60,
        )
        print(f"  KERNEL deploy: {'OK' if ok2 else 'FAIL'}")

        print("\n--- Phase 6c — FinalizeUpdate ---")
        resp = client.finalize_update()
        print(f"  resp: {resp}")
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        print("\n[OK] HMI flasheando — espera 5-10 min antes de power-cycle")


if __name__ == "__main__":
    main()
