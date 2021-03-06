import minitwit
import time
from flask import Flask, request, jsonify, g, json, abort, Response, flash
from flask_basicauth import BasicAuth
from werkzeug import check_password_hash, generate_password_hash

app = Flask(__name__)

# default authenticated configuration
app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'admin123'

basic_auth = BasicAuth(app)


'''return username of an user_id'''
def get_username(user_id):
    cur = minitwit.query_db('select username from user where user_id = ?', [user_id], one = True)
    return cur[0] if cur else None


def get_credentials(username):
    user_name = minitwit.query_db('''select username from user where user.username = ?''', [username], one=True)
    pw_hash = minitwit.query_db('''select pw_hash from user where user.username = ?''', [username], one=True)
    app.config['BASIC_AUTH_USERNAME'] = user_name[0]
    app.config['BASIC_AUTH_PASSWORD'] = pw_hash[0]


def get_credentials_by_user_id(user_id):
    user_name = minitwit.query_db('''select username from user where user.user_id = ?''', [user_id], one=True)
    pw_hash = minitwit.query_db('''select pw_hash from user where user.user_id = ?''', [user_id], one=True)
    app.config['BASIC_AUTH_USERNAME'] = user_name[0]
    app.config['BASIC_AUTH_PASSWORD'] = pw_hash[0]


def make_error(status_code, message, reason):
    response = jsonify({
        "status" : status_code,
        "message" : message,
        "reason" : reason
    })
    return response


def populate_db():
    """Re-populates the database with test data"""
    db = minitwit.get_db()
    with app.open_resource('population.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


@app.cli.command('populatedb')
def populatedb_command():
    """Inputs data in database tables."""
    populate_db()
    print('Database population is completed.')


@app.before_request
def only_json():
    if not request.is_json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")


@app.after_request
def after_request(response):
    if response.status_code == 400:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if response.status_code == 500:
        return make_error(500, "Internal Server Error", "The server encountered an internal error and was unable to complete your request.  Either the server is overloaded or there is an error in the application.")
    if response.status_code == 404:
        return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
    if response.status_code == 405:
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')
    return response


@app.route('/users/<username>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def user_info(username):
    """Gets user's information"""
    data = request.get_json()
    get_credentials(data["username"])
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if request.method == 'GET':
        user = minitwit.query_db('''select * from user where user.username = ?''', [username])
        user = map(dict, user)
        return jsonify(user)
    return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')


@app.route('/users/<username>/add_message', methods=['POST', 'GET', 'PUT', 'DELETE'])
def insert_message(username):
    """Inserts a new message from current <username>"""
    if request.method == 'POST':
        data = request.get_json()
        user_id = minitwit.get_user_id(username)
        get_credentials(data["username"])
        if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
            return make_error(401, 'Unauthorized', 'Correct username and password are required.')
        if data:
            db = minitwit.get_db()
            db.execute('''insert into message (author_id, text, pub_date)
            values (?, ?, ?)''', [user_id, data["text"], int(time.time())])
            db.commit()
            print 'Your message was recorded'
        return jsonify(data)
    return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')


@app.route('/users/<username>/messages', methods=['GET', 'POST', 'PUT', 'DELETE'])
def get_user_messages(username):
    """Displays a user's tweets"""
    profile_user = minitwit.query_db('select * from user where username = ?',[username], one=True)
    if profile_user is None:
        return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
    data = request.get_json()
    get_credentials(data["username"])
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if request.method == 'GET':
        messages = minitwit.query_db('''select message.*, user.* from message, user where user.user_id = message.author_id and user.user_id = ? order by message.pub_date desc limit ?''',
        [profile_user['user_id'], minitwit.PER_PAGE])
        messages = map(dict, messages)
        return jsonify(messages)
    return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')


@app.route('/users/<username1>/follow/<username2>', methods=['POST', 'GET', 'PUT', 'DELETE'])
def add_follow_user(username1, username2):
    """Adds the username1 as follower of the given username2."""
    data = request.get_json()
    get_credentials(username1)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    who_id = minitwit.get_user_id(username1)
    whom_id = minitwit.get_user_id(username2)
    if whom_id is None:
        return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
    cur = minitwit.query_db('select count(*) from follower where who_id = ? and whom_id = ?', [who_id, whom_id], one=True)
    if cur[0] > 0:
        return make_error(422, "Unprocessable Entity", "Data duplicated")
    if request.method == 'POST':
        db = minitwit.get_db()
        db.execute('insert into follower (who_id, whom_id) values (?, ?)', [who_id, whom_id])
        db.commit()
        print 'You are now following %s' % username2
        return jsonify(data)
    return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')


@app.route('/messages', methods=['POST', 'GET', 'PUT', 'DELETE'])
def get_messages():
    '''return all messages from all users '''
    if request.method != 'GET':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    messages = minitwit.query_db('''
            select message.text, user.username from message, user
            where message.author_id = user.user_id
            order by message.pub_date desc''',
            )
    messages = map(dict, messages)
    return jsonify(messages)


@app.route('/messages/<user_id>', methods =['POST', 'GET', 'PUT', 'DELETE'])
def get_message_user(user_id):
    '''return all messages form the user <user_id>'''
    if request.method != 'GET':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')
    data = request.json
    messages = minitwit.query_db('''
        select message.text, user.username from message, user
        where message.author_id = user.user_id and user.user_id = ? ''',
        [user_id])
    messages = map(dict, messages)

    return jsonify(messages)


@app.route('/users/<user_id>/followers', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def user_followers(user_id):
    '''return all users that are followers of the user <user_id>'''
    if request.method != 'GET':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')
    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    messages = minitwit.query_db('''
        select u1.username as followee, u2.username as follower from user u1, follower f, user u2
        where u1.user_id = f.who_id and u2.user_id = f.whom_id and u1.user_id = ? ''',
        [user_id])
    messages = map(dict, messages)

    return jsonify(messages)


@app.route('/users/<user_id>/follow', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def user_follow(user_id):
    '''return all users that the user <user_id> is following'''
    if request.method != 'GET':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')
    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    messages = minitwit.query_db('''
        select u1.username as followee, u2.username as follower from user u1, follower f, user u2
        where u1.user_id = f.who_id and u2.user_id = f.whom_id and u1.user_id = ? ''',
        [user_id])

    messages = map(dict, messages)
    return jsonify(messages)


@app.route('/messages/<user_id>/add_message', methods=['POST', 'GET', 'PUT', 'DELETE'])
def add_message(user_id):
    '''Insert a message into table message: json data: author_id, text'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'POST':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if data:
        username = get_username(user_id)
        get_credentials(username)
        if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
            return make_error(401, 'Unauthorized', 'Invalid Username ad/or Password')

        db = minitwit.get_db()
        db.execute('''insert into message (author_id, text)
        values (?, ?)''',
        [data["author_id"], data["text"]])
        db.commit()
        print 'Your message was successfully recorded'
    return jsonify(data)


@app.route('/users/<user_id>/add_follow', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def add_follow(user_id):
    '''Insert follow: json data: whom_id'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'POST':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if data:
        '''Check duplicate'''
        cur = minitwit.query_db('select count(*) from follower where who_id = ? and whom_id = ?', [user_id, data["whom_id"]], one=True)
        if cur[0] > 0:
            return make_error(422, "Unprocessable Entity", "Data duplicated")
        db = minitwit.get_db()
        db.execute('''insert into follower (who_id, whom_id)
            values (?, ?)''',
            [user_id, data["whom_id"]])
        db.commit()
        print 'You are following user has user_id ', data['whom_id']
    return jsonify(data)


@app.route('/users/<user_id>/unfollow', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def remove_follow(user_id):
    '''Unfollow: json data: whom_id'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'DELETE':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if data:
        '''Check who_id and whom_id existing'''
        cur = minitwit.query_db('select count(*) from follower where who_id = ? and whom_id = ?', [user_id, data["whom_id"]], one=True)
        if cur[0] == 0:
            return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
        db = minitwit.get_db()
        db.execute('''delete from follower
        where who_id = ? and whom_id = ?''',
         [user_id, data["whom_id"]])
        db.commit()
        print 'You are no longer following user has ', data["whom_id"]
    return jsonify(data)


@app.route('/users/<user_id>/change_password', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def change_password(user_id):
    '''Change password: json data: password, confirmed_password'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'PUT':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if data:
        '''Check user_id existing'''
        cur = minitwit.query_db('select count(*) from user where user_id = ?', [user_id], one=True)
        if cur[0] == 0:
            return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
        '''check password and confirmed password are equal'''
        if data["password"] != data["confirmed_password"]:
            return make_error(422, "Unprocessable Entity", "password and confirmed password not consistent")
        db = minitwit.get_db()
        pw = generate_password_hash(data['password'])
        db.execute('''update user
        set pw_hash = ?
        where user_id = ?''',
        [pw, user_id])
        db.commit()
        print 'Your password was successfully changed'
    return jsonify(data)


@app.route('/users/<user_id>/change_email', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def change_email(user_id):
    '''Change email: json data: email, confirmed_email'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'PUT':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json
    get_credentials_by_user_id(user_id)
    if not basic_auth.check_credentials(data["username"], data["pw_hash"]):
        return make_error(401, 'Unauthorized', 'Correct username and password are required.')
    if data:
        '''Check user_id existing'''
        cur = minitwit.query_db('select count(*) from user where user_id = ?', [user_id], one=True)
        if cur[0] == 0:
            return make_error(404, 'Not Found', 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.')
        '''check password and confirmed password are equal'''
        if data["email"] != data["confirmed_email"]:
            return make_error(422, "Unprocessable Entity", "password and confirmed password not consistent")
        db = minitwit.get_db()
        email = data["email"]
        db.execute('''update user
        set email = ?
        where user_id = ?''',
        [email, user_id])
        db.commit()
        print 'Your email was successfully changed'
    return jsonify(data)


@app.route('/users/Sign_up', methods = ['POST', 'GET', 'PUT', 'DELETE'])
def Sign_up():
    '''User Sign up: json data: username, email, password, confirmed_password'''
    if not request.json:
        return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
    if request.method != 'POST':
        return make_error(405, 'Method Not Allowed', 'The method is not allowed for the requested URL.')

    data = request.json

    if data:
        if not data["username"] or not data["email"] or not data["password"] \
            or not data["confirmed_password"] or data["password"] != data["confirmed_password"]:
            return make_error(400, "Bad Request", "The browser (or proxy) sent a request that this server could not understand.")
        '''check duplicate'''
        cur = minitwit.query_db('select count(*) from user where username = ?', [data["username"]], one=True)
        cur1 = minitwit.query_db('select count(*) from user where email = ?', [data["email"]], one=True)
        if cur[0] > 0:
            return make_error(422, "Unprocessable Entity", "Duplicated Username")
        if cur1[0] > 0:
            return make_error(422, "Unprocessable Entity", "Duplicated email")
        pw = generate_password_hash(data["password"])
        db = minitwit.get_db()
        db.execute('''insert into user (username, email, pw_hash)
            values (?, ?, ?)''',
            [data["username"], data["email"], pw])
        db.commit()
        print 'You were successfully registered'
    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=True)
