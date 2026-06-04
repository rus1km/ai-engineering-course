# Notes MCP Server

Власний MCP-сервер (Model Context Protocol), написаний з нуля на Python із
офіційним пакетом [`mcp`](https://pypi.org/project/mcp/). Дає MCP-клієнту
(Claude Desktop) персональне сховище нотаток із **реальним** збереженням
у JSON-файл на диску.

- **Стек:** Python 3.10+, пакет `mcp` (FastMCP high-level API)
- **Transport:** `stdio` (Claude Desktop запускає сервер як підпроцес)
- **Сховище:** JSON-файл, шлях задається змінною `NOTES_DB_PATH`
  (за замовчуванням `~/.mcp_notes/notes.json`)

---

## Tools та Resources

### Tools

| Tool | Аргументи | Опис |
|------|-----------|------|
| `add_note` | `content` *(required)*, `title` *(optional)*, `tags` *(optional, list)* | Створює нотатку. Повертає її `id`. |
| `search_notes` | `query` *(required)*, `tag` *(optional)*, `limit` *(optional, =10)* | Пошук без урахування регістру в заголовку + тексті; фільтр за тегом; `query="*"` — усі нотатки. |
| `delete_note` | `note_id` *(required, int)* | Видаляє нотатку за `id`. |

> Вимога завдання виконана: `delete_note` має **тільки required**-аргумент,
> а `add_note` / `search_notes` поєднують **required + optional**.

### Resources

| URI | Тип | Опис |
|-----|-----|------|
| `notes://all` | static | Усі нотатки, відформатовані як текст (нові — згори). |
| `notes://stats` | static | Агрегована статистика (JSON): кількість нотаток, теги, остання зміна. |
| `note://{note_id}` | template | Одна нотатка за `id`, напр. `note://3`. |

---

## Setup

### 1. Створити virtualenv і встановити залежності

```bash
cd "lesson 16 - mcp-model-context-protocol/homework"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

### 2. (Опційно) Перевірити локально

Швидка перевірка, що сервер стартує без помилок:

```bash
./.venv/bin/python server.py
# Сервер чекає на JSON-RPC через stdio. Зупиніть через Ctrl+C.
```

### 3. Підключити до Claude Desktop

Відредагуйте конфіг Claude Desktop (на macOS):

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

> Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Додайте блок `notes` (готовий приклад — у файлі [`claude_desktop_config.json`](claude_desktop_config.json)).
**Шляхи мають бути абсолютними** — Claude Desktop не знає робочої директорії:

```json
{
  "mcpServers": {
    "notes": {
      "command": "/ABSOLUTE/PATH/TO/homework/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/homework/server.py"],
      "env": {
        "NOTES_DB_PATH": "/Users/<you>/.mcp_notes/notes.json"
      }
    }
  }
}
```

### 4. Перезапустити Claude Desktop

Повністю закрийте та відкрийте Claude Desktop (Cmd+Q, не просто вікно).
Після старту в полі вводу зʼявиться іконка інструментів зі сервером `notes`
(3 tools), а в меню attach (📎 → *Add from notes*) — ресурси.

---

## 3 приклади діалогів

### Діалог 1 — створення нотаток (required + optional args)

> **You:** Save a note: "Buy oat milk and eggs".
>
> **Claude:** *(викликає `add_note(content="Buy oat milk and eggs")`)*
> Saved as note #1 (untitled).
>
> **You:** Add another one titled "Lesson 16" with tags course and mcp:
> "Ship the MCP homework before Friday".
>
> **Claude:** *(викликає `add_note(content="Ship the MCP homework before Friday",
> title="Lesson 16", tags=["course","mcp"])`)*
> Saved as note #2, title "Lesson 16", tags: course, mcp.

### Діалог 2 — пошук і фільтр за тегом

> **You:** Search my notes for "milk".
>
> **Claude:** *(викликає `search_notes(query="milk")`)*
> Found 1 note: #1 "Buy oat milk and eggs".
>
> **You:** Show me everything tagged "mcp".
>
> **Claude:** *(викликає `search_notes(query="*", tag="mcp")`)*
> Found 1 note: #2 "Lesson 16" — Ship the MCP homework before Friday.

### Діалог 3 — resource + видалення

> **You:** What stats do you have about my notes store?
>
> **Claude:** *(читає resource `notes://stats`)*
> You have 2 notes, 2 unique tags (course, mcp). Last updated 2026-06-04.
>
> **You:** Delete note #1.
>
> **Claude:** *(викликає `delete_note(note_id=1)`)*
> Note #1 deleted. You now have 1 note left.

Скріншоти реальних діалогів у Claude Desktop — у папці [`examples/`](examples/).

---

## Known limitations

- **Без конкурентного доступу.** Сховище — один JSON-файл; запис атомарний
  (`tmp` → `replace`), але якщо два клієнти писатимуть одночасно, останній
  перезапис виграє. Розраховано на один інстанс Claude Desktop.
- **Лінійний пошук.** `search_notes` — простий substring-match по всіх нотатках
  у памʼяті. На десятках тисяч нотаток буде повільно; повноцінного індексу/
  full-text-search немає.
- **Немає update-tool.** Нотатку можна лише створити чи видалити; редагування
  тексту не реалізовано (свідомо, щоб тримати набір інструментів мінімальним).
- **Без авторизації/шифрування.** Файл лежить у відкритому вигляді в домашній
  директорії; не для чутливих даних.
- **Несортовані id після видалення.** `id` монотонно зростають і не
  перевикористовуються — після видалення в нумерації будуть «дірки».
- **Тільки stdio.** Сервер не піднімає HTTP/SSE-transport; працює лише як
  локальний підпроцес клієнта.

---

## Структура проєкту

```
homework/
├── server.py                   # код MCP-сервера
├── requirements.txt            # залежності
├── claude_desktop_config.json  # приклад конфігу для Claude Desktop
├── README.md                   # цей файл
└── examples/                   # 3 скріншоти діалогів у Claude Desktop
```
