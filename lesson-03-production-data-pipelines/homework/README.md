# Homework: Lesson 03 — Production Data Pipelines

## Мета

Закріпити навички preprocessing даних для AI систем на практиці — доробити існуючі demo-проекти з лекції.

Виберіть **мінімум 2 з 3 проектів** і виконайте задачі до них.

---

## Проект 1: Healthcare RAG (demo-app/)

### Task 1.1 — Новий PII паттерн (10 балів)

Додайте новий паттерн PII detection у `preprocessing/pii.py`:

- Додайте паттерн для **IBAN** (International Bank Account Number)
  - Формат: `UA` + 2 цифри + 25 цифр (для України) або загальний: 2 букви + 2 цифри + до 30 алфанумеричних символів
- Додайте паттерн для **passport number**
  - Формат: 2 букви + 6 цифр (наприклад, `АВ123456`)
- Переконайтесь що `redact_pii()` замінює знайдені значення на `[IBAN]` і `[PASSPORT]`
- Створіть PDF документ в `docs/` який містить ці PII і покажіть що redaction працює

### Task 1.2 — Нова стратегія chunking (10 балів)

Додайте 8-му стратегію chunking у `preprocessing/chunking.py`:

- Реалізуйте **"Sliding window"** стратегію:
  - Фіксований розмір вікна (наприклад, 500 символів)
  - Крок (step) менший за розмір вікна (наприклад, 250 символів)
  - Кожен chunk перекривається з попереднім на `window_size - step` символів
- Додайте стратегію до списку `CHUNKING_STRATEGIES`
- Перевірте що вона з'являється в Streamlit dropdown і працює

### Task 1.3 — Порівняння chunking стратегій (10 балів)

Запустіть RAG pipeline з одним і тим же питанням, але з різними стратегіями chunking:

- Питання: `"What is the protocol for handling patient lab results?"`
- Запустіть для **3 різних стратегій** (на вибір)
- Для кожної зафіксуйте:
  - Кількість chunks
  - Top-3 retrieved chunks (перші 100 символів кожного)
  - GPT відповідь
  - Чи є PII у відповіді (з увімкненим redaction)
- Результати запишіть у файл `homework/chunking_comparison.md`

---

## Проект 2: Invoice Extraction (invoice-extraction/)

### Task 2.1 — Нові regex паттерни (10 балів)

Додайте нові паттерни у `regex_extractor.py`:

- **PO Number** (Purchase Order): формат `PO-XXXXX` або `PO #XXXXX`
- **VAT Number**: формат `VAT` + країна (2 букви) + 8-12 цифр
- **IBAN**: аналогічно Task 1.1

Переконайтесь що:
- `regex_extract()` повертає нові поля
- `llm_extract_remaining()` не запитує ці поля у LLM якщо regex їх знайшов

### Task 2.2 — Власний інвойс (10 балів)

- Створіть PDF інвойс (можна через Python fpdf2, Google Docs, або вручну)
- Інвойс повинен містити: PO number, VAT number, IBAN, мінімум 3 line items
- Додайте його в `invoices/`
- Запустіть pipeline і зафіксуйте результати обох режимів (LLM-only vs Hybrid) у `homework/invoice_test.md`:
  - Скільки полів знайшов regex
  - Скільки токенів використано в кожному режимі
  - Яка економія у %

### Task 2.3 — Порівняння моделей (10 балів)

Порівняйте якість та вартість двох OpenAI моделей:

- Запустіть extraction для всіх інвойсів з **GPT-4o-mini** і **GPT-3.5-turbo**
- Для кожної моделі зафіксуйте:
  - Кількість токенів (input + output)
  - Час виконання
  - Якість (чи всі поля правильно витягнуто)
- Результати у `homework/model_comparison.md`

---

## Проект 3: Resume Pipeline (resume-pipeline/)

### Task 3.1 — Нова dbt модель (10 балів)

Створіть нову dbt модель `mart_pii_report.sql` у `dbt_project/models/`:

```sql
-- Модель повинна показувати:
-- 1. resume_file
-- 2. Кількість PII по кожному типу (email, phone, ssn) — окремі колонки
-- 3. total PII
-- 4. pii_risk_level (HIGH/MEDIUM/CLEAN)
-- 5. Рекомендація: чи безпечно зберігати оригінал (safe_to_store: yes/no)
```

Запустіть `dbt run` і покажіть результат у `homework/pii_report.md`.

### Task 3.2 — Новий resume (10 балів)

- Створіть PDF resume який містить багато PII (SSN, credit card, address, date of birth)
- Додайте його в `data/resumes/`
- Запустіть весь pipeline: `python dags/resume_dag.py && python run_dbt.py`
- Зафіксуйте:
  - Скільки PII знайдено і якого типу
  - Score від LLM
  - Як resume виглядає в mart таблиці
- Результат у `homework/new_resume_test.md`

### Task 3.3 — Аналітичний запит (10 балів)

Напишіть 3 SQL запити до DuckDB (можна в окремому Python скрипті або notebook):

1. Середній score по pii_risk_level (GROUP BY)
2. Кореляція між compression_ratio і score — чи впливає очистка на оцінку
3. Рейтинг кандидатів: тільки ті де recommendation = 'yes' або 'strong_yes' І pii_risk != 'HIGH_RISK'

Результати з виводом у `homework/analytics.md`.

---

## Як здати

1. Fork репозиторій або створіть branch `homeworks`
2. Виконайте задачі (мінімум 2 проекти)
3. Всі результати збережіть у папці `homework/`
4. Push і створіть Pull Request

## Оцінювання

| Проект | Задачі | Макс. балів |
|--------|--------|-------------|
| Healthcare RAG | 1.1 + 1.2 + 1.3 | 30 |
| Invoice Extraction | 2.1 + 2.2 + 2.3 | 30 |
| Resume Pipeline | 3.1 + 3.2 + 3.3 | 30 |
| **Мінімум 2 проекти** | | **60** |
| **Максимум (всі 3)** | | **90** |

**Прохідний бал: 40/90**
