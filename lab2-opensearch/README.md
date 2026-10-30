
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

