import os
import secrets

from flask import Flask

from ai_handler import ai_handler_route
from delete_application import delete_application_route
from get_applications import get_applications_route
from get_canteen import get_canteen_route
from get_contents import get_contents_route
from get_home import get_home_route
from get_laundry import get_laundry_route
from get_notifications import get_notifications_route
from get_penalties import get_penalties_route
from get_profile import get_profile_route
from get_roommates import get_roommates_route
from index_route import index_route
from login import login_route
from logout import logout_route
from submit_application import submit_application_route
from update_api_key import update_api_key_route
from update_application import update_application_route
from update_profile import update_profile_route

app = Flask(__name__)

# --- Session secret key ---
# Flask sessions (login state) require this. Preferred: set SECRET_KEY as an
# environment variable in cPanel -> Setup Python App -> Environment Variables.
# If it's not set, a key is generated once and saved to secret_key.txt next
# to this file, so logins survive app restarts. Keep secret_key.txt out of
# version control if you use one.
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    _key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secret_key.txt')
    if os.path.exists(_key_path):
        with open(_key_path, 'r') as f:
            _secret_key = f.read().strip()
    if not _secret_key:
        _secret_key = secrets.token_hex(32)
        with open(_key_path, 'w') as f:
            f.write(_secret_key)
app.secret_key = _secret_key

# --- Routes ---
# Page (renders templates/index.html)
app.add_url_rule('/', 'index', index_route, methods=['GET'])

# Auth
app.add_url_rule('/login.php', 'login', login_route, methods=['POST'])
app.add_url_rule('/logout.php', 'logout', logout_route, methods=['GET'])

# Data (GET) — URL paths keep the old .php names so index.html's
# existing fetch() calls keep working unchanged.
app.add_url_rule('/get_home.php', 'get_home', get_home_route, methods=['GET'])
app.add_url_rule('/get_applications.php', 'get_applications', get_applications_route, methods=['GET'])
app.add_url_rule('/get_canteen.php', 'get_canteen', get_canteen_route, methods=['GET'])
app.add_url_rule('/get_contents.php', 'get_contents', get_contents_route, methods=['GET'])
app.add_url_rule('/get_laundry.php', 'get_laundry', get_laundry_route, methods=['GET'])
app.add_url_rule('/get_notifications.php', 'get_notifications', get_notifications_route, methods=['GET'])
app.add_url_rule('/get_penalties.php', 'get_penalties', get_penalties_route, methods=['GET'])
app.add_url_rule('/get_profile.php', 'get_profile', get_profile_route, methods=['GET'])
app.add_url_rule('/get_roommates.php', 'get_roommates', get_roommates_route, methods=['GET'])

# Mutations (POST)
app.add_url_rule('/submit_application.php', 'submit_application', submit_application_route, methods=['POST'])
app.add_url_rule('/update_application.php', 'update_application', update_application_route, methods=['POST'])
app.add_url_rule('/delete_application.php', 'delete_application', delete_application_route, methods=['POST'])
app.add_url_rule('/update_profile.php', 'update_profile', update_profile_route, methods=['POST'])
app.add_url_rule('/update_api_key.php', 'update_api_key', update_api_key_route, methods=['POST'])
app.add_url_rule('/ai_handler.php', 'ai_handler', ai_handler_route, methods=['POST'])

if __name__ == '__main__':
    app.run(debug=False)
