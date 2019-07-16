# AE Pairs
Amazon-eBay pairs manager for small teams.

## Apps
* pairs: main app, implements Pair and Order models.
* users: contains User model, managing users specific parameters like profit, minimum pairs count, etc.
* stats: displaying users and orders statistics by tables and interactive matplotlib figures.
* repricer: offers prices monitoring and setting by reprice strategy.
* logs: displays pages with celery workers logs from main admin page.

## Tasks
Backend tasks powered by celery and django-celery-beat scheduler.