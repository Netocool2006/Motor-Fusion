#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor Fusion IA - Instalador Visual v1.0
Instalador wizard completo usando tkinter (stdlib).
Compatible con Windows, macOS y Linux.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

# Embedded Python on Windows needs DLL directory for tkinter (tcl86t.dll, tk86t.dll)
if sys.platform == "win32":
    _exe_dir = os.path.dirname(sys.executable)
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(_exe_dir)

from tkinter import (
    Tk, Frame, Label, Button, Entry, Checkbutton, Radiobutton,
    BooleanVar, StringVar,
    Text, Scrollbar, filedialog, messagebox, font as tkfont,
    LEFT, RIGHT, BOTH, X, Y, TOP, BOTTOM, W, E, N, S, END,
    DISABLED, NORMAL, WORD, HORIZONTAL,
)
from tkinter.ttk import Progressbar, Style, Separator

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
APP_TITLE = "Motor Fusion IA - Instalador v1.0"
WINDOW_W, WINDOW_H = 700, 500
HEADER_BG = "#1a237e"
HEADER_FG = "#ffffff"
BODY_BG = "#ffffff"
SUCCESS_FG = "#2e7d32"
ACCENT_BLUE = "#1976d2"
BTN_BG = "#1976d2"
BTN_FG = "#ffffff"
BTN_HOVER = "#1565c0"
FONT_FAMILY = "Segoe UI" if platform.system() == "Windows" else "Helvetica"

ASCII_LOGO = r"""
    __  ___      __                ______           _
   /  |/  /___  / /_____  _____  / ____/_  _______(_)___  ____
  / /|_/ / __ \/ __/ __ \/ ___/ / /_  / / / / ___/ / __ \/ __ \
 / /  / / /_/ / /_/ /_/ / /    / __/ / /_/ (__  ) / /_/ / / / /
/_/  /_/\____/\__/\____/_/    /_/    \__,_/____/_/\____/_/ /_/
                         I  A
"""

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _default_install_dir() -> str:
    """Directorio de instalacion por defecto segun SO."""
    if platform.system() == "Windows":
        # Sugerir Program Files o home del usuario
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        return os.path.join(pf, "Motor Fusion IA")
    return str(Path.home() / "motor-fusion-ia")


def _find_motor_source() -> Path | None:
    """Localiza el directorio fuente de motor_ia.

    Busca en:
      1. ../ respecto al directorio del installer (desarrollo)
      2. ./motor_ia/ respecto al directorio del installer (paquete)
    """
    installer_dir = Path(__file__).resolve().parent
    # Opcion 1: padre del installer (estructura de desarrollo)
    parent = installer_dir.parent
    if (parent / "core" / "knowledge_base.py").is_file():
        return parent
    # Opcion 2: subcarpeta motor_ia junto al installer
    bundled = installer_dir / "motor_ia"
    if bundled.is_dir() and (bundled / "core" / "knowledge_base.py").is_file():
        return bundled
    return None


def _adaptive_cli_dir() -> Path:
    """Ruta al directorio de datos persistente."""
    return Path.home() / ".adaptive_cli"


def _claude_settings_path() -> Path:
    """Ruta al settings.json de Claude Code CLI."""
    return Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Clase principal del Installer GUI
# ---------------------------------------------------------------------------

class InstallerApp:
    """Wizard de instalacion de Motor Fusion IA."""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.resizable(False, False)
        self._center_window()
        self.root.configure(bg=BODY_BG)

        # Intentar icono (no critico si falla)
        try:
            if platform.system() == "Windows":
                self.root.iconbitmap(default="")
        except Exception:
            pass

        # Variables de configuracion
        self.install_dir = StringVar(value=_default_install_dir())
        self.chk_claude = BooleanVar(value=True)
        self.chk_gemini = BooleanVar(value=False)
        self.chk_ollama = BooleanVar(value=False)
        self.github_user = StringVar(value="")

        # Variables de dominios (pantalla 2)
        self.domain_mode = StringVar(value="desde_cero")
        self.scan_paths: list[str] = []
        self.preset_sa_gbm = BooleanVar(value=False)
        self.preset_dev = BooleanVar(value=False)
        self.preset_data = BooleanVar(value=False)
        self.preset_admin = BooleanVar(value=False)
        self.domains_created = 0
        self.domains_summary = ""

        # Estado
        self.current_screen = 0
        self.motor_source: Path | None = _find_motor_source()
        self.install_success = False
        self.install_config: dict = {}

        # Estilo ttk
        self._setup_styles()

        # Contenedores
        self.header_frame = Frame(self.root, bg=HEADER_BG, height=60)
        self.header_frame.pack(fill=X, side=TOP)
        self.header_frame.pack_propagate(False)

        self.body_frame = Frame(self.root, bg=BODY_BG)
        self.body_frame.pack(fill=BOTH, expand=True, side=TOP)

        self.footer_frame = Frame(self.root, bg=BODY_BG, height=50)
        self.footer_frame.pack(fill=X, side=BOTTOM)
        self.footer_frame.pack_propagate(False)

        # Header label
        self.header_label = Label(
            self.header_frame,
            text=APP_TITLE,
            bg=HEADER_BG, fg=HEADER_FG,
            font=(FONT_FAMILY, 16, "bold"),
        )
        self.header_label.pack(expand=True)

        # Mostrar primera pantalla
        self._show_screen(0)

    # -- Helpers visuales ---------------------------------------------------

    def _center_window(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - WINDOW_W) // 2
        y = (sh - WINDOW_H) // 2
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

    def _setup_styles(self) -> None:
        style = Style()
        style.theme_use("clam" if platform.system() != "Darwin" else "default")
        style.configure(
            "Blue.Horizontal.TProgressbar",
            troughcolor="#e0e0e0",
            background=ACCENT_BLUE,
            thickness=22,
        )

    def _clear_body(self) -> None:
        for child in self.body_frame.winfo_children():
            child.destroy()

    def _clear_footer(self) -> None:
        for child in self.footer_frame.winfo_children():
            child.destroy()

    def _make_button(self, parent: Frame, text: str, command, side=RIGHT,
                     padx=8, pady=6, state=NORMAL) -> Button:
        btn = Button(
            parent, text=text, command=command,
            bg=BTN_BG, fg=BTN_FG, activebackground=BTN_HOVER,
            activeforeground=BTN_FG, relief="flat", cursor="hand2",
            font=(FONT_FAMILY, 10, "bold"), padx=16, pady=4, state=state,
            borderwidth=0, highlightthickness=0,
        )
        btn.pack(side=side, padx=padx, pady=pady)
        return btn

    # -- Navegacion de pantallas --------------------------------------------

    def _show_screen(self, idx: int) -> None:
        self.current_screen = idx
        self._clear_body()
        self._clear_footer()
        screens = [
            self._screen_welcome,       # 0
            self._screen_config,        # 1
            self._screen_domains,       # 2
            self._screen_progress,      # 3
            self._screen_complete,      # 4
        ]
        if 0 <= idx < len(screens):
            screens[idx]()

    # ======================================================================
    # SCREEN 1: Bienvenida
    # ======================================================================
    def _screen_welcome(self) -> None:
        container = Frame(self.body_frame, bg=BODY_BG)
        container.pack(fill=BOTH, expand=True, padx=30, pady=10)

        # Logo ASCII
        logo_lbl = Label(
            container,
            text=ASCII_LOGO,
            bg=BODY_BG, fg=HEADER_BG,
            font=("Courier", 7 if platform.system() == "Windows" else 8),
            justify=LEFT,
        )
        logo_lbl.pack(pady=(0, 5))

        # Subtitulo
        Label(
            container,
            text="Motor de Aprendizaje Inteligente para CLIs",
            bg=BODY_BG, fg="#424242",
            font=(FONT_FAMILY, 13, "italic"),
        ).pack(pady=(0, 12))

        Separator(container, orient=HORIZONTAL).pack(fill=X, pady=5)

        # Descripcion
        desc_text = (
            "Motor Fusion IA es un sistema de aprendizaje continuo que se integra\n"
            "con tu CLI de inteligencia artificial preferido. Aprende patrones de uso,\n"
            "mantiene una base de conocimiento multi-dominio y se adapta a tu flujo\n"
            "de trabajo.\n\n"
            "Caracteristicas principales:\n"
            "  - Aprendizaje automatico de patrones y errores resueltos\n"
            "  - Base de conocimiento con dominios personalizables\n"
            "  - Adaptadores para Claude Code, Gemini CLI y Ollama\n"
            "  - Respaldo y sincronizacion via GitHub\n"
            "  - Funciona 100% local, sin dependencias externas"
        )
        Label(
            container,
            text=desc_text,
            bg=BODY_BG, fg="#333333",
            font=(FONT_FAMILY, 10),
            justify=LEFT,
            anchor=W,
        ).pack(fill=X, pady=(8, 0))

        # Advertencia si no se encontro fuente
        if self.motor_source is None:
            Label(
                container,
                text="ADVERTENCIA: No se encontraron los archivos fuente de Motor IA.",
                bg=BODY_BG, fg="#c62828",
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(pady=(10, 0))

        # Footer
        self._make_button(self.footer_frame, "Siguiente >", lambda: self._show_screen(1))

    # ======================================================================
    # SCREEN 2: Configuracion
    # ======================================================================
    def _screen_config(self) -> None:
        container = Frame(self.body_frame, bg=BODY_BG)
        container.pack(fill=BOTH, expand=True, padx=30, pady=15)

        # -- Directorio de instalacion --------------------------------------
        Label(
            container,
            text="Directorio de instalacion:",
            bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 11, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(0, 4))

        dir_frame = Frame(container, bg=BODY_BG)
        dir_frame.pack(fill=X, pady=(0, 14))

        dir_entry = Entry(
            dir_frame, textvariable=self.install_dir,
            font=(FONT_FAMILY, 10), relief="solid", borderwidth=1,
        )
        dir_entry.pack(side=LEFT, fill=X, expand=True, ipady=3)

        Button(
            dir_frame, text="Examinar...",
            command=self._browse_dir,
            font=(FONT_FAMILY, 9),
            padx=10, pady=2,
        ).pack(side=RIGHT, padx=(8, 0))

        Separator(container, orient=HORIZONTAL).pack(fill=X, pady=6)

        # -- Adaptadores CLI ------------------------------------------------
        Label(
            container,
            text="Adaptadores CLI a configurar:",
            bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 11, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(4, 6))

        chk_frame = Frame(container, bg=BODY_BG)
        chk_frame.pack(fill=X, padx=10, pady=(0, 10))

        Checkbutton(
            chk_frame, text="Claude Code CLI (recomendado)",
            variable=self.chk_claude, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 10), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=2)

        Checkbutton(
            chk_frame, text="Gemini CLI",
            variable=self.chk_gemini, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 10), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=2)

        Checkbutton(
            chk_frame, text="Ollama (LLM local)",
            variable=self.chk_ollama, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 10), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=2)

        Separator(container, orient=HORIZONTAL).pack(fill=X, pady=6)

        # -- GitHub user ----------------------------------------------------
        Label(
            container,
            text="Usuario GitHub (opcional, para respaldo en la nube):",
            bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 11, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(4, 4))

        Entry(
            container, textvariable=self.github_user,
            font=(FONT_FAMILY, 10), relief="solid", borderwidth=1,
        ).pack(fill=X, ipady=3)

        Label(
            container,
            text="Si proporcionas tu usuario, Motor IA puede sincronizar tu base de conocimiento con un repo privado.",
            bg=BODY_BG, fg="#757575",
            font=(FONT_FAMILY, 8),
            anchor=W,
        ).pack(fill=X, pady=(2, 0))

        # Footer
        self._make_button(self.footer_frame, "Siguiente >", lambda: self._show_screen(2))
        self._make_button(self.footer_frame, "< Atras", lambda: self._show_screen(0), side=LEFT)

    def _browse_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Seleccionar directorio de instalacion")
        if chosen:
            self.install_dir.set(chosen)

    # ======================================================================
    # SCREEN 3: Dominios de Conocimiento
    # ======================================================================
    def _screen_domains(self) -> None:
        container = Frame(self.body_frame, bg=BODY_BG)
        container.pack(fill=BOTH, expand=True, padx=30, pady=10)

        Label(
            container,
            text="Paso 3: Dominios de Conocimiento",
            bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 13, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(0, 6))

        Label(
            container,
            text="Como desea inicializar los dominios?",
            bg=BODY_BG, fg="#424242",
            font=(FONT_FAMILY, 10),
            anchor=W,
        ).pack(fill=X, pady=(0, 10))

        # --- Opcion 1: Desde cero ---
        Radiobutton(
            container, text="Empezar desde cero",
            variable=self.domain_mode, value="desde_cero",
            bg=BODY_BG, fg="#212121", activebackground=BODY_BG,
            font=(FONT_FAMILY, 10, "bold"), anchor=W,
            selectcolor=BODY_BG,
            command=self._on_domain_mode_change,
        ).pack(fill=X, pady=(0, 0))
        Label(
            container,
            text="      El motor creara dominios automaticamente segun su uso.",
            bg=BODY_BG, fg="#757575",
            font=(FONT_FAMILY, 9), anchor=W,
        ).pack(fill=X, pady=(0, 6))

        # --- Opcion 2: Explorar disco ---
        Radiobutton(
            container, text="Explorar mi disco",
            variable=self.domain_mode, value="explorar_disco",
            bg=BODY_BG, fg="#212121", activebackground=BODY_BG,
            font=(FONT_FAMILY, 10, "bold"), anchor=W,
            selectcolor=BODY_BG,
            command=self._on_domain_mode_change,
        ).pack(fill=X, pady=(0, 0))
        Label(
            container,
            text="      Escanea sus carpetas para crear dominios basados en sus archivos.",
            bg=BODY_BG, fg="#757575",
            font=(FONT_FAMILY, 9), anchor=W,
        ).pack(fill=X, pady=(0, 2))

        # Frame para boton y label de carpetas seleccionadas
        self.scan_frame = Frame(container, bg=BODY_BG)
        self.scan_frame.pack(fill=X, padx=40, pady=(0, 6))

        self.btn_select_folders = Button(
            self.scan_frame, text="Seleccionar carpetas...",
            command=self._select_scan_folders,
            font=(FONT_FAMILY, 9), padx=10, pady=2,
        )
        self.btn_select_folders.pack(side=LEFT)

        self.lbl_scan_paths = Label(
            self.scan_frame,
            text="  Ninguna carpeta seleccionada",
            bg=BODY_BG, fg="#757575",
            font=(FONT_FAMILY, 8), anchor=W,
        )
        self.lbl_scan_paths.pack(side=LEFT, padx=(8, 0))

        # --- Opcion 3: Perfil predefinido ---
        Radiobutton(
            container, text="Cargar perfil predefinido",
            variable=self.domain_mode, value="perfil_predefinido",
            bg=BODY_BG, fg="#212121", activebackground=BODY_BG,
            font=(FONT_FAMILY, 10, "bold"), anchor=W,
            selectcolor=BODY_BG,
            command=self._on_domain_mode_change,
        ).pack(fill=X, pady=(4, 2))

        self.presets_frame = Frame(container, bg=BODY_BG)
        self.presets_frame.pack(fill=X, padx=40, pady=(0, 4))

        Checkbutton(
            self.presets_frame, text="Solution Advisor GBM (13 dom.)",
            variable=self.preset_sa_gbm, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 9), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=1)
        Checkbutton(
            self.presets_frame, text="Desarrollador de Software (6)",
            variable=self.preset_dev, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 9), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=1)
        Checkbutton(
            self.presets_frame, text="Data Science / Analytics (4)",
            variable=self.preset_data, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 9), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=1)
        Checkbutton(
            self.presets_frame, text="Administracion de Empresas (4)",
            variable=self.preset_admin, bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 9), activebackground=BODY_BG,
            selectcolor=BODY_BG, anchor=W,
        ).pack(fill=X, pady=1)

        # Aplicar estado visual inicial
        self._on_domain_mode_change()

        # Footer
        self._make_button(self.footer_frame, "Instalar >", self._start_install)
        self._make_button(self.footer_frame, "< Atras", lambda: self._show_screen(1), side=LEFT)

    def _on_domain_mode_change(self) -> None:
        """Habilita/deshabilita widgets segun el modo de dominio seleccionado."""
        mode = self.domain_mode.get()
        # Scan folder widgets
        scan_state = NORMAL if mode == "explorar_disco" else DISABLED
        if hasattr(self, "btn_select_folders"):
            self.btn_select_folders.config(state=scan_state)
        # Preset checkboxes
        preset_state = NORMAL if mode == "perfil_predefinido" else DISABLED
        if hasattr(self, "presets_frame"):
            for child in self.presets_frame.winfo_children():
                child.config(state=preset_state)

    def _select_scan_folders(self) -> None:
        """Abre dialogo para seleccionar carpetas a escanear."""
        chosen = filedialog.askdirectory(title="Seleccionar carpeta para escanear")
        if chosen and chosen not in self.scan_paths:
            self.scan_paths.append(chosen)
        if self.scan_paths:
            display = f"  {len(self.scan_paths)} carpeta(s) seleccionada(s)"
            self.lbl_scan_paths.config(text=display, fg="#1565c0")
        else:
            self.lbl_scan_paths.config(text="  Ninguna carpeta seleccionada", fg="#757575")

    def _get_selected_presets(self) -> list[str]:
        """Retorna lista de nombres de presets seleccionados."""
        presets = []
        if self.preset_sa_gbm.get():
            presets.append("solution_advisor_gbm")
        if self.preset_dev.get():
            presets.append("desarrollador_software")
        if self.preset_data.get():
            presets.append("data_science")
        if self.preset_admin.get():
            presets.append("administracion_empresas")
        return presets

    def _get_preset_domain_count(self) -> int:
        """Calcula el total de dominios de los presets seleccionados."""
        counts = {
            "solution_advisor_gbm": 13,
            "desarrollador_software": 6,
            "data_science": 4,
            "administracion_empresas": 4,
        }
        return sum(counts.get(p, 0) for p in self._get_selected_presets())

    # ======================================================================
    # SCREEN 4: Progreso
    # ======================================================================
    def _screen_progress(self) -> None:
        container = Frame(self.body_frame, bg=BODY_BG)
        container.pack(fill=BOTH, expand=True, padx=30, pady=15)

        Label(
            container,
            text="Instalando Motor Fusion IA...",
            bg=BODY_BG, fg="#212121",
            font=(FONT_FAMILY, 13, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(0, 10))

        self.progress_bar = Progressbar(
            container, orient=HORIZONTAL, length=600,
            mode="determinate", style="Blue.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill=X, pady=(0, 10))

        log_frame = Frame(container, bg=BODY_BG)
        log_frame.pack(fill=BOTH, expand=True)

        scrollbar = Scrollbar(log_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.log_text = Text(
            log_frame, wrap=WORD, font=("Consolas" if platform.system() == "Windows" else "Courier", 9),
            bg="#fafafa", fg="#212121", relief="solid", borderwidth=1,
            state=DISABLED, yscrollcommand=scrollbar.set, height=12,
        )
        self.log_text.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Configurar tags de color
        self.log_text.tag_configure("ok", foreground=SUCCESS_FG)
        self.log_text.tag_configure("err", foreground="#c62828")
        self.log_text.tag_configure("info", foreground="#1565c0")

        # Boton siguiente (deshabilitado hasta que termine)
        self.btn_next_progress = self._make_button(
            self.footer_frame, "Siguiente >",
            lambda: self._show_screen(4), state=DISABLED,
        )

    def _log(self, msg: str, tag: str = "") -> None:
        """Agrega un mensaje al log de progreso (thread-safe)."""
        def _append():
            self.log_text.config(state=NORMAL)
            if tag:
                self.log_text.insert(END, msg + "\n", tag)
            else:
                self.log_text.insert(END, msg + "\n")
            self.log_text.config(state=DISABLED)
            self.log_text.see(END)
        self.root.after(0, _append)

    def _set_progress(self, value: float) -> None:
        """Actualiza la barra de progreso (thread-safe)."""
        self.root.after(0, lambda: self.progress_bar.configure(value=value))

    # ======================================================================
    # Logica de instalacion (ejecuta en hilo separado)
    # ======================================================================

    def _start_install(self) -> None:
        """Valida y lanza la instalacion en un hilo."""
        # Validar fuente
        if self.motor_source is None:
            messagebox.showerror(
                "Error",
                "No se encontraron los archivos fuente de Motor IA.\n"
                "Asegurate de ejecutar el instalador desde el directorio correcto.",
            )
            return

        install_path = Path(self.install_dir.get().strip())
        if not install_path.parts:
            messagebox.showerror("Error", "Debes especificar un directorio de instalacion.")
            return

        # Ir a pantalla de progreso
        self._show_screen(3)

        # Lanzar hilo
        thread = threading.Thread(target=self._run_install, daemon=True)
        thread.start()

    def _run_install(self) -> None:
        """Proceso de instalacion completo."""
        install_path = Path(self.install_dir.get().strip())
        source = self.motor_source
        total_steps = 8
        step = 0

        try:
            # ---- Paso 1: Crear directorio de instalacion -------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            self._log(f"[1/{total_steps}] Creando directorio de instalacion...", "info")
            install_path.mkdir(parents=True, exist_ok=True)
            self._log(f"   -> {install_path}", "ok")

            # ---- Paso 2: Copiar Motor IA -----------------------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            self._log(f"[2/{total_steps}] Copiando Motor IA...", "info")
            copied_count = self._copy_motor_files(source, install_path)
            self._log(f"   -> {copied_count} archivos copiados", "ok")

            # ---- Paso 3: Crear directorio de datos -------------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            self._log(f"[3/{total_steps}] Creando directorio de datos (~/.adaptive_cli/)...", "info")
            data_dir = _adaptive_cli_dir()
            for subdir in ["knowledge", "locks", "hook_state"]:
                (data_dir / subdir).mkdir(parents=True, exist_ok=True)
            self._log(f"   -> {data_dir}", "ok")

            # ---- Paso 4: Inicializar dominios de conocimiento --------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            domain_mode = self.domain_mode.get()
            if domain_mode == "explorar_disco" and self.scan_paths:
                self._log(f"[4/{total_steps}] Escaneando disco para descubrir dominios...", "info")
                self._log(f"   -> Carpetas: {len(self.scan_paths)}", "info")
                try:
                    sys.path.insert(0, str(install_path))
                    from core import disk_scanner
                    def _scan_progress(msg):
                        self._log(f"   {msg}")
                    result = disk_scanner.scan_and_apply(
                        self.scan_paths,
                        progress_callback=_scan_progress,
                    )
                    self.domains_created = result if isinstance(result, int) else 0
                    self._log(f"   -> {self.domains_created} dominios descubiertos", "ok")
                    self.domains_summary = f"{self.domains_created} (descubiertos escaneando su disco)"
                except ImportError:
                    self._log("   -> Modulo disk_scanner no disponible, se omite escaneo", "err")
                    self.domains_created = 0
                    self.domains_summary = "0 (disk_scanner no disponible)"
                except Exception as exc:
                    self._log(f"   -> Error en escaneo: {exc}", "err")
                    self.domains_created = 0
                    self.domains_summary = "0 (error en escaneo)"
            elif domain_mode == "perfil_predefinido":
                selected = self._get_selected_presets()
                if selected:
                    self._log(f"[4/{total_steps}] Aplicando perfiles predefinidos ({len(selected)})...", "info")
                    try:
                        sys.path.insert(0, str(install_path))
                        from core import domain_presets
                        domain_presets.apply_multiple_presets(selected)
                        self.domains_created = self._get_preset_domain_count()
                        preset_names = ", ".join(selected)
                        self._log(f"   -> {self.domains_created} dominios creados", "ok")
                        self.domains_summary = f"{self.domains_created} (perfil: {preset_names})"
                    except ImportError:
                        self._log("   -> Modulo domain_presets no disponible, se omite", "err")
                        self.domains_created = 0
                        self.domains_summary = "0 (domain_presets no disponible)"
                    except Exception as exc:
                        self._log(f"   -> Error aplicando presets: {exc}", "err")
                        self.domains_created = 0
                        self.domains_summary = "0 (error en presets)"
                else:
                    self._log(f"[4/{total_steps}] Ningun perfil seleccionado, se omite", "info")
                    self.domains_created = 0
                    self.domains_summary = "0 (se crearan automaticamente)"
            else:
                self._log(f"[4/{total_steps}] Dominios: empezar desde cero", "info")
                self._log("   -> Los dominios se crearan automaticamente segun su uso", "ok")
                self.domains_created = 0
                self.domains_summary = "0 (se crearan automaticamente)"

            # ---- Paso 5: Configurar adaptador Claude Code ------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            if self.chk_claude.get():
                self._log(f"[5/{total_steps}] Configurando adaptador Claude Code...", "info")
                hooks_ok = self._configure_claude_hooks(install_path)
                if hooks_ok:
                    self._log("   -> Hooks registrados en Claude Code CLI", "ok")
                else:
                    self._log("   -> No se encontro settings.json de Claude Code. Se creara.", "info")
                    self._create_claude_settings(install_path)
                    self._log("   -> Archivo de configuracion creado", "ok")
            else:
                self._log(f"[5/{total_steps}] Adaptador Claude Code: omitido por el usuario", "info")

            # ---- Paso 6: Configurar Ollama ---------------------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            if self.chk_ollama.get():
                self._log(f"[6/{total_steps}] Verificando Ollama...", "info")
                ollama_ok = self._verify_ollama()
                if ollama_ok:
                    self._log("   -> Ollama detectado y configurado", "ok")
                else:
                    self._log("   -> Ollama no encontrado. Instalalo despues y Motor IA lo detectara.", "err")
            else:
                self._log(f"[6/{total_steps}] Adaptador Ollama: omitido", "info")

            # ---- Paso 7: Guardar configuracion y GitHub --------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            self._log(f"[7/{total_steps}] Guardando configuracion...", "info")
            self._save_install_config(install_path)
            gh = self.github_user.get().strip()
            if gh:
                self._log(f"   -> GitHub user: {gh}", "ok")
            self._log("   -> install_config.json guardado", "ok")

            # ---- Paso 8: Crear desinstalador y verificar -------------------
            step += 1
            self._set_progress((step / total_steps) * 100)
            self._log(f"[8/{total_steps}] Creando desinstalador y verificando...", "info")
            self._create_uninstaller(install_path)
            self._log("   -> uninstall.py creado", "ok")

            # Verificacion final
            ok = self._verify_installation(install_path)
            if ok:
                self._log("")
                self._log("=" * 55)
                self._log("  INSTALACION COMPLETADA EXITOSAMENTE", "ok")
                self._log("=" * 55)
                self.install_success = True
            else:
                self._log("")
                self._log("ADVERTENCIA: La verificacion detecto problemas.", "err")
                self.install_success = True  # Parcial pero continuar

            self._set_progress(100)

        except PermissionError as exc:
            self._log(f"\nERROR DE PERMISOS: {exc}", "err")
            self._log("Intenta ejecutar el instalador como administrador.", "err")
        except Exception as exc:
            self._log(f"\nERROR: {exc}", "err")

        # Habilitar boton siguiente
        self.root.after(0, lambda: self.btn_next_progress.config(state=NORMAL))

    # -- Funciones de instalacion -------------------------------------------

    def _copy_motor_files(self, source: Path, dest: Path) -> int:
        """Copia todos los archivos .py y estructuras del motor al destino."""
        count = 0
        # Directorios a copiar
        dirs_to_copy = ["core", "adapters", "hooks"]
        # Archivos raiz a copiar
        root_files = [
            "__init__.py", "config.py", "mcp_kb_server.py",
            "ingest_knowledge.py", "ollama_chat.py",
            "sync_to_github.py", "restore_from_github.py",
        ]

        # Copiar archivos raiz
        for fname in root_files:
            src_file = source / fname
            if src_file.is_file():
                dst_file = dest / fname
                shutil.copy2(str(src_file), str(dst_file))
                count += 1

        # Copiar subdirectorios
        for dname in dirs_to_copy:
            src_dir = source / dname
            dst_dir = dest / dname
            if src_dir.is_dir():
                if dst_dir.exists():
                    shutil.rmtree(str(dst_dir))
                shutil.copytree(
                    str(src_dir), str(dst_dir),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                # Contar archivos copiados
                for _root, _dirs, files in os.walk(str(dst_dir)):
                    count += len([f for f in files if f.endswith(".py")])

        return count

    def _configure_claude_hooks(self, install_path: Path) -> bool:
        """Registra los hooks de Motor IA en Claude Code CLI settings.json."""
        settings_path = _claude_settings_path()
        if not settings_path.is_file():
            return False

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            settings = {}

        # Preparar hooks
        python_cmd = self._get_python_command()
        hooks_dir = install_path / "hooks"

        hook_definitions = [
            {
                "type": "PreToolUse",
                "command": f"{python_cmd} \"{hooks_dir / 'session_start.py'}\"",
            },
            {
                "type": "UserPromptSubmit",
                "command": f"{python_cmd} \"{hooks_dir / 'user_prompt_submit.py'}\"",
            },
            {
                "type": "PostToolUse",
                "command": f"{python_cmd} \"{hooks_dir / 'post_tool_use.py'}\"",
            },
            {
                "type": "Stop",
                "command": f"{python_cmd} \"{hooks_dir / 'session_end.py'}\"",
            },
        ]

        # Obtener hooks existentes o crear lista vacia
        existing_hooks = settings.get("hooks", [])
        if not isinstance(existing_hooks, list):
            existing_hooks = []

        # Remover hooks previos de Motor IA (por si ya estaban)
        motor_marker = str(hooks_dir)
        existing_hooks = [
            h for h in existing_hooks
            if motor_marker not in h.get("command", "")
        ]

        # Agregar nuevos hooks
        existing_hooks.extend(hook_definitions)
        settings["hooks"] = existing_hooks

        # Guardar
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        return True

    def _create_claude_settings(self, install_path: Path) -> None:
        """Crea el archivo settings.json de Claude Code con los hooks."""
        settings_path = _claude_settings_path()
        python_cmd = self._get_python_command()
        hooks_dir = install_path / "hooks"

        settings = {
            "hooks": [
                {
                    "type": "PreToolUse",
                    "command": f"{python_cmd} \"{hooks_dir / 'session_start.py'}\"",
                },
                {
                    "type": "UserPromptSubmit",
                    "command": f"{python_cmd} \"{hooks_dir / 'user_prompt_submit.py'}\"",
                },
                {
                    "type": "PostToolUse",
                    "command": f"{python_cmd} \"{hooks_dir / 'post_tool_use.py'}\"",
                },
                {
                    "type": "Stop",
                    "command": f"{python_cmd} \"{hooks_dir / 'session_end.py'}\"",
                },
            ]
        }

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def _verify_ollama(self) -> bool:
        """Verifica si Ollama esta instalado y accesible."""
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _get_python_command(self) -> str:
        """Determina el comando de Python a usar en hooks."""
        # Priorizar python3 en Mac/Linux, python en Windows
        if platform.system() == "Windows":
            return "python"
        return "python3"

    def _save_install_config(self, install_path: Path) -> None:
        """Guarda la configuracion de instalacion."""
        self.install_config = {
            "version": "1.0.0",
            "install_dir": str(install_path),
            "data_dir": str(_adaptive_cli_dir()),
            "adapters": {
                "claude_code": self.chk_claude.get(),
                "gemini": self.chk_gemini.get(),
                "ollama": self.chk_ollama.get(),
            },
            "github_user": self.github_user.get().strip() or None,
            "domain_mode": self.domain_mode.get(),
            "domains_created": self.domains_created,
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "installed_at": self._now_iso(),
        }

        config_path = install_path / "install_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.install_config, f, indent=2, ensure_ascii=False)

        # Tambien guardar en directorio de datos
        data_config = _adaptive_cli_dir() / "install_config.json"
        with open(data_config, "w", encoding="utf-8") as f:
            json.dump(self.install_config, f, indent=2, ensure_ascii=False)

    def _now_iso(self) -> str:
        """Timestamp ISO 8601 sin dependencia de datetime (usa time)."""
        import time
        t = time.localtime()
        return (
            f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}"
            f"T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
        )

    def _create_uninstaller(self, install_path: Path) -> None:
        """Genera un script de desinstalacion."""
        uninstall_code = f'''\
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motor Fusion IA - Desinstalador"""
import json
import shutil
import sys
from pathlib import Path

INSTALL_DIR = Path(r"{install_path}")
DATA_DIR = Path.home() / ".adaptive_cli"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

def main():
    print("=" * 50)
    print("  Motor Fusion IA - Desinstalador")
    print("=" * 50)
    print()
    print(f"Directorio de instalacion: {{INSTALL_DIR}}")
    print(f"Directorio de datos:       {{DATA_DIR}}")
    print()

    resp = input("Deseas desinstalar Motor Fusion IA? (s/n): ").strip().lower()
    if resp not in ("s", "si", "y", "yes"):
        print("Desinstalacion cancelada.")
        return

    # Remover hooks de Claude Code
    if CLAUDE_SETTINGS.is_file():
        try:
            with open(CLAUDE_SETTINGS, "r", encoding="utf-8") as f:
                settings = json.load(f)
            hooks = settings.get("hooks", [])
            marker = str(INSTALL_DIR / "hooks")
            settings["hooks"] = [h for h in hooks if marker not in h.get("command", "")]
            with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            print("[OK] Hooks removidos de Claude Code CLI")
        except Exception as e:
            print(f"[WARN] No se pudieron remover hooks: {{e}}")

    # Preguntar si borrar datos
    borrar_datos = input("Deseas borrar tambien los datos de aprendizaje? (s/n): ").strip().lower()
    if borrar_datos in ("s", "si", "y", "yes"):
        if DATA_DIR.exists():
            shutil.rmtree(str(DATA_DIR))
            print(f"[OK] Datos borrados: {{DATA_DIR}}")
    else:
        print("[INFO] Datos de aprendizaje conservados.")

    # Borrar directorio de instalacion
    print(f"Eliminando {{INSTALL_DIR}}...")
    # No podemos borrar el propio script mientras corre,
    # asi que dejamos un mensaje.
    for item in INSTALL_DIR.iterdir():
        if item.name == "uninstall.py":
            continue
        if item.is_dir():
            shutil.rmtree(str(item))
        else:
            item.unlink()
    print()
    print("[OK] Motor Fusion IA desinstalado.")
    print("     Puedes borrar manualmente este archivo: uninstall.py")
    print()
    input("Presiona Enter para salir...")

if __name__ == "__main__":
    main()
'''
        uninstall_path = install_path / "uninstall.py"
        with open(uninstall_path, "w", encoding="utf-8") as f:
            f.write(uninstall_code)

    def _verify_installation(self, install_path: Path) -> bool:
        """Verifica que los archivos criticos existan."""
        critical_files = [
            install_path / "config.py",
            install_path / "core" / "knowledge_base.py",
            install_path / "hooks" / "session_start.py",
            install_path / "install_config.json",
        ]
        all_ok = True
        for fpath in critical_files:
            if fpath.is_file():
                self._log(f"   [OK] {fpath.name}", "ok")
            else:
                self._log(f"   [FALTA] {fpath.name}", "err")
                all_ok = False
        return all_ok

    # ======================================================================
    # SCREEN 5: Completado
    # ======================================================================
    def _screen_complete(self) -> None:
        container = Frame(self.body_frame, bg=BODY_BG)
        container.pack(fill=BOTH, expand=True, padx=30, pady=15)

        if self.install_success:
            # Checkmark grande
            Label(
                container,
                text="[OK]",
                bg=BODY_BG, fg=SUCCESS_FG,
                font=(FONT_FAMILY, 48, "bold"),
            ).pack(pady=(10, 5))

            Label(
                container,
                text="Instalacion completada exitosamente",
                bg=BODY_BG, fg=SUCCESS_FG,
                font=(FONT_FAMILY, 16, "bold"),
            ).pack(pady=(0, 15))
        else:
            Label(
                container,
                text="Instalacion completada con advertencias",
                bg=BODY_BG, fg="#e65100",
                font=(FONT_FAMILY, 16, "bold"),
            ).pack(pady=(20, 15))

        Separator(container, orient=HORIZONTAL).pack(fill=X, pady=5)

        # Resumen
        summary_frame = Frame(container, bg="#f5f5f5", relief="solid", borderwidth=1)
        summary_frame.pack(fill=X, pady=10, ipady=8, ipadx=10)

        install_dir_str = self.install_dir.get().strip()
        adapters_str = []
        if self.chk_claude.get():
            adapters_str.append("Claude Code CLI")
        if self.chk_gemini.get():
            adapters_str.append("Gemini CLI")
        if self.chk_ollama.get():
            adapters_str.append("Ollama")
        adapters_display = ", ".join(adapters_str) if adapters_str else "Ninguno"

        domains_display = self.domains_summary if self.domains_summary else "0 (se crearan automaticamente)"

        summary_lines = [
            ("Directorio de instalacion:", install_dir_str),
            ("Directorio de datos:", str(_adaptive_cli_dir())),
            ("Adaptadores configurados:", adapters_display),
            ("Dominios iniciales:", domains_display),
        ]
        gh = self.github_user.get().strip()
        if gh:
            summary_lines.append(("Usuario GitHub:", gh))

        for label_text, value_text in summary_lines:
            row = Frame(summary_frame, bg="#f5f5f5")
            row.pack(fill=X, padx=10, pady=2)
            Label(
                row, text=label_text, bg="#f5f5f5", fg="#424242",
                font=(FONT_FAMILY, 9, "bold"), width=28, anchor=W,
            ).pack(side=LEFT)
            Label(
                row, text=value_text, bg="#f5f5f5", fg="#212121",
                font=(FONT_FAMILY, 9), anchor=W,
            ).pack(side=LEFT, fill=X, expand=True)

        # Nota de uso
        Label(
            container,
            text="Para empezar a usar Motor Fusion IA, abre tu CLI y trabaja normalmente.\nEl motor aprendera automaticamente de tus interacciones.",
            bg=BODY_BG, fg="#616161",
            font=(FONT_FAMILY, 9),
            justify=LEFT, anchor=W,
        ).pack(fill=X, pady=(10, 0))

        # Footer con botones
        self._make_button(self.footer_frame, "Finalizar", self._on_finish)
        self._make_button(
            self.footer_frame, "Abrir Manual",
            self._open_manual, side=LEFT,
        )

    def _open_manual(self) -> None:
        """Abre el manual HTML en el navegador por defecto."""
        # Buscar manual en varias ubicaciones
        candidates = [
            Path(self.install_dir.get()) / "docs" / "manual.html",
            Path(self.install_dir.get()) / "manual.html",
            Path(__file__).resolve().parent / "docs" / "manual.html",
            Path(__file__).resolve().parent.parent / "docs" / "manual.html",
        ]
        for candidate in candidates:
            if candidate.is_file():
                webbrowser.open(candidate.as_uri())
                return

        messagebox.showinfo(
            "Manual no encontrado",
            "No se encontro el archivo de manual.\n"
            "Consulta la documentacion en el repositorio del proyecto.",
        )

    def _on_finish(self) -> None:
        """Cierra el instalador."""
        self.root.destroy()

    # -- Punto de entrada ---------------------------------------------------
    def run(self) -> None:
        """Inicia el loop principal de tkinter."""
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    app = InstallerApp()
    app.run()


if __name__ == "__main__":
    main()
