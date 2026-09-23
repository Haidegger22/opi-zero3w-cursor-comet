#!/usr/bin/env python3
"""joy-to-keys.py — мост «джойстик → игровой курсор» для Hedgewars.

Почему так: игра ведёт собственный курсор и НЕ видит движение указателя, сделанное
виртуально (XWarpPointer / XTEST) — проверено кадрами. Но клавиши перемещения
игрового курсора (цифровой блок: 4/6/8/2) игра принимает, даже будучи нажатыми
виртуально — это и есть обход.

Логика (версия, которую Артём принял как «отлично работает», с чуть меньшей скоростью):
  • копим смещения указателя; как только накопилось THRESHOLD пикселей — нажимаем
    клавишу направления. Так ловится и медленное движение (мелкие шаги джойстика);
  • сколько пикселей приходится на одно нажатие — задаёт скорость: STEP_PX
    (больше = медленнее). По горизонтали курсор игры ходит быстрее, поэтому там
    нажатий вдвое меньше;
  • если движение идёт ровно, без пауз (так двигает мышь) — клавиши не жмём:
    мышь игра видит сама, иначе курсор двигался бы вдвое;
  • если движения не было 0.35 с — накопитель сбрасываем, чтобы остаток не сработал
    позже, «догоняя» курсор.

Запуск: joy-to-keys.py
Лог:    /tmp/joy-to-keys.log
"""
import math
import os
import queue
import signal
import threading
import time

from Xlib import X, XK, display
from Xlib.ext import xtest

JUMP_MIN = 3         # шаг указателя меньше этого — дрожание стика, игнорируем
SCALE = 14           # пикселей пути на одно нажатие по вертикали (больше = медленнее)
POLL = 0.006         # ~160 опросов в секунду
KEY_HOLD = 0.030     # держим клавишу 30 мс, иначе игра не успевает её принять
KEY_GAP = 0.004
MAX_PRESS = 3        # не больше нажатий на один шаг указателя
RESET_PX = 100       # прыжок больше этого = служебный перенос указателя
                     # (m5hub уводит его в центр, когда упёрся в край экрана):
                     # это не движение стика, клавиши жать нельзя
LOG = "/tmp/joy-to-keys.log"

KEYS = {"right": "KP_6", "left": "KP_4", "up": "KP_8", "down": "KP_2"}


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def release_keys():
    """Отпустить все клавиши курсора — на случай выхода посреди нажатия.

    Зачем: если процесс убьют ровно между нажатием и отпусканием (сторож гасит
    мост, игра закрывается, systemctl restart), отпускание не уйдёт, и X-сервер
    будет считать клавишу удержанной и повторять её сам ~30 раз в секунду — в
    приложении это выглядит как бесконечная прокрутка. Поймано на практике
    24.09.2026 (зажатый KP_Down); снимается только явным KeyRelease.
    """
    try:
        own = display.Display()
        for name in KEYS:
            code = own.keysym_to_keycode(XK.string_to_keysym(KEYS[name]))
            if code:
                xtest.fake_input(own, X.KeyRelease, code)
        own.sync()
    except Exception:
        pass


def main():
    d = display.Display()
    root = d.screen().root
    codes = {name: d.keysym_to_keycode(XK.string_to_keysym(sym)) for name, sym in KEYS.items()}

    # выход по сигналу: сначала отпустить клавиши, потом уходить
    def bye(*_):
        release_keys()
        log("выход: клавиши курсора отпущены")
        os._exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, bye)
        except Exception:
            pass

    def press(dpy, name):
        """Одно короткое нажатие клавиши перемещения игрового курсора."""
        code = dpy.keysym_to_keycode(XK.string_to_keysym(KEYS[name]))
        xtest.fake_input(dpy, X.KeyPress, code)
        dpy.flush()
        time.sleep(KEY_HOLD)
        xtest.fake_input(dpy, X.KeyRelease, code)
        dpy.flush()
        time.sleep(KEY_GAP)

    # нажатия делаем в отдельном потоке: иначе цикл наблюдения за указателем
    # «застревал» на 30 мс на каждое нажатие, прыжки копились — и курсор залипал
    press_q = queue.Queue(maxsize=8)

    def presser():
        # у потока своё подключение к X: Xlib не потокобезопасен
        own = display.Display()
        while True:
            name = press_q.get()
            try:
                press(own, name)
            except Exception:
                try:
                    own = display.Display()
                except Exception:
                    pass

    threading.Thread(target=presser, daemon=True).start()

    log("старт: дрожание < %d px игнор, %d px на одно нажатие (больше = медленнее)"
        % (JUMP_MIN, SCALE))

    prev = root.query_pointer()
    prev_x, prev_y = prev.root_x, prev.root_y
    presses = {"right": 0, "left": 0, "up": 0, "down": 0}
    window = []                   # для отличения мыши: у неё движение без пауз

    while True:
        try:
            p = root.query_pointer()
            x, y = p.root_x, p.root_y
            dx, dy = x - prev_x, y - prev_y
            prev_x, prev_y = x, y

            dist = math.hypot(dx, dy)
            if dist >= RESET_PX:
                # Служебный перенос указателя (m5hub уводит его в центр, когда
                # упирается в край экрана). Это не движение стика: клавиши не жмём,
                # иначе курсор игры прыгнет. Накопитель сбрасываем, чтобы остаток
                # не сработал позже.
                window.clear()
                continue
            window.append(dist >= JUMP_MIN)
            if len(window) > 12:
                window.pop(0)

            if dist >= JUMP_MIN:
                # джойстик двигает указатель редкими крупными прыжками (по данным журнала:
                # раз в ~70 мс, шаги 14–33 px), между ними — дрожание 0–2 px. Поэтому:
                # реагируем на каждый прыжок, дрожание игнорируем, ничего не накапливаем.
                smooth = len(window) >= 8 and all(window)
                if not smooth:
                    # ровное движение без пауз = мышь: игра видит её сама, клавиши не нужны
                    n = max(1, min(MAX_PRESS, int(round(dist / SCALE))))
                    plan = []
                    if abs(dx) >= JUMP_MIN:
                        plan.append(("right" if dx > 0 else "left", n))
                    if abs(dy) >= JUMP_MIN:
                        plan.append(("down" if dy > 0 else "up", n))
                    for name, count in plan:
                        for _ in range(count):
                            try:
                                press_q.put_nowait(name)
                            except queue.Full:
                                pass          # очередь полна — лишнее просто пропускаем
                        presses[name] += count
                    total = sum(presses.values())
                    if total <= 40 or total % 25 == 0:
                        log("шаг %+.0f,%+.0f (%.0f px) -> %s | всего R%d L%d U%d D%d"
                            % (dx, dy, dist, ", ".join("%s×%d" % kv for kv in plan),
                               presses["right"], presses["left"], presses["up"], presses["down"]))
        except Exception as e:
            log("ошибка: %r" % (e,))
        time.sleep(POLL)


if __name__ == "__main__":
    main()
