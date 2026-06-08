#!/usr/bin/env python3
"""
Schneider HMI Harmony (HMIST6 series) — Protocolo OTE↔HMI

Reverse-engineered desde captura Wireshark del upload real OTE 3.2 → HMIST6400.
Documenta el protocolo completo de comunicación y transferencia de proyecto.

Arquitectura:
  Puerto 3320 (TCP) — State broadcast del HMI (banner XML al conectar)
  Puerto 3321 (TCP) — Control XML (handshake + comandos)
  Puerto 8050 (TCP) — Transfer de archivos (binario raw + XML de control)

Pre-requisito:
  El HMI debe tener "Ethernet Download" habilitado en su menú de configuración.
  Sin eso, los puertos TCP están cerrados.

Formato de mensajes XML:
  - Length-prefix: 5 dígitos ASCII con el largo en bytes del XML que sigue
  - Wrapper: <TSM>...</TSM>
  - Comando como elemento hijo con atributos
  - Cliente usa Owner="Target" y Purpose="Request"
  - Servidor responde con Purpose="Response" + Result="1" (o "true"/"false")

Ejemplo:
  → "00091<TSM>\\n <CheckFctAvailability FunctionName=\\"RT_VERSION_FORMAT_2\\" Purpose=\\"Request\\"/>\\n</TSM>\\n"
  ← "00071<TSM>\\n <CheckFctAvailability Purpose=\\"Response\\" Result=\\"true\\"/>\\n</TSM>\\n"
"""

import socket
import time

CTRL_PORT     = 3321
STATE_PORT    = 3320
TRANSFER_PORT = 8050   # se negocia con PrepareUpload


def msg(xml: str) -> bytes:
    """Construye un mensaje length-prefix XML (formato Schneider TSM)."""
    body = xml.encode("ascii")
    return f"{len(body):05d}".encode("ascii") + body


def recv_msg(sock: socket.socket, timeout: float = 5.0) -> str | None:
    """Lee un mensaje completo length-prefix XML."""
    sock.settimeout(timeout)
    prefix = b""
    while len(prefix) < 5:
        chunk = sock.recv(5 - len(prefix))
        if not chunk:
            return None
        prefix += chunk
    length = int(prefix.decode("ascii"))
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            break
        body += chunk
    return body.decode("ascii", errors="replace")


class HmiClient:
    """Cliente Schneider HMI Harmony — replica el protocolo de OTE 3.2."""

    def __init__(self, host: str, ctrl_port: int = CTRL_PORT):
        self.host = host
        self.ctrl_port = ctrl_port
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.ctrl_port), timeout=5)

    def disconnect(self) -> None:
        if self.sock:
            try:
                self.send_xml('<Disconnect IP="0.0.0.0"/>')
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_xml(self, body: str) -> str | None:
        """Envía un comando XML envuelto en <TSM> y lee la respuesta."""
        if not self.sock:
            raise RuntimeError("Not connected")
        payload = f"<TSM>\n {body}\n</TSM>\n"
        self.sock.sendall(msg(payload))
        return recv_msg(self.sock)

    # ----- Comandos individuales (handshake básico) -----

    def check_fct_availability(self, function_name: str) -> str | None:
        return self.send_xml(
            f'<CheckFctAvailability FunctionName="{function_name}" Purpose="Request"/>'
        )

    def identification(self) -> str | None:
        return self.send_xml(
            '<Identification Owner="Target" RTVersionFormat="2"/>'
        )

    def check_brand(self, brand: str = "Schneider Electric") -> str | None:
        return self.send_xml(
            f'<CheckBrand Owner="Target" Brand="{brand}"/>'
        )

    def check_project_id(self, project_id: str = "",
                          build_date: str = "",
                          version: str = "") -> str | None:
        return self.send_xml(
            f'<CheckProjectID ProjectVersion="{version}" '
            f'ProjectBuildDate="{build_date}" ProjectID="{project_id}"/>'
        )

    def password_enabled(self) -> str | None:
        return self.send_xml(
            '<PasswordEnabled Owner="Target" OutputMsg=""/>'
        )

    def file_info(self, file_path: str = "application/xfile") -> str | None:
        return self.send_xml(
            f'<FileInfo Owner="Target" FilePath="{file_path}" Purpose="Request"/>'
        )

    def partition_info(self) -> str | None:
        return self.send_xml(
            '<PartitionInfo Name="" Owner="HMI" Purpose="Request"/>'
        )

    def export_data(self, timer: int = 15) -> str | None:
        return self.send_xml(
            f'<ExportData Owner="HMI" Timer="{timer}" Purpose="Request"/>'
        )

    def state_query(self) -> str | None:
        """Lee el banner inicial del puerto 3320 (state actual)."""
        with socket.create_connection((self.host, STATE_PORT), timeout=3) as s:
            return recv_msg(s, timeout=3)


# ---------------------------------------------------------------------------
# Demo: handshake completo solo lectura (no modifica el HMI)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.51"

    print(f"=== HMI Schneider Harmony @ {host} ===\n")

    client = HmiClient(host)

    print("[1] State broadcast (puerto 3320):")
    print(client.state_query())
    print()

    print("[2] Conectando puerto 3321 …")
    client.connect()

    print("[3] CheckFctAvailability RT_VERSION_FORMAT_2:")
    print(client.check_fct_availability("RT_VERSION_FORMAT_2"))
    print()

    print("[4] Identification:")
    print(client.identification())
    print()

    print("[5] CheckBrand:")
    print(client.check_brand("Schneider Electric"))
    print()

    print("[6] CheckProjectID (vacío — solo query):")
    print(client.check_project_id())
    print()

    print("[7] PasswordEnabled:")
    print(client.password_enabled())
    print()

    print("[8] FileInfo application/xfile:")
    print(client.file_info())
    print()

    print("[9] PartitionInfo:")
    print(client.partition_info())
    print()

    print("[10] Disconnect")
    client.disconnect()
    print("Done.")
