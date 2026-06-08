#!/usr/bin/env python3
"""
Deploy Panel0 verde al HMI usando conexión por comando (el nuevo proyecto del
usuario tiene comportamiento stateless en 3321).
"""
import socket, time, hashlib
from pathlib import Path
import re, sys

sys.path.insert(0, '/home/admin1/Modbus_TCP_Communication')
from hmi_protocol import msg, recv_msg
from hmi_uploader import md5_hex, send_length_prefix, CHUNK_SIZE

HOST = "192.168.1.51"
PANEL0_GREEN = "/home/admin1/ote_analysis/samples/Panel0_chanti.luac"
EXTRACTED = Path("/home/admin1/ote_analysis/extracted_files")


def cmd(xml: str, retries: int = 30) -> str | None:
    """Una conexión, un comando, una respuesta. Reintenta hasta conectar."""
    for _ in range(retries):
        try:
            s = socket.create_connection((HOST, 3321), timeout=2)
            payload = f"<TSM>\n {xml}\n</TSM>\n"
            s.sendall(msg(payload))
            resp = recv_msg(s, timeout=5)
            s.close()
            return resp
        except Exception:
            time.sleep(0.1)
    return None


def transfer_one(file_path: str, content: bytes) -> bool:
    """Hace Transfer XML + envía contenido por nueva conexión 8050."""
    crc = md5_hex(content) + "\r\n"
    req = (
        f'<Transfer Owner="HMI" FilePath="{file_path}" '
        f'FileSize="{len(content)}" Crc="{crc}" Purpose="Request"/>'
    )
    resp = cmd(req)
    if not resp or 'Result="1"' not in resp:
        print(f"  ✗ Transfer rechazado para {file_path}: {(resp or '')[:200]}")
        return False
    # Esperar que 8050 abra con polling agresivo
    upl_sock = None
    start = time.time()
    while time.time() - start < 15:
        try:
            upl_sock = socket.create_connection((HOST, 8050), timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    if upl_sock is None:
        print(f"  ✗ 8050 no abrió para {file_path} (timeout 15s)")
        return False
    try:
        for i in range(0, len(content), CHUNK_SIZE):
            send_length_prefix(upl_sock, content[i:i+CHUNK_SIZE])
            time.sleep(0.005)
        ack = recv_msg(upl_sock, timeout=60)
        if ack and 'Result="1"' in ack:
            print(f"  ✓ {file_path:50s} ({len(content)} B)")
            return True
        else:
            print(f"  ✗ ACK inesperado: {(ack or '')[:120]}")
            return False
    finally:
        try: upl_sock.close()
        except: pass


def main():
    print("=== HMI handshake (one-shot por comando) ===")
    print(f"  CheckFct RT_VERSION_FORMAT_2: {(cmd('<CheckFctAvailability FunctionName=' + chr(34) + 'RT_VERSION_FORMAT_2' + chr(34) + ' Purpose=' + chr(34) + 'Request' + chr(34) + '/>') or '')[:80]}")
    print(f"  Identification:               {(cmd('<Identification Owner=' + chr(34) + 'Target' + chr(34) + ' RTVersionFormat=' + chr(34) + '2' + chr(34) + '/>') or '')[:80]}")
    print(f"  CheckBrand:                   {(cmd('<CheckBrand Owner=' + chr(34) + 'Target' + chr(34) + ' Brand=' + chr(34) + 'Schneider Electric' + chr(34) + '/>') or '')[:80]}")
    print(f"  PasswordEnabled:              {(cmd('<PasswordEnabled Owner=' + chr(34) + 'Target' + chr(34) + ' OutputMsg=' + chr(34) + chr(34) + '/>') or '')[:80]}")
    print(f"  CheckFct UPLOAD_V2:           {(cmd('<CheckFctAvailability FunctionName=' + chr(34) + 'UPLOAD_V2' + chr(34) + ' Purpose=' + chr(34) + 'Request' + chr(34) + '/>') or '')[:80]}")

    # Cargar Panel0 verde
    green = open(PANEL0_GREEN, "rb").read()
    green_md5 = md5_hex(green)
    print(f"\n=== Panel0_user_green.luac: {len(green)} B md5={green_md5} ===")

    # Construir un xfile manifest MÍNIMO actualizando solo Panel0
    # Usamos el del pcap original (extracted_files/xfile) como base — referencia los archivos
    # del proyecto que estaba antes en el HMI
    # NOTA: idealmente descargaríamos el manifest actual pero el HMI cierra rápido
    # Solo cambiamos el line de Panel0
    xfile_orig = open("/home/admin1/ote_analysis/samples/xfile_user.txt").read()
    xfile_new = re.sub(
        r",application/Screens/Panel0\.luac,\d+,[0-9a-f]+",
        f",application/Screens/Panel0.luac,{len(green)},{green_md5}",
        xfile_orig,
    )
    xfile_bytes = xfile_new.encode("ascii")
    print(f"  xfile (nuevo): {len(xfile_bytes)} B md5={md5_hex(xfile_bytes)}")

    if "--confirm" not in sys.argv:
        print("\nRe-run con --confirm para ejecutar el deploy")
        return

    print("\n=== PrepareUpdate + DelFile ===")
    total = len(green) + len(xfile_bytes)
    print(f"  PrepareUpdate({total}): {(cmd(f'<PrepareUpdate Owner=' + chr(34) + 'Target' + chr(34) + f' FileSize=' + chr(34) + str(total) + chr(34) + f' Purpose=' + chr(34) + 'Request' + chr(34) + f' Pivot=' + chr(34) + '0' + chr(34) + f' OnlyApp=' + chr(34) + '0' + chr(34) + '/>') or '')[:80]}")
    print(f"  DelFile:                {(cmd('<DelFile FilePath=' + chr(34) + '[clean_projectdata_folder]' + chr(34) + ' Purpose=' + chr(34) + 'Request' + chr(34) + '/>') or '')[:80]}")
    print(f"  TRANSFER_SIZE_0:        {(cmd('<CheckFctAvailability FunctionName=' + chr(34) + 'TRANSFER_SIZE_0' + chr(34) + ' Purpose=' + chr(34) + 'Request' + chr(34) + '/>') or '')[:80]}")

    print("\n=== Transfer files ===")
    if not transfer_one("application/Screens/Panel0.luac", green):
        print("[FAIL] Panel0 transfer failed"); return
    if not transfer_one("application/xfile", xfile_bytes):
        print("[FAIL] xfile transfer failed"); return

    print("\n=== Finalizar ===")
    print(f"  FinalizeUpdate: {(cmd('<FinalizeUpdate Owner=' + chr(34) + 'Target' + chr(34) + ' Purpose=' + chr(34) + 'Request' + chr(34) + '/>') or '')[:80]}")
    print("\n[OK] HMI rebooteando")


if __name__ == "__main__":
    main()
