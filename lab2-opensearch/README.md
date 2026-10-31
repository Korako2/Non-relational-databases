
# Лабораторная работа №2. Эксплуатация OpenSearch

## Часть 1. Развертывание

В первой части нужно было развернуть кластер OpenSearch с архитектурой Hot–Warm, настроить TLS для Transport и REST API и запустить OpenSearch Dashboards. Все делал через **Ansible, без Docker**. В итоге кластер работает на трех виртуальных машинах Ubuntu Server в Яндекс Облаке, версия OpenSearch и Dashboards **3.9.0**.

### Развертывание кластера

Кластер `opensearch-lab` состоит из трех узлов:

| Узел | Внутренний IP | Роли | Назначение |
|---|---|---|---|
| `os-hot` | `10.128.0.22` | `data`, `cluster_manager`, `ingest` | Актуальные данные, Hot |
| `os-warm` | `10.130.0.17` | `data`, `cluster_manager` | Менее актуальные данные, Warm |
| `os-manager` | `10.131.0.30` | `cluster_manager` | Управление кластером и Dashboards |

Для установки я адаптировал официальные Ansible-роли OpenSearch под свой проект (`roles/opensearch` и `roles/dashboards`). Остальную настройку вынес в отдельные роли: `lab_hot_warm`, `lab_dashboards_tls` и `lab_verify`. Адреса для SSH и внутреннего взаимодействия узлов задаются в `host_vars` через переменные окружения, поэтому после переезда в облако не пришлось переписывать всю конфигурацию. В `group_vars/all/main.yml` находятся общие параметры кластера.

Сначала проверяется inventory и Java 21+ на управляющем компьютере, она нужна для генерации сертификатов. Затем последовательно запускаются playbook:

```bash
ansible-playbook playbooks/00-check-configuration.yml
ansible-playbook playbooks/02-opensearch.yml -b --ask-become-pass
ansible-playbook playbooks/03-dashboards.yml -b --ask-become-pass
ansible-playbook playbooks/04-hot-warm.yml -b --ask-become-pass
ansible-playbook playbooks/05-dashboards-tls.yml -b --ask-become-pass
ansible-playbook playbooks/06-verify.yml -b --ask-become-pass
```

`02-opensearch.yml` устанавливает OpenSearch из архива, создает пользователя и systemd-сервис, настраивает кластер и Security Plugin. Во время установки генерируется собственный корневой CA и сертификаты узлов. Они используются для защищенного Transport-соединения на порту **9300** и HTTPS REST API на порту **9200**. Сервисы включены в автозапуск через systemd.

В `04-hot-warm.yml` узлам с данными добавляются атрибуты `node.attr.temp: hot` и `node.attr.temp: warm`. При изменении конфигурации узлы перезапускаются **по одному**, чтобы не нарушать работу кластера. Пока это именно разметка узлов по уровням хранения; правила переноса индексов будут настраиваться в следующих частях работы.

![Развертывание OpenSearch через Ansible](images/01-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/02-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/03-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/04-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/05-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/06-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/07-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/08-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/09-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/10-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/11-opensearch-playbooks.png)
![Развертывание OpenSearch через Ansible](images/12-opensearch-playbooks.png)

### Проблемы при настройке

Больше всего времени ушло на попытку собрать кластер локально. Сначала `os-hot` работал в VirtualBox на ноутбуке с Linux, а `os-warm` и `os-manager` в VMware на втором ноутбуке с Windows. При этом виртуалки нормально пинговались, подключались по SSH, порты были доступны, а TLS-проверки проходили. Но именно **кластер OpenSearch не собирался**: `os-hot` видел только себя, а при попытке присоединиться к остальным узлам возникали ошибки Transport handshake и `Connection reset`.

Из-за этого зависала команда `securityadmin.sh`, которая ждала готовности кластера для загрузки настроек безопасности. За время отладки пришлось исправлять IP и `/etc/hosts`, проверять сертификаты, логи Java и OpenSearch и даже сравнивать сетевые пакеты через `tcpdump`. Однозначную причину сброса соединений между двумя ноутбуками так и не удалось установить.

Параллельно выяснилось, что для нормальной работы каждой ВМ желательно выделить около **4 ГБ ОЗУ**, а один ноутбук все три машины одновременно не тянул. Поэтому я решил отказаться от локального варианта и **перенести кластер в Яндекс Облако**. После настройки облачных IP-адресов и SSH все три узла смогли объединиться в один кластер.

### OpenSearch Dashboards и HTTPS

Dashboards установлен на `os-manager` и работает на порту **5601**. В `05-dashboards-tls.yml` для него создается отдельный серверный сертификат, подписанный тем же CA, включается `server.ssl.enabled: true`, проверка сертификата OpenSearch (`opensearch.ssl.verificationMode: full`) и защищенные cookies.

Так как на ВМ нет графического интерфейса, страницу Dashboards я открыл в браузере своего ноутбука через **SSH-туннель** на локальный порт `15601`. Сначала браузер ругался на сертификат: он не доверял учебному CA и я открывал сайт через `localhost`. В итоге добавил публичный `root-ca.pem` в доверенные и настроил локальное имя `os-manager.lab.internal`. После этого Dashboards открылся по HTTPS без ошибки сертификата.

![OpenSearch Dashboards по HTTPS](images/13-opensearch-dashboards.png)

### Проверка результата

Состав кластера проверял через `/_cat/nodes?v`: в ответе видны **все три узла**.

![Список узлов OpenSearch](images/14-opensearch-nodes.png)

Через `/_cat/nodeattrs?v` проверил атрибуты: у `os-hot` — `temp: hot`, у `os-warm` — `temp: warm`.

![Атрибуты Hot и Warm](images/15-opensearch-nodeattrs.png)

Последний playbook `06-verify.yml` проверяет состояние кластера по HTTPS с проверкой CA, число узлов, атрибуты Hot/Warm и доступность Dashboards. Он завершился без ошибок и показал:

```text
cluster: opensearch-lab
status: green
total_nodes: 3
data_nodes: 2
dashboards_http_status: 302
```

Код `302` здесь нормальный: Dashboards перенаправляет на страницу авторизации. В итоге **все требования первой части выполнены**.

![Итоговая проверка playbook 06-verify](images/16-opensearch-verify.png)

## Часть 2. Ролевая модель

Во второй части лабораторной работы нужно было создать три роли с разными правами доступа и трех пользователей, которым эти роли будут назначены. Все настраивалось через Ansible с использованием **OpenSearch Security REST API**, без переустановки или перезапуска кластера.

Для этого я создал отдельную роль `roles/rbac` и два playbook: `07-rbac.yml` для настройки пользователей и ролей и `08-rbac-verify.yml` для проверки их прав.

### Создание ролей

Были подготовлены три роли:

| Роль | Назначение |
|---|---|
| `logs_writer` | Запись документов только в data stream `logs` |
| `logs_reader` | Чтение индексов, соответствующих шаблону `logs*` |
| `cluster_monitor` | Получение состояния и метрик кластера и его узлов |

Для `logs_writer` используются разрешения `indices:data/write/index` и `indices:data/write/bulk*`. Роль предназначена для добавления документов в поток логов, без прав на удаление индексов или изменение настроек кластера.

Роль `logs_reader` получает группу разрешений `read` для индексов `logs*`, а `cluster_monitor` — только необходимые права `cluster:monitor/health`, `cluster:monitor/stats` и `cluster:monitor/nodes/stats`.

Роли создаются через запросы `PUT` к Security REST API:

```text
/_plugins/_security/api/roles/<role_name>
```

Для подключения Ansible использует существующие сертификаты администратора `admin.pem`, `admin.key` и корневой `root-ca.pem`. Таким образом, управление безопасностью выполняется через HTTPS с проверкой сертификатов.

### Создание пользователей

Для каждой роли был предусмотрен отдельный пользователь:

| Пользователь | Роль |
|---|---|
| `logs_writer_user` | `logs_writer` |
| `logs_reader_user` | `logs_reader` |
| `monitor_user` | `cluster_monitor` |

Пользователи создаются через `PUT /_plugins/_security/api/internalusers/<username>`. При создании каждому сразу назначается соответствующая роль через `opendistro_security_roles`.

Пароли не хранятся в открытом виде в Ansible-ролях. Для них используется **Ansible Vault**, а в задачах создания пользователей установлен `no_log: true`, чтобы пароли не попадали в вывод playbook.

Настройка запускается командой:

```bash
ansible-playbook playbooks/07-rbac.yml \
  -b --ask-become-pass --ask-vault-pass
```

При первом запуске роли создались успешно, но при создании пользователей возникла проблема: два запроса вернули ошибку `HTTP 404`, а один завершился успешно. Из-за `no_log: true` подробности ошибки были скрыты. Для диагностики предусмотрен отдельный вывод HTTP-статуса и сообщения API без отображения паролей.

![Настройка ролей и пользователей через Ansible](images/16-rbac-setup.png)

### Проверка разграничения доступа

Для проверки был подготовлен отдельный playbook:

```bash
ansible-playbook playbooks/08-rbac-verify.yml \
  -b --ask-become-pass --ask-vault-pass
```

Он использует API `/_plugins/_security/authinfo`, чтобы проверить аутентификацию пользователей и назначенные им роли.

Дополнительно предусмотрены запросы к `/_cluster/health`, `/_cluster/stats` и `/_nodes/stats`. Пользователь `monitor_user` должен успешно получать эти метрики, а пользователям чтения и записи доступ к статистике кластера должен быть запрещен с кодом `403 Forbidden`.

![Проверка пользователей и назначенных ролей](images/17-rbac-users.png)

Таким образом, во второй части была подготовлена ролевая модель OpenSearch и автоматизированные сценарии ее настройки и проверки. Основные разрешения разделены между записью логов, чтением и мониторингом, а пароли вынесены в Ansible Vault. На момент последнего запуска оставалось разобраться с ошибкой создания двух пользователей и завершить проверку их доступа.

## Часть 3. Управление индексами

В третьей части лабораторной работы нужно было настроить сбор логов Nginx в формате JSON, их отправку в OpenSearch и автоматическое управление индексами. Все снова делал через Ansible, без Docker. Для этого подготовил отдельные роли `lab_nginx_json`, `lab_fluentbit` и `lab_logs_ism`.

### Nginx и сбор логов

На узле `os-hot` развернул Nginx с простой HTML-страницей, которая доступна на локальном порту `8080`. Для access log настроил JSON-формат через `log_format` с параметром `escape=json`.

Каждая запись содержит время запроса (`@timestamp`), IP клиента, HTTP-метод, URL, код ответа, размер ответа и время обработки. Логи сохраняются в файл `/var/log/nginx/opensearch-access.json`.

Для проверки достаточно несколько раз обратиться к странице и посмотреть содержимое файла:

`sudo tail -n 5 /var/log/nginx/opensearch-access.json | jq .`

![Страница Nginx и JSON-логи](images/18-nginx-json.png)
![Страница Nginx и JSON-логи](images/19-nginx-json.png)


### Отправка логов через Fluent Bit

Для передачи логов выбрал **Fluent Bit**. Он достаточно легкий и подходит для чтения файлов с последующей отправкой записей в OpenSearch.

Fluent Bit использует входной плагин `tail`, который отслеживает JSON-лог Nginx. Положение чтения сохраняется в отдельной базе, чтобы после перезапуска не перечитывать весь файл заново.

Для отправки используется плагин `opensearch` с операцией `create`. Документы направляются в data stream `logs` по HTTPS с проверкой TLS-сертификата.

Подключение выполняется от пользователя `logs_writer_user`, созданного во второй части лабораторной. Таким образом, Fluent Bit не использует административные права. Пароль пользователя берется из Ansible Vault.

![Работа Fluent Bit и отправка логов](images/20-fluent-bit.png)

### Шаблон индекса и политика хранения

Для логов подготовил index template `logs-nginx-template`, который применяется к data stream `logs`.

В шаблоне указаны типы основных полей, включая `@timestamp`, `status`, `remote_addr` и `request_time`. Также настроено размещение новых индексов на Hot-узле через атрибут `temp: hot`.

Для управления хранением создал ISM-политику `logs-retention-10m` со следующими условиями:

| Параметр | Значение |
|---|---|
| Rollover по размеру | 1 МБ |
| Rollover по времени | 1 минута |
| Условие rollover | Любое из двух |
| Время хранения | 10 минут |
| Размещение новых индексов | Hot |
| Размещение после rollover | Warm |

После достижения 1 МБ или возраста 1 минута ISM должен выполнить rollover, создав новый backing index для записи логов. Предыдущий индекс переходит на Warm-узел, а при достижении возраста 10 минут подлежит удалению.

Для лабораторной уменьшил интервал проверки ISM до одной минуты и отключил случайную задержку. При этом удаление и rollover происходят не строго в указанную секунду, а при очередном выполнении фоновых задач ISM.

![Шаблон индекса и ISM-политика](images/21-ism-policy.png)

### Запуск и проверка

Развертывание третьей части вынесено в отдельный playbook:

`ansible-playbook playbooks/09-logs.yml -b --ask-become-pass --ask-vault-pass`

![Развертывание](images/22-logs-1.png)
![Развертывание](images/22-logs-2.png)
![Развертывание](images/22-logs-3.png)
![Развертывание](images/22-logs-4.png)
![Развертывание](images/22-logs-5.png)
![Развертывание](images/22-logs-6.png)


Он последовательно настраивает политику и data stream, устанавливает Nginx и запускает Fluent Bit.

Для проверки подготовил `10-logs-verify.yml`. Он генерирует HTTP-запросы к Nginx, проверяет формат JSON-лога, наличие документов в OpenSearch и параметры ISM-политики.

Дополнительно через OpenSearch REST API можно посмотреть документы в `logs`, поколения data stream и состояние backing indices с помощью `/_plugins/_ism/explain/.ds-logs-*`.

![Проверка документов в OpenSearch](images/23-logs-verify-1.png)
![Проверка документов в OpenSearch](images/23-logs-verify-2.png)
![Проверка документов в OpenSearch](images/23-logs-verify-3.png)

В итоге в третьей части подготовил полноценную цепочку сбора логов: Nginx -> Fluent Bit ->  OpenSearch. Заодно разобрался, чем data stream отличается от обычного индекса, как работает rollover и зачем нужны политики ISM. Самым интересным оказалось автоматическое управление жизненным циклом индексов: вместо ручного создания и удаления все можно настроить одной политикой.