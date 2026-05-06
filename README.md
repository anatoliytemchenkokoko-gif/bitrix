# GitHub Pages calendar sync

Это обходной вариант без VPS и без `workers.dev`.

Идея:

- GitHub Actions по расписанию тянет Bitrix `ics`;
- локально чистит проблемные `DTSTAMP` и часть `RRULE`-дублей;
- складывает готовые `.ics` в папку `docs/`;
- GitHub Pages публикует эти статические файлы по обычному HTTPS URL.

Почему это может быть лучше для Apple Calendar:

- Apple берет обычный статический файл по HTTPS;
- нет `workers.dev`, который у нас сейчас ловит `403 / 1010`.

## Что уже готово

- [generate_static_calendars.py](/Users/stolikkkkk/Library/CloudStorage/GoogleDrive-temchnko@gmail.com/Мой диск/1. спец. мероприятия_ Общая папка/спец. проекты/ИИ для ТЗ /битрикс/github-pages-sync/generate_static_calendars.py)
- [calendars.json](/Users/stolikkkkk/Library/CloudStorage/GoogleDrive-temchnko@gmail.com/Мой диск/1. спец. мероприятия_ Общая папка/спец. проекты/ИИ для ТЗ /битрикс/github-pages-sync/calendars.json)
- [update-calendars.yml](/Users/stolikkkkk/Library/CloudStorage/GoogleDrive-temchnko@gmail.com/Мой диск/1. спец. мероприятия_ Общая папка/спец. проекты/ИИ для ТЗ /битрикс/github-pages-sync/.github/workflows/update-calendars.yml)

## Как это запустить

1. Создать новый публичный GitHub-репозиторий.
2. Залить в него содержимое папки `github-pages-sync/`.
3. Включить GitHub Pages для ветки `main`, папка `/docs`.
4. Дать GitHub Actions права на запись в репозиторий.
5. Запустить workflow `Update Calendars` вручную.

После этого ссылки будут вида:

- `https://<username>.github.io/<repo>/atrium-local-demo-token.ics`
- `https://<username>.github.io/<repo>/bitrix-939-local-demo-token.ics`
- `https://<username>.github.io/<repo>/bitrix-940-local-demo-token.ics`

## Ограничения

- GitHub Actions schedule не realtime.
- По официальной документации GitHub, scheduled workflow может запускаться минимум раз в 5 минут и может задерживаться при высокой нагрузке.

Источники:

- [GitHub Pages overview](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages)
- [GitHub Actions schedule syntax](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#onschedule)
