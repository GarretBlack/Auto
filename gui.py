import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SCRIPT_PATH = BASE_DIR / "clicer.py"
DEFAULT_CONFIG = {
    "startup_delay": 5,
    "cycles": 1,
    "wait_min": 40,
    "wait_max": 110,
    "read_steps_min": 10,
    "read_steps_max": 18,
    "failsafe_enabled": True,
    "prompt_on_exit": False,
    "log_dir": "logs",
    "log_file": "clicer.log",
    "log_level": "INFO",
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Auto Control Center")
        self.root.geometry("980x720")
        self.root.minsize(860, 620)
        self.root.configure(bg="#eef3f8")

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._configure_style()
        self._build_variables()
        self._build_layout()
        self.load_config(show_message=False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self._flush_log_queue)

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f8")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#1f2937", font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", background="#eef3f8", foreground="#0f172a", font=("Segoe UI Semibold", 18))
        style.configure("Subtitle.TLabel", background="#eef3f8", foreground="#475569", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#eef3f8", foreground="#0f766e", font=("Segoe UI Semibold", 10))
        style.configure("TLabel", background="#ffffff", foreground="#1f2937", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(10, 7))
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=4)
        style.configure("TCheckbutton", background="#ffffff", foreground="#1f2937", font=("Segoe UI", 10))

    def _build_variables(self) -> None:
        self.startup_delay_var = tk.StringVar()
        self.cycles_var = tk.StringVar()
        self.wait_min_var = tk.StringVar()
        self.wait_max_var = tk.StringVar()
        self.read_steps_min_var = tk.StringVar()
        self.read_steps_max_var = tk.StringVar()
        self.log_dir_var = tk.StringVar()
        self.log_file_var = tk.StringVar()
        self.log_level_var = tk.StringVar()
        self.failsafe_var = tk.BooleanVar(value=True)
        self.prompt_on_exit_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Готово к запуску")

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Auto Control Center", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Настройка сценария, быстрый запуск и просмотр лога в одном окне.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, sticky="nsew", pady=(16, 14))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.rowconfigure(0, weight=1)

        self._build_runtime_card(controls).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_logging_card(controls).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        log_card = ttk.LabelFrame(outer, text="Журнал выполнения", style="Card.TLabelframe", padding=14)
        log_card.grid(row=2, column=0, sticky="nsew")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)

        button_row = ttk.Frame(log_card)
        button_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for idx in range(6):
            button_row.columnconfigure(idx, weight=1 if idx == 5 else 0)

        ttk.Button(button_row, text="Загрузить конфиг", command=self.load_config).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="Сохранить конфиг", command=self.save_config).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_row, text="Старт", command=self.start_process).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(button_row, text="Стоп", command=self.stop_process).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(button_row, text="Открыть папку логов", command=self.open_logs_folder).grid(row=0, column=4)

        self.log_widget = tk.Text(
            log_card,
            wrap="word",
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            font=("Consolas", 10),
            padx=12,
            pady=12,
            relief="flat",
        )
        self.log_widget.grid(row=1, column=0, sticky="nsew")
        self.log_widget.insert("end", "Лог интерфейса появится здесь.\n")
        self.log_widget.configure(state="disabled")

    def _build_runtime_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        card = ttk.LabelFrame(parent, text="Параметры запуска", style="Card.TLabelframe", padding=14)
        card.columnconfigure(1, weight=1)

        rows = [
            ("Задержка перед стартом", self.startup_delay_var),
            ("Количество циклов", self.cycles_var),
            ("Пауза между циклами: минимум", self.wait_min_var),
            ("Пауза между циклами: максимум", self.wait_max_var),
            ("Шаги чтения: минимум", self.read_steps_min_var),
            ("Шаги чтения: максимум", self.read_steps_max_var),
        ]
        for row_index, (label_text, variable) in enumerate(rows):
            ttk.Label(card, text=label_text).grid(row=row_index, column=0, sticky="w", pady=6, padx=(0, 12))
            ttk.Entry(card, textvariable=variable).grid(row=row_index, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(card, text="Включить FailSafe", variable=self.failsafe_var).grid(
            row=len(rows), column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        ttk.Checkbutton(card, text="Показывать ENTER в конце", variable=self.prompt_on_exit_var).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=4
        )
        return card

    def _build_logging_card(self, parent: ttk.Frame) -> ttk.LabelFrame:
        card = ttk.LabelFrame(parent, text="Логи и окружение", style="Card.TLabelframe", padding=14)
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Папка логов").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(card, textvariable=self.log_dir_var).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(card, text="Имя лог-файла").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(card, textvariable=self.log_file_var).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(card, text="Уровень логирования").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Combobox(
            card,
            textvariable=self.log_level_var,
            values=("DEBUG", "INFO", "WARNING", "ERROR"),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=6)

        helper = (
            "Подсказка:\n"
            "1. Сохраните конфиг.\n"
            "2. Нажмите Старт.\n"
            "3. Следите за выводом ниже.\n"
            "4. При необходимости остановите процесс кнопкой Стоп."
        )
        ttk.Label(card, text=helper, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(16, 0))
        return card

    def _append_log(self, message: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _flush_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)

        self._update_process_state()
        self.root.after(120, self._flush_log_queue)

    def _update_process_state(self) -> None:
        if self.process is None:
            return

        exit_code = self.process.poll()
        if exit_code is None:
            return

        self.log_queue.put(f"\nПроцесс завершился с кодом {exit_code}.\n")
        self.status_var.set("Процесс завершен")
        self.process = None

    def _read_process_output(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(line)

    def _collect_config(self) -> dict:
        try:
            config = {
                "startup_delay": self._parse_int(self.startup_delay_var.get(), "Задержка перед стартом"),
                "cycles": self._parse_optional_positive_int(self.cycles_var.get(), "Количество циклов"),
                "wait_min": self._parse_int(self.wait_min_var.get(), "Минимальная пауза"),
                "wait_max": self._parse_int(self.wait_max_var.get(), "Максимальная пауза"),
                "read_steps_min": self._parse_int(self.read_steps_min_var.get(), "Минимум шагов чтения"),
                "read_steps_max": self._parse_int(self.read_steps_max_var.get(), "Максимум шагов чтения"),
                "failsafe_enabled": self.failsafe_var.get(),
                "prompt_on_exit": self.prompt_on_exit_var.get(),
                "log_dir": self.log_dir_var.get().strip() or "logs",
                "log_file": self.log_file_var.get().strip() or "clicer.log",
                "log_level": (self.log_level_var.get().strip() or "INFO").upper(),
            }
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if config["wait_min"] > config["wait_max"]:
            raise ValueError("Минимальная пауза не может быть больше максимальной.")
        if config["read_steps_min"] > config["read_steps_max"]:
            raise ValueError("Минимум шагов чтения не может быть больше максимума.")
        return config

    @staticmethod
    def _parse_int(value: str, label: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError(f"{label}: нужно целое число.") from exc
        if number < 0:
            raise ValueError(f"{label}: значение не может быть отрицательным.")
        return number

    @staticmethod
    def _parse_optional_positive_int(value: str, label: str) -> int | None:
        text = value.strip()
        if not text:
            return None
        try:
            number = int(text)
        except ValueError as exc:
            raise ValueError(f"{label}: нужно целое число.") from exc
        if number <= 0:
            raise ValueError(f"{label}: значение должно быть больше нуля.")
        return number

    def load_config(self, show_message: bool = True) -> None:
        config = DEFAULT_CONFIG.copy()
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                config.update(loaded)

        self.startup_delay_var.set(str(config.get("startup_delay", 5)))
        self.cycles_var.set("" if config.get("cycles") is None else str(config.get("cycles")))
        self.wait_min_var.set(str(config.get("wait_min", 40)))
        self.wait_max_var.set(str(config.get("wait_max", 110)))
        self.read_steps_min_var.set(str(config.get("read_steps_min", 10)))
        self.read_steps_max_var.set(str(config.get("read_steps_max", 18)))
        self.log_dir_var.set(str(config.get("log_dir", "logs")))
        self.log_file_var.set(str(config.get("log_file", "clicer.log")))
        self.log_level_var.set(str(config.get("log_level", "INFO")).upper())
        self.failsafe_var.set(bool(config.get("failsafe_enabled", True)))
        self.prompt_on_exit_var.set(bool(config.get("prompt_on_exit", False)))
        self.status_var.set("Конфиг загружен")

        if show_message:
            messagebox.showinfo("Конфиг", "Настройки успешно загружены.")

    def save_config(self) -> bool:
        try:
            config = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("Ошибка валидации", str(exc))
            return False

        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        self.status_var.set("Конфиг сохранен")
        self._append_log(f"Конфиг сохранен в {CONFIG_PATH.name}\n")
        return True

    def start_process(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("Запуск", "Процесс уже запущен.")
            return

        if not self.save_config():
            return

        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--config",
            str(CONFIG_PATH),
            "--no-prompt",
        ]

        self._append_log(f"\nЗапуск: {' '.join(command)}\n")
        self.process = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.status_var.set("Процесс выполняется")

        reader = threading.Thread(target=self._read_process_output, args=(self.process,), daemon=True)
        reader.start()

    def stop_process(self) -> None:
        if self.process is None or self.process.poll() is not None:
            messagebox.showinfo("Стоп", "Сейчас нет активного процесса.")
            return

        self.process.terminate()
        self.status_var.set("Остановка процесса...")
        self._append_log("Отправлена команда остановки процесса.\n")

    def open_logs_folder(self) -> None:
        log_dir = BASE_DIR / (self.log_dir_var.get().strip() or "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(log_dir)

    def on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno("Выход", "Процесс еще работает. Остановить его и закрыть окно?"):
                return
            self.process.terminate()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
