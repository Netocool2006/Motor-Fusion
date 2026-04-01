# -*- coding: utf-8 -*-
"""
file_extractor.py -- Extractor de contenido de archivos (solo stdlib)
=====================================================================
Extrae texto de multiples formatos de archivo usando solo la biblioteca
estandar de Python. No requiere pip install ni internet.

Formatos soportados:
  TEXTO PLANO:  .txt, .md, .csv, .tsv, .log, .ini, .cfg, .yaml, .yml,
                .toml, .json, .xml, .html, .css
  CODIGO:       .py, .js, .ts, .java, .go, .rs, .c, .cpp, .h, .cs,
                .rb, .php, .sh, .bat, .ps1, .r, .jl, .sql
  OFFICE (ZIP): .docx, .xlsx, .pptx (se leen como ZIP de XML)
  PDF:          .pdf (extraccion basica sin libreria externa)

Limitaciones (sin librerias externas):
  - .doc (Word binario antiguo): no soportado
  - .xls (Excel binario antiguo): no soportado
  - .pdf: extraccion basica (solo texto plano embebido, no OCR)
  - Archivos protegidos con password: no soportados

API:
  extract_text(file_path, max_chars=5000) -> str
  can_extract(file_path) -> bool
  supported_extensions() -> set[str]
  chunk_text(text, chunk_size=800, overlap=100) -> list[str]
"""

import os
import re
import json
import csv
import zipfile
import io
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# -- Constantes ---------------------------------------------------------------
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB maximo por archivo
MAX_CHARS_DEFAULT = 5000

# Extensiones de texto plano (leer directo)
TEXT_EXTENSIONS = {
    '.txt', '.md', '.csv', '.tsv', '.log', '.ini', '.cfg',
    '.yaml', '.yml', '.toml', '.json', '.xml', '.html', '.css',
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php',
    '.sh', '.bat', '.ps1', '.r', '.jl', '.sql',
    '.env.example', '.gitignore', '.dockerignore',
    '.rst', '.tex', '.org', '.adoc',
}

# Extensiones Office (ZIP de XML)
OFFICE_EXTENSIONS = {'.docx', '.xlsx', '.pptx'}

# PDF
PDF_EXTENSIONS = {'.pdf'}

# Extensiones que NO podemos leer (binarios antiguos)
UNSUPPORTED_BINARY = {'.doc', '.xls', '.ppt', '.odt', '.ods', '.odp'}


# =============================================================================
# Funciones publicas de consulta
# =============================================================================

def supported_extensions() -> set:
    """Retorna el conjunto de todas las extensiones soportadas."""
    return TEXT_EXTENSIONS | OFFICE_EXTENSIONS | PDF_EXTENSIONS


def can_extract(file_path) -> bool:
    """
    Verifica si podemos extraer texto del archivo dado.

    Condiciones:
      - El archivo existe
      - La extension esta soportada
      - El tamano no excede MAX_FILE_SIZE
    """
    try:
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return False
        ext = p.suffix.lower()
        if ext not in supported_extensions():
            return False
        if p.stat().st_size > MAX_FILE_SIZE:
            return False
        return True
    except (OSError, PermissionError):
        return False


# =============================================================================
# Lectores internos
# =============================================================================

def _read_text_file(path: Path, max_chars: int) -> str:
    """
    Lee un archivo de texto plano.
    Usa utf-8 con errors=ignore para tolerar archivos con encoding mixto.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except (OSError, PermissionError, UnicodeDecodeError):
        return ""


def _read_docx(path: Path, max_chars: int) -> str:
    """
    Lee un archivo .docx extrayendo texto de word/document.xml.

    Los .docx son archivos ZIP que contienen XML.
    Estructura relevante:
      word/document.xml -> <w:body> -> <w:p> (parrafos) -> <w:r> (runs) -> <w:t> (texto)
      Tambien maneja tablas: <w:tbl> -> <w:tr> -> <w:tc> -> <w:p> -> <w:r> -> <w:t>
    """
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    try:
        with zipfile.ZipFile(str(path), 'r') as zf:
            # Verificar que el archivo de documento existe
            if 'word/document.xml' not in zf.namelist():
                return ""

            xml_data = zf.read('word/document.xml')
            root = ET.fromstring(xml_data)

        # Extraer texto de todos los elementos <w:t> agrupados por parrafo <w:p>
        paragraphs = []
        for para in root.iter('{%s}p' % ns['w']):
            texts = []
            for t_elem in para.iter('{%s}t' % ns['w']):
                if t_elem.text:
                    texts.append(t_elem.text)
            if texts:
                paragraphs.append("".join(texts))

        result = "\n".join(paragraphs)
        return result[:max_chars]

    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
        return ""


def _read_xlsx(path: Path, max_chars: int) -> str:
    """
    Lee un archivo .xlsx extrayendo datos de la primera hoja.

    Los .xlsx son archivos ZIP. Estructura:
      xl/sharedStrings.xml -> tabla de strings compartidos
      xl/worksheets/sheet1.xml -> datos de la primera hoja

    Las celdas con type="s" referencian un indice en sharedStrings.
    Las celdas sin type (o type="n") contienen valor numerico directo.
    """
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    try:
        with zipfile.ZipFile(str(path), 'r') as zf:
            names = zf.namelist()

            # -- Paso 1: Leer tabla de strings compartidos --
            shared_strings = []
            if 'xl/sharedStrings.xml' in names:
                ss_data = zf.read('xl/sharedStrings.xml')
                ss_root = ET.fromstring(ss_data)
                # Cada <si> puede tener <t> directo o <r><t> (rich text)
                for si in ss_root.iter('{%s}si' % ns):
                    parts = []
                    for t_elem in si.iter('{%s}t' % ns):
                        if t_elem.text:
                            parts.append(t_elem.text)
                    shared_strings.append("".join(parts))

            # -- Paso 2: Encontrar la primera hoja --
            sheet_file = None
            # Intentar sheet1.xml primero
            if 'xl/worksheets/sheet1.xml' in names:
                sheet_file = 'xl/worksheets/sheet1.xml'
            else:
                # Buscar cualquier sheet*.xml
                for n in sorted(names):
                    if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'):
                        sheet_file = n
                        break

            if not sheet_file:
                return ""

            sheet_data = zf.read(sheet_file)
            sheet_root = ET.fromstring(sheet_data)

        # -- Paso 3: Extraer filas y celdas --
        rows_text = []
        total_chars = 0

        for row in sheet_root.iter('{%s}row' % ns):
            cells = []
            for cell in row.iter('{%s}c' % ns):
                cell_type = cell.get('t', '')
                # Buscar el elemento <v> (valor)
                v_elem = cell.find('{%s}v' % ns)
                cell_value = ""

                if v_elem is not None and v_elem.text:
                    if cell_type == 's':
                        # Referencia a shared string
                        try:
                            idx = int(v_elem.text)
                            if 0 <= idx < len(shared_strings):
                                cell_value = shared_strings[idx]
                        except (ValueError, IndexError):
                            cell_value = v_elem.text
                    elif cell_type == 'inlineStr':
                        # String inline: buscar <is><t>
                        is_elem = cell.find('{%s}is' % ns)
                        if is_elem is not None:
                            t_elem = is_elem.find('{%s}t' % ns)
                            if t_elem is not None and t_elem.text:
                                cell_value = t_elem.text
                    else:
                        # Valor numerico o directo
                        cell_value = v_elem.text
                else:
                    # Celda sin <v>: podria ser inline string
                    is_elem = cell.find('{%s}is' % ns)
                    if is_elem is not None:
                        t_elem = is_elem.find('{%s}t' % ns)
                        if t_elem is not None and t_elem.text:
                            cell_value = t_elem.text

                cells.append(cell_value)

            if cells:
                row_str = "\t".join(cells)
                total_chars += len(row_str) + 1
                if total_chars > max_chars:
                    # Agregar lo que quepa y cortar
                    remaining = max_chars - (total_chars - len(row_str) - 1)
                    if remaining > 0:
                        rows_text.append(row_str[:remaining])
                    break
                rows_text.append(row_str)

        return "\n".join(rows_text)

    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError, ValueError):
        return ""


def _read_pptx(path: Path, max_chars: int) -> str:
    """
    Lee un archivo .pptx extrayendo texto de todas las diapositivas.

    Los .pptx son archivos ZIP. Estructura:
      ppt/slides/slide1.xml, slide2.xml, ...
      Texto en elementos <a:t> dentro de cada slide.
    """
    ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'

    try:
        with zipfile.ZipFile(str(path), 'r') as zf:
            names = zf.namelist()

            # Encontrar todos los slides, ordenados numericamente
            slide_files = []
            for n in names:
                if re.match(r'^ppt/slides/slide\d+\.xml$', n):
                    slide_files.append(n)

            # Ordenar por numero de slide
            slide_files.sort(key=lambda x: int(re.search(r'slide(\d+)', x).group(1)))

            if not slide_files:
                return ""

            slides_text = []
            total_chars = 0

            for i, slide_file in enumerate(slide_files, start=1):
                slide_data = zf.read(slide_file)
                slide_root = ET.fromstring(slide_data)

                # Extraer todos los <a:t> del slide
                texts = []
                for t_elem in slide_root.iter('{%s}t' % ns_a):
                    if t_elem.text:
                        texts.append(t_elem.text)

                if texts:
                    slide_str = "Slide %d:\n%s" % (i, " ".join(texts))
                else:
                    slide_str = "Slide %d:\n(sin texto)" % i

                total_chars += len(slide_str) + 2
                if total_chars > max_chars:
                    remaining = max_chars - (total_chars - len(slide_str) - 2)
                    if remaining > 0:
                        slides_text.append(slide_str[:remaining])
                    break
                slides_text.append(slide_str)

        return "\n\n".join(slides_text)

    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
        return ""


def _read_pdf_basic(path: Path, max_chars: int) -> str:
    """
    Extraccion basica de texto de PDF sin librerias externas.

    Estrategia:
      1. Intentar PyPDF2 o pypdf si estan disponibles (mejor calidad)
      2. Fallback: buscar texto entre parentesis () en el contenido raw
         y texto en bloques BT/ET (operadores de texto PDF)

    Limitacion: la extraccion raw es muy basica y no funciona con todos los PDFs.
    """
    # -- Intento 1: Usar PyPDF2 o pypdf si estan instalados --
    text = _try_pypdf(path, max_chars)
    if text and len(text.strip()) > 20:
        return text[:max_chars]

    # -- Intento 2: Extraccion raw basica --
    try:
        file_size = path.stat().st_size
        with open(path, "rb") as f:
            raw = f.read(min(file_size, MAX_FILE_SIZE))

        extracted_parts = []

        # Metodo A: Buscar texto entre parentesis en operadores de texto
        # Los operadores Tj y TJ contienen texto entre parentesis
        # Ejemplo: (Hello World) Tj
        paren_texts = re.findall(rb'\(([^)]{1,500})\)', raw)
        for pt in paren_texts:
            try:
                decoded = pt.decode('utf-8', errors='ignore')
                # Filtrar basura: solo si tiene caracteres imprimibles
                printable = ''.join(c for c in decoded if c.isprintable() or c in '\n\r\t')
                if len(printable) >= 2:
                    extracted_parts.append(printable)
            except Exception:
                continue

        # Metodo B: Buscar streams decodificados con texto legible
        # Algunos PDFs simples tienen texto plano en los streams
        stream_pattern = re.compile(rb'stream\r?\n(.+?)\r?\nendstream', re.DOTALL)
        for match in stream_pattern.finditer(raw):
            stream_data = match.group(1)
            # Solo intentar si parece texto (no binario comprimido)
            if len(stream_data) < 10000:
                try:
                    text_candidate = stream_data.decode('utf-8', errors='ignore')
                    # Buscar texto entre parentesis dentro del stream
                    inner_texts = re.findall(r'\(([^)]{2,500})\)', text_candidate)
                    for it in inner_texts:
                        printable = ''.join(c for c in it if c.isprintable() or c in '\n\r\t')
                        if len(printable) >= 2:
                            extracted_parts.append(printable)
                except Exception:
                    continue

        if extracted_parts:
            # Deduplicar manteniendo orden
            seen = set()
            unique = []
            for part in extracted_parts:
                if part not in seen:
                    seen.add(part)
                    unique.append(part)

            result = " ".join(unique)
            # Limpiar espacios excesivos
            result = re.sub(r'\s+', ' ', result).strip()
            if len(result) > 20:
                return result[:max_chars]

        # Si no se pudo extraer nada util
        filename = path.name
        size_kb = file_size / 1024
        return (
            "[PDF: contenido no extraible sin libreria externa. "
            "Archivo: %s, Tamano: %.1f KB]" % (filename, size_kb)
        )

    except (OSError, PermissionError):
        return ""


def _try_pypdf(path: Path, max_chars: int) -> str:
    """
    Intenta usar PyPDF2 o pypdf para extraer texto (si estan instalados).
    Retorna string vacio si no estan disponibles.
    """
    # Intentar pypdf (version moderna)
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except ImportError:
        pass
    except Exception:
        pass

    # Intentar PyPDF2 (version antigua)
    try:
        from PyPDF2 import PdfReader  # noqa: F811
        reader = PdfReader(str(path))
        parts = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except ImportError:
        pass
    except Exception:
        pass

    return ""


# =============================================================================
# API publica principal
# =============================================================================

def extract_text(file_path, max_chars: int = MAX_CHARS_DEFAULT) -> str:
    """
    Extrae texto de un archivo, despachando al lector apropiado.

    Args:
        file_path: Ruta al archivo (str o Path).
        max_chars: Maximo de caracteres a retornar (default 5000).

    Returns:
        Texto extraido. String vacio si falla o no soportado.
    """
    try:
        p = Path(file_path)

        if not can_extract(p):
            return ""

        ext = p.suffix.lower()

        # Despachar al lector correcto
        if ext in TEXT_EXTENSIONS:
            text = _read_text_file(p, max_chars)
        elif ext == '.docx':
            text = _read_docx(p, max_chars)
        elif ext == '.xlsx':
            text = _read_xlsx(p, max_chars)
        elif ext == '.pptx':
            text = _read_pptx(p, max_chars)
        elif ext == '.pdf':
            text = _read_pdf_basic(p, max_chars)
        else:
            return ""

        # Limpiar espacios excesivos (multiples lineas vacias -> una)
        if text:
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.strip()

        return text

    except Exception:
        return ""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """
    Divide texto en chunks con solapamiento, cortando en limites de oracion.

    Args:
        text:       Texto a dividir.
        chunk_size: Tamano maximo de cada chunk en caracteres.
        overlap:    Caracteres de solapamiento entre chunks consecutivos.

    Returns:
        Lista de strings (chunks). Si text es mas corto que chunk_size,
        retorna [text].
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # Ultimo chunk: tomar todo lo que queda
            chunks.append(text[start:])
            break

        # Intentar cortar en un limite de oracion dentro del ultimo 20%
        # del chunk para no cortar a mitad de frase
        search_start = start + int(chunk_size * 0.8)
        search_region = text[search_start:end]

        # Buscar el ultimo punto de corte natural (. ! ? o \n)
        best_cut = -1
        for pattern in ['. ', '! ', '? ', '.\n', '!\n', '?\n', '\n']:
            idx = search_region.rfind(pattern)
            if idx != -1:
                # Posicion absoluta del corte (despues del caracter de puntuacion)
                candidate = search_start + idx + len(pattern)
                if candidate > best_cut:
                    best_cut = candidate

        if best_cut > start:
            end = best_cut

        chunks.append(text[start:end])

        # Siguiente chunk empieza con solapamiento
        start = end - overlap
        if start <= (end - chunk_size):
            # Evitar loop infinito si overlap >= chunk_size
            start = end

    return chunks


# =============================================================================
# CLI
# =============================================================================

def _cli_extract(args):
    """Subcomando: extraer texto de un archivo."""
    if not args:
        print("Error: especificar ruta de archivo")
        print("  python file_extractor.py extract \"ruta/al/archivo.docx\"")
        sys.exit(1)

    file_path = args[0]
    max_chars = MAX_CHARS_DEFAULT

    # Parsear --max-chars si viene
    if len(args) >= 3 and args[1] == '--max-chars':
        try:
            max_chars = int(args[2])
        except ValueError:
            print("Error: --max-chars debe ser un numero entero")
            sys.exit(1)

    p = Path(file_path)
    if not p.exists():
        print("Error: archivo no encontrado: %s" % file_path)
        sys.exit(1)

    if not can_extract(p):
        ext = p.suffix.lower()
        if ext in UNSUPPORTED_BINARY:
            print("Error: formato no soportado (binario antiguo): %s" % ext)
        elif p.stat().st_size > MAX_FILE_SIZE:
            print("Error: archivo demasiado grande (max %d MB)" % (MAX_FILE_SIZE // (1024*1024)))
        else:
            print("Error: extension no soportada: %s" % ext)
        sys.exit(1)

    text = extract_text(file_path, max_chars)
    if text:
        print(text)
    else:
        print("(sin contenido extraible)")


def _cli_supported():
    """Subcomando: mostrar extensiones soportadas."""
    exts = sorted(supported_extensions())
    print("Extensiones soportadas (%d):" % len(exts))

    # Agrupar por categoria
    print("\n  Texto plano / Codigo:")
    for ext in sorted(TEXT_EXTENSIONS):
        print("    %s" % ext)

    print("\n  Office (ZIP de XML):")
    for ext in sorted(OFFICE_EXTENSIONS):
        print("    %s" % ext)

    print("\n  PDF:")
    for ext in sorted(PDF_EXTENSIONS):
        print("    %s" % ext)

    print("\n  NO soportados (binarios antiguos):")
    for ext in sorted(UNSUPPORTED_BINARY):
        print("    %s" % ext)


def _cli_check(args):
    """Subcomando: verificar si un archivo es extraible."""
    if not args:
        print("Error: especificar ruta de archivo")
        sys.exit(1)

    file_path = args[0]
    p = Path(file_path)

    if not p.exists():
        print("NO - archivo no encontrado: %s" % file_path)
        sys.exit(1)

    ext = p.suffix.lower()
    size = p.stat().st_size
    size_str = "%.1f KB" % (size / 1024) if size < 1024*1024 else "%.1f MB" % (size / (1024*1024))

    if can_extract(p):
        print("SI - se puede extraer")
        print("  Archivo:   %s" % p.name)
        print("  Extension: %s" % ext)
        print("  Tamano:    %s" % size_str)
    else:
        reason = "extension no soportada"
        if ext in UNSUPPORTED_BINARY:
            reason = "formato binario antiguo (no soportado)"
        elif size > MAX_FILE_SIZE:
            reason = "archivo demasiado grande"
        elif ext in supported_extensions():
            reason = "error de acceso al archivo"

        print("NO - %s" % reason)
        print("  Archivo:   %s" % p.name)
        print("  Extension: %s" % ext)
        print("  Tamano:    %s" % size_str)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python file_extractor.py extract \"ruta/archivo.docx\" [--max-chars 2000]")
        print("  python file_extractor.py supported")
        print("  python file_extractor.py check \"ruta/archivo\"")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "extract":
        _cli_extract(sys.argv[2:])
    elif cmd == "supported":
        _cli_supported()
    elif cmd == "check":
        _cli_check(sys.argv[2:])
    else:
        print("Comando desconocido: %s" % cmd)
        print("Comandos disponibles: extract, supported, check")
        sys.exit(1)
