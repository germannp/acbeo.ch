New ACBeo website 🪂
===================

Unfortunately, our current website is built on a Joomla extension that seems no longer 
under development. Therefore, eventually we will need a new homepage. Here, we develop 
a prototype in Python. Having no strong opinions ourselves, we use the opinionated web 
framework [Django](https://www.djangoproject.com/) for the backend. For the frontend we 
use [Bootstrap 5](https://getbootstrap.com/), as it feels like LaTeX for mobile (in the 
good, the bad, and the ugly way 🤷).

To download the code, install the necessary packages, and set up a local database run:
```
$ git clone https://github.com/germannp/acbeo.ch.git
$ cd acbeo.ch
$ pip install -r requirements.txt
$ python manage.py makemigrations
$ python manage.py migrate
```
In principle, database migrations should be versioned and `makemigrations` should not 
find any new migrations. However, during this early stage of development, we take the 
liberty to introduce breaking changes. If the migration fails, remove `db.sqlite3` and 
all previously generated migrations scripts from the `app/migrations` folders (but not 
`__init__.py` 🙄) and try again.

Once set up, the tests or a local server can be run as follows:
```
$ python manage.py test
$ python manage.py createsuperuser
$ python manage.py runserver
```
Creating a super user is only necessary to access the admin site, where the database 
can be edited directly. Normal pilot accounts can be registered over the website.

The Django project folder, `acbeo`, contains the settings. The code is organized in 
two Django apps: `news` contains the front page and user management and `trainings` 
the tool for organizing trainings. Within each app `url.py` contains paths to views, 
which load, manipulate, and save models mapped to the database, and render data and 
forms in templates.