from flask import session, redirect

def logout_route():
    session.clear()
    return redirect('/')