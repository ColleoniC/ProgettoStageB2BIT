import os
import secrets
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'CIAO')

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '1234')  # testo semplice, solo per sviluppo locale


def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea la tabella users (se non esiste) e inserisce un utente demo."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT
        )
    ''')

    # Migrazione: aggiunge le colonne mancanti se il DB esisteva già con lo schema vecchio
    cursor.execute('PRAGMA table_info(users)')
    colonne_esistenti = {riga[1] for riga in cursor.fetchall()}
    colonne_richieste = {
        'cognome': 'TEXT',
        'orario_inizio': 'TEXT',
        'orario_pausa_inizio': 'TEXT',
        'orario_pausa_fine': 'TEXT',
        'orario_fine': 'TEXT',
    }
    for nome_colonna, tipo in colonne_richieste.items():
        if nome_colonna not in colonne_esistenti:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {nome_colonna} {tipo}')
            print(f"Colonna aggiunta: {nome_colonna}")

    email_demo = 'demo@prova.com'
    password_demo = 'demo1234'

    cursor.execute('SELECT id FROM users WHERE email = ?', (email_demo,))
    if cursor.fetchone() is None:
        cursor.execute(
            'INSERT INTO users (email, password, name) VALUES (?, ?, ?)',
            (email_demo, generate_password_hash(password_demo), 'Utente Demo')
        )
        print(f"Utente demo creato: {email_demo} / {password_demo}")

    conn.commit()
    conn.close()


def require_admin():
    """Restituisce None se l'utente è admin, altrimenti un redirect al login admin."""
    if session.get('tipo_utente') != 'admin':
        return redirect(url_for('admin_login_page'))
    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin/login', methods=['GET'])
def admin_login_page():
    return render_template('admin_login.html')


@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')


@app.route('/admin/login', methods=['POST'])
def admin_login():
    nome = request.form.get('nome', '').strip()
    password = request.form.get('password', '').strip()

    if nome == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session.permanent = True
        session['user'] = {
            'email': 'admin@gmail.com',
            'name': 'Administrator',
            'authenticated_at': datetime.utcnow().isoformat()
        }
        session['tipo_utente'] = 'admin'
        return redirect(url_for('admin_panel'))

    return jsonify({'ok': False, 'errore': 'Credenziali non valide'}), 401


@app.route('/admin/panel')
def admin_panel():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response
    return render_template('admin_panel.html', admin_name=session['user']['name'])


@app.route('/admin/create_user', methods=['GET'])
def create_user_page():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response
    return render_template('admin_crea.html')


@app.route('/admin/create_user', methods=['POST'])
def create_user():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    nome = request.form.get('nome', '').strip()
    cognome = request.form.get('cognome', '').strip()
    orario_inizio = request.form.get('orario_inizio', '').strip()
    orario_pausa_inizio = request.form.get('orario_pausa_inizio', '').strip()
    orario_pausa_fine = request.form.get('orario_pausa_fine', '').strip()
    orario_fine = request.form.get('orario_fine', '').strip()
    email = request.form.get('email', '').strip().lower()

    if not nome or not cognome or not email:
        return jsonify({'ok': False, 'errore': 'Nome, cognome ed email sono obbligatori'}), 400

    # Password provvisoria generata automaticamente, da comunicare all'utente
    password_provvisoria = secrets.token_urlsafe(8)

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT INTO users
               (email, password, name, cognome, orario_inizio, orario_pausa_inizio, orario_pausa_fine, orario_fine)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (email, generate_password_hash(password_provvisoria), nome, cognome,
             orario_inizio, orario_pausa_inizio, orario_pausa_fine, orario_fine)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'ok': False, 'errore': 'Email già registrata'}), 409
    conn.close()

    return render_template('admin_crea_ok.html', email=email, password=password_provvisoria)


@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not email or not password:
        return jsonify({'ok': False, 'errore': 'Email e password sono obbligatorie'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()

    if user is None or not check_password_hash(user['password'], password):
        return jsonify({'ok': False, 'errore': 'Credenziali non valide'}), 401

    session.permanent = True
    session['user'] = {
        'id': user['id'],
        'email': user['email'],
        'name': user['name'] if 'name' in user.keys() else user['email'],
        'authenticated_at': datetime.utcnow().isoformat()
    }
    session['tipo_utente'] = 'utente'

    return redirect(url_for('timbro_page'))


@app.route('/timbro')
def timbro_page():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    return render_template('timbro.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run('127.0.0.1', 5000, debug=True)