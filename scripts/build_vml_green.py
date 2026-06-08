#!/usr/bin/env python3
"""
Genera package_green.VML reemplazando Panel0.luac por la version verde,
manteniendo todos los demás archivos del VML del usuario sin tocar.
"""
import struct
import hashlib
from pathlib import Path


VML_IN = "/home/admin1/ote_analysis/vml_sample/package.vml"
PANEL0_GREEN = "/home/admin1/ote_analysis/samples/Panel0_green.luac"
VML_OUT = "/home/admin1/ote_analysis/vml_sample/package_green.vml"

TARGET_NAME = "application/Screens/Panel0.luac"


def parse_blocks(buf):
    blocks = []
    off = 0
    while off < len(buf) - 50:
        try:
            type_val = struct.unpack(">I", buf[off:off+4])[0]
            if type_val not in (1, 2, 3, 4, 5):
                off += 1; continue
            filesize = struct.unpack(">I", buf[off+4:off+8])[0]
            namelen = struct.unpack(">I", buf[off+8:off+12])[0]
            if namelen > 200 or namelen < 4 or namelen % 2 != 0:
                off += 1; continue
            if off + 12 + namelen + 37 + filesize > len(buf):
                off += 1; continue
            name = buf[off+12:off+12+namelen].decode("utf-16-be")
            marker = buf[off+12+namelen:off+12+namelen+4]
            sep = buf[off+12+namelen+4:off+12+namelen+5]
            md5 = buf[off+12+namelen+5:off+12+namelen+37]
            if marker != b'\x01\x00\x00\x00' or sep != b' ':
                off += 1; continue
            if not all(c in b'0123456789abcdef' for c in md5):
                off += 1; continue
            blocks.append({
                'offset': off, 'type': type_val, 'name': name,
                'filesize': filesize, 'namelen': namelen,
                'content_offset': off + 12 + namelen + 37,
                'block_size': 12 + namelen + 4 + 1 + 32 + filesize,
                'md5_declared': md5.decode(),
            })
            off += 12 + namelen + 4 + 1 + 32 + filesize
        except Exception:
            off += 1
    return blocks


def build_block(type_val: int, name: str, content: bytes) -> bytes:
    """Construye un bloque VML con el formato visto."""
    name_utf16 = name.encode("utf-16-be")
    md5_hex = hashlib.md5(content).hexdigest().encode("ascii")
    out = b""
    out += struct.pack(">I", type_val)
    out += struct.pack(">I", len(content))
    out += struct.pack(">I", len(name_utf16))
    out += name_utf16
    out += b'\x01\x00\x00\x00'
    out += b' '
    out += md5_hex
    out += content
    return out


def main():
    print("=== Cargando VML original ===")
    data = open(VML_IN, "rb").read()
    print(f"  Tamaño: {len(data)} bytes")

    green = open(PANEL0_GREEN, "rb").read()
    print(f"  Panel0_green.luac: {len(green)} bytes, md5={hashlib.md5(green).hexdigest()}")

    print("\n=== Localizando bloque application/Screens/Panel0.luac ===")
    blocks = parse_blocks(data)
    print(f"  Total bloques: {len(blocks)}")
    target = next((b for b in blocks if b['name'] == TARGET_NAME), None)
    if target is None:
        raise RuntimeError(f"No encontré {TARGET_NAME}")
    print(f"  Encontrado @ offset {target['offset']}, size {target['filesize']}")
    print(f"  MD5 original: {target['md5_declared']}")

    print("\n=== Generando bloque nuevo (verde) ===")
    new_block = build_block(target['type'], target['name'], green)
    print(f"  Nuevo bloque: {len(new_block)} bytes (anterior: {target['block_size']})")
    delta = len(new_block) - target['block_size']
    print(f"  Diferencia: {delta:+d} bytes")

    print("\n=== Construyendo VML modificado ===")
    pre = data[:target['offset']]
    post = data[target['offset'] + target['block_size']:]

    # Actualizar el xfile manifest al final si está en post
    # El manifest esta en CSV ASCII al final, buscar la linea de Panel0
    pre_md5 = target['md5_declared']
    new_md5 = hashlib.md5(green).hexdigest()
    post_text = post.decode('ascii', errors='replace')
    old_line = f",application/Screens/Panel0.luac,{target['filesize']},{pre_md5}"
    new_line = f",application/Screens/Panel0.luac,{len(green)},{new_md5}"
    if old_line in post_text:
        post_text = post_text.replace(old_line, new_line)
        print(f"  Manifest xfile actualizado: Panel0 {target['filesize']}→{len(green)} B, md5 {pre_md5[:8]}→{new_md5[:8]}")
        post = post_text.encode('ascii', errors='replace')
    else:
        print(f"  ⚠ Línea de Panel0 en manifest no encontrada — el VML puede no validarse")

    new_data = pre + new_block + post
    print(f"  Tamaño VML resultado: {len(new_data)} bytes (anterior: {len(data)}, delta: {len(new_data)-len(data):+d})")

    print(f"\n=== Guardando {VML_OUT} ===")
    open(VML_OUT, "wb").write(new_data)
    print(f"  Guardado: {Path(VML_OUT).stat().st_size} bytes")

    # Verificar re-parsing
    print("\n=== Verificando re-parsing ===")
    new_blocks = parse_blocks(new_data)
    print(f"  Bloques: {len(new_blocks)} (esperado {len(blocks)})")
    new_panel0 = next((b for b in new_blocks if b['name'] == TARGET_NAME), None)
    if new_panel0:
        print(f"  Panel0 verde: size={new_panel0['filesize']} md5={new_panel0['md5_declared'][:10]}")


if __name__ == "__main__":
    main()
