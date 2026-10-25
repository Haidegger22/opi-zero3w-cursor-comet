# Orange Pi Zero 3W — эталонная плата

Здесь всё проверено и работает в полном объёме: комета, невидимая тема курсора,
игровой сторож `game-cursor.py`, прицел `game-pointer.py`, мост `joy-to-keys.py`
и пользовательская служба `game-cursor.service`.

- Плата: Orange Pi Zero 3W, Allwinner A733, Debian 13, MATE, X11, 1024×600, тачскрин.
- Комета: `~/.local/bin/cursor-comet.py --hide-cursor` (без `--no-xfixes`).
- Сторож игр: `~/.config/systemd/user/game-cursor.service` (включён, `Restart=always`).
- Автозапуск кометы: `~/.config/autostart/cursor-comet.desktop`.

## Правила

- **Этот скрипт — эталон.** При переносе на другую плату копировать файлы и править
  копию, а не источник: комета связана со сторожем игровых курсоров и переживает
  перезагрузки, ломать её ради эксперимента нельзя.
- **Флаг `--no-xfixes` здесь не нужен.** На этой плате `xfixes_hide_cursor()` работает
  без ошибок; вызовы XFixes можно оставить как есть (поведение по умолчанию).
- **Тема курсора:** `comet-hidden`, ставится `make_empty_cursor.py`, ключи
  `org.mate.peripherals-mouse` и `org.gnome.desktop.interface`.

Отличия и порядок переноса на вторую плату — в [4pro.md](4pro.md) и в
`INSTALL.md` (раздел «Другая плата: Orange Pi 4 Pro»).
