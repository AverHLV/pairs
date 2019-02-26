# AE Pairs
Website powered by Django. Requires python3.x.

## Apps
* pairs: main app, implement Pair and Order models.
* users: contains User model, managing users specific parameters like profit, minimum pairs count, etc.
* stats: displaying users and orders statistics by tables and interactive matplotlib figures.
* buyer: selenium buyer powered by Chrome in headless mode. Provides automated purchases on eBay.
* logs: displays pages with celery workers logs from main admin page.

## Tasks
Backend tasks powered by celery and django-celery-beat scheduler.