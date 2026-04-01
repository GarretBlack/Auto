import argparse
import json
import logging
import random
import time
import traceback
from dataclasses import dataclass
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pyautogui


LOGGER = logging.getLogger("clicer")


@dataclass
class ScriptConfig:
    startup_delay: int = 10
    top_scroll_bursts_min: int = 4
    top_scroll_bursts_max: int = 7
    top_scroll_amount_min: int = 250
    top_scroll_amount_max: int = 300
    read_steps_min: int = 10
    read_steps_max: int = 18
    read_scroll_amount: int = -100
    wait_min_seconds: int = 40
    wait_max_seconds: int = 110
    panic_threshold: int = 5
    pause_between_actions: float = 0.2
    failsafe_enabled: bool = True
    prompt_on_exit: bool = True
    cycle_limit: int | None = None
    log_dir: str = "logs"
    log_file: str = "clicer.log"
    log_level: str = "INFO"
    config_path: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Имитация активности в окне с безопасной остановкой и настраиваемыми интервалами."
    )
    parser.add_argument("--config", default="config.json", help="Путь к JSON-конфигу.")
    parser.add_argument("--startup-delay", type=int, default=None, help="Задержка перед стартом в секундах.")
    parser.add_argument("--cycles", type=int, default=None, help="Ограничение числа циклов.")
    parser.add_argument("--wait-min", type=int, default=None, help="Минимальная пауза между циклами.")
    parser.add_argument("--wait-max", type=int, default=None, help="Максимальная пауза между циклами.")
    parser.add_argument("--read-steps-min", type=int, default=None, help="Минимум шагов чтения вниз.")
    parser.add_argument("--read-steps-max", type=int, default=None, help="Максимум шагов чтения вниз.")
    parser.add_argument("--log-level", default=None, help="Уровень логирования: DEBUG, INFO, WARNING, ERROR.")
    parser.add_argument("--log-dir", default=None, help="Папка для логов.")
    parser.add_argument(
        "--disable-failsafe",
        action="store_true",
        help="Отключить штатную защиту pyautogui. Не рекомендуется.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Не ждать ENTER при завершении. Удобно для запуска из bat/Task Scheduler.",
    )
    return parser.parse_args()


def load_config_file(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("Конфиг должен быть JSON-объектом.")

    return data


def get_value(args: argparse.Namespace, file_config: dict, field_name: str, fallback):
    arg_value = getattr(args, field_name)
    if arg_value is not None:
        return arg_value
    return file_config.get(field_name, fallback)


def build_config(args: argparse.Namespace) -> ScriptConfig:
    file_config = load_config_file(args.config)

    failsafe_enabled = file_config.get("failsafe_enabled", True)
    if args.disable_failsafe:
        failsafe_enabled = False

    prompt_on_exit = file_config.get("prompt_on_exit", True)
    if args.no_prompt:
        prompt_on_exit = False

    config = ScriptConfig(
        startup_delay=get_value(args, file_config, "startup_delay", 10),
        wait_min_seconds=get_value(args, file_config, "wait_min", 40),
        wait_max_seconds=get_value(args, file_config, "wait_max", 110),
        read_steps_min=get_value(args, file_config, "read_steps_min", 10),
        read_steps_max=get_value(args, file_config, "read_steps_max", 18),
        failsafe_enabled=failsafe_enabled,
        prompt_on_exit=prompt_on_exit,
        cycle_limit=get_value(args, file_config, "cycles", None),
        log_dir=get_value(args, file_config, "log_dir", "logs"),
        log_file=file_config.get("log_file", "clicer.log"),
        log_level=(get_value(args, file_config, "log_level", "INFO") or "INFO").upper(),
        config_path=args.config,
    )

    if config.wait_min_seconds > config.wait_max_seconds:
        raise ValueError("--wait-min не может быть больше --wait-max")
    if config.read_steps_min > config.read_steps_max:
        raise ValueError("--read-steps-min не может быть больше --read-steps-max")
    if config.startup_delay < 0:
        raise ValueError("--startup-delay не может быть отрицательным")
    if config.cycle_limit is not None and config.cycle_limit <= 0:
        raise ValueError("--cycles должен быть положительным числом")

    return config


def configure_runtime(config: ScriptConfig) -> None:
    log_path = Path(config.log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.log_level, logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_path / config.log_file,
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


def get_safe_point(screen_width: int, screen_height: int) -> tuple[int, int]:
    margin_x = max(100, screen_width // 10)
    margin_y = max(100, screen_height // 10)
    x = random.randint(margin_x, max(margin_x, screen_width - margin_x))
    y = random.randint(margin_y, max(margin_y, screen_height - margin_y))
    return x, y


def human_move(config: ScriptConfig, target_x: int, target_y: int) -> bool:
    current_x, current_y = pyautogui.position()
    mid_x = int((current_x + target_x) / 2 + random.randint(-70, 70))
    mid_y = int((current_y + target_y) / 2 + random.randint(-70, 70))
    duration = random.uniform(0.8, 1.5)

    for point_x, point_y in ((mid_x, mid_y), (target_x, target_y)):
        if check_panic_exit(config):
            return True
        pyautogui.moveTo(point_x, point_y, duration=duration / 2, tween=pyautogui.easeInOutQuad)
    return False


def switch_tab() -> None:
    pyautogui.hotkey("ctrl", "tab")


def scroll_to_top(config: ScriptConfig) -> None:
    bursts = random.randint(config.top_scroll_bursts_min, config.top_scroll_bursts_max)
    LOGGER.info("Действие: быстрый возврат в начало страницы (%s рывков).", bursts)
    for _ in range(bursts):
        pyautogui.scroll(random.randint(config.top_scroll_amount_min, config.top_scroll_amount_max))
        time.sleep(random.uniform(0.1, 0.3))


def read_page(config: ScriptConfig) -> bool:
    screen_width, screen_height = pyautogui.size()
    steps = random.randint(config.read_steps_min, config.read_steps_max)
    LOGGER.info("Действие: чтение (%s шагов вниз).", steps)

    for _ in range(steps):
        if check_panic_exit(config):
            return True

        pyautogui.scroll(config.read_scroll_amount)

        if random.random() < 0.8:
            curr_x, curr_y = pyautogui.position()
            new_x = clamp(curr_x + random.randint(-80, 80), 50, max(50, screen_width - 50))
            new_y = clamp(curr_y + random.randint(-20, 20), 50, max(50, screen_height - 50))
            pyautogui.moveTo(new_x, new_y, duration=random.uniform(0.4, 0.8))

        time.sleep(random.uniform(1.0, 2.5))

    return False


def change_focus(config: ScriptConfig) -> bool:
    screen_width, screen_height = pyautogui.size()
    target_x, target_y = get_safe_point(screen_width, screen_height)
    if human_move(config, target_x, target_y):
        return True
    pyautogui.press("shift")
    return False


def wait_between_cycles(config: ScriptConfig) -> bool:
    wait_seconds = random.randint(config.wait_min_seconds, config.wait_max_seconds)
    LOGGER.info("Ожидание %s сек. Для стопа переведите мышь в угол.", wait_seconds)

    for _ in range(wait_seconds):
        if check_panic_exit(config):
            return True
        time.sleep(1)
    return False


def run(config: ScriptConfig) -> tuple[int, int, float]:
    start_time = time.time()
    total_cycles = 0
    total_tabs = 0

    LOGGER.info("=== ИМИТАЦИЯ РАБОТЫ ===")
    LOGGER.info("Конфиг: %s", config.config_path or "встроенные значения")
    LOGGER.info("Лог-файл: %s", Path(config.log_dir) / config.log_file)
    LOGGER.info("Для аварийной остановки переведите мышь в верхний левый угол.")
    LOGGER.info("Подготовка %s секунд. Разверните нужное окно.", config.startup_delay)
    time.sleep(config.startup_delay)

    while True:
        if check_panic_exit(config):
            break
        if config.cycle_limit is not None and total_cycles >= config.cycle_limit:
            LOGGER.info("Достигнут лимит циклов: %s.", config.cycle_limit)
            break

        total_cycles += 1
        LOGGER.info(">>> ЦИКЛ № %s <<<", total_cycles)

        switch_tab()
        total_tabs += 1

        scroll_to_top(config)

        if check_panic_exit(config):
            break
        time.sleep(1.5)

        if read_page(config):
            break

        if change_focus(config):
            break

        if wait_between_cycles(config):
            break

    return total_cycles, total_tabs, time.time() - start_time


def print_summary(total_cycles: int, total_tabs: int, elapsed_seconds: float) -> None:
    readable_time = str(timedelta(seconds=int(elapsed_seconds)))
    print("\n" + "=" * 40)
    print("ИТОГИ СЕССИИ:")
    print(f"Время работы:   {readable_time}")
    print(f"Циклов:         {total_cycles}")
    print(f"Вкладок:        {total_tabs}")
    print("=" * 40)


def main() -> int:
    try:
        config = build_config(parse_args())
        configure_runtime(config)
        total_cycles, total_tabs, elapsed_seconds = run(config)
        print_summary(total_cycles, total_tabs, elapsed_seconds)
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
