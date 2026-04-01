import copy
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app_runtime import ensure_user_config, get_bundle_dir, get_install_dir, is_frozen, resolve_user_path
from clicer import ACTION_TEMPLATES, DEFAULT_CONFIG, normalize_actions

try:
    from pynput import keyboard, mouse
except ImportError:  # pragma: no cover
    keyboard = None
    mouse = None


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ensure_user_config(DEFAULT_CONFIG)
SCRIPT_PATH = BASE_DIR / "clicer.py"
ICON_PATH = get_bundle_dir() / "assets" / "emulation-work.ico"

TYPE_LABELS = {
    "switch_tab": "Переключить вкладку",
    "scroll": "Прокрутка",
    "pause": "Пауза",
    "wait": "Ожидание",
    "move_random": "Случайное движение мыши",
    "mouse_move": "Перемещение мыши",
    "click": "Клик мышью",
    "keypress": "Клавиша",
    "hotkey": "Горячая клавиша",
}

RUN_MODE_LABELS = {
    "cycles": "Количество циклов",
    "infinite": "Бесконечная работа",
    "timer": "Работа по таймеру",
}
RUN_MODE_VALUES = {label: key for key, label in RUN_MODE_LABELS.items()}

FIELDS = {
    "switch_tab": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("switch_mode", "Режим переключения", "mapped_combo", (("ctrl_tab", "Ctrl+Tab"), ("alt_tab_delay", "Alt+Tab с задержкой"))),
        ("repeat_min", "Повтор мин", "int"),
        ("repeat_max", "Повтор макс", "int"),
        ("hold_before_tab_min", "Удержание Alt до Tab мин", "float"),
        ("hold_before_tab_max", "Удержание Alt до Tab макс", "float"),
        ("hold_after_tab_min", "Удержание Alt после Tab мин", "float"),
        ("hold_after_tab_max", "Удержание Alt после Tab макс", "float"),
        ("sleep_after_min", "Пауза мин", "float"),
        ("sleep_after_max", "Пауза макс", "float"),
    ],
    "scroll": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("repeat_min", "Повтор мин", "int"),
        ("repeat_max", "Повтор макс", "int"),
        ("amount_min", "Скролл мин", "int"),
        ("amount_max", "Скролл макс", "int"),
        ("sleep_min", "Пауза мин", "float"),
        ("sleep_max", "Пауза макс", "float"),
        ("micro_move_chance", "Шанс микродвижения", "float"),
        ("micro_move_x_min", "Смещение X мин", "int"),
        ("micro_move_x_max", "Смещение X макс", "int"),
        ("micro_move_y_min", "Смещение Y мин", "int"),
        ("micro_move_y_max", "Смещение Y макс", "int"),
        ("micro_move_duration_min", "Длит. микродв. мин", "float"),
        ("micro_move_duration_max", "Длит. микродв. макс", "float"),
    ],
    "pause": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("duration_min", "Длительность мин", "float"),
        ("duration_max", "Длительность макс", "float"),
    ],
    "wait": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("duration_min", "Ожидание мин", "float"),
        ("duration_max", "Ожидание макс", "float"),
    ],
    "move_random": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x_margin", "Отступ X", "int"),
        ("y_margin", "Отступ Y", "int"),
        ("human_like", "Человеческая имитация", "bool"),
        ("duration_min", "Длит. мин", "float"),
        ("duration_max", "Длит. макс", "float"),
    ],
    "mouse_move": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x", "X", "int"),
        ("y", "Y", "int"),
        ("duration_min", "Длит. мин", "float"),
        ("duration_max", "Длит. макс", "float"),
    ],
    "click": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x", "X", "optional_int"),
        ("y", "Y", "optional_int"),
        ("button", "Кнопка", "combo", ("left", "right", "middle")),
        ("clicks", "Кликов", "int"),
        ("interval", "Интервал", "float"),
    ],
    "keypress": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("key", "Клавиша", "str"),
        ("sleep_after_min", "Пауза мин", "float"),
        ("sleep_after_max", "Пауза макс", "float"),
    ],
    "hotkey": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("keys", "Клавиши через запятую", "csv"),
        ("sleep_after_min", "Пауза мин", "float"),
        ("sleep_after_max", "Пауза макс", "float"),
    ],
}


class Recorder:
    def __init__(self, done):
        self.done = done
        self.actions = []
        self.last_time = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.modifiers = []
        self.pressed = set()
        self.recording = False

    def start(self):
        if keyboard is None or mouse is None:
            raise RuntimeError("Для записи нужна библиотека pynput.")
        self.actions = []
        self.last_time = None
        self.modifiers = []
        self.pressed = set()
        self.recording = True
        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.done(copy.deepcopy(self.actions))

    def _pause(self):
        now = time.monotonic()
        if self.last_time is not None:
            delta = round(now - self.last_time, 2)
            if delta >= 0.15:
                self.actions.append(
                    {
                        "type": "pause",
                        "label": "Пауза из записи",
                        "enabled": True,
                        "duration_min": delta,
                        "duration_max": delta,
                    }
                )
        self.last_time = now

    def on_click(self, x, y, button, pressed):
        if self.recording and pressed:
            self._pause()
            self.actions.append(
                {
                    "type": "click",
                    "label": "Клик из записи",
                    "enabled": True,
                    "x": int(x),
                    "y": int(y),
                    "button": getattr(button, "name", "left"),
                    "clicks": 1,
                    "interval": 0.0,
                }
            )

    def on_scroll(self, x, y, dx, dy):
        if self.recording:
            self._pause()
            amount = int(dy * 120)
            self.actions.append(
                {
                    "type": "scroll",
                    "label": "Прокрутка из записи",
                    "enabled": True,
                    "repeat_min": 1,
                    "repeat_max": 1,
                    "amount_min": amount,
                    "amount_max": amount,
                    "sleep_min": 0.0,
                    "sleep_max": 0.0,
                    "micro_move_chance": 0.0,
                }
            )

    def on_press(self, key):
        if not self.recording:
            return
        name = self._key_name(key)
        if not name:
            return
        if name == "f8":
            self.stop()
            return False
        if name in self.pressed:
            return
        self.pressed.add(name)
        if name in {"ctrl", "alt", "shift", "win"}:
            if name not in self.modifiers:
                self.modifiers.append(name)
            return
        self._pause()
        if self.modifiers:
            self.actions.append(
                {
                    "type": "hotkey",
                    "label": "Горячая клавиша из записи",
                    "enabled": True,
                    "keys": [*self.modifiers, name],
                    "sleep_after_min": 0.0,
                    "sleep_after_max": 0.1,
                }
            )
        else:
            self.actions.append(
                {
                    "type": "keypress",
                    "label": "Клавиша из записи",
                    "enabled": True,
                    "key": name,
                    "sleep_after_min": 0.0,
                    "sleep_after_max": 0.1,
                }
            )

    def on_release(self, key):
        name = self._key_name(key)
        if name:
            self.pressed.discard(name)
            self.modifiers = [item for item in self.modifiers if item != name]

    @staticmethod
    def _key_name(key):
        if keyboard is None:
            return None
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else None
        aliases = {
            "ctrl_l": "ctrl",
            "ctrl_r": "ctrl",
            "alt_l": "alt",
            "alt_r": "alt",
            "shift_l": "shift",
            "shift_r": "shift",
            "cmd_l": "win",
            "cmd_r": "win",
            "cmd": "win",
        }
        return aliases.get(getattr(key, "name", None), getattr(key, "name", None))


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Эмуляция работы")
        self._set_window_icon()
        self.root.geometry("1200x860")
        self.process = None
        self.actions = []
        self.selected = None
        self.editor = {}
        self.log_queue = queue.Queue()
        self.recorder = None
        self.recording = False
        self.vars = {
            "startup_delay": tk.StringVar(),
            "run_mode": tk.StringVar(value=RUN_MODE_LABELS["cycles"]),
            "cycles": tk.StringVar(),
            "timer_minutes": tk.StringVar(),
            "log_dir": tk.StringVar(),
            "log_file": tk.StringVar(),
            "log_level": tk.StringVar(),
            "failsafe_enabled": tk.BooleanVar(),
            "prompt_on_exit": tk.BooleanVar(),
        }
        self._build()
        self.load_config(False)
        self.root.after(120, self._flush_logs)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_window_icon(self):
        if not ICON_PATH.exists():
            return
        try:
            self.root.iconbitmap(default=str(ICON_PATH))
        except tk.TclError:
            pass

    def _build(self):
        top = ttk.Frame(self.root, padding=14)
        top.pack(fill="both", expand=True)

        ttk.Label(top, text="Эмуляция работы", font=("Segoe UI Semibold", 19)).pack(anchor="w")
        ttk.Label(
            top,
            text="Без отдельной консоли, с редактированием сценария и записью действий.",
            foreground="#475569",
        ).pack(anchor="w", pady=(2, 12))

        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=(0, 12))
        for text, cmd in [
            ("Загрузить", lambda: self.load_config(True)),
            ("Сохранить", self.save_config),
            ("Старт", self.start_process),
            ("Стоп", self.stop_process),
            ("Открыть логи", self.open_logs),
        ]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 8))
        self.record_btn = ttk.Button(bar, text="Запись действий", command=self.toggle_recording)
        self.record_btn.pack(side="left")
        self.status = ttk.Label(bar, text="Готово")
        self.status.pack(side="right")

        notebook = ttk.Notebook(top)
        notebook.pack(fill="both", expand=True)

        general = ttk.Frame(notebook, padding=12)
        scenario = ttk.Frame(notebook, padding=12)
        logs = ttk.Frame(notebook, padding=12)
        notebook.add(general, text="Общие")
        notebook.add(scenario, text="Сценарий")
        notebook.add(logs, text="Лог")

        form = ttk.LabelFrame(general, text="Настройки", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Задержка перед стартом").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(form, textvariable=self.vars["startup_delay"]).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Режим работы").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.run_mode_combo = ttk.Combobox(
            form,
            textvariable=self.vars["run_mode"],
            values=tuple(RUN_MODE_LABELS.values()),
            state="readonly",
        )
        self.run_mode_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.run_mode_combo.bind("<<ComboboxSelected>>", self.on_run_mode_changed)

        ttk.Label(form, text="Количество циклов").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.cycles_entry = ttk.Entry(form, textvariable=self.vars["cycles"])
        self.cycles_entry.grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Время работы, минут").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.timer_entry = ttk.Entry(form, textvariable=self.vars["timer_minutes"])
        self.timer_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Папка логов").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(form, textvariable=self.vars["log_dir"]).grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Имя лог-файла").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(form, textvariable=self.vars["log_file"]).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Уровень логирования").grid(row=6, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(
            form,
            textvariable=self.vars["log_level"],
            values=("DEBUG", "INFO", "WARNING", "ERROR"),
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(form, text="Включить FailSafe", variable=self.vars["failsafe_enabled"]).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )
        ttk.Checkbutton(form, text="Показывать ENTER после завершения", variable=self.vars["prompt_on_exit"]).grid(
            row=8, column=0, columnspan=2, sticky="w"
        )

        scenario.columnconfigure(0, weight=1)
        scenario.columnconfigure(1, weight=1)
        scenario.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(scenario, text="Действия", padding=12)
        right = ttk.LabelFrame(scenario, text="Параметры выбранного действия", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(1, weight=1)

        btns = ttk.Frame(left)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for text, cmd in [
            ("Добавить", self.add_action),
            ("Дублировать", self.duplicate_action),
            ("Удалить", self.delete_action),
            ("Вверх", lambda: self.move_action(-1)),
            ("Вниз", lambda: self.move_action(1)),
        ]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 6))

        self.tree = ttk.Treeview(left, columns=("on", "type", "label"), show="headings", selectmode="browse")
        self.tree.heading("on", text="✓")
        self.tree.heading("type", text="Тип")
        self.tree.heading("label", text="Название")
        self.tree.column("on", width=55, anchor="center")
        self.tree.column("type", width=180)
        self.tree.column("label", width=280)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        ttk.Label(
            right,
            text="F8 останавливает запись. Записанные шаги добавляются в конец сценария.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.details = ttk.Frame(right)
        self.details.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.details.columnconfigure(1, weight=1)
        ttk.Button(right, text="Применить изменения", command=self.apply_selected).grid(row=2, column=0, sticky="w", pady=(10, 0))

        self.log = tk.Text(
            logs,
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "Здесь будет журнал запуска и записи.\n")
        self.log.configure(state="disabled")

    def on_run_mode_changed(self, _event=None):
        self.update_run_mode_state()

    def update_run_mode_state(self):
        run_mode = RUN_MODE_VALUES.get(self.vars["run_mode"].get(), "cycles")
        self.cycles_entry.configure(state="normal" if run_mode == "cycles" else "disabled")
        self.timer_entry.configure(state="normal" if run_mode == "timer" else "disabled")

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _flush_logs(self):
        while True:
            try:
                text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.append_log(text)
        if self.process and self.process.poll() is not None:
            self.append_log(f"\nПроцесс завершился с кодом {self.process.poll()}.\n")
            self.status.configure(text="Процесс завершен")
            self.process = None
        self.root.after(120, self._flush_logs)

    def load_config(self, show):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                cfg.update({key: value for key, value in loaded.items() if key != "actions"})
                if isinstance(loaded.get("actions"), list):
                    cfg["actions"] = loaded["actions"]

        self.vars["startup_delay"].set(str(cfg.get("startup_delay", 5)))
        self.vars["run_mode"].set(RUN_MODE_LABELS.get(str(cfg.get("run_mode", "cycles")), RUN_MODE_LABELS["cycles"]))
        self.vars["cycles"].set("" if cfg.get("cycles") is None else str(cfg.get("cycles")))
        self.vars["timer_minutes"].set("" if cfg.get("timer_minutes") is None else str(cfg.get("timer_minutes")))
        self.vars["log_dir"].set(str(cfg.get("log_dir", "logs")))
        self.vars["log_file"].set(str(cfg.get("log_file", "clicer.log")))
        self.vars["log_level"].set(str(cfg.get("log_level", "INFO")).upper())
        self.vars["failsafe_enabled"].set(bool(cfg.get("failsafe_enabled", True)))
        self.vars["prompt_on_exit"].set(bool(cfg.get("prompt_on_exit", False)))
        self.actions = normalize_actions(copy.deepcopy(cfg.get("actions", [])))
        self.update_run_mode_state()
        self.refresh_tree()
        self.status.configure(text="Конфиг загружен")
        if show:
            messagebox.showinfo("Конфиг", "Настройки загружены.")

    def collect_config(self):
        if not self.apply_selected_if_needed():
            return None
        if not self.actions:
            raise ValueError("Сценарий пуст.")

        run_mode = RUN_MODE_VALUES.get(self.vars["run_mode"].get(), "cycles")
        config = {
            "startup_delay": self.to_int(self.vars["startup_delay"].get(), "Задержка", True),
            "run_mode": run_mode,
            "cycles": self.to_optional_int(self.vars["cycles"].get(), "Количество циклов"),
            "timer_minutes": self.to_optional_float(self.vars["timer_minutes"].get(), "Время работы"),
            "log_dir": self.vars["log_dir"].get().strip() or "logs",
            "log_file": self.vars["log_file"].get().strip() or "clicer.log",
            "log_level": (self.vars["log_level"].get().strip() or "INFO").upper(),
            "failsafe_enabled": self.vars["failsafe_enabled"].get(),
            "prompt_on_exit": self.vars["prompt_on_exit"].get(),
            "actions": copy.deepcopy(self.actions),
        }

        if run_mode == "cycles" and config["cycles"] is None:
            raise ValueError("Для режима 'Количество циклов' укажите число циклов.")
        if run_mode == "timer" and (config["timer_minutes"] is None or config["timer_minutes"] <= 0):
            raise ValueError("Для режима 'Работа по таймеру' укажите время в минутах.")

        return config

    def save_config(self):
        try:
            cfg = self.collect_config()
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return False
        if cfg is None:
            return False
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(cfg, file, ensure_ascii=False, indent=2)
        self.append_log(f"Конфиг сохранен в {CONFIG_PATH}\n")
        self.status.configure(text="Конфиг сохранен")
        return True

    def refresh_tree(self, select=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, action in enumerate(self.actions):
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "✓" if action.get("enabled", True) else "",
                    TYPE_LABELS.get(action.get("type", ""), action.get("type", "")),
                    action.get("label", ""),
                ),
            )
        if self.actions:
            idx = 0 if select is None else max(0, min(select, len(self.actions) - 1))
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
            self.selected = idx
            self.render_editor(idx)
        else:
            self.selected = None
            self.clear_editor()

    def clear_editor(self):
        self.editor = {}
        for widget in self.details.winfo_children():
            widget.destroy()

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if selection:
            self.selected = int(selection[0])
            self.render_editor(self.selected)

    def render_editor(self, idx):
        self.clear_editor()
        action = self.actions[idx]
        ttk.Label(self.details, text=f"Тип: {TYPE_LABELS.get(action['type'], action['type'])}").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        for row, field in enumerate(FIELDS[action["type"]], start=1):
            name, label, kind, *extra = field
            ttk.Label(self.details, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            widget, var = self.make_widget(kind, action.get(name), extra[0] if extra else None)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self.editor[name] = (var, kind)

    def make_widget(self, kind, value, extra):
        if kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            return ttk.Checkbutton(self.details, variable=var), var
        if kind == "combo":
            var = tk.StringVar(value="" if value is None else str(value))
            return ttk.Combobox(self.details, textvariable=var, values=extra, state="readonly"), var
        if kind == "mapped_combo":
            mapping = dict(extra)
            reverse = {label: key for key, label in mapping.items()}
            display_var = tk.StringVar(value=mapping.get(value, next(iter(mapping.values()))))
            widget = ttk.Combobox(self.details, textvariable=display_var, values=tuple(mapping.values()), state="readonly")
            return widget, (display_var, reverse)
        if kind == "csv":
            value = ", ".join(value) if isinstance(value, list) else value
        var = tk.StringVar(value="" if value is None else str(value))
        return ttk.Entry(self.details, textvariable=var), var

    def apply_selected(self):
        if self.selected is None:
            return False
        action = copy.deepcopy(self.actions[self.selected])
        try:
            for name, (var, kind) in self.editor.items():
                action[name] = self.read_value(var, kind, name)
            self.validate_action(action)
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return False
        self.actions[self.selected] = action
        self.refresh_tree(self.selected)
        self.status.configure(text="Изменения применены")
        return True

    def apply_selected_if_needed(self):
        return True if self.selected is None or not self.editor else self.apply_selected()

    def read_value(self, var, kind, label):
        if kind == "bool":
            return bool(var.get())
        if kind == "mapped_combo":
            display_var, reverse = var
            return reverse[display_var.get()]
        text = var.get().strip()
        if kind == "str":
            return text
        if kind == "int":
            return self.to_int(text, label, False)
        if kind == "optional_int":
            return None if not text else self.to_int(text, label, False)
        if kind == "float":
            return self.to_float(text, label)
        if kind == "csv":
            return [item.strip() for item in text.split(",") if item.strip()]
        return text

    def validate_action(self, action):
        if action["type"] in {"switch_tab", "scroll"} and action["repeat_min"] > action["repeat_max"]:
            raise ValueError("repeat_min не может быть больше repeat_max.")
        if action["type"] in {"pause", "wait"} and action["duration_min"] > action["duration_max"]:
            raise ValueError("duration_min не может быть больше duration_max.")
        if action["type"] == "switch_tab":
            if action["hold_before_tab_min"] > action["hold_before_tab_max"]:
                raise ValueError("Минимальное удержание Alt до Tab больше максимального.")
            if action["hold_after_tab_min"] > action["hold_after_tab_max"]:
                raise ValueError("Минимальное удержание Alt после Tab больше максимального.")
            if action["sleep_after_min"] > action["sleep_after_max"]:
                raise ValueError("Минимальная пауза после действия больше максимальной.")
        if action["type"] == "scroll":
            if action["sleep_min"] > action["sleep_max"]:
                raise ValueError("sleep_min не может быть больше sleep_max.")
            if action["micro_move_duration_min"] > action["micro_move_duration_max"]:
                raise ValueError("Минимальная длительность микродвижения больше максимальной.")
        if action["type"] in {"keypress", "hotkey"} and action["sleep_after_min"] > action["sleep_after_max"]:
            raise ValueError("Минимальная пауза после действия больше максимальной.")
        if action["type"] in {"move_random", "mouse_move"} and action["duration_min"] > action["duration_max"]:
            raise ValueError("Минимальная длительность движения больше максимальной.")
        if action["type"] == "click" and action["clicks"] <= 0:
            raise ValueError("Количество кликов должно быть больше нуля.")

    def add_action(self):
        if not self.apply_selected_if_needed():
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Новое действие")
        dialog.transient(self.root)
        dialog.grab_set()
        value = tk.StringVar(value="scroll")
        ttk.Label(dialog, text="Тип действия:", padding=10).pack(anchor="w")
        ttk.Combobox(dialog, textvariable=value, values=tuple(TYPE_LABELS.keys()), state="readonly").pack(fill="x", padx=10)

        def accept():
            dialog.result = value.get()
            dialog.destroy()

        ttk.Button(dialog, text="Добавить", command=accept).pack(padx=10, pady=10, anchor="w")
        dialog.result = None
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        idx = len(self.actions) if self.selected is None else self.selected + 1
        self.actions.insert(idx, copy.deepcopy(ACTION_TEMPLATES[dialog.result]))
        self.refresh_tree(idx)

    def duplicate_action(self):
        if self.selected is None or not self.apply_selected_if_needed():
            return
        item = copy.deepcopy(self.actions[self.selected])
        item["label"] = f"{item.get('label', 'Действие')} (копия)"
        self.actions.insert(self.selected + 1, item)
        self.refresh_tree(self.selected + 1)

    def delete_action(self):
        if self.selected is None:
            return
        del self.actions[self.selected]
        self.refresh_tree(max(0, self.selected - 1))

    def move_action(self, delta):
        if self.selected is None or not self.apply_selected_if_needed():
            return
        target = self.selected + delta
        if 0 <= target < len(self.actions):
            self.actions[self.selected], self.actions[target] = self.actions[target], self.actions[self.selected]
            self.refresh_tree(target)

    def toggle_recording(self):
        if not self.recording:
            if keyboard is None or mouse is None:
                messagebox.showerror(
                    "Запись недоступна",
                    "Не найдена библиотека pynput. После обновления зависимостей запустите setup.ps1.",
                )
                return
            self.recorder = Recorder(self.finish_recording)
            self.recorder.start()
            self.recording = True
            self.record_btn.configure(text="Остановить запись")
            self.status.configure(text="Идет запись... F8 для остановки")
            self.append_log("\nЗапись действий началась. Остановка: F8\n")
            return
        if self.recorder:
            self.recorder.stop()

    def finish_recording(self, actions):
        def finalize():
            self.recording = False
            self.record_btn.configure(text="Запись действий")
            if actions:
                self.actions.extend(normalize_actions(actions))
                self.refresh_tree(len(self.actions) - 1)
                self.append_log(f"Добавлено записанных действий: {len(actions)}\n")
                self.status.configure(text=f"Записано: {len(actions)} действий")
            else:
                self.append_log("Запись завершена без действий.\n")
                self.status.configure(text="Запись завершена")

        self.root.after(0, finalize)

    def start_process(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Запуск", "Процесс уже выполняется.")
            return
        if not self.save_config():
            return
        if is_frozen():
            cmd = [str(Path(sys.executable)), "--run-automation", "--config", str(CONFIG_PATH), "--no-prompt"]
            working_dir = get_install_dir()
        else:
            python_exe = Path(sys.executable)
            if python_exe.name.lower() == "pythonw.exe":
                candidate = python_exe.with_name("python.exe")
                if candidate.exists():
                    python_exe = candidate
            cmd = [str(python_exe), str(SCRIPT_PATH), "--config", str(CONFIG_PATH), "--no-prompt"]
            working_dir = BASE_DIR
        kwargs = {
            "cwd": working_dir,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = info
        self.append_log(f"\nЗапуск: {' '.join(cmd)}\n")
        self.process = subprocess.Popen(cmd, **kwargs)
        self.status.configure(text="Процесс выполняется")
        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self):
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.log_queue.put(line)

    def stop_process(self):
        if not self.process or self.process.poll() is not None:
            messagebox.showinfo("Стоп", "Активного процесса нет.")
            return
        self.process.terminate()
        self.append_log("Отправлена команда остановки процесса.\n")
        self.status.configure(text="Остановка процесса...")

    def open_logs(self):
        path = resolve_user_path(self.vars["log_dir"].get().strip() or "logs")
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def on_close(self):
        if self.recording and self.recorder:
            self.recorder.stop()
        if self.process and self.process.poll() is None and not messagebox.askyesno(
            "Выход", "Сценарий еще работает. Остановить и закрыть?"
        ):
            return
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.root.destroy()

    @staticmethod
    def to_int(value, label, allow_zero):
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError(f"{label}: нужно целое число.") from exc
        if number < 0 or (number == 0 and not allow_zero):
            raise ValueError(f"{label}: недопустимое значение.")
        return number

    @staticmethod
    def to_optional_int(value, label):
        value = value.strip()
        return None if not value else App.to_int(value, label, False)

    @staticmethod
    def to_float(value, label):
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label}: нужно число.") from exc
        if number < 0:
            raise ValueError(f"{label}: число не может быть отрицательным.")
        return number

    @staticmethod
    def to_optional_float(value, label):
        value = value.strip()
        return None if not value else App.to_float(value, label)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
