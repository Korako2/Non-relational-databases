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
