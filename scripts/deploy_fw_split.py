#!/usr/bin/env python3
"""Deploy firmware en 2 fases separadas (BOOTLOADER → reboot → KERNEL)."""
import socket, time, sys, hashlib
sys.path.insert(0, '/home/admin1/Modbus_TCP_Communication')
from hmi_uploader import HmiUploader, md5_hex, send_length_prefix, CHUNK_SIZE
from hmi_protocol import msg, recv_msg
from pathlib import Path

HOST = "192.168.1.51"
A2 = Path("/home/admin1/ote_analysis/recovery_a2")

PHASES = {
    "A": {
        "files": [
            ("/tmp/readme",       (A2 / "readme").read_bytes()),
            ("/tmp/BOOTLD0E.SYS", (A2 / "BOOTLD0E.SYS").read_bytes()),
        ],
        "deploy_params": "/tmp/BOOTLD0E.SYS BOOTLOADER",
        "deploy_path": "/tmp/readme",
    },
    "B": {
        "files": [
            ("/tmp/chrootfs.sh",  (A2 / "chrootfs.sh").read_bytes()),
            ("/tmp/BOOTOS0E.SYS", (A2 / "BOOTOS0E.SYS").read_bytes()),
        ],
        "deploy_params": "KERNEL 240",
        "deploy_path": "/tmp/chrootfs.sh",
    },
}


def wait_3321(timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection((HOST, 3321), timeout=1)
            s.close()
            return True
        except Exception:
            pass
    return False


def deploy_phase(phase_name: str) -> bool:
    cfg = PHASES[phase_name]
    files = cfg["files"]
    total = sum(len(c) for _, c in files)
    print(f"\n{'='*60}\nPhase {phase_name}: {len(files)} archivos, {total} B\n{'='*60}")
    for p, c in files:
        print(f"  {p:25s} {len(c):>10d} B")

    # Connect persistently
    start = time.time()
    client = None
    while time.time() - start < 300:
        try:
            client = HmiUploader(HOST); client.connect()
            print(f"[{time.strftime('%H:%M:%S')}] Conectado")
            break
        except Exception:
            pass
    if not client:
        print(f"[{phase_name}] sin conexión"); return False

    try:
        # Mini-handshake
        client.send_xml('<CheckFctAvailability FunctionName="RT_VERSION_FORMAT_2" Purpose="Request"/>')
        client.send_xml('<CheckFctAvailability FunctionName="UPLOAD_V2" Purpose="Request"/>')

        # PrepareUpdate
        r = client.send_xml(f'<PrepareUpdate Owner="Target" FileSize="{total}" Purpose="Request" Pivot="0" OnlyApp="0"/>')
        if not r or 'true' not in r.lower():
            print(f"  PrepareUpdate fail: {r}"); return False
        client.send_xml('<DelFile FilePath="[clean_projectdata_folder]" Purpose="Request"/>')

        # Transfer
        upl_sock = None
        for file_path, content in files:
            crc = md5_hex(content) + "\r\n"
            req = f'<Transfer Owner="HMI" FilePath="{file_path}" FileSize="{len(content)}" Crc="{crc}" Purpose="Request"/>'
            resp = client.send_xml(req)
            if not resp or 'Result="1"' not in resp:
                print(f"  ✗ Transfer rejected for {file_path}: {resp}"); return False
            if upl_sock is None:
                time.sleep(0.05)
                upl_sock = socket.create_connection((HOST, 8050), timeout=10)
            nchunks = (len(content) + CHUNK_SIZE - 1) // CHUNK_SIZE
            for i in range(nchunks):
                chunk = content[i*CHUNK_SIZE:(i+1)*CHUNK_SIZE]
                send_length_prefix(upl_sock, chunk)
                time.sleep(0.005)
            ack = recv_msg(upl_sock, timeout=60)
            if not ack or 'Result="1"' not in ack:
                print(f"  ✗ ACK fail for {file_path}"); return False
            print(f"  ✓ {file_path:25s} ({nchunks} chunks)")
        send_length_prefix(upl_sock, b"SHUTDOWN")
        upl_sock.close()

        # Deployment + FinalizeUpdate
        r = client.send_xml(
            f'<Deployment Params="{cfg["deploy_params"]}" Owner="Target" '
            f'FilePath="{cfg["deploy_path"]}" Timer="60" Purpose="Request"/>'
        )
        print(f"  Deployment: {(r or '').strip()[:120]}")
        r = client.send_xml('<FinalizeUpdate Owner="Target" Purpose="Request"/>')
        print(f"  FinalizeUpdate: {(r or '').strip()[:120]}")
        return True
    finally:
        try: client.disconnect()
        except Exception: pass


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "A"
    if phase not in PHASES:
        print(f"Phase debe ser A o B"); sys.exit(1)
    if deploy_phase(phase):
        print(f"\n[OK] Phase {phase} completa — HMI rebootea")
    else:
        print(f"\n[FAIL] Phase {phase} falló")
