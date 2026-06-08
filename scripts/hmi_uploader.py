#!/usr/bin/env python3
"""
Schneider HMI Harmony — Uploader completo (6 fases del Transfer)

Reverse-engineered del pcap 604.pcapng del upload exitoso OTE 3.2 → HMIST6400.

Flujo verificado:
  Fase 1 — Handshake (puerto 3321, ~7 mensajes XML)
  Fase 2 — OTE conecta al HMI:8050 #1 y recibe el manifest actual
  Fase 3 — Metadata queries (DatabaseVersion, ExportData, PartitionInfo)
  Fase 4 — PrepareUpdate + DelFile (apaga UI, limpia)
  Fase 5 — Transfer file-by-file:
            - por cada archivo: XML Transfer Request por 3321
            - una sola conexión OTE→HMI:8050 #2 para mandar todos los archivos
              en serie, cada uno length-prefixed, con ACK <TSM> después de cada uno
  Fase 6 — Deployment + FinalizeUpdate (reboot)
"""

import hashlib
import re
import socket
import time

from hmi_protocol import HmiClient, msg, recv_msg, CTRL_PORT, STATE_PORT, TRANSFER_PORT

CHUNK_SIZE = 8187   # Schneider usa chunks de 8192-5=8187 bytes payload


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def chunked(content: bytes, chunk_size: int = CHUNK_SIZE):
    for off in range(0, len(content), chunk_size):
        yield content[off:off + chunk_size]


def send_length_prefix(sock: socket.socket, payload: bytes) -> None:
    """Manda un mensaje length-prefix Schneider (5-digit ASCII + content)."""
    sock.sendall(f"{len(payload):05d}".encode("ascii") + payload)


class HmiUploader(HmiClient):
    """Extiende HmiClient con las 5 fases adicionales del Transfer."""

    # ---------------- Fase 1 — handshake completo ----------------

    def full_handshake(self, project_id: str = "",
                        project_build_date: str = "",
                        project_version: str = ""):
        steps = [
            ('CheckFct RT_VERSION_FORMAT_2',
             '<CheckFctAvailability FunctionName="RT_VERSION_FORMAT_2" Purpose="Request"/>'),
            ('Identification',
             '<Identification Owner="Target" RTVersionFormat="2"/>'),
            ('CheckBrand',
             '<CheckBrand Owner="Target" Brand="Schneider Electric"/>'),
            ('CheckProjectID',
             f'<CheckProjectID ProjectVersion="{project_version}" '
             f'ProjectBuildDate="{project_build_date}" ProjectID="{project_id}"/>'),
            ('PasswordEnabled',
             '<PasswordEnabled Owner="Target" OutputMsg=""/>'),
            ('FileInfo xfile',
             '<FileInfo Owner="Target" FilePath="application/xfile" Purpose="Request"/>'),
            ('CheckFct UPLOAD_V2',
             '<CheckFctAvailability FunctionName="UPLOAD_V2" Purpose="Request"/>'),
        ]
        results = {}
        for name, xml in steps:
            resp = self.send_xml(xml)
            results[name] = resp
            print(f"  [P1] {name}: {(resp or '')[:80].strip()}")
            if resp is None:
                raise RuntimeError(f"No response at step {name}")
        return results

    # ---------------- Fase 2 — descargar manifest actual ----------------

    def download_manifest(self) -> bytes:
        """
        Phase 2: OTE conecta a HMI:8050 y recibe el xfile actual del HMI.
        Async — el HMI no responde al Upload por 3321 hasta que termine el
        flujo de la 8050.
        """
        resp = self.send_xml(
            f'<PrepareUpload Owner="Target" Port="{TRANSFER_PORT}" Purpose="Request"/>'
        )
        print(f"  [P2] PrepareUpload: {(resp or '').strip()[:120]}")

        # Abrir 8050
        upl_sock = socket.create_connection((self.host, TRANSFER_PORT), timeout=10)
        manifest = b""

        try:
            # Mandar Upload command por 3321 SIN esperar respuesta
            upload_xml = (
                '<TSM>\n <Upload IP="" Owner="Target" Port="0" '
                'FileName="application/xfile" Purpose="Request"/>\n</TSM>\n'
            )
            self.sock.sendall(msg(upload_xml))
            print(f"  [P2] Upload command enviado, esperando manifest por 8050…")

            # Leer manifest por 8050 (varios length-prefix chunks hasta que sea
            # un chunk vacio o demasiado largo o el HMI cierre)
            upl_sock.settimeout(8.0)
            while True:
                try:
                    chunk = recv_msg(upl_sock, timeout=5.0)
                except (socket.timeout, OSError):
                    break
                if chunk is None:
                    break
                # El xfile es texto ASCII (CSV manifest); paramos cuando llegue un
                # chunk pequeno o tras un timeout corto
                manifest += chunk.encode("ascii", errors="replace")
                if len(chunk) < CHUNK_SIZE:
                    break

            print(f"  [P2] Manifest recibido: {len(manifest)} bytes")

            # Mandar ACK + SHUTDOWN por 8050
            ack_xml = '<TSM>\n <Transfer IP="Transfer reception ending" Port="-1" Result="1"/>\n</TSM>\n'
            send_length_prefix(upl_sock, ack_xml.encode("ascii"))
            send_length_prefix(upl_sock, b"SHUTDOWN")

            # Ahora SÍ leer la respuesta del Upload por 3321
            upload_resp = recv_msg(self.sock, timeout=5.0)
            print(f"  [P2] Upload response (3321): {(upload_resp or '').strip()[:80]}")
        finally:
            try:
                upl_sock.close()
            except Exception:
                pass
        return manifest

    # ---------------- Fase 3 — metadata ----------------

    def query_metadata(self) -> None:
        for xml in [
            '<CheckFctAvailability FunctionName="DatabaseVersion" Purpose="Request"/>',
            '<DatabaseVersion name="UserManagement" Owner="Target" Purpose="Request"/>',
            '<CheckFctAvailability FunctionName="ExportData" Purpose="Request"/>',
            '<ExportData Owner="HMI" Timer="15" Purpose="Request"/>',
            '<PartitionInfo Name="" Owner="HMI" Purpose="Request"/>',
        ]:
            self.send_xml(xml)
        print(f"  [P3] Metadata queries OK")

    # ---------------- Fase 4 — Prepare + Clean ----------------

    def prepare_update(self, file_size: int, pivot: int = 0, only_app: int = 0) -> bool:
        resp = self.send_xml(
            f'<PrepareUpdate Owner="Target" FileSize="{file_size}" '
            f'Purpose="Request" Pivot="{pivot}" OnlyApp="{only_app}"/>'
        )
        ok = resp is not None and 'true' in (resp or '').lower()
        print(f"  [P4] PrepareUpdate({file_size}): {(resp or '').strip()[:80]} → {'OK' if ok else 'FAIL'}")
        return ok

    def del_file(self, path: str = "[clean_projectdata_folder]") -> bool:
        resp = self.send_xml(f'<DelFile FilePath="{path}" Purpose="Request"/>')
        ok = resp is not None and 'true' in (resp or '').lower()
        print(f"  [P4] DelFile({path}): {(resp or '').strip()[:80]} → {'OK' if ok else 'FAIL'}")
        return ok

    def check_transfer_size_0(self) -> None:
        self.send_xml('<CheckFctAvailability FunctionName="TRANSFER_SIZE_0" Purpose="Request"/>')

    # ---------------- Fase 5 — Transfer file ----------------

    def transfer_files(self, files: list[tuple[str, bytes]]) -> bool:
        """
        Phase 5: por cada archivo:
          - OTE manda <Transfer> request por 3321
          - HMI responde con IP+Port (siempre 8050)
          - OTE abre conexión OTE→HMI:8050 (la primera vez) y reusa para los siguientes
          - OTE manda el contenido en chunks length-prefix por la conexión 8050
          - HMI manda ACK <TSM><Transfer Result=1.../></TSM> por la 8050
        """
        upl_sock: socket.socket | None = None
        try:
            for file_path, content in files:
                file_size = len(content)
                crc = md5_hex(content) + "\r\n"
                req = (
                    f'<Transfer Owner="HMI" FilePath="{file_path}" '
                    f'FileSize="{file_size}" Crc="{crc}" Purpose="Request"/>'
                )
                resp = self.send_xml(req)
                if not resp or 'Result="1"' not in resp:
                    print(f"  [P5] ✗ Transfer rechazado para {file_path}: {resp}")
                    return False

                # El HMI acaba de aceptar el Transfer y abrió el 8050 — conectar
                # la primera vez y reusar.
                if upl_sock is None:
                    # Pequena pausa para que el HMI levante el listener
                    time.sleep(0.05)
                    upl_sock = socket.create_connection(
                        (self.host, TRANSFER_PORT), timeout=10
                    )

                for chunk in chunked(content, CHUNK_SIZE):
                    send_length_prefix(upl_sock, chunk)
                    time.sleep(0.005)  # 5ms throttle para no saturar HMI recovery

                ack = recv_msg(upl_sock, timeout=30)
                if not ack or 'Result="1"' not in ack:
                    print(f"  [P5] ✗ ACK inesperado para {file_path}: {ack}")
                    return False

                print(f"  [P5] ✓ {file_path:50s} ({file_size:6d} B)")

            if upl_sock is not None:
                send_length_prefix(upl_sock, b"SHUTDOWN")
        finally:
            if upl_sock is not None:
                try:
                    upl_sock.close()
                except Exception:
                    pass
        return True

    # ---------------- Fase 6 — Deployment + Finalize ----------------

    def deployment(self, params: str, file_path: str, timer: int = 60) -> bool:
        resp = self.send_xml(
            f'<Deployment Params="{params}" Owner="Target" '
            f'FilePath="{file_path}" Timer="{timer}" Purpose="Request"/>'
        )
        ok = resp is not None and 'Result="1"' in (resp or '')
        print(f"  [P6] Deployment: {(resp or '').strip()[:80]} → {'OK' if ok else 'FAIL'}")
        return ok

    def finalize_update(self) -> str | None:
        resp = self.send_xml('<FinalizeUpdate Owner="Target" Purpose="Request"/>')
        print(f"  [P6] FinalizeUpdate: {(resp or '').strip()[:80]}")
        return resp


# ---------------------------------------------------------------------------
# Helper para actualizar el xfile manifest
# ---------------------------------------------------------------------------

def update_xfile_entry(xfile_text: str, file_path: str, new_content: bytes) -> str:
    """Devuelve el xfile con el size/md5 de file_path actualizado."""
    new_size = len(new_content)
    new_md5 = md5_hex(new_content)
    lines = xfile_text.split("\n")
    out = []
    found = False
    for line in lines:
        if f",{file_path}," in line:
            parts = line.split(",")
            if len(parts) >= 4:
                parts[2] = str(new_size)
                parts[3] = new_md5
                out.append(",".join(parts))
                found = True
                continue
        out.append(line)
    if not found:
        raise ValueError(f"{file_path} no aparece en xfile manifest")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Demo: handshake + metadata (sin Phase 4-6 destructivas)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.51"

    print(f"=== HMI Uploader — Phase 1 + 2 + 3 only (NO destructive) @ {host} ===\n")

    client = HmiUploader(host)
    client.connect()
    try:
        print("--- Phase 1 — Handshake ---")
        results = client.full_handshake()
        ident = results.get('Identification', '')
        m = re.search(r'TargetId="(\d+)"', ident)
        print(f"\n→ Target HMI: TargetId={m.group(1) if m else '?'}")

        print("\n--- Phase 2 — Download manifest ---")
        manifest = client.download_manifest()
        if manifest:
            preview = manifest.decode('ascii', errors='replace')[:300]
            print(f"\n  Manifest preview:\n{preview}\n")

        print("--- Phase 3 — Metadata ---")
        client.query_metadata()

        print("\n[OK] Phases 1-3 completas — HMI NO modificado")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        client.disconnect()
        print("[OK] Disconnect limpio")
