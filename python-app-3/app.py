from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Response
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
from PIL import Image
import pymysql
import base64
import os
import requests
from io import BytesIO


app = Flask(__name__)


'''
Config MySQL for local MySQL db
'''

# app.config['MYSQL_HOST'] = 'localhost'
# app.config['MYSQL_USER'] = 'root'
# app.config['MYSQL_PASSWORD'] = 'password'
# app.config['MYSQL_DB'] = 'myflaskapp'
# app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# app.config['MYSQL_PORT'] = 3306

'''
Config MySQL for Cloud
'''


# app.config['MYSQL_HOST'] = hostname
# app.config['MYSQL_USER'] = os.environ.get('MYSQLCS_MYSQL_USER_NAME', 'root')
# app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQLCS_MYSQL_USER_PASSWORD', 'password')
# app.config['MYSQL_DB'] = database
# app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# app.config['MYSQL_PORT'] = int(os.environ.get('MYSQLCS_MYSQL_PORT', '3306'))

auth_token_header = {'X-Auth-Token': 'AUTH_tk5ed7e7e3b78bcff82f96f49c184fbe0d'}


def connect():
	connectString = os.environ.get('MYSQLCS_CONNECT_STRING', 'localhost:3306/myflaskapp') 
	hostname = connectString[:connectString.index(":")]
	database = connectString[connectString.index("/")+1:]
	mysql = pymysql.connect(host=hostname, port=int(os.environ.get('MYSQLCS_MYSQL_PORT', '3306')), user=os.environ.get('MYSQLCS_USER_NAME', 'root'), passwd=os.environ .get('MYSQLCS_USER_PASSWORD', 'password'), db=database,cursorclass=pymysql.cursors.DictCursor)
	return mysql

def refresh_token():
	r = requests.head('https://uscom-east-1.storage.oraclecloud.com/v1/Storage-gse00015183', headers = auth_token_header)
	if (r.ok == False):
		header = {'X-Storage-User': 'Storage-gse00015183:cloud.admin', 'X-Storage-Pass': 'Acyclic@3BaBy'}
		r = requests.get('https://uscom-east-1.storage.oraclecloud.com/auth/v1.0', headers=header)
		auth_token_header['X-Auth-Token'] = r.headers['X-Auth-Token']

# mysql = MySQL(app)

@app.route('/setupdb')
def setupDB():
    mysql = connect()
    cur = mysql.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users( \
    	id INT(11) AUTO_INCREMENT PRIMARY KEY, \
    	name VARCHAR(100), email VARCHAR(100), \
    	username VARCHAR(100), password VARCHAR(100), \
    	register_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")

    cur.execute("CREATE TABLE IF NOT EXISTS articles( \
    	id INT(11) AUTO_INCREMENT PRIMARY KEY, \
    	title VARCHAR(255), \
    	author VARCHAR(100), body TEXT, \
    	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")

    mysql.commit()
    cur.close()
    mysql.close()
    print ('The tables were created succesfully')

@app.route('/')
def index():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles")
	articles = cur.fetchall()
	if result > 0 :
		return render_template('home.html', articles=articles)
	else:
		msg = "No stories on your feed!"

	return render_template('home.html', msg=msg)

@app.route('/get_img')
def get_img():
	r = requests.get('https://uscom-east-1.storage.oraclecloud.com/v1/Storage-gse00015183/Images/babypic.jpg', headers = auth_token_header)
	if (r.ok == False):
		refresh_token()
		return get_img()
	else:
		img = Response(r.content, mimetype="image/jpg")
		return img

@app.route('/images')
def images():
	return render_template('images.html')

@app.route('/about')
def about():
	return render_template('about.html')

@app.route('/articles')
def articles():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles")
	articles = cur.fetchall()
	if result > 0:
		return render_template('articles.html', articles=articles)
	else:
		msg = 'No Articles found'
		return render_template('articles.html', msg=msg)
	mysql.close()


@app.route('/articles/<string:id>/')
def article(id):
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles WHERE id = %s", [id])
	article = cur.fetchone()
	mysql.close()
	return render_template('article.html', article = article)

class RegisterForm(Form):
	name = StringField('Name', [validators.Length(min=1, max=50)])
	username = StringField('Username', [validators.Length(min=4, max=25)])
	email = StringField('Email', [validators.Length(min=6, max=50)])
	password = PasswordField('Password', [validators.DataRequired(),
		validators.EqualTo('confirm', message="Passwords do not match"),
		])
	confirm = PasswordField('Confirm Password')

@app.route('/register', methods=['GET', 'POST'])
def register():
	form = RegisterForm(request.form)
	if request.method == 'POST' and form.validate():
		name = form.name.data
		email = form.email.data
		username = form.username.data
		password = sha256_crypt.encrypt(str(form.password.data))

		#Create cursor
		mysql = connect()
		cur = mysql.cursor()
		cur.execute("INSERT INTO users(name, email, username, password) VALUES(%s, %s, %s, %s)", (name, email, username, password))
		mysql.commit()
		cur.close()
		mysql.close()
		flash('You are now registered and can log in', 'success')
		return redirect(url_for('index'))

	return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		#Get form fields
		username = request.form['username']
		password_candidate = request.form['password']
		#Cur
		mysql = connect()
		cur = mysql.cursor()
		#get user by username
		result = cur.execute("SELECT * FROM users WHERE username = %s", [username])
		if result > 0:
			#get stored hash
			data = cur.fetchone()
			password = data['password']

			#compare passwords
			if sha256_crypt.verify(password_candidate, password):

				session['logged_in'] = True
				session['username'] = username

				flash('You are now logged in', 'success')
				return redirect(url_for('dashboard'))

			else:
				error = 'Invalid password'
				return render_template('login.html', error=error)

		else:
			error = 'Invalid username'
			return render_template('login.html', error=error)

		cur.close()
		mysql.close()

	return render_template('login.html')

def is_logged_in(f):
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			return f(*args, **kwargs)
		else:
			flash('Unauthorized access', 'danger')
			return redirect(url_for('login'))
	return wrap


@app.route('/logout')
def logout():
	session.clear()
	flash('You are now logged out', 'success')
	return redirect(url_for('login'))

@app.route('/dashboard')
@is_logged_in
def dashboard():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles WHERE author=%s", [session['username']])
	articles = cur.fetchall()
	if result > 0:
		return render_template('dashboard.html', articles=articles)
	else:
		msg = 'No posts found!'
		return render_template('dashboard.html', msg=msg)

	cur.close()
	mysql.close()

class ArticleForm(Form):
	title = StringField('Title', [validators.Length(min=1, max=200)])
	body = TextAreaField('Body', [validators.Length(min=30,)])

@app.route('/add_article', methods=['GET', 'POST'])
@is_logged_in
def add_article():
	form = ArticleForm(request.form)
	if request.method == 'POST' and form.validate():
		title = form.title.data
		body = form.body.data

		mysql = connect()
		cur = mysql.cursor()

		cur.execute("INSERT INTO articles(title, body, author) VALUES(%s, %s, %s)", (title, body, session['username']))
		mysql.commit()
		cur.close()
		mysql.close()

		flash('Article created', 'success')
		return redirect(url_for('dashboard'))

	return render_template('/add_article.html', form=form)

@app.route('/edit_article/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def edit_article(id):
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles WHERE id = %s", [id])
	article = cur.fetchone()

	form = ArticleForm(request.form)

	form.title.data = article['title']
	form.body.data = article['body']


	if request.method == 'POST' and form.validate():
		title = request.form['title']
		body = request.form['body']

		cur = mysql.connection.cursor()

		cur.execute("UPDATE articles SET title=%s, body=%s WHERE id = %s", (title, body, id))
		mysql.commit()
		cur.close()
		mysql.close()

		flash('Article saved', 'success')
		return redirect(url_for('dashboard'))

	cur.close()
	mysql.close()

	return render_template('/edit_article.html', form=form)

@app.route('/delete_article/<string:id>', methods=['POST'])
@is_logged_in
def delete_article(id):
	mysql = connect()
	cur = mysql.cursor()
	cur.execute("DELETE FROM articles WHERE id=%s", [id])
	mysql.commit()
	cur.close()
	mysql.close()
	flash('Article deleted', 'success')
	return redirect(url_for('dashboard'))

if __name__ == '__main__':
	app.secret_key='secret123'
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), debug=True)

