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

from clicer import ACTION_TEMPLATES, DEFAULT_CONFIG

try:
    from pynput import keyboard, mouse
except ImportError:  # pragma: no cover
    keyboard = None
    mouse = None


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SCRIPT_PATH = BASE_DIR / "clicer.py"

TYPE_LABELS = {
    "switch_tab": "Переключить вкладку",
    "scroll": "Прокрутка",
    "pause": "Пауза",
    "wait": "Ожидание",
    "move_random": "Случайное движение мыши",
    "mouse_move": "Перемещение мыши",
    "click": "Клик мышью",
    "keypress": "Нажатие клавиши",
    "hotkey": "Горячая клавиша",
}

FIELDS = {
    "switch_tab": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("repeat_min", "Повтор минимум", "int"),
        ("repeat_max", "Повтор максимум", "int"),
        ("sleep_after_min", "Пауза после минимум", "float"),
        ("sleep_after_max", "Пауза после максимум", "float"),
    ],
    "scroll": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("repeat_min", "Повтор минимум", "int"),
        ("repeat_max", "Повтор максимум", "int"),
        ("amount_min", "Прокрутка минимум", "int"),
        ("amount_max", "Прокрутка максимум", "int"),
        ("sleep_min", "Пауза минимум", "float"),
        ("sleep_max", "Пауза максимум", "float"),
        ("micro_move_chance", "Шанс микродвижения", "float"),
        ("micro_move_x_min", "Смещение X минимум", "int"),
        ("micro_move_x_max", "Смещение X максимум", "int"),
        ("micro_move_y_min", "Смещение Y минимум", "int"),
        ("micro_move_y_max", "Смещение Y максимум", "int"),
        ("micro_move_duration_min", "Длительность микродвижения минимум", "float"),
        ("micro_move_duration_max", "Длительность микродвижения максимум", "float"),
    ],
    "pause": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("duration_min", "Длительность минимум", "float"),
        ("duration_max", "Длительность максимум", "float"),
    ],
    "wait": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("duration_min", "Ожидание минимум", "float"),
        ("duration_max", "Ожидание максимум", "float"),
    ],
    "move_random": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x_margin", "Отступ X", "int"),
        ("y_margin", "Отступ Y", "int"),
        ("duration_min", "Длительность минимум", "float"),
        ("duration_max", "Длительность максимум", "float"),
    ],
    "mouse_move": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x", "X", "int"),
        ("y", "Y", "int"),
        ("duration_min", "Длительность минимум", "float"),
        ("duration_max", "Длительность максимум", "float"),
    ],
    "click": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("x", "X", "optional_int"),
        ("y", "Y", "optional_int"),
        ("button", "Кнопка", "combo", ("left", "right", "middle")),
        ("clicks", "Количество кликов", "int"),
        ("interval", "Интервал", "float"),
    ],
    "keypress": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("key", "Клавиша", "str"),
        ("sleep_after_min", "Пауза после минимум", "float"),
        ("sleep_after_max", "Пауза после максимум", "float"),
    ],
    "hotkey": [
        ("label", "Название", "str"),
        ("enabled", "Включено", "bool"),
        ("keys", "Клавиши через запятую", "csv"),
        ("sleep_after_min", "Пауза после минимум", "float"),
        ("sleep_after_max", "Пауза после максимум", "float"),
    ],
}


class Recorder:
    def __init__(self, done_callback):
        self.done_callback = done_callback
        self.actions = []
        self.last_event_time = None
        self.recording = False
        self.mouse_listener = None
        self.keyboard_listener = None
        self.pressed = set()
        self.modifiers = []

    def start(self):
        if keyboard is None or mouse is None:
            raise RuntimeError("Для записи нужна библиотека pynput.")
        self.actions = []
        self.last_event_time = None
        self.recording = True
        self.pressed.clear()
        self.modifiers.clear()
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
        self.done_callback(copy.deepcopy(self.actions))

    def append_pause(self):
        now = time.monotonic()
        if self.last_event_time is not None:
            delta = round(now - self.last_event_time, 2)
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
        self.last_event_time = now

    def on_click(self, x, y, button, pressed):
        if self.recording and pressed:
            self.append_pause()
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
            self.append_pause()
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
        name = self.normalize_key(key)
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
        self.append_pause()
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
        name = self.normalize_key(key)
        if name:
            self.pressed.discard(name)
            self.modifiers = [item for item in self.modifiers if item != name]

    @staticmethod
    def normalize_key(key):
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
        raw_name = getattr(key, "name", None)
        return aliases.get(raw_name, raw_name)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Эмуляция работы")
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
            "cycles": tk.StringVar(),
            "log_dir": tk.StringVar(),
            "log_file": tk.StringVar(),
            "log_level": tk.StringVar(),
            "failsafe_enabled": tk.BooleanVar(),
            "prompt_on_exit": tk.BooleanVar(),
        }
        self.build()
        self.load_config(False)
        self.root.after(120, self.flush_logs)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build(self):
        top = ttk.Frame(self.root, padding=14)
        top.pack(fill="both", expand=True)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(3, weight=1)
        top.rowconfigure(4, weight=1)

        ttk.Label(top, text="Эмуляция работы", font=("Segoe UI Semibold", 19)).grid(row=0, column=0, sticky="w")
        ttk.Label(top, text="Настройка сценария и запись действий в одном окне.", foreground="#475569").grid(
            row=1, column=0, sticky="w", pady=(2, 12)
        )

        bar = ttk.Frame(top)
        bar.grid(row=0, column=0, sticky="e")
        for text, command in [
            ("Загрузить", lambda: self.load_config(True)),
            ("Сохранить", self.save_config),
            ("Старт", self.start_process),
            ("Стоп", self.stop_process),
            ("Открыть логи", self.open_logs),
        ]:
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 8))
        self.record_btn = ttk.Button(bar, text="Запись действий", command=self.toggle_recording)
        self.record_btn.pack(side="left")
        self.status = ttk.Label(bar, text="Готово")
        self.status.pack(side="right")

        general = ttk.LabelFrame(top, text="Настройки", padding=12)
        general.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        general.columnconfigure(1, weight=1)
        fields = [
            ("startup_delay", "Задержка перед стартом"),
            ("cycles", "Количество циклов"),
            ("log_dir", "Папка логов"),
            ("log_file", "Имя лог-файла"),
        ]
        for row, (name, label) in enumerate(fields):
            ttk.Label(general, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            ttk.Entry(general, textvariable=self.vars[name]).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Label(general, text="Уровень логирования").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(
            general,
            textvariable=self.vars["log_level"],
            values=("DEBUG", "INFO", "WARNING", "ERROR"),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(general, text="Включить FailSafe", variable=self.vars["failsafe_enabled"]).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )
        ttk.Checkbutton(general, text="Показывать ENTER после завершения", variable=self.vars["prompt_on_exit"]).grid(
            row=6, column=0, columnspan=2, sticky="w"
        )

        scenario = ttk.Frame(top)
        scenario.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        scenario.columnconfigure(0, weight=1)
        scenario.columnconfigure(1, weight=1)
        scenario.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(scenario, text="Сценарий", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        right = ttk.LabelFrame(scenario, text="Параметры действия", padding=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(1, weight=1)

        buttons = ttk.Frame(left)
        buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for text, command in [
            ("Добавить", self.add_action),
            ("Дублировать", self.duplicate_action),
            ("Удалить", self.delete_action),
            ("Вверх", lambda: self.move_action(-1)),
            ("Вниз", lambda: self.move_action(1)),
        ]:
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))

        self.tree = ttk.Treeview(left, columns=("on", "type", "label"), show="headings", selectmode="browse")
        self.tree.heading("on", text="✓")
        self.tree.heading("type", text="Тип")
        self.tree.heading("label", text="Название")
        self.tree.column("on", width=55, anchor="center")
        self.tree.column("type", width=180)
        self.tree.column("label", width=300)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        ttk.Label(right, text="F8 останавливает запись. Записанные шаги добавляются в конец сценария.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        self.details = ttk.Frame(right)
        self.details.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.details.columnconfigure(1, weight=1)
        ttk.Button(right, text="Применить изменения", command=self.apply_selected).grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )

        log_frame = ttk.LabelFrame(top, text="Лог", padding=12)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.insert("end", "Здесь будет журнал запуска и записи.\n")
        self.log.configure(state="disabled")

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def flush_logs(self):
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
        self.root.after(120, self.flush_logs)

    def load_config(self, show_message):
        config = copy.deepcopy(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                config.update({key: value for key, value in loaded.items() if key != "actions"})
                if isinstance(loaded.get("actions"), list):
                    config["actions"] = loaded["actions"]
        self.vars["startup_delay"].set(str(config.get("startup_delay", 5)))
        self.vars["cycles"].set("" if config.get("cycles") is None else str(config.get("cycles")))
        self.vars["log_dir"].set(str(config.get("log_dir", "logs")))
        self.vars["log_file"].set(str(config.get("log_file", "clicer.log")))
        self.vars["log_level"].set(str(config.get("log_level", "INFO")).upper())
        self.vars["failsafe_enabled"].set(bool(config.get("failsafe_enabled", True)))
        self.vars["prompt_on_exit"].set(bool(config.get("prompt_on_exit", False)))
        self.actions = copy.deepcopy(config.get("actions", []))
        self.refresh_tree()
        self.status.configure(text="Конфиг загружен")
        if show_message:
            messagebox.showinfo("Конфиг", "Настройки загружены.")

    def collect_config(self):
        if not self.apply_selected_if_needed():
            return None
        if not self.actions:
            raise ValueError("Сценарий пуст.")
        return {
            "startup_delay": self.to_int(self.vars["startup_delay"].get(), "Задержка", allow_zero=True),
            "cycles": self.to_optional_int(self.vars["cycles"].get(), "Количество циклов"),
            "log_dir": self.vars["log_dir"].get().strip() or "logs",
            "log_file": self.vars["log_file"].get().strip() or "clicer.log",
            "log_level": (self.vars["log_level"].get().strip() or "INFO").upper(),
            "failsafe_enabled": self.vars["failsafe_enabled"].get(),
            "prompt_on_exit": self.vars["prompt_on_exit"].get(),
            "actions": copy.deepcopy(self.actions),
        }

    def save_config(self):
        try:
            config = self.collect_config()
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return False
        if config is None:
            return False
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        self.append_log(f"Конфиг сохранен в {CONFIG_PATH.name}\n")
        self.status.configure(text="Конфиг сохранен")
        return True

    def refresh_tree(self, select_index=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, action in enumerate(self.actions):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "✓" if action.get("enabled", True) else "",
                    TYPE_LABELS.get(action.get("type", ""), action.get("type", "")),
                    action.get("label", ""),
                ),
            )
        if self.actions:
            index = 0 if select_index is None else max(0, min(select_index, len(self.actions) - 1))
            self.tree.selection_set(str(index))
            self.tree.focus(str(index))
            self.selected = index
            self.render_editor(index)
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

    def render_editor(self, index):
        self.clear_editor()
        action = self.actions[index]
        ttk.Label(self.details, text=f"Тип: {TYPE_LABELS.get(action['type'], action['type'])}").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        for row, field in enumerate(FIELDS[action["type"]], start=1):
            name, label, kind, *extra = field
            ttk.Label(self.details, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            widget, variable = self.make_widget(kind, action.get(name), extra[0] if extra else None)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self.editor[name] = (variable, kind)

    def make_widget(self, kind, value, extra):
        if kind == "bool":
            variable = tk.BooleanVar(value=bool(value))
            return ttk.Checkbutton(self.details, variable=variable), variable
        if kind == "combo":
            variable = tk.StringVar(value="" if value is None else str(value))
            return ttk.Combobox(self.details, textvariable=variable, values=extra, state="readonly"), variable
        if kind == "csv" and isinstance(value, list):
            value = ", ".join(value)
        variable = tk.StringVar(value="" if value is None else str(value))
        return ttk.Entry(self.details, textvariable=variable), variable

    def apply_selected(self):
        if self.selected is None:
            return False
        action = copy.deepcopy(self.actions[self.selected])
        try:
            for name, (variable, kind) in self.editor.items():
                action[name] = self.read_value(variable, kind, name)
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

    def read_value(self, variable, kind, label):
        if kind == "bool":
            return bool(variable.get())
        text = variable.get().strip()
        if kind == "str":
            return text
        if kind == "int":
            return self.to_int(text, label, allow_zero=False)
        if kind == "optional_int":
            return None if not text else self.to_int(text, label, allow_zero=False)
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
        if action["type"] == "scroll":
            if action["sleep_min"] > action["sleep_max"]:
                raise ValueError("sleep_min не может быть больше sleep_max.")
            if action["micro_move_duration_min"] > action["micro_move_duration_max"]:
                raise ValueError("Минимальная длительность микродвижения больше максимальной.")
        if action["type"] in {"switch_tab", "keypress", "hotkey"} and action["sleep_after_min"] > action["sleep_after_max"]:
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
        index = len(self.actions) if self.selected is None else self.selected + 1
        self.actions.insert(index, copy.deepcopy(ACTION_TEMPLATES[dialog.result]))
        self.refresh_tree(index)

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
                messagebox.showerror("Запись недоступна", "Не найдена библиотека pynput. После обновления зависимостей запустите setup.ps1.")
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
                self.actions.extend(actions)
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
        python_exe = Path(sys.executable)
        if python_exe.name.lower() == "pythonw.exe":
            candidate = python_exe.with_name("python.exe")
            if candidate.exists():
                python_exe = candidate
        command = [str(python_exe), str(SCRIPT_PATH), "--config", str(CONFIG_PATH), "--no-prompt"]
        kwargs = {
            "cwd": BASE_DIR,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startup
        self.append_log(f"\nЗапуск: {' '.join(command)}\n")
        self.process = subprocess.Popen(command, **kwargs)
        self.status.configure(text="Процесс выполняется")
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self):
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
        path = BASE_DIR / (self.vars["log_dir"].get().strip() or "logs")
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def on_close(self):
        if self.recording and self.recorder:
            self.recorder.stop()
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Выход", "Сценарий еще работает. Остановить и закрыть?"):
                return
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
        return None if not value else App.to_int(value, label, allow_zero=False)

    @staticmethod
    def to_float(value, label):
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label}: нужно число.") from exc
        if number < 0:
            raise ValueError(f"{label}: число не может быть отрицательным.")
        return number


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
