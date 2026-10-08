<task id="ses_f8a548c20ffeov4ttieIdnb9gD" state="completed">
<task_result>
# Процесс заблаговременного управления дополнительными SSL-корневыми сертификатами (extra root CA bundle) в мобильном приложении для Android и Huawei

**Статус:** v1.2 (одобрен ревью; полировка по замечаниям ревьюера)
**Владелец:** TrustStore-менеджер (см. §2)
**Область применения:** Android-приложение, распространяемое в т.ч. на устройства Huawei (EMUI / HarmonyOS), включая AppGallery-канал.

---

## 1. Цель и принципы

### 1.1. Проблема

Системное хранилище доверенных корневых CA на Android обновляется вместе с ОС, а не приложением, и не обновляется на уже выпущенных устройствах (кроме редких security-patch-апдейтов системы). Новые корневые CA (например, GlobalSign Root R46 и Root E46) появляются в AOSP-сторе пакетно и с задержкой: R46/E46 добавлены в AOSP коммитом `20642a7` (2023-02-21) и **первый раз поставляются нативно в Android 14**; в финальном теге Android 13 (`android-13.0.0_r84`, 126 корней) их нет. Устройства Huawei с EMUI/HarmonyOS используют собственные хранилища, которые могут отставать от AOSP (эмпирически, по пользовательским репортам: R46 отсутствует в Huawei 15.0.0), и их нельзя проверить по публичным исходникам.

Когда бэкенд или CDN переходит на цепочки, завершающиеся в такой новый корень, все устройства с «старым» хранилищем (Android ≤ 13, затронутые сборки EMUI/HarmonyOS) получают `CertPathValidatorException` / «Trust anchor for certification path not found» — приложение теряет способность работать по HTTPS.

### 1.2. Решение

Приложение поставляет **минимальный дополнительный набор корневых сертификатов** (extra trust anchors) через `Network Security Config` (`res/xml/network_security_config.xml` + сгенерированные `res/raw/<id>.pem`, источник — `truststore/extra_roots/`). В сборку попадают **только** те корни, которых может не быть на целевых устройствах. Как только целевые ОС поставляют корень нативно, корень **удаляется из сборки** управляемым релизом.

### 1.3. Принципы

1. **Системное хранилище — база, не замена.** В каждом блоке `<trust-anchors>` (и в `base-config`, и в каждом `domain-config` с собственными якорями) явно присутствует `<certificates src="system"/>`; extra-корни — аддитивное дополнение. Семантика платформы: указание `<trust-anchors>` внутри `<base-config>`/`<domain-config>` **полностью заменяет** наследуемый набор, поэтому `src="system"` обязателен явно.
2. **Бандлим только недостающее.** Каждый PEM в бандле обоснован: подтверждённое отсутствие корня хотя бы на одной значимой целевой конфигурации ОС (Android floor-тег или Huawei-матрица).
3. **Единый источник истины.** PEM-файлы — `truststore/extra_roots/`; метаданные — `truststore/certs.json`; floor-политика — `truststore/policy.yaml`. PEM без записи в манифесте (и наоборот), ссылка `@raw/` без PEM, PEM без ссылки = падение сборки. `res/raw/*.pem` — сгенерированные файлы, руками не редактируются.
4. **Бандл стремится к нулю.** Цель процесса — проживать каждый корень минимально необходимое время и удалять его, как только целевые ОС закрывают потребность.
5. **Верификация — по первоисточникам.** Fingerprint корня сверяется только с официальным источником CA-оператора (его сайт / CCADB / AOSP-репозиторий), никогда — с агрегаторов и «случайных» сайтов.
6. **Удаление — управляемый релиз.** Удаление корня из сборки — отдельная операция с условиями выхода, мониторингом TLS-ошибок и планом N-1, а не «тихий» коммит.
7. **Huawei — только эмпирика.** Присутствие корня в сторах Huawei не выводится из AOSP; подтверждается физической/виртуальной тестовой матрицей.

---

## 2. Термины и роли

### 2.1. Термины

| Термин | Определение |
|---|---|
| **Floor (min-supported OS)** | Минимальная поддерживаемая конфигурация ОС: `minSdk` приложения для Android и явный список конфигураций EMUI/HarmonyOS из матрицы поддержки. Ключевой вход правил добавления/удаления. Хранится канонически в `truststore/policy.yaml` (§3.4). |
| **Extra anchor (бандл)** | Корневой CA, добавленный в сборку приложения сверх системного набора. |
| **Нативная поставка** | Корень присутствует в системном хранилище данной версии ОС (для Android — в AOSP-теге соответствующей версии). |
| **Empirical matrix (Huawei-матрица)** | `truststore/huawei_matrix.yaml` — таблица результатов проверки нативной поставки корней на реальных конфигурациях Huawei (модель × продукт/версия ОС × регион). |
| **`first_os`** | Первая версия ОС с нативной поставкой корня (`android: 14`, `huawei: null` — пока не подтверждено эмпирикой). |
| **Статусы корня** | `active` → `deprecated` → `removal_scheduled` → `removed` (запись со статусом `removed` не имеет PEM и ссылки `@raw/`; живёт в `certs.json` до закрытия N-1-окна, затем архивируется). |
| **N-1 совместимость** | Учёт того, что пользователи бегают на предыдущей мажорной версии приложения, которая несёт старый бандл. |

### 2.2. Роли

| Роль | Ответственность |
|---|---|
| **TrustStore-менеджер** | Владелец `certs.json`, `policy.yaml` и процесса в целом. Следит за триггерами мониторинга (§4.1), принимает решения add/keep/remove, ведёт Huawei-матрицу и review-даты. |
| **Release-инженер** | CI/CD-гейты (§7), Gradle-обвязка `copyExtraRoots` (§3.1), версионирование, staged rollout релизов с изменением бандла. |
| **QA** | Эмпирические проверки на девайс-матрице (в первую очередь Huawei), прогон TLS-сценариев на floor-конфигурациях, обновление `huawei_matrix.yaml`. |
| **Security** | Ревью PR на добавление/удаление корня: сверка fingerprint по первоисточнику, оценка расширения поверхности доверия, одобрение удаления. |
| **Бэкенд/инфраструктура (консультирует)** | Согласовывают смену серверных цепочек (сервер обязан отдавать полную цепочку с промежуточными сертификатами (intermediates); корень в handshake не отправляется), ставят TrustStore-менеджера в известность до ротации сертификатов на сервере. |

---

## 3. Архитектура решения

### 3.1. Файловая структура репозитория и платформенное ограничение

```
app/
  src/main/AndroidManifest.xml                      # android:networkSecurityConfig="@xml/network_security_config"
  src/main/res/xml/network_security_config.xml      # конфиг доверия (§3.2)
  src/main/res/raw/                                 # ПЛОСКИЙ каталог; *.pem здесь СГЕНЕРИРОВАНЫ
    globalsign_root_r46.pem                         #   таской copyExtraRoots → в .gitignore
    globalsign_root_e46.pem
truststore/                                         # НЕ попадает в APK; зона ревью и CI
  extra_roots/                                      # ← SOURCE OF TRUTH для PEM-файлов
    globalsign_root_r46.pem
    globalsign_root_e46.pem
  certs.json                                        # манифест метаданных (§3.3)
  policy.yaml                                       # floor-политика — каноническое место (§3.4)
  huawei_matrix.yaml                                # эмпирическая матрица Huawei (§3.5)
  scripts/
    check_duplicate_against_aosp.sh                 # гейт G6
    lint_certs.sh                                   # гейты G1–G4, G7–G8
  archive/                                          # архив удалённых записей (после N-1-окна)
ci/
  truststore_gate.yml                               # пайплайн гейтов G1–G8 (§7)
.github/pull_request_template/truststore.md
```

**Платформенное ограничение (объясняем явно, чтобы его не «чинили» обратно):** `res/raw/` — плоский ресурсный тип. Каталоги `res/` не поддерживают подпапки: aapt2 не обходит их рекурсивно, файл `res/raw/extra_roots/x.pem` **молча игнорируется** (проверено: `aapt2 compile` даёт 0 записей), а ссылка `@raw/extra_roots/x` синтаксически невозможна — имя ресурса не содержит `/`. Единственный корректный способ — плоские файлы `res/raw/<id>.pem`. Поэтому каноническая схема: PEM-файлы живут и ревьюятся в `truststore/extra_roots/`, а в `res/raw/` их **генерирует** Gradle-таска перед сборкой. Это даёт: единый source of truth, CI-lint именно тех файлов, что ревьюятся, отсутствие merge-конфликтов и «забытых» файлов в `res/`.

**Gradle-таска** (`app/build.gradle.kts`):

```kotlin
// res/raw НЕ поддерживает подпапки → генерируем плоские res/raw/<id>.pem
// из truststore/extra_roots/. Sync (не Copy): копирует и удаляет устаревшие *.pem,
// так что при удалении корня из truststore/ «хвост» в res/raw не остаётся.
val copyExtraRoots by tasks.registering(Sync::class) {
    from(rootProject.layout.projectDirectory.dir("truststore/extra_roots"))
    include("*.pem")
    into(layout.projectDirectory.dir("src/main/res/raw"))
    preserve { it.exclude("*.pem") }   // не трогаем прочие raw-ресурсы приложения
}
tasks.matching { it.name == "preBuild" }.configureEach { dependsOn(copyExtraRoots) }
```

**`.gitignore`** (корень репозитория):

```
# сгенерировано таской copyExtraRoots из truststore/extra_roots/
app/src/main/res/raw/*.pem
```

### 3.2. `network_security_config.xml`

`AndroidManifest.xml`:

```xml
<application android:networkSecurityConfig="@xml/network_security_config" ... >
```

Существует два корректных варианта размещения extra-корней. Выбор фиксируется в этом документе и проверяется Security.

**Вариант A (простой):** extra-корни в `base-config` — глобальное доверие. Меньше изменений, но extra-корни могут vouchить за **любые** хосты (расширяют поверхность доверия для сторонних доменов тоже).

```xml
<base-config cleartextTrafficPermitted="false">
    <trust-anchors>
        <certificates src="system"/>
        <certificates src="@raw/globalsign_root_r46"/>
        <certificates src="@raw/globalsign_root_e46"/>
    </trust-anchors>
</base-config>
```

**Вариант B (рекомендуемый Security; используется во всех примерах далее):** `base-config` — только системные якоря; extra-корни — **только** в `domain-config` наших доменов. Extra-корни не могут заверять сторонние хосты. Цена: список доменов должен быть полным и поддерживаться актуальным (см. §4.5, §9).

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Вариант B: база — ТОЛЬКО системные якоря.
         ВАЖНО: <trust-anchors> внутри base-config/domain-config ЗАМЕНЯЕТ
         наследуемый набор целиком, поэтому src="system" обязателен в каждом
         блоке с собственными trust-anchors. -->
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </base-config>

    <!-- Наши API/CDN-домены: системные якоря + бандл недостающих корней.
         Файлы res/raw/<id>.pem генерируются таской copyExtraRoots (§3.1). -->
    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="true">api.example.com</domain>
        <domain includeSubdomains="true">cdn.example.com</domain>
        <trust-anchors>
            <certificates src="system"/>
            <certificates src="@raw/globalsign_root_r46"/>
            <certificates src="@raw/globalsign_root_e46"/>
        </trust-anchors>
    </domain-config>

    <!-- Пользовательские CA — только debug-overrides, никогда в prod.
         src="user" в base-config/domain-config = доверие к пользовательски
         установленным CA на всех устройствах — MITM-риск (структурная проверка G8). -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="user"/>
        </trust-anchors>
    </debug-overrides>
</network-security-config>
```

Инвариант: набор `<certificates src="@raw/..."/>` в XML 1:1 совпадает со списком записей `certs.json` со статусом `active | deprecated | removal_scheduled` (гейт G3). `deprecated`/`removal_scheduled` корни остаются в XML и сборке до фактического релиза удаления.

### 3.3. Манифест `truststore/certs.json`

Floor-политику НЕ дублирует — ссылается на `policy.yaml` (§3.4), где она задаётся канонически (так её единообразно потребляют скрипты).

```json
{
  "schema_version": 1,
  "policy_ref": "truststore/policy.yaml",
  "certificates": [
    {
      "id": "globalsign_root_r46",
      "subject": "/C=BE/O=GlobalSign nv-sa/CN=GlobalSign Root R46",
      "sha256": "4F:A3:12:6D:8D:3A:11:D1:C4:85:5A:4F:80:7C:BA:D6:CF:91:9D:3A:5A:88:B0:3B:EA:2C:63:72:D9:3C:40:C9",
      "aosp_file": "files/1b0f7e5c.0",
      "source_url": "https://secure.globalsign.com/cacert/rootr46.crt",
      "source_format": "DER",
      "not_before": "2019-03-20T00:00:00Z",
      "not_after": "2046-03-20T00:00:00Z",
      "first_os": { "android": 14, "huawei": null },
      "huawei_evidence": "huawei_matrix.yaml#r46",
      "status": "active",
      "added_in_app_version": "24.7.0",
      "removal_ticket": null,
      "review_date": "2026-12-01",
      "notes": "Отсутствует в android-13.0.0_r84 (последний тег A13), присутствует с android-14.0.0_r1. Huawei 15.0.0 / HarmonyOS 4.0 — отсутствие подтверждено эмпирически (huawei_matrix)."
    },
    {
      "id": "globalsign_root_e46",
      "subject": "/C=BE/O=GlobalSign nv-sa/CN=GlobalSign Root E46",
      "sha256": "CB:B9:C4:4D:84:B8:04:3E:10:50:EA:31:A6:9F:51:49:55:D7:BF:D2:E2:C6:B4:93:01:01:9A:D6:1D:9F:50:58",
      "aosp_file": "files/e7c037b4.0",
      "source_url": "https://secure.globalsign.com/cacert/roote46.crt",
      "source_format": "DER",
      "not_before": "2019-03-20T00:00:00Z",
      "not_after": "2046-03-20T00:00:00Z",
      "first_os": { "android": 14, "huawei": null },
      "huawei_evidence": "huawei_matrix.yaml#e46",
      "status": "active",
      "added_in_app_version": "24.7.0",
      "removal_ticket": null,
      "review_date": "2026-12-01",
      "notes": "Тот же батч AOSP, что и R46 (коммит 20642a7, 2023-02-21)."
    }
  ]
}
```

Правила статусов: `active | deprecated | removal_scheduled | removed`. Обязательные поля записи: `subject`, `sha256`, `aosp_file`, `source_url`, `not_before`, `not_after`, `first_os` (`huawei: null`, пока эмпирика не подтвердила), `status`, `review_date` (не дальше 6 месяцев; просроченная — warning от G8). Запись `removed` не имеет PEM в `truststore/extra_roots/` и ссылки `@raw/` в NSC; живёт в `certs.json` до закрытия N-1-окна (затем — `truststore/archive/`).

Поле `aosp_file` — имя файла корня в AOSP-сторе `platform/system/ca-certificates`; имена там — OpenSSL **old-style subject hash** (`openssl x509 -subject_hash_old`; для R46 — `1b0f7e5c`, для E46 — `e7c037b4`). Это ключ для автоматики гейта G6 (§7).

### 3.4. `truststore/policy.yaml` — каноническое место floor-политики

```yaml
schema_version: 1
min_supported_android:
  os_version: 13
  api_level: 33                 # = minSdk в app/build.gradle.kts; синхронизирует G3
  aosp_floor_tag: "android-13.0.0_r84"   # последний тег floor-версии; читает G6
min_supported_huawei:            # ЯВНЫЙ список floor-конфигураций (product × version),
  - { product: "EMUI",      version: "15.0.0" }   # соответствует huawei_matrix.yaml
  - { product: "HarmonyOS", version: "4.0" }
huawei_channel_supported: true    # false = Huawei-канал исключён из матрицы поддержки
removal_share_threshold_pct: 1.0  # порог аналитического пути удаления (§5.1)
huawei_matrix_max_age_days: 180   # свежесть эмпирических проверок (G7)
```

### 3.5. `truststore/huawei_matrix.yaml`

```yaml
matrix_version: 2026-09-06
devices:                          # конфигурации = фактический топ парка из аналитики
  - { id: 0, model: "HUAWEI P50",     product: "HarmonyOS", version: "4.0",  region: "RU" }
  - { id: 1, model: "HUAWEI nova 11", product: "HarmonyOS", version: "4.2",  region: "RU" }
  - { id: 2, model: "HUAWEI Mate 60", product: "HarmonyOS", version: "4.0",  region: "RU" }
  - { id: 3, model: "HUAWEI Mate 40", product: "EMUI",       version: "15.0.0", region: "RU" }  # user-reported floor
roots:
  r46:
    checks:
      - { device_ref: 0, method: "adb+conscrypt-probe", present: false, date: "2026-08-30", ticket: "QA-1234" }
      - { device_ref: 3, method: "adb+conscrypt-probe", present: false, date: "2026-08-30", ticket: "QA-1234" }
    verdict: absent_on_floor
  e46:
    checks:
      - { device_ref: 0, method: "adb+conscrypt-probe", present: false, date: "2026-08-30", ticket: "QA-1235" }
      - { device_ref: 3, method: "adb+conscrypt-probe", present: false, date: "2026-08-30", ticket: "QA-1235" }
    verdict: absent_on_floor
```

Verdict'ы: `absent_on_floor` / `present_on_floor`. Verdict обязан опираться на свежие (≤ `huawei_matrix_max_age_days`) проверки **на каждой** floor-конфигурации из `policy.yaml` (в примере — EMUI 15.0.0 и HarmonyOS 4.0; именно поэтому у обоих корней есть чеки на device_ref 0 и 3).

---

## 4. Процесс ADD (заблаговременное добавление)

### 4.1. Триггеры мониторинга

| # | Триггер | Механика | Кто |
|---|---|---|---|
| T1 | **Коммиты/теги AOSP `platform/system/ca-certificates`** | Подписка на новые коммиты и теги (gitiles log / `git fetch` по расписанию; nightly-джоба). Новые файлы `files/*.0` = кандидаты. | TrustStore-менеджер (автоматика в CI как watchdog-джоба) |
| T2 | **Mozilla root program / NSS / CCADB** | События добавления/удаления (inclusion/de-inclusion) в NSS и CCADB; изменения Mozilla root store. | TrustStore-менеджер |
| T3 | **Анонсы CA-операторов** | Бюллетени операторов (пример: репозиторий GlobalSign), уведомления о новых корнях и ротациях. | TrustStore-менеджер |
| T4 | **План серверной ротации** | Бэкенд/CDN объявляет переход цепочек на новый корень ДО включения — обязателен SLA согласования ≥ 1 квартал до ротации. | Бэкенд → TrustStore-менеджер |
| T5 | **Инцидентная телеметрия** | Рост `CertPathValidatorException`/`SSLHandshakeException: Trust anchor...` по версиям ОС — реактивный резервный канал (процесс должен срабатывать по T1–T4 раньше). | Дежурный инженер |
| T6 | **Ежеквартальный аудит** | Полный пересмотр `certs.json`, `policy.yaml`, Huawei-матрицы (§6). | TrustStore-менеджер + QA |

Реакция на T1–T3 без внешней ротации: кандидат ставится в backlog с оценкой «понадобится ли он нашим серверам вообще» (решение ADD-0 в §4.3). Реакция на T4 — процесс обязателен к запуску.

### 4.2. Верификация отсутствия на целевых ОС

**Android (автоматическая, по AOSP-тегам).** Прямая проверка floor-тега из `policy.yaml`:

```bash
# Вариант А — без клона, через gitiles (для одного файла):
# 404 = корня нет в floor-теге, 200 = есть; любой другой код = «не верифицировано» (см. гейт G6)
curl -s -o /dev/null -w "%{http_code}\n" --max-time 30 \
  "https://android.googlesource.com/platform/system/ca-certificates/+/refs/tags/android-13.0.0_r84/files/1b0f7e5c.0"

# Вариант B — с неглубоким клоном (для батчевых проверок и diff'ов):
git clone --filter=blob:none --no-checkout \
  https://android.googlesource.com/platform/system/ca-certificates
cd ca-certificates
git ls-tree -r --name-only android-14.0.0_r1 -- files | grep 1b0f7e5c   # есть в A14?
git diff --stat android-13.0.0_r84 android-14.0.0_r1 -- files             # diff между ОС
```

Формальная фиксация: «корень отсутствует в последнем теге floor-версии (для A13 — `android-13.0.0_r84`) и присутствует начиная с `first_os.android`-тега (для R46/E46 — `android-14.0.0_r1`)». Дополнительно сверить SHA256 PEM из бандла с PEM из AOSP-тега: байты стабильны между тегами (проверено: fingerprint R46 в `main` и `android-14.0.0_r1` идентичен) — дешёвая перекрёстная верификация подлинности.

**Huawei (эмпирическая, QA-матрица).** Для каждой floor-конфигурации из `policy.yaml` (модель × продукт/версия ОС × регион) выполняется проба на реальном устройстве/эмуляторе:

1. **Probe-скрипт** (adb): приложение-пробник c NSC-конфигом, где якоря заданы только системные, открывает TLS-соединение к тестовому хосту, чей сертификат подписан цепочкой в проверяемый корень; логируем успех/`Trust anchor not found`. Альтернатива — Java-пробник, выводящий набор системных TrustAnchors через `TrustManagerFactory` (плюс: работает через `adb shell`/инструментацию; минус: дамп полного стора на несистемных сборках Huawei — сверять по fingerprint).
2. Результат (`present: true/false`, дата, тикет, метод) заносится в `huawei_matrix.yaml` по **каждой** floor-конфигурации.
3. Verdict `absent_on_floor` валиден, только если все floor-конфигурации закрыты свежими проверками (гейт G7).

**Запрещено** выводить наличие корня в Huawei из AOSP, «обычной логики обновлений ОС» или таблиц из интернета: только матрица.

### 4.3. Таблица решений

| ID | Условие | Решение |
|---|---|---|
| ADD-0 | Корень анонсирован/появился в сторе ОС, но наши серверы (текущие и заявленные T4 ротации) не используют цепочки в него и не планируют | **Не добавлять.** Запись в backlog, реактивное наблюдение (T5). |
| ADD-1 | Серверная ротация запланирована (T4) И (корень отсутствует на Android floor ИЛИ на Huawei floor) | **ADD**: полный цикл §4.4–§4.7. |
| ADD-2 | Корень присутствует на всех целевых floor | **Не добавлять** (лишнее расширение доверия и размера APK). |
| ADD-3 | Корень нужен, но это не публичный корень (частный CA) | **Вне этого процесса** — отдельная политика (пиннинг/двусторонний TLS); этот процесс — только публичные корни. |
| KEEP-1 | Корень в бандле, условия §5.1 ещё не закрыты (нет нативной поставки хотя бы на одном целевом floor) | **Оставить** (`active`), обновить `review_date`. |
| REM-1 | См. §5.1 | **REMOVE** |

### 4.4. Оформление записи и добавление PEM

1. TrustStore-менеджер создаёт запись в `certs.json` (все обязательные поля §3.3), `status: active`, `review_date` ≤ +6 мес.
2. PEM берётся **только** с `source_url` (первоисточник оператора; для R46 — `https://secure.globalsign.com/cacert/rootr46.crt`, DER) или из AOSP-тега. Файл нормализуется (`openssl x509 -outform PEM`, без лишнего текста) и кладётся в `truststore/extra_roots/<id>.pem`. В `res/raw/` руками ничего не кладётся — файл сгенерирует `copyExtraRoots` на следующей сборке.
3. Обновляется `network_security_config.xml`: добавляется `<certificates src="@raw/<id>"/>` в `domain-config` наших доменов (Вариант B; при утверждённом Варианте A — в `base-config`).

### 4.5. PR + чеклист (Security review обязателен)

PR-чеклист (шаблон — `.github/pull_request_template/truststore.md`):

- [ ] Корень действительно нужен (решение ADD-1, приложены доказательства: ссылки на AOSP-теги, тикеты QA по Huawei-матрице).
- [ ] **Fingerprint сверен с официальным источником оператора** (не с агрегатором/вики): `curl -s <source_url> | openssl x509 -inform DER -noout -fingerprint -sha256` — совпадает с полем `sha256` в `certs.json` и с PEM в PR. Проверку делают и человек, и CI (G4/G5).
- [ ] Перекрёстная сверка с AOSP: PEM из AOSP-тега `first_os.android` имеет тот же SHA256.
- [ ] `not_after` — не ранее +24 мес от сегодня (для свежих корней обычно так и есть; R46/E46 — 2046-03-20).
- [ ] `first_os` заполнен и подтверждён (AOSP-теги присутствия/отсутствия указаны в notes).
- [ ] Huawei-матрица обновлена: свежие проверки на **каждой** floor-конфигурации из `policy.yaml`, verdict `absent_on_floor`.
- [ ] Список доменов в `domain-config` актуален (Вариант B): все API/CDN-домены с цепочками в новый корень перечислены.
- [ ] `review_date` ≤ +6 мес.
- [ ] Security approval получен: изменение файлов `truststore/**`, `app/src/main/res/xml/network_security_config.xml` и `app/build.gradle.kts` (там живёт таска `copyExtraRoots`) без аппрува Security не мержится (CODEOWNERS).

### 4.6. CI-проверки (см. §7)

На PR запускается `truststore_gate`: G1–G4, G6–G8 (G5 — nightly). Перед G3 запускается `./gradlew copyExtraRoots` (или полный `assemble`), чтобы сверить сгенерированный `res/raw/` с `truststore/extra_roots/`. Без зелёного гейта мерж невозможен.

### 4.7. Выпуск

1. Мерж в release-ветку; `added_in_app_version` фиксирует версию.
2. Релиз — staged rollout: 5% → 20% → 100% с контролем метрики «доля TLS-ошибок по ОС» (§10) на каждом шаге. Добавление корня — низкорисковое изменение, но раскатка всё равно каскадная.
3. При выпуске — уведомление в чат релизов: «в сборке N добавлены корни X, Y (причина: absent on Android ≤13 / Huawei floor)».

**SLA процесса:** от триггера T4 (заявленная серверная ротация) до релиза с корнем — ≤ 1 квартала; от триггера T1/T2/T3 — целевой lead time ≤ 30 дней (§10).

---

## 5. Процесс REMOVE (удаление)

### 5.1. Условия выхода (safe exit criteria)

Корень может быть удалён из сборки, когда выполнены **оба** условия:

- **Android-условие (любое из двух путей):**
  - **(а) Путь floor:** `min_supported_android.os_version ≥ first_os.android` — floor поднят выше версии ОС, начинающей нативную поставку корня (для R46: floor ≥ Android 14);
  - **(б) Путь аналитики:** доля устройств с ОС ниже `first_os.android`, использующих цепочки в этот корень, < `removal_share_threshold_pct` (1% DAU по аналитике, §6) — floor при этом может оставаться прежним.
- **Huawei-условие (всегда обязательно):** Huawei-матрица эмпирически подтверждает нативную поставку корня во **всех** floor-конфигурациях из `policy.yaml` (для `first_os.huawei: null` — после подтверждения поле заполняется, например `"HarmonyOS 5.0"`), **ИЛИ** Huawei-канал (AppGallery / Huawei-устройства) исключён из матрицы поддержки (`huawei_channel_supported: false` — фиксируется продуктовым решением).

Оба условия обязательны, потому что Huawei-стор не выводится из AOSP. Путь (б) не противоречит гейту G6: G6 сравнивает с AOSP floor-тегом, в котором (пока floor не поднят) корень отсутствует — сборка зелёная, решение принимается по §5.1.

**Переходное состояние: «Android floor закрыт, Huawei — нет».** Если floor поднят до версии с нативным корнем (например, A14), а Huawei-матрица всё ещё фиксирует `absent_on_floor`, возникает переходное состояние: корень больше не нужен Android-парку, но нужен Huawei-парку. G6 в этом случае **не валит сборку**, а выдаёт WARNING и создаёт/поддерживает блокирующий тикет «REM-1 pending Huawei verification» (сборка зелёная, слияния возможны; удаление заблокировано §5.1). TrustStore-менеджер обязан: (а) держать корень в бандле (`active`/`deprecated`), (б) держать тикет видимым, (в) на каждом квартальном аудите запрашивать у QA свежую пробу Huawei-матрицы (≤180 дней). Как только Huawei-условие закрывается (`present_on_floor` или исключение канала), G6 переводит WARNING в FAIL и запускается REMOVE. В варианте B такое «залёживание» безопасно: корень заверяет только наши домены, на Android 14+ он просто избыточен.

### 5.2. Шаги удаления

1. **Ревью (TrustStore-менеджер; триггер — T6, изменение floor или WARNING от G6):** проверить §5.1 по аналитике и Huawei-матрице; завести тикет удаления; `status: deprecated` (корень ещё в сборке, кандидат на удаление).
2. **Release planning / квартальный аудит:** перевод в `status: removal_scheduled`, заполнить `removal_ticket`, зафиксировать версию приложения, в которой корень уходит; обновить Huawei-матрицу свежими (≤180 дней) проверками.
3. **Выпуск с удалением:**
   - Удалить PEM из `truststore/extra_roots/`, убрать `<certificates src="@raw/<id>"/>` из `network_security_config.xml`, выставить `status: removed` + `removed_in_app_version` в `certs.json`. `res/raw/<id>.pem` исчезнет автоматически — таска `copyExtraRoots` типа `Sync` удаляет устаревшие `*.pem` (§3.1).
   - Удаление идёт **отдельным релизом** (не в одном PR с крупными фичами) и со staged rollout: старые версии приложения (N-1) продолжают носить этот корень, и если удаление ошибочно, откатить можно быстро, не откатывая фичи.
   - В release notes для инженеров: «удалён корень X — Android-условие закрыто (floor/аналитика) и Huawei-матрица подтвердила нативную поставку; ожидаемое влияние: ноль; мониторим TLS-метрики».
   - Feature flag для NSC не применяется (конфиг не рантайм-переключаем); страховой механизм — staged rollout + метрики + горячий хотфикс, возвращающий корень.
4. **Мониторинг после удаления (2–4 недели):** контроль rate of `CertPathValidatorException` / `SSLHandshakeException("Trust anchor...")`, агрегированный по (ОС-версия × версия приложения). Ожидание: отсутствие аномалий на floor-совместимых версиях. Аномалия на версиях приложения с удалённым корнем на устройствах вне поддерживаемого парка — нормальна и вне SLA; аномалия **внутри** поддерживаемого парка = инцидент → хотфикс с возвратом корня (путь назад — 1 PR).
5. **Полное удаление записи:** когда парк на версиях приложения с удалённым корнем < 1% DAU (обычно ~2 мажорных релиза) — запись уходит в `truststore/archive/`; Huawei-матрица сохраняет историю.

### 5.3. Запреты

- Не удалять корень в том же релизе, где поднимается floor (floor-релиз и cleanup-релиз — разные события, между ними ≥ 1 релиз наблюдения).
- Не удалять корень, если Huawei-матрица не обновлялась > 6 месяцев, даже при выполнении Android-условия.
- Не удалять корень «по неактивности» без выполнения §5.1: держать лишний корень — приемлемый, но осознанный риск: свежая `review_date` и, при закрытом Android-условии, видимый тикет от G6.

---

## 6. Правила версионирования floor и связь с аналитикой

1. **Floor задаётся в двух местах и синхронизируется CI:** `minSdkVersion` в Gradle (Android) и `truststore/policy.yaml` — каноническое хранилище floor-политики (список Huawei-конфигураций, пороги, тег AOSP). `certs.json` политику не дублирует, а ссылается (`policy_ref`). G3 сверяет `minSdk` ↔ `policy.yaml`; G6 читает `aosp_floor_tag` из `policy.yaml`.
2. **Поднятие floor** — продуктовое решение по аналитике долей ОС-версий (порог: суммарная доля ОС ниже кандидата-на-floor < 2% DAU на протяжении квартала). Поднятие floor автоматически открывает REM-1 для всех корней с `first_os.android ≤ новый floor` — TrustStore-менеджер заводит тикеты на квартальный аудит; G6 начнёт сигнализировать (FAIL или WARNING по Huawei-условию).
3. **Понижение floor** (например, возврат поддержки старых Huawei) — обязательный триггер пересмотра всех `removed`/архивных корней: если новая floor-ОС не содержит корень, он возвращается в бандл по сокращённому циклу ADD (§4.4; Security-ревью и Huawei-эмпирика выполняются заново).
4. **Аналитика долей** снимается с приложения: `os_version` (для Huawei — модель + продукт/версия, не только API level: EMUI/HarmonyOS отображаются в Android API, но стор может отличаться) × `app_version` × DAU. Еженедельный экспорт; порог `removal_share_threshold_pct` считается по этой таблице и используется в аналитическом пути §5.1(б).
5. **`aosp_floor_tag`** — последний тег floor-версии Android (для A13 — `android-13.0.0_r84`). Меняется вместе с floor; потребители — G6 и проверки §4.2.

---

## 7. CI/CD-гейты (`truststore_gate`)

Запускается на каждый PR и на nightly. Все гейты red = падение сборки, кроме явно отмеченного (warning). Перед гейтами выполняется `./gradlew copyExtraRoots` (генерация `res/raw/`).

| ID | Проверка | Что делает |
|---|---|---|
| **G1** | Lint PEM | Каждый `truststore/extra_roots/*.pem` парсится `openssl x509 -noout`: ровно один self-signed корневой сертификат (`subject == issuer`, basicConstraints CA:true), нормализованный PEM. |
| **G2** | Expiry | `not_after > now + 90 дней` для каждого `status != removed`. Истекающий (<90 дн) — fail; <180 дн — warning в PR. |
| **G3** | Sync-инварианты | (а) `minSdk` (Gradle) == `policy.yaml: min_supported_android.api_level`; (б) множество PEM в `truststore/extra_roots/` == множество записей `certs.json` со статусом `active|deprecated|removal_scheduled`; (в) множество `@raw/<id>`-ссылок в `network_security_config.xml` == тому же множеству; (г) после `copyExtraRoots`: содержимое `app/src/main/res/raw/*.pem` == `truststore/extra_roots/*.pem`; (д) все обязательные поля `certs.json` заполнены; `huawei_evidence` существует в `huawei_matrix.yaml`. |
| **G4** | Fingerprint match | `openssl x509 -fingerprint -sha256` каждого PEM == `sha256` в `certs.json`; `subject`, `not_before`, `not_after` тоже сверяются. |
| **G5** | Source-of-truth (nightly) | Скачивает `source_url` (DER/PEM) и сверяет fingerprint с `truststore/extra_roots/`. Ловит подмену корня оператором (ре-выпуск тем же subject). Fail в nightly → инцидент TrustStore-менеджеру. |
| **G6** | **Дубль-чек против AOSP-тега floor** | Для каждого PEM: old-style subject hash → ожидаемое имя `files/<hash>.0`; скрипт пробирует файл в теге `policy.yaml: aosp_floor_tag`. **404** = корень отсутствует на floor → OK. **200** = корень нативен на floor → два исхода: (i) Huawei-матрица `present_on_floor` для этого корня **или** `huawei_channel_supported: false` → **FAIL** «выполните REMOVE (§5)» — условия §5.1 закрыты; (ii) Huawei-матрица ещё `absent_on_floor` → **WARNING** + CI-джоба создаёт/поддерживает блокирующий тикет «REM-1 pending Huawei verification» (сборка зелёная; удаление заблокировано §5.1). **Любой другой HTTP-код / таймаут / DNS-ошибка** = FAIL «AOSP unverifiable» — никогда не трактуется как «отсутствует». Скрипт — ниже. |
| **G7** | Huawei-матрица | Для каждого корня со статусом `active|deprecated|removal_scheduled`: в `huawei_matrix.yaml` есть verdict и свежие (≤ `huawei_matrix_max_age_days`) проверки на **каждой** floor-конфигурации из `policy.yaml: min_supported_huawei`. `first_os.huawei: null` ⇒ матрица обязана подтверждать `absent_on_floor`; если матрица показывает `present_on_floor` при незаполненном `first_os.huawei` — warning «заполните поле и запустите REM-1». |
| **G8** | Структура NSC / статусы / review | В `network_security_config.xml` нет `src="user"` вне `<debug-overrides>` (fail); статус-переходы только `active → deprecated → removal_scheduled → removed` (fail); `review_date` не просрочена (warning). |

**Скрипт G6 — `truststore/scripts/check_duplicate_against_aosp.sh`:**

```bash
#!/usr/bin/env bash
# Гейт G6. Семантика gitiles: 200 = файл есть в теге, 404 = нет.
# Любой другой исход (429/5xx/DNS/timeout) = «AOSP unverifiable» = FAIL,
# никогда не трактуется как «отсутствует» (иначе G6 молча пропускал бы корни).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

FLOOR_TAG=$(yq '.min_supported_android.aosp_floor_tag' truststore/policy.yaml)
HUAWEI_SUPPORTED=$(yq '.huawei_channel_supported' truststore/policy.yaml)
BASE="https://android.googlesource.com/platform/system/ca-certificates"

probe() { # $1 = имя файла; печатает 200|404; при недоступности — exit 1
  local code
  for attempt in 1 2 3; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
      "$BASE/+/refs/tags/${FLOOR_TAG}/files/$1") || code="000"
    case "$code" in
      200|404) echo "$code"; return 0 ;;
      *) [ "$attempt" -lt 3 ] && sleep $((attempt * 10)) ;;   # backoff 10/20 c между попытками
    esac
  done
  echo "FAIL: AOSP unverifiable: files/$1, последний HTTP-код $code (3 попытки)" >&2
  exit 1
}

fail=0
for pem in truststore/extra_roots/*.pem; do
  id=$(basename "$pem" .pem)
  hash=$(openssl x509 -in "$pem" -noout -subject_hash_old)
  code=$(probe "${hash}.0")
  if [ "$code" != "200" ]; then
    echo "OK: $id отсутствует в ${FLOOR_TAG} (files/${hash}.0 → 404)"
    continue
  fi
  # Корень нативен на Android floor → судьба решается по Huawei-условию §5.1
  matrix_key=$(jq -r --arg id "$id" \
    '.certificates[] | select(.id==$id) | .huawei_evidence | split("#")[1]' truststore/certs.json)
  [ -n "$matrix_key" ] || { echo "FAIL: $id — пустой huawei_evidence в certs.json (G3)"; fail=1; continue; }
  verdict=$(yq ".roots.${matrix_key}.verdict" truststore/huawei_matrix.yaml)
  if [ "$verdict" = "present_on_floor" ] || [ "$HUAWEI_SUPPORTED" = "false" ]; then
    echo "FAIL: $id нативен в ${FLOOR_TAG} (files/${hash}.0), Huawei-условие закрыто" \
         "(verdict=${verdict}, канал=${HUAWEI_SUPPORTED}) — выполните REMOVE (§5)"
    fail=1
  else
    # WARNING: сборка остаётся зелёной; CI-джоба (gh issue create/find по метке
    # "rem-1-pending-huawei") создаёт/поддерживает блокирующий тикет удаления.
    echo "WARN: $id нативен в ${FLOOR_TAG}, но Huawei-матрица: ${verdict} —" \
         "удаление заблокировано (§5.1); тикет REM-1 pending Huawei verification"
  fi
done
[ $fail -eq 0 ] || exit 1
exit 0
```

Пример вывода сегодня (floor = Android 13, тег `android-13.0.0_r84`):

```
OK: globalsign_root_r46.pem отсутствует в android-13.0.0_r84 (files/1b0f7e5c.0 → 404)
OK: globalsign_root_e46.pem отсутствует в android-13.0.0_r84 (files/e7c037b4.0 → 404)
```

Когда floor станет Android 14 (`aosp_floor_tag: android-14.0.0_r*`), тот же скрипт по обоим файлам выдаст: FAIL (если Huawei-условие закрыто) или WARN + тикет (если Huawei ещё `absent_on_floor`) — см. §8.5.

Nightly-джоба T1 (watchdog): `git ls-remote --tags` репозитория + diff последних коммитов `platform/system/ca-certificates` против прошлого среза → новые корни = комментарий-тикет TrustStore-менеджеру (кандидаты ADD-0/ADD-1).

---

## 8. Worked example: GlobalSign R46 (+ E46)

### 8.1. Триггер

T1/T4: бэкенд объявляет ротацию цепочек на GlobalSign (корни R46/E46); одновременно watchdog фиксирует новые файлы в AOSP-сторе (для истории: батч, добавивший R46/E46, — коммит `20642a7`, 2023-02-21 «Copy set of certificates from internal to AOSP»; корни созданы оператором 2019-03-20; исходное добавление в AOSP для T было в коммите `c8d7f51` 2022-03-06 и было ревернуто — что само по себе иллюстрирует волатильность стора и необходимость watchdog'а).

### 8.2. Верификация отсутствия

- **Android:** `files/1b0f7e5c.0` (R46) и `files/e7c037b4.0` (E46) отсутствуют в последнем теге Android 13 `android-13.0.0_r84` (в теге 126 корней) — подтверждено пробами §4.2 (404). Присутствуют начиная с `android-14.0.0_r1` (в `android-14.0.0_r75` — 134 файла `files/*.0`). Вывод: `first_os.android = 14`; все устройства Android ≤ 13 (включая API 33 = Android 13) не имеют корней нативно.
- **Huawei:** QA-матрица: HarmonyOS 4.0 (device 0) и EMUI 15.0.0 (device 3) — обе floor-конфигурации из `policy.yaml`; проба TLS-соединения к тестовому хосту с цепочкой в R46/E46 → `Trust anchor for certification path not found`; conscrypt-дамп стора fingerprint'ов не содержит. `first_os.huawei = null`, verdict `absent_on_floor` (тикеты QA-1234/QA-1235). Отсутствие в Huawei 15.0.0 — user-reported, подтверждено эмпирически.
- **Решение ADD-1:** добавляем оба корня (E46 — тот же батч оператора и AOSP; серверная ротация может использовать EC-цепочки; добавляем пачкой, чтобы не делать два релиза).

### 8.3. Добавление

- PEM: официальные DER с `https://secure.globalsign.com/cacert/rootr46.crt` и `https://secure.globalsign.com/cacert/roote46.crt` → `openssl x509 -inform DER -outform PEM` → `truststore/extra_roots/globalsign_root_r46.pem`, `truststore/extra_roots/globalsign_root_e46.pem`. В `res/raw/` файлы сгенерирует `copyExtraRoots`.
- Security сверяет SHA256 (таблица ниже) с fingerprint официального DER — совпадает; и с PEM из AOSP-тега `android-14.0.0_r1` — совпадает (байты стора стабильны между `14.0.0_r1` и `main`).
- `certs.json`: две записи по §3.3 (`status: active`, `added_in_app_version: 24.7.0`, `review_date` на квартал).
- NSC (Вариант B): в `domain-config` наших доменов добавлены обе ссылки — `<certificates src="@raw/globalsign_root_r46"/>` и `<certificates src="@raw/globalsign_root_e46"/>` (наряду с `src="system"`); `base-config` не тронут.
- CI: G1–G4, G6–G8 зелёные (G6: оба корня отсутствуют в floor-теге A13 → 404 → OK; G3: PEM ↔ certs.json ↔ `@raw`-ссылки ↔ сгенерированный `res/raw` синхронны).
- Выпуск 24.7.0: staged 5% → 20% → 100%, TLS-метрики чистые.

Справочные данные корней (для PR и certs.json):

| | R46 | E46 |
|---|---|---|
| Subject | `/C=BE/O=GlobalSign nv-sa/CN=GlobalSign Root R46` | `/C=BE/O=GlobalSign nv-sa/CN=GlobalSign Root E46` |
| SHA256 | `4F:A3:12:6D:8D:3A:11:D1:C4:85:5A:4F:80:7C:BA:D6:CF:91:9D:3A:5A:88:B0:3B:EA:2C:63:72:D9:3C:40:C9` | `CB:B9:C4:4D:84:B8:04:3E:10:50:EA:31:A6:9F:51:49:55:D7:BF:D2:E2:C6:B4:93:01:01:9A:D6:1D:9F:50:58` |
| Validity | 2019-03-20 → **2046-03-20** | 2019-03-20 → 2046-03-20 |
| Key/Sig | RSA-4096, SHA-384 | ECDSA P-384, SHA-384 |
| AOSP file | `files/1b0f7e5c.0` | `files/e7c037b4.0` |
| PEM size (normalized) | ~1.9 KB | ~0.8 KB |
| first_os | android: 14, huawei: null (эмпирика) | android: 14, huawei: null |

### 8.4. Жизнь в бандле

Каждый квартальный аудит: floor всё ещё Android 13 (доля A≤13 в парке > 2%) → KEEP-1, `review_date` сдвигается. G6 каждую сборку подтверждает 404 в floor-теге A13.

### 8.5. Будущее удаление (сценарий, оба пути)

**Путь 1 (floor):** доля Android ≤ 13 падает < 2% → floor поднимается на Android 14 (`minSdk 34`, `aosp_floor_tag: android-14.0.0_r*`). Floor-релиз выходит; удаление корней **не** в нём (§5.3). С этого момента G6 находит оба корня в floor-теге:
- если Huawei-матрица ещё `absent_on_floor` → **WARNING + блокирующий тикет «REM-1 pending Huawei verification»**, сборка зелёная, корни остаются в бандле (переходное состояние §5.1);
- когда QA подтверждает нативную поставку R46/E46 во всех floor-конфигурациях Huawei (`present_on_floor`, `first_os.huawei` заполняется) или Huawei-канал исключается из матрицы — G6 переводит WARNING в **FAIL**: «выполните REMOVE».

**Путь 2 (аналитика):** floor не поднимается, но доля ОС < Android 14 с использованием цепочек в R46/E46 падает < 1% DAU → Android-условие закрыто по §5.1(б). G6 при этом остаётся зелёным (в floor-теге A13 корней по-прежнему нет); для активации удаления нужно лишь закрытие Huawei-условия (матрица/канал).

**Далее (оба пути):**
1. Тикет REM: `status: deprecated` → `removal_scheduled` (версия, скажем, 27.4.0).
2. Релиз 27.4.0: PEM удалены из `truststore/extra_roots/`, `<certificates>` убраны из NSC, `status: removed`; `res/raw/*.pem` вычищены таской `copyExtraRoots` (Sync) автоматически; staged rollout; 2–4 недели мониторинга `CertPathValidatorException` по (ОС × версия приложения) — чисто.
3. Когда доля приложения < 27.4.0 < 1% DAU — записи архивируются (`truststore/archive/` + git-история).

---

## 9. Риски и нюансы

| Риск/нюанс | Суть | Митигация |
|---|---|---|
| **Huawei — эмпирика** | Сторы Huawei не публикуются; различаются по регионам/моделям; обновления стора приходят с системными апдейтами, которые Huawei может не выкатывать на старые модели. | Матрица строится на фактическом топе парка (модель × продукт/версия × регион), floor-конфигурации перечислены явно в `policy.yaml`; свежесть проверок ≤180 дней (G7); Huawei-условие удаления блокирующее (§5.1); переходное состояние «Android закрыт, Huawei нет» не ломает сборку (G6 WARNING + тикет); при расширении каналов (Китай-регион) — отдельные конфигурации в матрице. |
| **Другие TLS-стеки** | NSC действует только для платформенного TLS (Conscrypt: `HttpsURLConnection`, OkHttp с дефолтным `SSLContext`/`TrustManager`, WebView). Собственные `X509TrustManager`, Cronet без конфига, нативные (BoringSSL/rustls) и сторонние рантаймы (Flutter) **не видят** `@raw`-корни. | Инвентаризация сетевых стеков при внедрении; для не-платформенных стеков — отдельная подача того же набора PEM (бандл читается из ресурсов/`certs.json` при инициализации стека) — вне NSC, но из того же source of truth. TLS-сценарий на девайс-матрице гоняется через **все** стеки приложения. |
| **WebView** | WebView уважает NSC (включая `domain-config`), но версии WebView различаются — тестировать явно. | QA-матрица включает WebView-сценарий на floor-устройствах Huawei. |
| **Пользовательские CA** | Включение `src="user"` в prod доверяет пользовательски установленным CA (MITM на управляемых/скомпрометированных устройствах). | Только `<debug-overrides>`; появление `src="user"` вне debug — fail G8 (структурная проверка XML). |
| **Расширение атакной поверхности** | Каждый extra-корень — ещё один CA, который может заверять хосты. В Варианте A — глобально (любой хост), в Варианте B — только перечисленные домены. | Вариант B — по умолчанию (§3.2): `base-config` — только `system`, extras — только в `domain-config` наших доменов; минимальный набор (дисциплина G6/KEEP-1); Security-аппрув на каждое изменение. |
| **Полнота списка доменов (Вариант B)** | Если бэкенд начнёт отдавать цепочки в новый корень с домена, не перечисленного в `domain-config`, extras не применятся — TLS-ошибки при живом бандле. | Чеклист §4.5 («список доменов актуален»); бэкенд обязан анонсировать новые домены (роль §2.2); метрики §10 разрезаны по домену/стеку. |
| **Expiry корней** | Корень может истечь, пока лежит в бандле (для R46/E46 — 2046, риска нет). | G2 (90/180 дней), G5 ловит ротацию оператора тем же subject. |
| **Размер APK** | PEM почти не сжимаются (DER — высокая энтропия). Пара R46+E46 ≈ 2.7 KB в APK. Несущественно, но аргумент держать набор минимальным. | G6 + KEEP-1; метрика размера в §10. |
| **Пиннинг** | Если приложение дополнительно использует certificate pinning — новый корень обязан попасть в pin-набор (SPKI) синхронно с серверной ротацией; иначе — ошибочная недоступность при живом бандле. | Pin-политика — отдельный документ, но изменение `certs.json` обязано триггерить ревью pin-конфига (чеклист §4.5). |
| **N-1 совместимость** | Старые версии приложения месяцами носят удалённые корни (безопасно) и не имеют новых (опасно). | Окно опережения: корень добавляем ≥ 1 квартал до серверной ротации (SLA T4); при удалении — staged rollout + мониторинг по версии приложения; полный выход из поддержки N-1 контролируется аналитикой (§5.2.5). |
| **Серверные цепочки** | Сервер обязан отдавать полную цепочку с промежуточными сертификатами (intermediates); корень в TLS-handshake не отправляется. | Согласовано с бэкендом (роль §2.2); тестовый хост матрицы отдаёт эталонную цепочку. |
| **AOSP-стор меняется батчами нерегулярно** | Пакетные обновления (2022-03 «for T», 2023-02-21, 2023-07-19 (NSS 3.91), 2024-02-14, 2024-03-26 (NSS 3.97), 2025-02-04 и т.п.) — watchdog обязан ловить коммиты в `main`, не только теги: до тега версии ОС корень уже «внутри». История R46/E46 (добавление в T, реверт, ре-добавление) это подтверждает. | Watchdog T1 по коммитам; решения ADD-0/ADD-1 отсекают лишнее. |
| **Недоступность AOSP в CI** | Сетевые сбои gitiles (429/5xx) не должны ни валить, ни — тем более — «пропускать» проверки молча. | G6: только 200/404 — валидные исходы; всё прочее = FAIL «AOSP unverifiable» с 3 попытками и backoff (гейт G6). |

---

## 10. Метрики

| Метрика | Определение | Цель |
|---|---|---|
| **Lead time ADD** | От первого триггера (T1/T2/T3 — анонс/появление корня; T4 — заявка бэкенда) до 100% staged rollout релиза с корнем. | ≤ 30 дней по T1–T3; ≤ 1 квартала по T4 (жёсткий SLA). |
| **Время реакции на новые корни** | От появления корня в AOSP `main` (watchdog) до заведённого тикета-решения ADD-0/ADD-1. | ≤ 5 рабочих дней. |
| **Время реакции на TLS-инциденты** | От всплеска `CertPathValidatorException` по ОС-версии до заведённого ADD-тикета (резервный канал T5). | ≤ 1 рабочего дня; сам всплеск на поддерживаемом парке — повод для пост-мортема. |
| **Rate TLS-ошибок** | Доля `CertPathValidatorException`/`Trust anchor...` из всех TLS-сессий, разрез: ОС-версия × продукт/версия (Huawei) × версия приложения × домен. Базовые линии по floor-конфигурациям. | < 0.1% на каждой поддерживаемой конфигурации; алерт при x3 за сутки. |
| **Число активных anchors** | Количество записей `certs.json` со статусом `active|deprecated|removal_scheduled`. | Минимизация; каждый anchor имеет свежий `review_date`; ноль «застрявших» WARNING-тикетов G6 старше квартала. |
| **Время жизни anchor** | От релиза с добавлением до релиза с удалением. | Тренд к сокращению; удаление срабатывает в первый же квартал после закрытия §5.1 (G6/аудит наводят автоматически). |
| **Свежесть Huawei-матрицы** | Доля floor-конфигураций с проверками ≤ `huawei_matrix_max_age_days`. | 100%. |
| **Покрытие TLS-стеков** | Доля сетевых стеков приложения, для которых extra-корни реально применяются и покрыты QA-сценарием. | 100% инвентаризированных стеков. |
| **Размер бандла** | Суммарный размер `truststore/extra_roots/*.pem` (≈ размер в APK). | Трекается в релиз-репортах; аномалии — на ревью. |

Дашборд метрик строится на: релизной телеметрии приложения (TLS-ошибки), аналитике долей ОС (§6), CI-статусах гейтов и истории `certs.json` (все события add/keep/remove логируются PR-мержами).

---

## Приложение A. Сводная карта процесса

```
      [T1 AOSP] [T2 Mozilla/NSS/CCADB] [T3 CA-операторы] [T4 бэкенд] [T6 аудит] [T5 телеметрия]
                                 │
                                 ▼
                   Решение: ADD-0 / ADD-1 / ADD-2 (§4.3)
                                 │ ADD-1
                                 ▼
      Верификация: AOSP-тег floor (404?) + Huawei-матрица (absent_on_floor на всех floor-конфигах?)
                                 │ оба подтверждены
                                 ▼
      certs.json запись + PEM в truststore/extra_roots/ + @raw в NSC → PR
                                 │
                                 ▼
                Security review (fingerprint по первоисточнику!)
                                 │
                                 ▼
      CI: G1–G4, G6–G8 (+ copyExtraRoots → G3) → merge → staged rollout
                                 │
                ......(квартальные аудиты: KEEP-1 / пересмотр)......
                                 │
                                 ▼
      REM-1 — условия выхода §5.1, ДВА пути закрытия Android-условия:
      ┌─ Путь 1 (floor): minSdk поднят ≥ first_os.android (напр. A14)
      │    → корень появился в AOSP floor-теге, G6 даёт:
      │        • Huawei present_on_floor / канал вне матрицы → FAIL «run REMOVE»
      │        • Huawei absent_on_floor → WARNING + блокирующий тикет
      │          «REM-1 pending Huawei verification» (сборка зелёная, ждём эмпирики)
      └─ Путь 2 (аналитика; floor НЕ поднят): доля ОС < first_os.android < 1% DAU
           → G6 зелёный (в floor-теге корня по-прежнему нет), решение по §5.1(б)
                 │ оба условия §5.1 закрыты (Android-путь И Huawei-условие)
                 ▼
      deprecated → removal_scheduled → отдельный релиз удаления (copyExtraRoots
      вычищает res/raw) → staged rollout → 2–4 нед. мониторинг
      CertPathValidatorException (ОС × версия приложения)
                 │ чисто
                 ▼
      N-1 окно закрыто (<1% DAU на старых версиях приложения) → архив записи
```

## Приложение B. Минимальный набор команд

```bash
# Проверка присутствия корня в AOSP-теге:
# 404 = отсутствует, 200 = присутствует, прочее = «не верифицировано» (не «отсутствует»!)
curl -s -o /dev/null -w "%{http_code}\n" --max-time 30 \
  "https://android.googlesource.com/platform/system/ca-certificates/+/refs/tags/android-13.0.0_r84/files/1b0f7e5c.0"

# Нормализация PEM + fingerprint
openssl x509 -inform DER -in rootr46.crt -outform PEM -out globalsign_root_r46.pem
openssl x509 -in globalsign_root_r46.pem -noout -subject -dates -fingerprint -sha256

# Ожидаемое имя AOSP-файла (= old-style subject hash)
openssl x509 -in globalsign_root_r46.pem -noout -subject_hash_old   # → 1b0f7e5c

# Загрузка PEM прямо из AOSP-тега (gitiles отдаёт base64; чистим переносы) и сверка fingerprint
curl -s "https://android.googlesource.com/platform/system/ca-certificates/+/refs/tags/android-14.0.0_r1/files/1b0f7e5c.0?format=TEXT" \
  | tr -d '\n ' | base64 -d | openssl x509 -noout -fingerprint -sha256

# Diff стора между версиями ОС (неглубокий клон)
git clone --filter=blob:none --no-checkout \
  https://android.googlesource.com/platform/system/ca-certificates
cd ca-certificates && git diff --stat android-13.0.0_r84 android-14.0.0_r1 -- files
```

---

*Конец документа. Данный текст — черновик v1.1 (учтены замечания ревью: каноническая схема с генерацией res/raw, двухисходный G6, устойчивость G6 к недоступности AOSP, явный список Huawei floor-конфигураций, единое место floor-политики в policy.yaml, варианты A/B NSC, два пути удаления в карте процесса). Фактические значения (теги, fingerprints, доли ОС) подлежат актуализации на момент внедрения.*
</task_result>
</task>