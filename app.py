from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Response
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
import pymysql
import os
import requests


app = Flask(__name__)


'''
Config MySQL for local MySQL db
'''

app.config['UPLOAD_FOLDER'] = os.path.dirname(os.path.abspath(__file__)) + '/upload'

#This token is for authenticating to MySQL Storage. It most likely needs to be refreshed
auth_token_header = {'X-Auth-Token': 'AUTH_tk5ed7e7e3b78bcff82f96f49c184fbe0d'}

#Connect the Flask app to MySQL Cloud
def connect():
	connectString = os.environ.get('MYSQLCS_CONNECT_STRING', 'localhost:3306/myflaskapp') 
	hostname = connectString[:connectString.index(":")]
	database = connectString[connectString.index("/")+1:]
	mysql = pymysql.connect(host=hostname, port=int(os.environ.get('MYSQLCS_MYSQL_PORT', '3306')), user=os.environ.get('MYSQLCS_USER_NAME', 'root'), passwd=os.environ .get('MYSQLCS_USER_PASSWORD', 'password'), db=database,cursorclass=pymysql.cursors.DictCursor)
	return mysql

#Tokens for MySQL Storage expire and need to be refreshed. This will get a new one
def refresh_token():
	r = requests.head('https://uscom-east-1.storage.oraclecloud.com/v1/Storage-gse00015183', headers = auth_token_header)
	if (r.ok == False):
		header = {'X-Storage-User': 'login', 'X-Storage-Pass': 'password'}
		r = requests.get('https://uscom-east-1.storage.oraclecloud.com/auth/v1.0', headers=header)
		auth_token_header['X-Auth-Token'] = r.headers['X-Auth-Token']

#Create the tables for users, articles, and images. The homepage needs the database to be set up before it can function
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

	cur.execute("CREATE TABLE IF NOT EXISTS images( \
		id INT(11) AUTO_INCREMENT PRIMARY KEY, \
		name VARCHAR(255), \
		ref VARCHAR(255), body TEXT, \
		create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")

	mysql.commit()
	cur.close()
	mysql.close()
	flash('The tables were created succesfully', 'success')
	return redirect(url_for('index'))

#Deletes the tables for users, articles, and images.
@app.route('/resetdb')
def resetDB():
	mysql = connect()
	cur = mysql.cursor()
	cur.execute("DROP TABLE IF EXISTS users;")
	cur.execute("DROP TABLE IF EXISTS articles;")
	cur.execute("DROP TABLE IF EXISTS images;")
	mysql.commit()
	cur.close()
	mysql.close()
	session.clear()
	flash('The database has been reset', 'danger')
	return redirect(url_for('index'))

#The homepage will find all articles in the db and present them in descending order of creation
@app.route('/')
def index():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles ORDER BY id DESC;")
	if result > 0 :
		articles = cur.fetchall()
		return render_template('home.html', articles=articles)
	else:
		msg = "No stories on your feed!"

	return render_template('home.html', msg=msg)

#Takes you to a form to upload a file and send it to the uploader route
@app.route('/upload')
def upload_file():
   return render_template('upload.html')

#CAN ONLY TAKE IN JPG IMAGES <- Need to fix
#Takes a picture and uploads it into Oracle Cloud Storage. Adds a new entry in the images table.
@app.route('/uploader', methods = ['GET', 'POST'])
def uploader_file():
	if request.method == 'POST':
		f = request.files['file']
		# f.save(f.filename)
		filepath= os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
		ref = 'https://uscom-east-1.storage.oraclecloud.com/v1/Storage-gse00015183/Images/' + f.filename
		f.seek(0)
		data = f.read()
		print(data)

		r = requests.put(ref, headers=auth_token_header, data=data)
	  # os.remove(filepath)
		if (r.ok):
			mysql = connect()
			cur = mysql.cursor()
			cur.execute("INSERT INTO images(name, ref) VALUES(%s, %s)", (f.filename, ref))
			mysql.commit()
			cur.close()
			mysql.close()
			flash('File uploaded successfully', 'success')
		else:
			flash('Upload unsuccessful: ' + r.text, 'danger')
			refresh_token()
		return redirect(url_for('profile'))

#Downloads an image from Oracle Cloud Storage
@app.route('/get_img/<string:ref>')
def get_img(ref):
	print(ref)
	r = requests.get("https://uscom-east-1.storage.oraclecloud.com/v1/Storage-gse00015183/Images/" + ref, headers = auth_token_header)
	if (r.ok == False):
		refresh_token()
		return get_img(ref)
	else:
		img = Response(r.content, mimetype="image/jpg")
		return img

#Displays images that exist in the images table.
@app.route('/images')
def images():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM images")
	images = cur.fetchall()
	if result > 0:
		return render_template('images.html', images=images)
	else:
		msg = "No images exist!"
		return render_template('images.html', msg=msg)

@app.route('/about')
def about():
	return render_template('about.html')

#Displays a post in its own separate page
@app.route('/post/<string:id>/')
def article(id):
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles WHERE id = %s", [id])
	article = cur.fetchone()
	mysql.close()
	return render_template('post.html', article = article)

#Form used for registering users
class RegisterForm(Form):
	name = StringField('Name', [validators.Length(min=1, max=50)])
	username = StringField('Username', [validators.Length(min=4, max=25)])
	email = StringField('Email', [validators.Length(min=6, max=50)])
	password = PasswordField('Password', [validators.DataRequired(),
		validators.EqualTo('confirm', message="Passwords do not match"),
		])
	confirm = PasswordField('Confirm Password')

#Registers users and saves entry in users table
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

#Checks login details with entry in users table and validates login and creates a new session
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
				return redirect(url_for('profile'))

			else:
				error = 'Invalid password'
				return render_template('login.html', error=error)

		else:
			error = 'Invalid username'
			return render_template('login.html', error=error)

		cur.close()
		mysql.close()

	return render_template('login.html')

#Checks to see if a user is logged in
def is_logged_in(f):
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			return f(*args, **kwargs)
		else:
			flash('Unauthorized access', 'danger')
			return redirect(url_for('login'))
	return wrap

#Logs a user out and clears the session
@app.route('/logout')
def logout():
	session.clear()
	flash('You are now logged out', 'success')
	return redirect(url_for('login'))

#Takes user to their profile page where they can make a new post or upload an image
@app.route('/profile')
@is_logged_in
def profile():
	mysql = connect()
	cur = mysql.cursor()
	result = cur.execute("SELECT * FROM articles WHERE author=%s", [session['username']])
	articles = cur.fetchall()
	if result > 0:
		return render_template('profile.html', articles=articles)
	else:
		msg = 'No posts found!'
		return render_template('profile.html', msg=msg)

	cur.close()
	mysql.close()

#Form used to create a new text post
class ArticleForm(Form):
	title = StringField('Title', [validators.Length(min=1, max=200)])
	body = TextAreaField('Body', [validators.Length(min=30,)])

#Page that creates a new post and adds it to the articles table
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
		return redirect(url_for('profile'))

	return render_template('/add_article.html', form=form)

#Page that gets an existing post in the articles table and updates it
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
		mysql = connect()
		cur = mysql.cursor()

		cur.execute("UPDATE articles SET title=%s, body=%s WHERE id = %s", (title, body, id))
		mysql.commit()
		cur.close()
		mysql.close()
		
		flash('Article saved', 'success')
		return redirect(url_for('profile'))

	cur.close()
	mysql.close()

	return render_template('/edit_article.html', form=form)

#Gets an existing article from the articles table and deletes it
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
	return redirect(url_for('profile'))

if __name__ == '__main__':
	app.secret_key='secret'
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), debug=True)

