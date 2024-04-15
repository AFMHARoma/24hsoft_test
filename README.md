# Парсер esportsbattle.com
***
## Дисклеймер
Приложение не является образцом архитектурного исполнения. В нем значительно упрощено логирование, имеются элементы хардкодинга, база данных не приведена к нормальным формам в силу тестового характера задания.

***
## Что делает приложение
- Собирает информацию по матчам выбранных видов спорта
- Записывает данные в требуемом виде в базу данных

### Допущения
Поскольку время для ознакомления с сайтом было ограничено, мной были сделаны некоторые допущения относительно алгоритма его работы, а именно:
- Турниры добавляются в расписание последовательно, друг за другом в хронологическом порядке их начала. Не возникнет ситуации, в которой турнир, начинающийся в 09:00, будет добавлен в расписание позже, чем турнир, стартующий в 10:00
- Время начала матчей и турниров не переносится

Допущения соответствовали действительности в течение 2 дней наблюдения и согласованы с Михаилом Пучковым, который в течение долгого времени работает с данным сайтом. 
***
## Конфигурирование

#### Файлы ```log/py_log.log``` и ```config.json``` проброшены из Docker наружу. Это значит, что можно просматривать генерируемые приложением логи и управлять его конфигурацией на хостовой машине (последнее требует перезапуска контейнера) 
Все файлы предзаполнены в соответствии с требованиями тестового задания и не требуют редактирования при запуске через Docker.


Файл конфигурации ```config.json``` принимает следующие параметры:
- ```parse_interval_sec (int)``` - интервал запроса данных
- ```filter_status_code_match (list[str])``` - статусы матчей для фильтрации. Значение по-умолчанию оставляет только предстоящие матчи 
- ```filter_status_code_tournament (list[str])``` - статусы турниров для фильтрации. Значение по-умолчанию оставляет предстоящие и начавшиеся турниры
- ```seek_forward_days (int)``` - количество дней вперед от текущей даты для поиска предстоящих турниров. Не предполагает изменения, но может понадобиться при изменении сайта
- ```log_level (int)``` - уровень логирования
- ```sports_to_parse (list[str])``` - виды спорта для сбора данных. Возможные значения: cs2, football, basketball, hockey

В файле ```.env``` указываются:
- Пароль от базы данных, который будет одновременно в ней установлен и передан в приложение для подключения
- Хост базы данных, к которой приложение будет подключаться по порту ```5432``` с использованием логина ```postgres```. По-умолчанию указан хост ```postgres```, который соответствует имени контейнера БД в Docker. Для запуска приложения вне Docker нужно изменить хост БД

***
## Алгоритм работы парсера
Приложение получает информацию о статус-кодах событий с эндпоинта ```/statuses```  с поддоментов видов спорта. Запоминает только те ```status_id```, которые соответствуют указанным в конфиге фильтрам.


Далее для каждого вида спорта циклично делает следующее:
1. Собирает информацию о турнирах с эндпоинта ```/tournaments```. Эндпоинт принимает на вход 3 параметра: ```page```, ```dateFrom```, ```dateTo```. 
Чтобы определить ```dateFrom```, с базы данных получаем время старта самого позднего турнира по данному виду спорта. Если в базе ничего нет или данные слишком старые, то время устанавливается как текущее время минус 1 день. 
2. Собранные турниры фильтруются по статус-кодам, собранным в начале
3. Для каждого оставшегося турнира собираем информацию по его матчам с эндпоинта ```/tournament/{tournament_id}/matches```
4. Собранные матчи также отсеиваются по статус-кодам
5. Данные преобразуются в требуемый заданием вид и записываются в базу данных
6. База данных очищается от матчей, время начала которых уже наступило

Особенность работы приложения такова, что первый проход может быть достаточного долгим, но последующие, если оно работает непрерывно или находится в простое не более 1 дня, будут очень быстрыми. 


***

## Запуск приложения

1. Клонировать репозиторий с GitHub

```
git clone https://github.com/AFMHARoma/24hsoft_test.git
```

2. Перейти в директорию проекта
```
cd 24hsoft_test
```

### Docker

3. Запустить сборку через docker-compose
```
docker-compose up -d
```

### Локальный запуск (при наличии внешней БД)

3. Создать виртуальное окружение:

````
python -m venv venv
````

4. Активировать окружение:

````
source venv\bin\activate
````

5. Установка зависимостей
``` 
pip install -r requirements.txt
```
6. Запуск скрипта
``` 
python main.py
```