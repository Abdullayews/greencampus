from flask import session, render_template
from datetime import datetime


def index_route():
    """
    Renders the Student Portal home page.
    Replaces the old index.php, whose 500 error was caused by
    `require 'config.php';` pointing at a PHP file that no longer
    exists in this project (the backend was migrated to Flask/config.py).
    Register in app.py, e.g.:
        app.add_url_rule('/', 'index', index_route)
    """
    user_name = session.get('user_name', '')
    user_ixtisas = session.get('ixtisas', '')
    user_kurs = session.get('kurs', '')
    user_otaq = session.get('otaq_nomresi', '')
    is_logged_in = 'user_id' in session

    name_first = ''
    user_initials = 'T'
    name_short = 'Tələbə'

    if user_name:
        name_parts = user_name.split(' ')
        name_first = name_parts[0]
        user_initials = name_first[0].upper() if name_first else 'T'
        name_short = name_first
        if len(name_parts) > 1 and name_parts[1]:
            name_short += ' ' + name_parts[1][0].upper() + '.'

    return render_template(
        'index.html',
        user_name=user_name,
        user_ixtisas=user_ixtisas,
        user_kurs=user_kurs,
        user_otaq=user_otaq,
        is_logged_in=is_logged_in,
        name_first=name_first,
        user_initials=user_initials,
        name_short=name_short,
        current_year=datetime.now().year,
    )
