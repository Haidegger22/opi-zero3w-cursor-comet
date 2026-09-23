#!/usr/bin/env python3
"""game-pointer.py — точный курсор для игр (Zero 3W).

Зачем: на рабочем столе курсор рисует «комета» (cursor-comet.py) — у неё есть шлейф,
а шлейф визуально отстаёт от указателя. В игре это мешает: непонятно, куда именно
попадёт клик (например в меню выбора оружия).

Что делает этот скрипт: рисует аккуратный прицел-перекрестие РОВНО в точке указателя,
без шлейфа и без сглаживания, 60 раз в секунду. Окно прозрачно для кликов
(пустая область ввода), поэтому нажатия уходят прямо в игру.

Запуск: game-pointer.py          (живёт, пока его не остановят)
"""
import math
import os
import sys
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

SIZE = 44          # размер окна курсора
TICK_MS = 16       # ~60 кадров в секунду
LOG = "/tmp/game-pointer.log"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


class Pointer(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_size_request(SIZE, SIZE)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("map-event", self.on_map)
        self.show_all()
        self.dpy = Gdk.Display.get_default()
        self.last = None
        GLib.timeout_add(TICK_MS, self.tick)

    def on_realize(self, *_):
        self._apply_input()
        try:
            self.get_window().set_override_redirect(True)
        except Exception:
            pass

    def on_map(self, *_):
        # GTK сбрасывает форму ввода при показе окна — применяем ещё раз
        self._apply_input()
        return False

    def _apply_input(self):
        """Пустая область ввода: клики не задерживаются оверлеем, а уходят в игру."""
        try:
            self.get_window().input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def pointer(self):
        """Положение указателя на экране (GTK отдаёт: экран, X, Y)."""
        seat = self.dpy.get_default_seat()
        _screen, x, y = seat.get_pointer().get_position()
        return x, y

    def tick(self):
        try:
            x, y = self.pointer()
            if (x, y) != self.last:
                self.last = (x, y)
                self.move(x - 6, y - 6)   # чуть влево-вверх, чтобы точка была в центре прицела
            self._n = getattr(self, "_n", 0) + 1
            if self._n % 30 == 0:          # ~2 раза в секунду подстраховываемся
                self._apply_input()
        except Exception as e:
            log("ошибка: %r" % (e,))
        return True

    def on_draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        c = SIZE / 2.0
        # крестик: чёрная подложка + белые штрихи (видно на любом фоне)
        for width, color in ((5.0, (0, 0, 0, 0.85)), (2.4, (1, 1, 1, 1))):
            cr.set_line_width(width)
            cr.set_source_rgba(*color)
            r1, r2 = 6.0, 16.0
            for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                cr.move_to(c + math.cos(a) * r1, c + math.sin(a) * r1)
                cr.line_to(c + math.cos(a) * r2, c + math.sin(a) * r2)
            cr.stroke()
        # точка точно в позиции указателя
        for rad, color in ((3.4, (0, 0, 0, 0.9)), (1.8, (1, 0.25, 0.15, 1))):
            cr.set_source_rgba(*color)
            cr.arc(c, c, rad, 0, 2 * math.pi)
            cr.fill()
        return False


def main():
    log("старт точного курсора для игр")
    win = Pointer()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
