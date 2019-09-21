# AE Pairs
Amazon-eBay pairs manager for small teams.

## Apps
* pairs: main app, implements Pair and Order models.
* users: contains User model, managing users specific parameters like profit, minimum pairs count, etc.
* stats: displaying users and orders statistics by tables and interactive matplotlib figures.
* repricer: offers prices monitoring and setting by reprice strategy.
* logs: displays pages with celery workers logs from main admin page.
* finder: asynchronous Amazon and eBay items info finder
* buyer: eBay items automated buyer, powered by selenium

## Tasks
Backend tasks powered by celery and django-celery-beat scheduler.

## REST API endpoints
* `/auth/api/`: [django-rest-auth endpoints](https://django-rest-auth.readthedocs.io/en/latest/api_endpoints.html).