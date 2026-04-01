# -*- coding: utf-8 -*-
"""
disk_scanner.py -- Descubrimiento automatico de dominios desde el disco
=======================================================================
Escanea carpetas del usuario para generar dominios automaticamente
basados en el contenido real de su maquina.

Logica:
  1. Recorre carpetas hasta depth=3
  2. Agrupa archivos por carpeta padre (cluster tematico)
  3. Analiza nombres de archivos, extensiones, y contenido (primeros 500 chars de .txt/.md/.py/.json)
  4. Genera dominios candidatos con keywords y confidence score
  5. Filtra dominios con menos de MIN_FILES archivos
  6. Guarda dominios confirmados en domains.json via domain_detector.learn_domain_keywords()

API:
  scan(paths, depth=3, min_files=3) -> dict of discovered domains
  scan_and_apply(paths, depth=3, min_files=3) -> dict (scan + save to domains.json)
  get_default_scan_paths() -> list of paths to scan (Documents, Desktop, Projects, etc.)
  estimate_scan_time(paths, depth=3) -> tuple(file_count, est_seconds)
"""

import os
import re
import json
import time
import sys
from pathlib import Path
from collections import defaultdict, Counter

# -- Importar modulos hermanos ------------------------------------------------
_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

from config import DOMAINS_FILE

# -- Constantes ---------------------------------------------------------------
MIN_FILES_DEFAULT = 3
MAX_DEPTH_DEFAULT = 3
MAX_CONTENT_CHARS = 500
SCANNABLE_EXTENSIONS = {
    '.txt', '.md', '.py', '.js', '.ts', '.java', '.go', '.rs', '.sql',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.csv',
    '.html', '.css', '.sh', '.bat', '.ps1', '.r', '.jl', '.rb', '.php',
    '.c', '.cpp', '.h', '.cs',
}
BINARY_EXTENSIONS = {
    '.exe', '.dll', '.pyd', '.so', '.dylib', '.bin', '.dat', '.db',
    '.sqlite', '.zip', '.tar', '.gz', '.7z', '.rar', '.iso', '.img',
    '.mp3', '.mp4', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif',
    '.bmp', '.ico', '.psd', '.ai',
}

# Carpetas que se saltan siempre
SKIP_DIRS = {
    'node_modules', '.git', '.svn', '__pycache__', '.venv', 'venv',
    'env', '.env', '.idea', '.vs', '.vscode', 'dist', 'build', 'target',
    'bin', 'obj', '.cache', '.npm', '.yarn', 'AppData', 'ProgramData',
    '$Recycle.Bin', 'Windows', 'Program Files', 'Program Files (x86)',
}

# Stop words para nombrado de dominios (espanol + ingles)
STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que",
    "y", "a", "por", "con", "para", "es", "se", "no", "lo", "le", "su",
    "the", "an", "in", "of", "to", "is", "it", "for", "and", "or",
    "new", "old", "temp", "tmp", "test", "copy", "backup", "copia",
}

# Mapeo de extension a categoria para enriquecer keywords
EXT_CATEGORIES = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
    '.java': 'java', '.go': 'golang', '.rs': 'rust',
    '.sql': 'sql', '.xlsx': 'excel', '.xls': 'excel',
    '.docx': 'word', '.doc': 'word', '.pdf': 'pdf',
    '.pptx': 'powerpoint', '.ppt': 'powerpoint',
    '.html': 'web', '.css': 'web', '.json': 'json',
    '.xml': 'xml', '.yaml': 'yaml', '.yml': 'yaml',
    '.r': 'estadistica', '.jl': 'julia', '.rb': 'ruby',
    '.php': 'php', '.c': 'c_lang', '.cpp': 'cpp',
    '.cs': 'csharp', '.sh': 'shell', '.bat': 'batch',
    '.ps1': 'powershell', '.csv': 'datos',
}


# =============================================================================
# Funciones auxiliares
# =============================================================================

def get_default_scan_paths() -> list:
    """
    Retorna directorios comunes del usuario para escanear.
    Multiplataforma: Windows, Mac, Linux.
    Solo retorna paths que existen en disco.
    """
    home = Path.home()
    candidates = [
        home / "Documents",
        home / "Desktop",
        home / "Projects",
        home / "repos",
        home / "src",
        home / "dev",
        home / "code",
        home / "workspace",
    ]

    # Windows: variantes en espanol
    if sys.platform == "win32":
        candidates.extend([
            home / "Documentos",
            home / "Escritorio",
            home / "OneDrive" / "Documents",
            home / "OneDrive" / "Documentos",
            home / "OneDrive" / "Desktop",
            home / "OneDrive" / "Escritorio",
        ])

    # Mac: Developer folder
    if sys.platform == "darwin":
        candidates.extend([
            home / "Developer",
            home / "Library" / "Developer",
        ])

    # Linux: comunes
    if sys.platform.startswith("linux"):
        candidates.extend([
            home / "Proyectos",
        ])

    # Filtrar solo los que existen
    existing = []
    for p in candidates:
        try:
            if p.exists() and p.is_dir():
                existing.append(str(p))
        except (PermissionError, OSError):
            continue

    return existing


def estimate_scan_time(paths: list = None, depth: int = MAX_DEPTH_DEFAULT) -> tuple:
    """
    Estimacion rapida del tiempo de escaneo.
    Cuenta archivos sin leer contenido.

    Args:
        paths: Lista de paths a escanear. Si None, usa get_default_scan_paths().
        depth: Profundidad maxima de escaneo.

    Returns:
        (file_count, estimated_seconds) donde est = file_count * 0.001
    """
    if paths is None:
        paths = get_default_scan_paths()

    file_count = 0
    for base_path in paths:
        base = Path(base_path)
        if not base.exists():
            continue
        file_count += _count_files_fast(base, depth, current_depth=0)

    est_seconds = file_count * 0.001
    return (file_count, round(est_seconds, 2))


def _count_files_fast(directory: Path, max_depth: int, current_depth: int) -> int:
    """Cuenta archivos rapido con os.scandir (sin leer contenido)."""
    if current_depth > max_depth:
        return 0

    count = 0
    try:
        with os.scandir(str(directory)) as entries:
            for entry in entries:
                try:
                    # Saltar symlinks
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        ext = Path(entry.name).suffix.lower()
                        if ext not in BINARY_EXTENSIONS:
                            count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIP_DIRS:
                            count += _count_files_fast(
                                Path(entry.path), max_depth, current_depth + 1
                            )
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass

    return count


def _extract_folder_keywords(folder_name: str) -> list:
    """
    Extrae keywords de un nombre de carpeta.
    Divide CamelCase, snake_case, guiones. Filtra stop words y cortas.

    Args:
        folder_name: Nombre de la carpeta (sin ruta).

    Returns:
        Lista de keywords en minuscula.
    """
    if not folder_name:
        return []

    # Separar CamelCase: "MiProyectoWeb" -> "Mi Proyecto Web"
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', folder_name)
    # Separar snake_case y guiones
    name = re.sub(r'[_\-.]', ' ', name)
    # Extraer palabras alfanumericas
    words = re.findall(r'[a-zA-Z0-9]+', name.lower())

    # Filtrar stop words y palabras cortas (< 3 chars)
    return [w for w in words if len(w) >= 3 and w not in STOP_WORDS]


def _extract_file_keywords(file_path: Path) -> list:
    """
    Extrae keywords de un archivo: nombre + contenido (si es escaneable).

    Args:
        file_path: Path completo del archivo.

    Returns:
        Lista de keywords extraidas.
    """
    keywords = []

    # -- Keywords del nombre del archivo --
    stem = file_path.stem  # nombre sin extension
    name_kw = _extract_folder_keywords(stem)
    keywords.extend(name_kw)

    # -- Categoria por extension --
    ext = file_path.suffix.lower()
    if ext in EXT_CATEGORIES:
        keywords.append(EXT_CATEGORIES[ext])

    # -- Keywords del contenido (si es escaneable y < 100KB) --
    if ext in SCANNABLE_EXTENSIONS:
        try:
            size = file_path.stat().st_size
            if size <= 100_000:  # 100KB maximo
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(MAX_CONTENT_CHARS)
                # Extraer palabras significativas del contenido
                words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', content.lower())
                # Filtrar stop words, quedarse con las mas frecuentes
                content_kw = [w for w in words if w not in STOP_WORDS and len(w) >= 3]
                # Solo las 10 mas comunes para no inundar
                counted = Counter(content_kw)
                top_kw = [w for w, _ in counted.most_common(10)]
                keywords.extend(top_kw)
        except (PermissionError, OSError, UnicodeDecodeError):
            pass

    return keywords


def _cluster_by_folder(paths: list, depth: int) -> dict:
    """
    Recorre directorios y agrupa archivos por carpeta padre (1-2 niveles arriba).

    Args:
        paths: Lista de paths base a escanear.
        depth: Profundidad maxima.

    Returns:
        {folder_name: {"files": [Path], "keywords": Counter, "extensions": Counter}}
    """
    clusters = defaultdict(lambda: {
        "files": [],
        "keywords": Counter(),
        "extensions": Counter(),
        "source_path": "",
    })

    for base_path in paths:
        base = Path(base_path)
        if not base.exists():
            continue
        _walk_and_cluster(base, base, depth, 0, clusters)

    return dict(clusters)


def _walk_and_cluster(directory: Path, base: Path, max_depth: int,
                      current_depth: int, clusters: dict):
    """Recorre recursivamente y agrupa archivos en clusters."""
    if current_depth > max_depth:
        return

    try:
        with os.scandir(str(directory)) as entries:
            for entry in entries:
                try:
                    # Saltar symlinks
                    if entry.is_symlink():
                        continue

                    if entry.is_file(follow_symlinks=False):
                        fpath = Path(entry.path)
                        ext = fpath.suffix.lower()

                        # Saltar binarios
                        if ext in BINARY_EXTENSIONS:
                            continue

                        # Determinar cluster: carpeta padre significativa
                        # Usar 1-2 niveles arriba del base como nombre de cluster
                        try:
                            rel = fpath.relative_to(base)
                            parts = rel.parts
                            if len(parts) >= 2:
                                # Usar la primera carpeta significativa
                                cluster_name = parts[0]
                            else:
                                # Archivo en raiz del base: usar nombre del base
                                cluster_name = base.name
                        except ValueError:
                            cluster_name = directory.name

                        clusters[cluster_name]["files"].append(fpath)
                        clusters[cluster_name]["extensions"][ext] += 1
                        if not clusters[cluster_name]["source_path"]:
                            clusters[cluster_name]["source_path"] = str(
                                directory if cluster_name == directory.name
                                else base / cluster_name
                            )

                        # Extraer keywords del nombre de la carpeta
                        folder_kw = _extract_folder_keywords(cluster_name)
                        for kw in folder_kw:
                            clusters[cluster_name]["keywords"][kw] += 1

                    elif entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIP_DIRS:
                            _walk_and_cluster(
                                Path(entry.path), base, max_depth,
                                current_depth + 1, clusters
                            )
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass


def _suggest_domain_name(folder_name: str, keywords: Counter) -> str:
    """
    Genera un nombre de dominio limpio a partir del nombre de carpeta.

    Args:
        folder_name: Nombre de la carpeta del cluster.
        keywords:    Counter de keywords del cluster.

    Returns:
        Nombre de dominio limpio (lowercase, max 30 chars).
    """
    # Limpiar nombre base
    name = folder_name.lower().strip()
    # Reemplazar espacios y guiones por underscore
    name = re.sub(r'[\s\-]+', '_', name)
    # Solo alfanumerico y underscore
    name = re.sub(r'[^a-z0-9_]', '', name)
    # Quitar underscores multiples
    name = re.sub(r'_+', '_', name).strip('_')

    # Si el nombre quedo vacio, usar la keyword mas frecuente
    if not name or len(name) < 2:
        if keywords:
            name = keywords.most_common(1)[0][0]
        else:
            name = "dominio_auto"

    # Truncar a 30 chars
    return name[:30]


def _calculate_confidence(cluster: dict) -> float:
    """
    Calcula score de confianza para un cluster.

    Factores:
      - Numero de archivos (mas archivos = mas confianza)
      - Concentracion de keywords (pocas keywords dominantes = mas coherente)
      - Consistencia de extensiones (menos variedad = mas enfocado)

    Returns:
        Float entre 0.0 y 1.0
    """
    files = cluster["files"]
    keywords = cluster["keywords"]
    extensions = cluster["extensions"]

    n_files = len(files)
    n_keywords = len(keywords)
    n_extensions = len(extensions)

    # Factor 1: Cantidad de archivos (saturacion logaritmica)
    # 3 archivos = 0.3, 10 = 0.6, 30+ = 0.9
    if n_files <= 0:
        return 0.0
    import math
    file_factor = min(1.0, math.log(n_files + 1) / math.log(50))

    # Factor 2: Concentracion de keywords
    # Si las top-3 keywords representan > 60% del total -> alta concentracion
    if n_keywords > 0 and sum(keywords.values()) > 0:
        total_freq = sum(keywords.values())
        top3_freq = sum(c for _, c in keywords.most_common(3))
        concentration = top3_freq / total_freq
    else:
        concentration = 0.0

    # Factor 3: Consistencia de extensiones
    # Menos tipos de extension = mas enfocado
    if n_extensions > 0:
        ext_consistency = 1.0 / (1.0 + (n_extensions - 1) * 0.15)
    else:
        ext_consistency = 0.0

    # Promedio ponderado
    confidence = (file_factor * 0.45) + (concentration * 0.35) + (ext_consistency * 0.20)
    return round(min(1.0, max(0.0, confidence)), 3)


# =============================================================================
# API publica
# =============================================================================

def scan(paths: list = None, depth: int = MAX_DEPTH_DEFAULT,
         min_files: int = MIN_FILES_DEFAULT, progress_callback=None) -> dict:
    """
    Escanea directorios y descubre dominios candidatos.

    Args:
        paths:             Lista de paths a escanear. None = get_default_scan_paths().
        depth:             Profundidad maxima de recursion.
        min_files:         Minimo de archivos para considerar un cluster como dominio.
        progress_callback: Funcion opcional (current, total, message) para progreso.

    Returns:
        {domain_name: {
            "keywords": [...],
            "files_found": int,
            "confidence": float,
            "source_path": str,
            "extensions": {".py": 5, ...}
        }}
    """
    if paths is None:
        paths = get_default_scan_paths()

    if not paths:
        return {}

    # Paso 1: Agrupar archivos en clusters
    if progress_callback:
        progress_callback(0, 100, "Escaneando directorios...")

    clusters = _cluster_by_folder(paths, depth)

    if not clusters:
        return {}

    total_clusters = len(clusters)
    results = {}

    # Paso 2: Analizar cada cluster
    for idx, (folder_name, cluster) in enumerate(clusters.items()):
        if progress_callback:
            pct = int((idx / total_clusters) * 80) + 10
            progress_callback(pct, 100, f"Analizando: {folder_name}")

        # Filtrar por minimo de archivos
        if len(cluster["files"]) < min_files:
            continue

        # Enriquecer keywords con contenido de archivos (muestreo)
        sample_files = cluster["files"][:20]  # maximo 20 archivos por cluster
        for fpath in sample_files:
            file_kw = _extract_file_keywords(fpath)
            for kw in file_kw:
                cluster["keywords"][kw] += 1

        # Generar nombre de dominio
        domain_name = _suggest_domain_name(folder_name, cluster["keywords"])

        # Calcular confianza
        confidence = _calculate_confidence(cluster)

        # Extraer top keywords (las 20 mas frecuentes, sin stop words)
        top_keywords = [
            kw for kw, _ in cluster["keywords"].most_common(30)
            if kw not in STOP_WORDS and len(kw) >= 3
        ][:20]

        results[domain_name] = {
            "keywords": top_keywords,
            "files_found": len(cluster["files"]),
            "confidence": confidence,
            "source_path": cluster.get("source_path", ""),
            "extensions": dict(cluster["extensions"]),
        }

    if progress_callback:
        progress_callback(100, 100, f"Escaneo completo: {len(results)} dominios encontrados")

    return results


def scan_and_apply(paths: list = None, depth: int = MAX_DEPTH_DEFAULT,
                   min_files: int = MIN_FILES_DEFAULT,
                   progress_callback=None) -> dict:
    """
    Escanea y guarda dominios con confianza >= 0.5 en domains.json.
    SOLO crea dominios con keywords. NO alimenta contenido al KB.

    Usa domain_detector.learn_domain_keywords() para persistir.

    Args:
        paths, depth, min_files, progress_callback: igual que scan().

    Returns:
        Mismo dict que scan() pero con campo "saved": True/False por dominio.
    """
    # Importar aqui para evitar circular
    from core.domain_detector import learn_domain_keywords

    results = scan(paths, depth, min_files, progress_callback)

    for domain_name, info in results.items():
        if info["confidence"] >= 0.5 and info["keywords"]:
            try:
                learn_domain_keywords(domain_name, info["keywords"])
                info["saved"] = True
            except Exception:
                info["saved"] = False
        else:
            info["saved"] = False

    return results


def scan_and_ingest(paths: list = None, depth: int = MAX_DEPTH_DEFAULT,
                    min_files: int = MIN_FILES_DEFAULT,
                    max_files_per_domain: int = 50,
                    progress_callback=None) -> dict:
    """
    Escanea, crea dominios Y alimenta el KB con contenido de archivos.

    Proceso:
      1. scan() para descubrir dominios
      2. Crea dominios en domains.json (como scan_and_apply)
      3. Para cada dominio, lee archivos con file_extractor
      4. Divide contenido en chunks y los guarda como facts en el KB

    Args:
        paths:                Paths a escanear.
        depth:                Profundidad maxima.
        min_files:            Minimo de archivos por cluster.
        max_files_per_domain: Maximo de archivos a ingerir por dominio.
        progress_callback:    Funcion (current, total, message).

    Returns:
        Dict con dominios descubiertos + campos:
          "saved": bool, "facts_ingested": int, "files_ingested": int
    """
    from core.domain_detector import learn_domain_keywords
    from core.file_extractor import extract_text, can_extract, chunk_text
    from core.knowledge_base import add_fact

    # Paso 1: Escanear y obtener clusters con archivos
    # Usamos scan() internamente pero necesitamos acceso a los archivos
    if paths is None:
        paths = get_default_scan_paths()
    if not paths:
        return {}

    if progress_callback:
        progress_callback(0, 100, "Escaneando directorios...")

    clusters = _cluster_by_folder(paths, depth)
    if not clusters:
        return {}

    total_clusters = len(clusters)
    results = {}

    # Paso 2: Analizar clusters y crear dominios
    valid_clusters = {}
    for idx, (folder_name, cluster) in enumerate(clusters.items()):
        if len(cluster["files"]) < min_files:
            continue

        # Enriquecer keywords con muestreo
        sample_files = cluster["files"][:20]
        for fpath in sample_files:
            file_kw = _extract_file_keywords(fpath)
            for kw in file_kw:
                cluster["keywords"][kw] += 1

        domain_name = _suggest_domain_name(folder_name, cluster["keywords"])
        confidence = _calculate_confidence(cluster)

        top_keywords = [
            kw for kw, _ in cluster["keywords"].most_common(30)
            if kw not in STOP_WORDS and len(kw) >= 3
        ][:20]

        results[domain_name] = {
            "keywords": top_keywords,
            "files_found": len(cluster["files"]),
            "confidence": confidence,
            "source_path": cluster.get("source_path", ""),
            "extensions": dict(cluster["extensions"]),
            "saved": False,
            "facts_ingested": 0,
            "files_ingested": 0,
        }

        if confidence >= 0.5 and top_keywords:
            try:
                learn_domain_keywords(domain_name, top_keywords)
                results[domain_name]["saved"] = True
                valid_clusters[domain_name] = cluster
            except Exception:
                pass

    if progress_callback:
        progress_callback(30, 100, f"{len(valid_clusters)} dominios creados. Ingiriendo contenido...")

    # Paso 3: Ingerir contenido de archivos en el KB
    total_domains = len(valid_clusters)
    for d_idx, (domain_name, cluster) in enumerate(valid_clusters.items()):
        if progress_callback:
            pct = 30 + int((d_idx / max(total_domains, 1)) * 65)
            progress_callback(pct, 100, f"Alimentando: {domain_name}")

        # Seleccionar archivos extraibles, priorizando los mas grandes (mas contenido)
        extractable = [
            f for f in cluster["files"]
            if can_extract(f)
        ]
        # Ordenar por tamano descendente (mas contenido primero)
        extractable.sort(key=lambda f: f.stat().st_size if f.exists() else 0, reverse=True)
        # Limitar cantidad por dominio
        extractable = extractable[:max_files_per_domain]

        files_ingested = 0
        facts_ingested = 0

        for fpath in extractable:
            try:
                text = extract_text(fpath, max_chars=5000)
                if not text or len(text.strip()) < 50:
                    continue  # Archivo con muy poco contenido util

                # Dividir en chunks
                chunks = chunk_text(text, chunk_size=800, overlap=100)

                for c_idx, chunk in enumerate(chunks):
                    if not chunk.strip():
                        continue

                    # Crear key unico basado en archivo + chunk
                    fact_key = f"{fpath.stem}_{c_idx}"

                    # Determinar tags del archivo
                    tags = []
                    ext = fpath.suffix.lower()
                    if ext in EXT_CATEGORIES:
                        tags.append(EXT_CATEGORIES[ext])
                    tags.append(ext.lstrip('.'))
                    # Agregar keywords del nombre
                    name_kw = _extract_folder_keywords(fpath.stem)
                    tags.extend(name_kw[:5])

                    fact = {
                        "rule": chunk,
                        "applies_to": domain_name,
                        "source": str(fpath),
                        "confidence": "observed",
                        "examples": [],
                        "exceptions": "",
                    }

                    try:
                        add_fact(domain_name, fact_key, fact, tags=tags)
                        facts_ingested += 1
                    except Exception:
                        pass  # Si falla un fact, seguir con el siguiente

                files_ingested += 1

            except Exception:
                continue  # Si falla un archivo, seguir con el siguiente

        results[domain_name]["files_ingested"] = files_ingested
        results[domain_name]["facts_ingested"] = facts_ingested

    if progress_callback:
        total_facts = sum(r.get("facts_ingested", 0) for r in results.values())
        total_files = sum(r.get("files_ingested", 0) for r in results.values())
        progress_callback(
            100, 100,
            f"Completo: {len(valid_clusters)} dominios, {total_files} archivos, {total_facts} facts"
        )

    return results


# =============================================================================
# CLI
# =============================================================================

def _print_results(results: dict):
    """Imprime resultados de escaneo formateados."""
    if not results:
        print("  (sin dominios descubiertos)")
        return

    # Ordenar por confianza descendente
    sorted_domains = sorted(results.items(), key=lambda x: -x[1]["confidence"])
    for name, info in sorted_domains:
        saved_mark = " [GUARDADO]" if info.get("saved") else ""
        print(f"\n  Dominio: {name}{saved_mark}")
        print(f"    Confianza: {info['confidence']:.1%}")
        print(f"    Archivos:  {info['files_found']}")
        print(f"    Path:      {info.get('source_path', '?')}")
        print(f"    Keywords:  {', '.join(info['keywords'][:10])}")
        exts = info.get("extensions", {})
        if exts:
            top_ext = sorted(exts.items(), key=lambda x: -x[1])[:5]
            ext_str = ", ".join(f"{e}({c})" for e, c in top_ext)
            print(f"    Extensiones: {ext_str}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python disk_scanner.py scan [path1] [path2]    -- escanear y mostrar")
        print("  python disk_scanner.py apply [path1] [path2]   -- escanear y guardar en domains.json")
        print("  python disk_scanner.py ingest [path1] [path2]  -- escanear, crear dominios Y alimentar KB")
        print("  python disk_scanner.py estimate [path1]         -- estimar tiempo")
        print("  python disk_scanner.py paths                    -- mostrar paths por defecto")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "paths":
        print("Paths por defecto para escaneo:")
        for p in get_default_scan_paths():
            print(f"  {p}")

    elif cmd == "estimate":
        scan_paths = sys.argv[2:] if len(sys.argv) > 2 else None
        print("Estimando...")
        n_files, est_secs = estimate_scan_time(scan_paths)
        print(f"  Archivos encontrados: {n_files:,}")
        print(f"  Tiempo estimado:      {est_secs:.1f} segundos")

    elif cmd == "scan":
        scan_paths = sys.argv[2:] if len(sys.argv) > 2 else None
        print("Escaneando...")
        t0 = time.time()
        results = scan(scan_paths)
        elapsed = time.time() - t0
        print(f"Escaneo completado en {elapsed:.1f}s")
        _print_results(results)

    elif cmd == "apply":
        scan_paths = sys.argv[2:] if len(sys.argv) > 2 else None
        print("Escaneando y aplicando dominios...")
        t0 = time.time()
        results = scan_and_apply(scan_paths)
        elapsed = time.time() - t0
        print(f"Escaneo completado en {elapsed:.1f}s")
        _print_results(results)
        saved_count = sum(1 for v in results.values() if v.get("saved"))
        print(f"\n  Total guardados en domains.json: {saved_count}")

    elif cmd == "ingest":
        scan_paths = sys.argv[2:] if len(sys.argv) > 2 else None
        print("Escaneando, creando dominios Y alimentando KB...")
        t0 = time.time()

        def _cli_progress(cur, tot, msg):
            print(f"  [{cur}%] {msg}")

        results = scan_and_ingest(scan_paths, progress_callback=_cli_progress)
        elapsed = time.time() - t0
        print(f"\nIngestion completada en {elapsed:.1f}s")
        _print_results(results)
        total_facts = sum(r.get("facts_ingested", 0) for r in results.values())
        total_files = sum(r.get("files_ingested", 0) for r in results.values())
        print(f"\n  Archivos procesados: {total_files}")
        print(f"  Facts ingresados al KB: {total_facts}")

    else:
        print(f"Comando desconocido: {cmd}")
        sys.exit(1)
