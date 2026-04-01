# Auto

Локальный Python-проект для автоматизации действий через `pyautogui`.

## Что внутри

- `clicer.py` - основной скрипт с параметрами запуска и безопасной остановкой.
- `requirements.txt` - минимальные зависимости проекта.
- `setup.ps1` - создание `.venv` и установка зависимостей.
- `run.ps1` - удобный запуск через PowerShell.
- `.gitignore` - исключения для Python, логов и редакторов.

## Быстрый старт

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
python .\clicer.py --startup-delay 5 --cycles 1
```

## Удобный запуск

После создания `.venv` и установки зависимостей можно запускать так:

```powershell
.\run.ps1 -StartupDelay 5 -Cycles 1 -NoPrompt
```

## Полезные параметры

```powershell
python .\clicer.py --help
```

Поддерживаются, например:

- `--startup-delay` - задержка перед стартом.
- `--cycles` - ограничение числа циклов.
- `--wait-min` и `--wait-max` - диапазон паузы между циклами.
- `--read-steps-min` и `--read-steps-max` - глубина прокрутки в режиме чтения.
- `--no-prompt` - не ждать ENTER при завершении.
- `--disable-failsafe` - отключить штатную защиту `pyautogui`.

## Git

Репозиторий инициализирован локально. Удаленный `origin` пока не настроен.
