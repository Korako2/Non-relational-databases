# Лабораторная работа №1. Эксплуатация MongoDB

## Часть 1. Базовая настройка

В первой части лабораторной работы требовалось развернуть MongoDB на виртуальной машине, настроить автоматический запуск сервиса, управление его состоянием и проверку доступности. Все действия выполнялись с помощью Ansible.

Сначала была проверена возможность подключения Ansible к серверу:
``` bash
ansible mongodb -m ansible.builtin.ping
```
В результате сервер успешно ответил `pong`.

![Проверка подключения Ansible](images/01-ansible-ping.png)

Для подключения к виртуальной машине параметры сервера не указывались напрямую в `inventory`. Они передавались через переменные окружения и считывались Ansible с помощью `lookup('ansible.builtin.env', ...)`:

```yaml
ansible_host: "{{ lookup('ansible.builtin.env', 'SERVER_IP') }}"
ansible_user: "{{ lookup('ansible.builtin.env', 'SERVER_USER') }}"
ansible_ssh_private_key_file: "{{ lookup('ansible.builtin.env', 'SSH_KEY') | default('~/.ssh/id_ed25519', true) }}"
```

Таким образом, IP-адрес сервера, SSH-пользователь и путь к приватному ключу можно менять без редактирования самого inventory-файла. Если переменная `SSH_KEY` не задана, по умолчанию используется ключ `~/.ssh/id_ed25519`. Перед запуском Ansible достаточно экспортировать необходимые значения в окружение, например `SERVER_IP` и `SERVER_USER`.

Для установки MongoDB был создан playbook `install.yml`. Он подключает официальный репозиторий MongoDB, устанавливает необходимые пакеты, формирует `/etc/mongod.conf` из Jinja2-шаблона и запускает сервис `mongod`.

```bash
ansible-playbook playbooks/install.yml
```

![Установка MongoDB](images/02-install-playbook_1.png)

![Установка MongoDB](images/02-install-playbook_2.png)

MongoDB была настроена на порт `27017` и адрес `127.0.0.1`, поэтому на данном этапе база доступна только локально с виртуальной машины.

Автоматический запуск реализован через:

```yaml
ansible.builtin.systemd_service:
  name: mongod
  enabled: true
  state: started
```

Таким образом, MongoDB запускается автоматически после перезагрузки сервера.

Для управления сервисом был создан отдельный playbook `service.yml`. Одним playbook можно запустить, остановить или перезапустить MongoDB:

```bash
ansible-playbook playbooks/service.yml -e mongodb_service_state=stopped
ansible-playbook playbooks/service.yml -e mongodb_service_state=started
ansible-playbook playbooks/service.yml -e mongodb_service_state=restarted
```

![Управление сервисом MongoDB](images/03-service_1.png)
![Управление сервисом MongoDB](images/03-service_2.png)

Также был реализован отдельный health-check. Он подключается к MongoDB через `mongosh` и выполняет команду:

```javascript
db.adminCommand({ ping: 1 })
```

```bash
ansible-playbook playbooks/healthcheck.yml
```

При работающей MongoDB проверка завершается успешно:

![Успешный health-check](images/04-healthcheck.png)

Дополнительно я остановил MongoDB и повторно запустил health-check. В этом случае проверка корректно определила, что сервер недоступен.

![Health-check остановленной MongoDB](images/04-healthcheck-failed.png)

## Часть 2. Управление ролевой моделью

Во второй части лабораторной работы требовалось настроить пользователей и собственные роли MongoDB, реализовать назначение и отзыв ролей, изменение набора разрешений, доступ только к отдельной коллекции, а также удаление пользователя и роли.

Для работы использовались две учебные базы:

```yaml
mongodb_university_db: "education"
mongodb_reports_db: "reports"
```

Также была включена авторизация MongoDB:

```yaml
security:
  authorization: enabled
```

Пароли пользователей не хранились в открытом виде в playbook. Для них использовался Ansible Vault:

```bash
ansible-vault edit group_vars/mongodb/vault.yml
```

Например, в зашифрованном файле хранятся пароли администратора и учебных пользователей.

Для работы модулей `community.mongodb` потребовался PyMongo версии 4+. Так как системный пакет Ubuntu 22.04 содержал более старую версию PyMongo, для Ansible было создано отдельное Python-окружение:

```yaml
mongodb_ansible_venv: "/opt/ansible-mongodb"
mongodb_ansible_python: "/opt/ansible-mongodb/bin/python"
```

Подготовка RBAC выполнялась отдельным playbook:

```bash
ansible-playbook playbooks/rbac_setup.yml --ask-vault-pass
```

Он устанавливает необходимые Python-зависимости, включает работу с PyMongo 4 и создает административного пользователя `lab_admin`.

![Подготовка MongoDB RBAC и PyMongo](images/05-rbac-setup.png)

После этого для демонстрации всех операций второй части использовался отдельный playbook:

```bash
ansible-playbook playbooks/rbac_demo.yml --ask-vault-pass
```

В начале сценария создавались четыре собственные роли:

```text
educationReader
educationEditor
reportsReader
studentsReader
```

`educationReader` позволяет читать все коллекции базы `education`, а первоначальная версия `educationEditor` разрешает чтение и добавление документов. Роль `reportsReader` предназначена для чтения базы `reports`.

Отдельная роль `studentsReader` была создана для демонстрации ограничения доступа только одной коллекцией:

```yaml
privileges:
  - resource:
      db: "{{ mongodb_university_db }}"
      collection: "students"
    actions:
      - find
```

Таким образом, пользователь с этой ролью может читать `education.students`, но не получает права на остальные коллекции базы `education`.

Также были созданы пользователи:

```text
reader_user   → educationReader
editor_user   → educationEditor
students_user → studentsReader
```

![Создание собственных ролей и пользователей](images/06-rbac-create_1.png)
![Создание собственных ролей и пользователей](images/06-rbac-create_2.png)

Для проверки ограничения по коллекции были подготовлены тестовые данные в коллекциях:

```text
education.students
education.teachers
education.courses
```

После этого playbook проверил доступ пользователя `students_user`.

Ожидаемый результат:

```text
students_user CAN read education.students
students_user CANNOT read education.teachers
```

![Проверка доступа только к коллекции students](images/07-collection-access.png)

Далее была продемонстрирована выдача дополнительной роли. Пользователю `reader_user`, который изначально имел только `educationReader`, была дополнительно назначена роль `reportsReader`.

После назначения доступ к `reports.monthly_reports` успешно прошел проверку.

```text
reader_user
├── educationReader
└── reportsReader
```

![Назначение дополнительной роли](images/08-role-grant.png)

После этого набор разрешений роли `educationEditor` был изменен.

Изначально роль разрешала:

```text
find
insert
```

После изменения:

```text
find
insert
update
remove
```

Таким образом был выполнен пункт задания по изменению набора разрешенных операций уже существующей роли.

Далее роль `reportsReader` была отозвана у `reader_user`. После этого повторная проверка доступа к `reports.monthly_reports` завершилась ожидаемым отказом:

```text
reader_user CANNOT read reports.monthly_reports
```

![Изменение роли и отзыв reportsReader](images/09-role-modify-revoke.png)

В конце демонстрационного сценария пользователь `editor_user` и роль `educationEditor` были удалены:

```text
Delete editor_user
Delete educationEditor
```

Playbook успешно завершил весь сценарий создания, изменения и удаления элементов ролевой модели.

![Удаление пользователя и роли и итоговый PLAY RECAP](images/10-rbac-delete-result.png)

Таким образом, во второй части лабораторной работы были реализованы все требуемые операции с ролевой моделью MongoDB. При этом отдельные операции были вынесены в параметризованные Ansible task-файлы, поэтому одна и та же логика может использоваться для разных пользователей и ролей без копирования одинакового YAML-кода.

## Часть 3. Резервное копирование и восстановление

В третьей части лабораторной работы требовалось реализовать резервное копирование одной и всех учебных баз, хранение нескольких копий без перезаписи предыдущих, а также восстановление удаленной коллекции.

В качестве учебных баз используются уже созданные ранее:

```yaml
mongodb_lab_databases:
  - "{{ mongodb_university_db }}"
  - "{{ mongodb_reports_db }}"
```

То есть резервному копированию подлежат базы `education` и `reports`.

Для работы с резервными копиями была создана отдельная Ansible-роль `mongodb_backup`. В ней устанавливаются стандартные MongoDB Database Tools, содержащие утилиты `mongodump` и `mongorestore`.

Также создается отдельный технический пользователь:

```text
backup_user
├── backup
└── restore
```

Для него используются встроенные роли MongoDB `backup` и `restore`. Таким образом, резервное копирование не выполняется от административного пользователя `lab_admin`.

Пароль `backup_user`, как и остальные пароли в проекте, хранится в Ansible Vault. Для `mongodump` и `mongorestore` он передается через защищенный конфигурационный файл:

```text
/etc/mongodb-backup-tools.yml
```

Файл создается с правами `0600`, поэтому доступ к нему имеет только `root`.

Перед выполнением резервного копирования окружение подготавливается отдельным playbook:

```bash
ansible-playbook playbooks/backup_setup.yml --ask-vault-pass
```

Он устанавливает MongoDB Database Tools, создает `backup_user`, необходимые каталоги и проверяет доступность `mongodump`.

![Подготовка окружения резервного копирования](images/11-backup-setup_1.png)

![Подготовка окружения резервного копирования](images/11-backup-setup_2.png)

Резервные копии сохраняются в каталогах:

```text
/var/backups/mongodb/
├── single/
├── all/
└── restore-demo/
```

### Резервная копия одной базы

Для копирования одной учебной базы используется `backup_one.yml`:

```bash
ansible-playbook playbooks/backup_one.yml --ask-vault-pass
```

По умолчанию создается резервная копия базы `education`.

Внутри роли выполняется `mongodump` с использованием `--archive` и `--gzip`, поэтому результат сохраняется одним сжатым файлом.
После создания Ansible дополнительно проверяет существование файла и его ненулевой размер.

![Создание резервной копии базы education](images/12-backup-one.png)

При необходимости тот же playbook можно использовать для другой учебной базы:

```bash
ansible-playbook playbooks/backup_one.yml \
  --ask-vault-pass \
  -e mongodb_backup_database=reports
```

То есть playbook не привязан жестко к одной базе.

### Хранение нескольких резервных копий

Чтобы новая копия не перезаписывала предыдущую, в имя каждого архива добавляется текущее время:

```yaml
mongodb_backup_file: >-
  {{ mongodb_backup_dir }}/{{ mongodb_backup_database }}_{{ mongodb_backup_timestamp_command.stdout }}.archive.gz
```

Таким образом, предыдущие резервные копии сохраняются.

Для проверки я несколько раз запустил `backup_one.yml`, после чего вывел содержимое каталога резервных копий.

```bash
ansible mongodb -b --ask-vault-pass \
  -m ansible.builtin.command \
  -a "ls -lh /var/backups/mongodb/single"
```

![Несколько сохраненных резервных копий](images/13-backup-multiple.png)

### Резервное копирование всех учебных баз

Для создания копий всех учебных баз используется:

```bash
ansible-playbook playbooks/backup_all.yml --ask-vault-pass
```

Playbook перебирает список:

```yaml
mongodb_lab_databases:
  - education
  - reports
```

и для каждой базы вызывает одну и ту же параметризованную задачу резервного копирования.

В результате в `/var/backups/mongodb/all` создаются архивы обеих баз:

```text
education_<timestamp>.archive.gz
reports_<timestamp>.archive.gz
```

Таким образом, для одной базы и для нескольких баз используется одна и та же логика `backup_one.yml`, а `backup_all.yml` только запускает ее в цикле.

![Резервное копирование всех учебных баз](images/14-backup-all_1.png)

![Резервное копирование всех учебных баз](images/14-backup-all_2.png)

### Восстановление удаленной коллекции

Для демонстрации восстановления был создан отдельный playbook:

```bash
ansible-playbook playbooks/restore_demo.yml --ask-vault-pass
```

В качестве тестовой коллекции используется:

```text
education.students
```

Перед удалением в коллекцию добавляется специальный документ:

```text
_id: "restore-demo"
name: "Restore Demo Student"
course: 4
```

После этого создается резервная копия базы, а коллекция `students` удаляется командой `drop()`.

![Создание копии и удаление коллекции students](images/15-restore-drop_1.png)
![Создание копии и удаление коллекции students](images/15-restore-drop_2.png)

Для восстановления используется `mongorestore`. При этом восстанавливается не вся база `education`, а только необходимая коллекция:

```text
--nsInclude=education.students
```

После восстановления playbook проверяет сразу два условия:

- коллекция `students` снова существует;
- документ с `_id: "restore-demo"` снова присутствует.

При успешной проверке выводится сообщение:

```text
Collection education.students was successfully restored from ...
```

![Успешное восстановление коллекции students](images/16-restore-success.png)

Таким образом, в третьей части были реализованы резервное копирование отдельной базы, копирование всех учебных баз, хранение нескольких независимых копий и восстановление конкретной удаленной коллекции. Все операции выполняются через Ansible, а общая логика резервного копирования вынесена в переиспользуемые task-файлы роли `mongodb_backup`.

## Часть 4. Мониторинг

В четвертой части лабораторной работы требовалось настроить сбор метрик MongoDB, вывести их на дашборд и проверить, как показатели меняются при создании нагрузки. Как и в предыдущих частях, настройка выполнялась через Ansible, без Docker.

Для мониторинга использовалась связка **Percona MongoDB Exporter -> Prometheus -> Grafana**. Exporter получает статистику из MongoDB и публикует ее по HTTP на порту `9216`, Prometheus собирает метрики каждые 5 секунд и сохраняет их, а Grafana отображает значения на графиках. Для подключения Exporter к MongoDB был создан отдельный пользователь `pmm` с необходимыми правами мониторинга. Пароль хранится в Ansible Vault. В конфигурации Exporter также включен `--compatible-mode`, чтобы использовать имена метрик, указанные в дашборде.

Установка и настройка компонентов выполняются playbook:

```bash
ansible-playbook playbooks/monitoring_setup.yml --ask-vault-pass
```

Он настраивает MongoDB Exporter, Prometheus и Grafana, регистрирует необходимые systemd-сервисы и автоматически добавляет источник данных Prometheus и готовый дашборд в Grafana.
`
![Настройка MongoDB Exporter, Prometheus и Grafana](images/17-monitoring-setup-1.png)
![Настройка MongoDB Exporter, Prometheus и Grafana](images/17-monitoring-setup-2.png)
![Настройка MongoDB Exporter, Prometheus и Grafana](images/17-monitoring-setup-3.png)
![Настройка MongoDB Exporter, Prometheus и Grafana](images/17-monitoring-setup-4.png)
Для проверки работоспособности был создан отдельный playbook:

```bash
ansible-playbook playbooks/monitoring_check.yml --ask-vault-pass
```

Он проверяет, что Exporter действительно подключается к базе (`mongodb_up = 1`), Prometheus успешно получает его метрики (`up{job="mongodb"} = 1`), а Grafana отвечает на HTTP-запросы.

![Проверка работы системы мониторинга](images/18-monitoring-check.png)

### Дашборд и выбранные метрики

В Grafana был настроен дашборд **MongoDB Lab Monitoring**, включающий семь панелей:

- **MongoDB UP** - доступность базы данных: `1` означает, что Exporter смог подключиться к MongoDB.
- **Current connections** - число текущих подключений к MongoDB.
- **Document operations / sec** - скорость операций с документами (чтение, вставка, обновление и удаление).
- **Network traffic** - входящий и исходящий сетевой трафик в байтах в секунду.
- **MongoDB resident memory** - объем оперативной памяти, занимаемой процессом MongoDB.
- **WiredTiger cache usage** - доля заполнения кеша движка хранения WiredTiger.
- **Operation latency** - средняя задержка операций чтения и записи в миллисекундах.

Для счетчиков операций и сетевого трафика использовалась функция PromQL `rate()`, которая рассчитывает среднюю скорость изменения счетчика за выбранный интервал. Дашборд обновляется каждые 5 секунд.

### Проверка мониторинга под нагрузкой

Сначала было зафиксировано состояние MongoDB без выраженной пользовательской нагрузки. На графиках видно, что база доступна (`MongoDB UP = 1`), количество соединений и операций небольшое, а сетевой трафик остается относительно стабильным.

![Дашборд MongoDB без выраженной нагрузки](images/grafana-1.png)

Затем был запущен нагрузочный тест:

```bash
ansible-playbook playbooks/load_test.yml --ask-vault-pass
```

Playbook запускает Python-скрипт с 4 параллельными потоками на 180 секунд. Скрипт подключается к учебной базе `education` от отдельного пользователя `load_user` и многократно выполняет операции `insert`, `find`, `update` и `delete` с документами коллекции `education.load_test`.

![Дашборд MongoDB при выполнении нагрузочного теста](images/grafana-2.png)

На втором скриншоте хорошо заметно влияние нагрузки. Число соединений увеличивается примерно до 15-18, скорость вставки документов достигает порядка 350 операций в секунду, а обновления до 150-180 операций в секунду. Одновременно растет сетевой трафик: входящий достигает примерно 800 КБ/с. Это ожидаемо, поскольку скрипт постоянно передает MongoDB документы и команды.

Также во время теста увеличивается потребление памяти (примерно с 52 до 78 МиБ) и заполнение кеша WiredTiger. MongoDB использует память для обработки операций и кеширования данных. На графике задержек виден рост времени выполнения операций записи с пиками около 8 мс: под нагрузкой обработка запросов занимает больше времени. При этом `MongoDB UP` остается равным `1`, то есть база продолжает отвечать.

Таким образом, в четвертой части была настроена система мониторинга MongoDB, выбран набор показателей доступности и производительности, создан дашборд Grafana и проведен нагрузочный тест. Сравнение графиков показывает, что увеличение активности в базе отражается на количестве соединений, интенсивности операций, сетевом трафике, использовании памяти и задержках запросов.

С этой лабораторной я провозился примерно неделю, зато узнал много нового. Раньше я в основном запускал готовые Ansible-скрипты, а тут впервые пришлось полноценно писать их самому, разбираться в ролях, переменных и отладке. Больше всего проблем было с зависимостями, правами пользователей MongoDB и настройкой мониторинга. С Prometheus и Grafana тоже впервые работал самостоятельно, поэтому не все получалось с первого раза. На лабу пришлось потратить прилично времени, но зато она оказалась действительно полезной :)