# Orange Pi 4 Pro — что отличается

Плата: Orange Pi 4 Pro, Allwinner A733 (`sun60iw2`), Debian 13 Trixie, X11 + MATE,
панель 5″ по HDMI, режим 1024×600 (66,45 Гц, паспортный режим EDID).
Проверено: комета работает, системный курсор скрыт, журнал чист.

## Что копировать

Полный комплект, как на Zero 3W — одного скрипта недостаточно:

```bash
sudo apt install -y python3-gi python3-gi-cairo python3-xlib gir1.2-gtk-3.0
install -m 755 cursor-comet.py make_empty_cursor.py ~/.local/bin/
python3 ~/.local/bin/make_empty_cursor.py      # тема comet-hidden
install -Dm 644 autostart/cursor-comet.desktop ~/.config/autostart/
```

Если тема уже есть на другой машине, её можно просто перенести каталогом
`~/.icons/comet-hidden` (28 КБ, 123 курсора) — генератор тогда не нужен.

## Ключевое отличие: флаг `--no-xfixes`

На 4 Pro **нельзя** дёргать `xfixes_hide_cursor()`. В python-xlib этот вызов уходит
в RandR-запрос к CRTC, которого на драйвере нет, и возвращает
`BadRRCrtcError (major_opcode=138, minor_opcode=29)` — по одному на каждый вызов.

Замер, которым это найдено (два минимальных скрипта):

| Что в цикле | Результат |
|---|---|
| `root.query_pointer()` 30 раз | чисто, ни одной ошибки |
| `root.xfixes_hide_cursor()` 40 раз | ошибка на каждый вызов |

Объём: за 3 минуты работы без флага в отладочный файл набежало **9,2 МБ**.

Поэтому автозапуск на 4 Pro:

```
Exec=sh -c '/home/orangepi/.local/bin/cursor-comet.py --hide-cursor --no-xfixes >/dev/null 2>&1'
```

С флагом скрипт не вызывает XFixes вообще: системный курсор и так невидим благодаря
теме `comet-hidden` и пустому root-курсуру (`xsetroot`).

## Проверка

```bash
# процесс и его аргументы
pgrep -af cursor-comet.py

# после правки: три строки старта и размер НЕ растёт
runuser -u orangepi -- env HOME=/home/orangepi DISPLAY=:0 \
  XAUTHORITY=/home/orangepi/.Xauthority XDG_RUNTIME_DIR=/run/user/1000 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  setsid -f sh -c '~/.local/bin/cursor-comet.py --hide-cursor --no-xfixes >/tmp/comet.log 2>&1'
sleep 12; stat -c %s /tmp/comet.log      # ~146 байт, дальше не растёт
```

Кадр (на 4 Pro `scrot` не нужен, снимаем через GTK):

```python
import gi; gi.require_version("Gdk", "3.0")
from gi.repository import Gdk
w = Gdk.get_default_root_window()
Gdk.pixbuf_get_from_window(w, 0, 0, w.get_width(), w.get_height()).savev("/tmp/shot.png", "png", [], [])
```

На кадре должна быть зелёная комета с ореолом и хвостом, белой стрелки — нет.

## Грабли

- **Два экземпляра.** Ручной запуск плюс автозапуск дают две кометы (двойной хвост).
  Проверять `pgrep -af cursor-comet.py`, оставлять один.
- **`pkill -f cursor-comet.py` в одной команде с SSH-строкой убивает саму оболочку** —
  шаблон совпадает с её cmdline. Убивать по конкретному PID.
- **Запуск только в окружении сеанса:** без `XDG_RUNTIME_DIR` и
  `DBUS_SESSION_BUS_ADDRESS` gsettings пишет в `/run/user/0`, тема не применяется,
  а в выводе видно `dconf-CRITICAL`.
- **Шум в журнале ≠ сломанная отрисовка.** Если комета на кадре есть, а в логе сыпятся
  ошибки — искать причину в вызовах Xlib, а не в рисовании.

## Чего здесь нет

Игровая связка (`game-cursor.py`, `game-pointer.py`, `joy-to-keys.py`, служба
`game-cursor.service`) на 4 Pro не устанавливалась и не проверялась: там нет m5hub и
сторожа игровых курсоров. Если понадобится — ставится тем же комплектом, но требует
отдельной проверки на этой плате.
