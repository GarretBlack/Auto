import pyautogui
import time
import random
import traceback
from datetime import timedelta

# Настройки для RDP
pyautogui.PAUSE = 0.2 
pyautogui.FAILSAFE = False 

start_time = time.time()
total_cycles = 0  
total_tabs = 0

def check_panic_exit():
    """Проверка: если мышь в углу (0,0) — экстренный выход"""
    cur_x, cur_y = pyautogui.position()
    if cur_x <= 5 and cur_y <= 5: 
        print("\n[!!!] ОБНАРУЖЕН СИГНАЛ ПАНИКИ (Мышь в углу 0,0)")
        return True
    return False

def human_move(target_x, target_y):
    current_x, current_y = pyautogui.position()
    mid_x = (current_x + target_x) / 2 + random.randint(-70, 70)
    mid_y = (current_y + target_y) / 2 + random.randint(-70, 70)
    dur = random.uniform(0.8, 1.5)
    
    for tx, ty in [(mid_x, mid_y), (target_x, target_y)]:
        if check_panic_exit(): return True 
        pyautogui.moveTo(tx, ty, duration=dur/2, tween=pyautogui.easeInOutQuad)
    return False

print("=== ИМИТАЦИЯ РАБОТЫ ===")
print("Для экстренной остановки: мышь в самый верхний левый угол.")
print("Подготовка 10 секунд... Разверните окно RDP.")
time.sleep(10)

try:
    while True:
        if check_panic_exit(): break
        
        total_cycles += 1
        print(f"\n>>> ЦИКЛ № {total_cycles} <<<")
        
        # 1. Смена вкладки
        pyautogui.keyDown('ctrl'); time.sleep(0.5); pyautogui.press('tab'); time.sleep(0.5); pyautogui.keyUp('ctrl')
        total_tabs += 1
        
        # 2. ПОШАГОВЫЙ СКРОЛЛ НАВЕРХ (Имитация быстрой прокрутки назад)
        print("Действие: Быстрый возврат в начало страницы...")
        # Делаем 4-6 быстрых движений колесиком вверх
        for _ in range(random.randint(4, 7)):
            pyautogui.scroll(random.randint(250, 300))
            time.sleep(random.uniform(0.1, 0.3)) # Очень короткая пауза между рывками
        
        if check_panic_exit(): break
        time.sleep(1.5)

        # 3. Активное чтение (скролл вниз + микродвижения)
        steps = random.randint(10, 18)
        print(f"Действие: Чтение ({steps} шагов вниз)...")
        for i in range(steps):
            if check_panic_exit(): break
            pyautogui.scroll(-100)
            
            if random.random() < 0.8:
                curr_x, curr_y = pyautogui.position()
                new_x = max(100, min(curr_x + random.randint(-80, 80), 1000))
                new_y = max(100, min(curr_y + random.randint(-20, 20), 800))
                pyautogui.moveTo(new_x, new_y, duration=random.uniform(0.4, 0.8))
            
            time.sleep(random.uniform(1.0, 2.5))

        # 4. Смена фокуса
        if human_move(random.randint(150, 950), random.randint(200, 750)): break
        pyautogui.press('shift')

        # 5. Ожидание между циклами
        wait = random.randint(40, 110)
        print(f"Ожидание {wait} сек. (Для СТОП - мышь в угол)")
        for _ in range(wait):
            if check_panic_exit(): break
            time.sleep(1)
        else:
            continue 
        break 

except KeyboardInterrupt:
    print("\n[!] Остановлено вручную.")
except Exception:
    traceback.print_exc()
finally:
    end_time = time.time()
    readable_time = str(timedelta(seconds=int(end_time - start_time)))
    print("\n" + "="*40)
    print(f"ИТОГИ СЕССИИ:")
    print(f"Время работы:   {readable_time}")
    print(f"Циклов:         {total_cycles}")
    print(f"Вкладок:        {total_tabs}")
    print("="*40)
    input("\nНажмите ENTER для закрытия...")
