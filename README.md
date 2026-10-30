# Non-relational-databases

## Проверка Ansible

Из корня репозитория:

```bash
python -m pip install ansible-lint
ansible-galaxy collection install -r requirements.yml
ansible-lint .
```

Для явной проверки всех файлов лабораторной (в том числе при проблемах
с раскрытием `.` в установленной версии линтера):

```bash
ansible-lint lab2-opensearch/ requirements.yml
```

Корневой `ansible.cfg` задаёт путь к ролям для линтера. Для запуска playbook
используйте каталог `lab2-opensearch` с его `ansible.cfg` и inventory.
Роли находятся в `roles/opensearch`, `roles/dashboards` и `roles/check_configuration`.
Роли узлов OpenSearch задаются переменной `opensearch_node_roles` в `host_vars`.

Локальное окружение, сертификаты и файл секретов `group_vars/all/vault.yml`
исключены из проверки. Проверка синтаксиса не запускает задачи на серверах.
