New ACBeo website 🪂
===================

Unfortunately, our former website was built on a Joomla extension that seems no longer 
under development. Therefore, eventually we needed a new homepage. Having no strong
opinions, we use the opinionated web framework [Django](https://www.djangoproject.com/)
for the backend. For the frontend we use [Bootstrap 5](https://getbootstrap.com/), as it
feels like LaTeX for mobile (in the good, the bad, and the ugly way 🤷).

To download the code, install the necessary packages, and set up a local database run:
```
$ git clone https://github.com/germannp/acbeo.ch.git
$ cd acbeo.ch
$ pip install -r requirements.txt
$ python manage.py makemigrations
$ python manage.py migrate
```
In principle, database migrations should be versioned and `makemigrations` should not 
find any new migrations. However, if the migration still fails, remove `db.sqlite3` and 
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

The code is organized as follows: Django project folder, `acbeo`, contains the settings. 
In particular, `acbeo/settings.py` reads secrets from environmental variables, which 
need to be configured for deployment. The logic is organized in Django apps: `news` 
contains the front page and user management, `trainings` the tool for organizing 
trainings, and `bookkeeping` the tool for creating reports and bills during a training. 
Within each app `url.py` contains paths to views, which load, manipulate, and save models 
mapped to the database, and render data and forms in templates.

To customize Bootstrap, it's source code and [SASS](https://sass-lang.com/) are required. 
These can be installed using `$ nmp i bootstrap@5.2.0 sass`. Then the stylesheets can be
compiled using `sass news/static/news/custom.scss news/static/news/custom.css`. The 
resulting files need to be versioned for the site to work.

To build push to [github.com/germannp/acbeo.ch](https://github.com/germannp/acbeo.ch).
The new container will be deployed, if the unit tests pass. To back up the database use
e.g.:
```
$ fly ssh console
# python manage.py dumpdata > acbeo-db_2024-05-17.json
$ fly sftp get /app/acbeo-db_2024-05-17.json
```

## Translation
_https://docs.djangoproject.com/en/5.2/topics/i18n/translation/_  
To translate the site to english, default is german. Translations are defined in the `locale/en/LC_MESSAGES/django.po` file.
### 1. Mark strings to be translated  
In Python:
```python
from django.utils.translation import gettext_lazy as _

message = _(
    "%(first_name)s %(last_name)s hat folgende Änderungen am Konto gemacht:\n\n"
) % {
    "first_name": self.cleaned_data["first_name"],
    "last_name": self.cleaned_data["last_name"],
}
```
In HTML templates:
```html
{% load i18n %}

{% translate "Kontakt" %}

{% url 'login' as login_url %}
{% blocktrans trimmed with url=login_url %}
    Falls du bereits ein Konto hast, bitte <a href="{{ url }}?next={{ next }}">einloggen</a>.
{% endblocktrans %}
```

### 2. Generate translation `.po` file
Run this to extract strings into the `.po` file:
```
django-admin makemessages -l en
```

### 3. Translate content in the `.po` file
After running `makemessages`, your `.po` file will include entries like this:
```
#: trainings/templates/trainings/emergency_mail.html:57
#, fuzzy
#| msgid "Absenden"
msgid "Senden"
msgstr ""
```
The `#, fuzzy` flag means this translation was auto-guessed and must be confirmed manually. Fuzzy translations are ignored during `compilemessages` unless you remove the `fuzzy` flag.
Remove `#, fuzzy` and add a valid `msgstr` to activate the translation:
```
#: trainings/templates/trainings/emergency_mail.html:57
msgid "Senden"
msgstr "Submit"
```

### 4. Check `.po` file for formatting errors (optional)
```
msgfmt -c -v -o /dev/null locale/en/LC_MESSAGES/django.po
```

### 5. Compile translated content
```
django-admin compilemessages
```
