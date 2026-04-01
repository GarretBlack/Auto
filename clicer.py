import argparse
import copy
import json
import logging
import random
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import pyautogui

from app_runtime import ensure_user_config, resolve_user_path


LOGGER = logging.getLogger("clicer")

ACTION_TEMPLATES: dict[str, dict[str, Any]] = {
    "switch_tab": {
        "type": "switch_tab",
        "label": "Переключить вкладку",
        "enabled": True,
        "repeat_min": 1,
        "repeat_max": 1,
        "sleep_after_min": 0.3,
        "sleep_after_max": 0.6,
    },
    "scroll": {
        "type": "scroll",
        "label": "Прокрутка",
        "enabled": True,
        "repeat_min": 1,
        "repeat_max": 1,
        "amount_min": -100,
        "amount_max": -100,
        "sleep_min": 0.0,
        "sleep_max": 0.0,
        "micro_move_chance": 0.0,
        "micro_move_x_min": -80,
        "micro_move_x_max": 80,
        "micro_move_y_min": -20,
        "micro_move_y_max": 20,
        "micro_move_duration_min": 0.2,
        "micro_move_duration_max": 0.6,
    },
    "pause": {
        "type": "pause",
        "label": "Пауза",
        "enabled": True,
        "duration_min": 1.0,
        "duration_max": 1.0,
    },
    "move_random": {
        "type": "move_random",
        "label": "Случайное движение мыши",
        "enabled": True,
        "x_margin": 100,
        "y_margin": 100,
        "human_like": True,
        "duration_min": 0.8,
        "duration_max": 1.4,
    },
    "mouse_move": {
        "type": "mouse_move",
        "label": "Переместить мышь",
        "enabled": True,
        "x": 300,
        "y": 300,
        "duration_min": 0.2,
        "duration_max": 0.4,
    },
    "click": {
        "type": "click",
        "label": "Клик мышью",
        "enabled": True,
        "x": None,
        "y": None,
        "button": "left",
        "clicks": 1,
        "interval": 0.0,
    },
    "keypress": {
        "type": "keypress",
        "label": "Нажать клавишу",
        "enabled": True,
        "key": "shift",
        "sleep_after_min": 0.0,
        "sleep_after_max": 0.1,
    },
    "hotkey": {
        "type": "hotkey",
        "label": "Горячая клавиша",
        "enabled": True,
        "keys": ["ctrl", "tab"],
        "sleep_after_min": 0.0,
        "sleep_after_max": 0.15,
    },
    "wait": {
        "type": "wait",
        "label": "Ожидание между циклами",
        "enabled": True,
        "duration_min": 40.0,
        "duration_max": 110.0,
    },
}

DEFAULT_ACTIONS = [
    {
        "type": "switch_tab",
        "label": "Переключить вкладку",
        "repeat_min": 1,
        "repeat_max": 1,
        "sleep_after_min": 0.4,
        "sleep_after_max": 0.7,
    },
    {
        "type": "scroll",
        "label": "Вернуться вверх",
        "repeat_min": 4,
        "repeat_max": 7,
        "amount_min": 250,
        "amount_max": 300,
        "sleep_min": 0.1,
        "sleep_max": 0.3,
    },
    {
        "type": "pause",
        "label": "Короткая пауза",
        "duration_min": 1.5,
        "duration_max": 1.5,
    },
    {
        "type": "scroll",
        "label": "Чтение страницы",
        "repeat_min": 10,
        "repeat_max": 18,
        "amount_min": -100,
        "amount_max": -100,
        "sleep_min": 1.0,
        "sleep_max": 2.5,
        "micro_move_chance": 0.8,
        "micro_move_x_min": -80,
        "micro_move_x_max": 80,
        "micro_move_y_min": -20,
        "micro_move_y_max": 20,
        "micro_move_duration_min": 0.4,
        "micro_move_duration_max": 0.8,
    },
    {
        "type": "move_random",
        "label": "Сменить фокус мыши",
        "x_margin": 150,
        "y_margin": 120,
        "human_like": True,
        "duration_min": 0.8,
        "duration_max": 1.4,
    },
    {
        "type": "keypress",
        "label": "Нажать Shift",
        "key": "shift",
        "sleep_after_min": 0.0,
        "sleep_after_max": 0.1,
    },
    {
        "type": "wait",
        "label": "Ожидание между циклами",
        "duration_min": 40.0,
        "duration_max": 110.0,
    },
]

DEFAULT_CONFIG: dict[str, Any] = {
    "startup_delay": 5,
    "cycles": 1,
    "failsafe_enabled": True,
    "prompt_on_exit": False,
    "log_dir": "logs",
    "log_file": "clicer.log",
    "log_level": "INFO",
    "actions": DEFAULT_ACTIONS,
}

DEFAULT_CONFIG_PATH = ensure_user_config(DEFAULT_CONFIG)


@dataclass
class ScriptConfig:
    startup_delay: int
    failsafe_enabled: bool
    prompt_on_exit: bool
    cycle_limit: int | None
    log_dir: str
    log_file: str
    log_level: str
    actions: list[dict[str, Any]]
    panic_threshold: int = 5
    pause_between_actions: float = 0.2
    config_path: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Исполнение сценария автоматизации из JSON-конфига.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Путь к JSON-конфигу.")
    parser.add_argument("--startup-delay", type=int, default=None, help="Задержка перед стартом в секундах.")
    parser.add_argument("--cycles", type=int, default=None, help="Ограничение числа циклов.")
    parser.add_argument("--log-level", default=None, help="Уровень логирования: DEBUG, INFO, WARNING, ERROR.")
    parser.add_argument("--log-dir", default=None, help="Папка для логов.")
    parser.add_argument("--disable-failsafe", action="store_true", help="Отключить штатную защиту pyautogui.")
    parser.add_argument("--no-prompt", action="store_true", help="Не ждать ENTER при завершении.")
    return parser.parse_args()


def load_json_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("Конфиг должен быть JSON-объектом.")
    return data


def build_config(args: argparse.Namespace) -> ScriptConfig:
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = resolve_user_path(config_path)

    raw_config = copy.deepcopy(DEFAULT_CONFIG)
    file_config = load_json_config(str(config_path))
    raw_config.update({k: v for k, v in file_config.items() if k != "actions"})
    if "actions" in file_config:
        raw_config["actions"] = file_config["actions"]

    if args.startup_delay is not None:
        raw_config["startup_delay"] = args.startup_delay
    if args.cycles is not None:
        raw_config["cycles"] = args.cycles
    if args.log_level is not None:
        raw_config["log_level"] = args.log_level
    if args.log_dir is not None:
        raw_config["log_dir"] = args.log_dir
    if args.disable_failsafe:
        raw_config["failsafe_enabled"] = False
    if args.no_prompt:
        raw_config["prompt_on_exit"] = False

    actions = normalize_actions(raw_config.get("actions", []))
    startup_delay = int(raw_config.get("startup_delay", 5))
    cycles = raw_config.get("cycles")

    if startup_delay < 0:
        raise ValueError("Задержка перед стартом не может быть отрицательной.")
    if cycles is not None and int(cycles) <= 0:
        raise ValueError("Количество циклов должно быть больше нуля.")

    return ScriptConfig(
        startup_delay=startup_delay,
        failsafe_enabled=bool(raw_config.get("failsafe_enabled", True)),
        prompt_on_exit=bool(raw_config.get("prompt_on_exit", False)),
        cycle_limit=None if cycles in (None, "") else int(cycles),
        log_dir=str(raw_config.get("log_dir", "logs")),
        log_file=str(raw_config.get("log_file", "clicer.log")),
        log_level=str(raw_config.get("log_level", "INFO")).upper(),
        actions=actions,
        config_path=str(config_path),
    )


def normalize_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not actions:
        actions = copy.deepcopy(DEFAULT_ACTIONS)

    normalized = []
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            raise ValueError(f"Действие #{index} должно быть объектом.")
        action_type = action.get("type")
        if action_type not in ACTION_TEMPLATES:
            raise ValueError(f"Неизвестный тип действия: {action_type!r}")
        merged = copy.deepcopy(ACTION_TEMPLATES[action_type])
        merged.update(action)
        merged["enabled"] = bool(merged.get("enabled", True))
        merged["label"] = str(merged.get("label") or ACTION_TEMPLATES[action_type]["label"])
        if action_type == "hotkey" and isinstance(merged.get("keys"), str):
            merged["keys"] = [part.strip() for part in merged["keys"].split(",") if part.strip()]
        normalized.append(merged)
    return normalized


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except ValueError:
            # Ignore already-closed redirected streams.
            continue


def configure_runtime(config: ScriptConfig) -> None:
    log_dir = resolve_user_path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    level = getattr(logging, config.log_level, logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_dir / config.log_file,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    LOGGER.handlers.clear()
    LOGGER.setLevel(level)
    LOGGER.addHandler(console_handler)
    LOGGER.addHandler(file_handler)
    LOGGER.propagate = False

    pyautogui.PAUSE = config.pause_between_actions
    pyautogui.FAILSAFE = config.failsafe_enabled


def check_panic_exit(config: ScriptConfig) -> bool:
    cur_x, cur_y = pyautogui.position()
    if cur_x <= config.panic_threshold and cur_y <= config.panic_threshold:
        LOGGER.warning("Обнаружен сигнал аварийной остановки: курсор в левом верхнем углу.")
        return True
    return False


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def random_float(min_value: float, max_value: float) -> float:
    return random.uniform(float(min_value), float(max_value))


def random_int(min_value: int, max_value: int) -> int:
    return random.randint(int(min_value), int(max_value))


def sleep_with_checks(duration: float, config: ScriptConfig, step: float = 0.2) -> bool:
    remaining = max(0.0, float(duration))
    while remaining > 0:
        if check_panic_exit(config):
            return True
        chunk = min(step, remaining)
        time.sleep(chunk)
        remaining -= chunk
    return False


def human_move(target_x: int, target_y: int, duration: float, config: ScriptConfig) -> bool:
    current_x, current_y = pyautogui.position()
    midpoint_x = int((current_x + target_x) / 2 + random.randint(-70, 70))
    midpoint_y = int((current_y + target_y) / 2 + random.randint(-70, 70))

    for point_x, point_y in ((midpoint_x, midpoint_y), (target_x, target_y)):
        if check_panic_exit(config):
            return True
        pyautogui.moveTo(point_x, point_y, duration=duration / 2, tween=pyautogui.easeInOutQuad)
    return False


def straight_move(target_x: int, target_y: int, duration: float, config: ScriptConfig) -> bool:
    if check_panic_exit(config):
        return True
    pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.linear)
    return check_panic_exit(config)


def human_like_move(target_x: int, target_y: int, duration: float, config: ScriptConfig) -> bool:
    current_x, current_y = pyautogui.position()
    delta_x = target_x - current_x
    delta_y = target_y - current_y
    waypoints = []

    for fraction in (0.22, 0.47, 0.73):
        waypoint_x = int(current_x + delta_x * fraction + random.randint(-45, 45))
        waypoint_y = int(current_y + delta_y * fraction + random.randint(-45, 45))
        waypoints.append((waypoint_x, waypoint_y))

    waypoints.append((target_x, target_y))
    segment_duration = max(0.08, duration / len(waypoints))

    for point_x, point_y in waypoints:
        if check_panic_exit(config):
            return True
        pyautogui.moveTo(point_x, point_y, duration=segment_duration, tween=pyautogui.easeInOutQuad)

    return check_panic_exit(config)


def get_safe_point(action: dict[str, Any]) -> tuple[int, int]:
    screen_width, screen_height = pyautogui.size()
    x_margin = max(0, int(action.get("x_margin", 100)))
    y_margin = max(0, int(action.get("y_margin", 100)))
    min_x = min(max(x_margin, 0), max(0, screen_width - 1))
    max_x = max(min_x, screen_width - max(1, x_margin))
    min_y = min(max(y_margin, 0), max(0, screen_height - 1))
    max_y = max(min_y, screen_height - max(1, y_margin))
    return random_int(min_x, max_x), random_int(min_y, max_y)


def maybe_micro_move(action: dict[str, Any], config: ScriptConfig) -> bool:
    chance = float(action.get("micro_move_chance", 0.0))
    if chance <= 0 or random.random() > chance:
        return False

    screen_width, screen_height = pyautogui.size()
    curr_x, curr_y = pyautogui.position()
    new_x = clamp(
        curr_x + random_int(int(action.get("micro_move_x_min", -80)), int(action.get("micro_move_x_max", 80))),
        50,
        max(50, screen_width - 50),
    )
    new_y = clamp(
        curr_y + random_int(int(action.get("micro_move_y_min", -20)), int(action.get("micro_move_y_max", 20))),
        50,
        max(50, screen_height - 50),
    )
    duration = random_float(action.get("micro_move_duration_min", 0.2), action.get("micro_move_duration_max", 0.6))
    pyautogui.moveTo(new_x, new_y, duration=duration)
    return check_panic_exit(config)


def execute_action(action: dict[str, Any], config: ScriptConfig) -> bool:
    if not action.get("enabled", True):
        return False

    action_type = action["type"]
    label = action.get("label", action_type)
    LOGGER.info("Действие: %s", label)

    if action_type == "switch_tab":
        repeat = random_int(action.get("repeat_min", 1), action.get("repeat_max", 1))
        for _ in range(repeat):
            if check_panic_exit(config):
                return True
            pyautogui.hotkey("ctrl", "tab")
            if sleep_with_checks(random_float(action.get("sleep_after_min", 0.0), action.get("sleep_after_max", 0.0)), config):
                return True
        return False

    if action_type == "scroll":
        repeat = random_int(action.get("repeat_min", 1), action.get("repeat_max", 1))
        for _ in range(repeat):
            if check_panic_exit(config):
                return True
            amount = random_int(action.get("amount_min", -100), action.get("amount_max", -100))
            pyautogui.scroll(amount)
            if maybe_micro_move(action, config):
                return True
            if sleep_with_checks(random_float(action.get("sleep_min", 0.0), action.get("sleep_max", 0.0)), config):
                return True
        return False

    if action_type in {"pause", "wait"}:
        return sleep_with_checks(random_float(action.get("duration_min", 0.0), action.get("duration_max", 0.0)), config, step=0.2)

    if action_type == "move_random":
        target_x, target_y = get_safe_point(action)
        duration = random_float(action.get("duration_min", 0.8), action.get("duration_max", 1.4))
        if action.get("human_like", False):
            return human_like_move(target_x, target_y, duration, config)
        return straight_move(target_x, target_y, duration, config)

    if action_type == "mouse_move":
        target_x = int(action.get("x", 0))
        target_y = int(action.get("y", 0))
        duration = random_float(action.get("duration_min", 0.2), action.get("duration_max", 0.4))
        return human_move(target_x, target_y, duration, config)

    if action_type == "click":
        target_x = action.get("x")
        target_y = action.get("y")
        if target_x is not None and target_y is not None:
            if human_move(int(target_x), int(target_y), 0.25, config):
                return True
        pyautogui.click(
            button=str(action.get("button", "left")),
            clicks=int(action.get("clicks", 1)),
            interval=float(action.get("interval", 0.0)),
        )
        return check_panic_exit(config)

    if action_type == "keypress":
        pyautogui.press(str(action.get("key", "shift")))
        return sleep_with_checks(random_float(action.get("sleep_after_min", 0.0), action.get("sleep_after_max", 0.0)), config)

    if action_type == "hotkey":
        keys = action.get("keys", [])
        if not keys:
            raise ValueError("Для действия hotkey нужен список keys.")
        pyautogui.hotkey(*keys)
        return sleep_with_checks(random_float(action.get("sleep_after_min", 0.0), action.get("sleep_after_max", 0.0)), config)

    raise ValueError(f"Неподдерживаемый тип действия: {action_type}")


def run(config: ScriptConfig) -> tuple[int, int, float]:
    start_time = time.time()
    total_cycles = 0

    LOGGER.info("=== ИСПОЛНЕНИЕ СЦЕНАРИЯ ===")
    LOGGER.info("Конфиг: %s", config.config_path or "встроенные значения")
    LOGGER.info("Лог-файл: %s", Path(config.log_dir) / config.log_file)
    LOGGER.info("Активных действий в сценарии: %s", len([item for item in config.actions if item.get("enabled", True)]))
    LOGGER.info("Подготовка %s секунд. Разверните нужное окно.", config.startup_delay)
    if sleep_with_checks(config.startup_delay, config):
        return 0, 0, time.time() - start_time

    while True:
        if check_panic_exit(config):
            break
        if config.cycle_limit is not None and total_cycles >= config.cycle_limit:
            LOGGER.info("Достигнут лимит циклов: %s.", config.cycle_limit)
            break

        total_cycles += 1
        LOGGER.info(">>> ЦИКЛ № %s <<<", total_cycles)

        for action in config.actions:
            if execute_action(action, config):
                return total_cycles, count_executed_actions(config.actions), time.time() - start_time

    return total_cycles, count_executed_actions(config.actions), time.time() - start_time


def count_executed_actions(actions: list[dict[str, Any]]) -> int:
    return len([action for action in actions if action.get("enabled", True)])


def print_summary(total_cycles: int, total_actions: int, elapsed_seconds: float) -> None:
    readable_time = str(timedelta(seconds=int(elapsed_seconds)))
    print("\n" + "=" * 40)
    print("ИТОГИ СЕССИИ:")
    print(f"Время работы:   {readable_time}")
    print(f"Циклов:         {total_cycles}")
    print(f"Действий:       {total_actions}")
    print("=" * 40)


def main() -> int:
    try:
        configure_stdio()
        config = build_config(parse_args())
        configure_runtime(config)
        total_cycles, total_actions, elapsed_seconds = run(config)
        print_summary(total_cycles, total_actions, elapsed_seconds)
    except KeyboardInterrupt:
        LOGGER.warning("Остановлено вручную.")
    except pyautogui.FailSafeException:
        LOGGER.warning("Сработала штатная защита pyautogui (FailSafe).")
    except Exception:
        traceback.print_exc()
        return 1
    else:
        return 0
    finally:
        try:
            if "config" in locals() and config.prompt_on_exit:
                input("\nНажмите ENTER для закрытия...")
        except EOFError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
