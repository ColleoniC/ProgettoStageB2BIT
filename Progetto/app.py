import os
import secrets
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import date, datetime, timedelta

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timbrature (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            creato_il TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifiche (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            messaggio TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'info',
            creato_il TEXT NOT NULL,
            letta INTEGER NOT NULL DEFAULT 0,
            user_id INTEGER,
            data_riferimento TEXT
        )
    ''')

    cursor.execute('PRAGMA table_info(notifiche)')
    colonne_notifiche = {riga[1] for riga in cursor.fetchall()}
    for nome_colonna, tipo_colonna in {'user_id': 'INTEGER', 'data_riferimento': 'TEXT'}.items():
        if nome_colonna not in colonne_notifiche:
            cursor.execute(f'ALTER TABLE notifiche ADD COLUMN {nome_colonna} {tipo_colonna}')

    conn.commit()
    conn.close()


def crea_notifica(messaggio, tipo='info', user_id=None, data_riferimento=None):
    """Inserisce una nuova notifica per l'admin."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO notifiche (messaggio, tipo, creato_il, user_id, data_riferimento)
           VALUES (?, ?, ?, ?, ?)''',
        (messaggio, tipo, datetime.now().isoformat(), user_id, data_riferimento)
    )
    conn.commit()
    conn.close()


def controlla_assenze():
    """Segnala i dipendenti che non hanno ancora timbrato l'entrata 30 minuti
    dopo il loro orario previsto. Evita duplicati creando al massimo una
    notifica di assenza per utente per giorno."""
    oggi = date.today()
    oggi_iso = oggi.isoformat()
    adesso = datetime.now()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE orario_inizio IS NOT NULL AND orario_inizio != ''")
    utenti = cursor.fetchall()

    for utente in utenti:
        try:
            atteso = datetime.strptime(utente['orario_inizio'], '%H:%M').time()
        except (ValueError, TypeError):
            continue

        atteso_dt = datetime.combine(oggi, atteso)
        if adesso < atteso_dt + timedelta(minutes=30):
            continue  # troppo presto per considerarlo assente

        cursor.execute(
            "SELECT 1 FROM timbrature WHERE user_id = ? AND tipo = 'entrata' AND creato_il LIKE ?",
            (utente['id'], f'{oggi_iso}%')
        )
        if cursor.fetchone():
            continue  # ha già timbrato oggi

        cursor.execute(
            "SELECT 1 FROM notifiche WHERE user_id = ? AND tipo = 'assenza' AND data_riferimento = ?",
            (utente['id'], oggi_iso)
        )
        if cursor.fetchone():
            continue  # notifica già creata oggi

        nome_completo = f"{utente['name']} {utente['cognome']}"
        conn.execute(
            '''INSERT INTO notifiche (messaggio, tipo, creato_il, user_id, data_riferimento)
               VALUES (?, ?, ?, ?, ?)''',
            (
                f"{nome_completo} non ha ancora timbrato l'entrata (prevista alle {utente['orario_inizio']})",
                'assenza',
                adesso.isoformat(),
                utente['id'],
                oggi_iso
            )
        )

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

    controlla_assenze()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY cognome, name')
    users = cursor.fetchall()

    cursor.execute('SELECT * FROM notifiche ORDER BY creato_il DESC LIMIT 30')
    notifiche = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) AS n FROM notifiche WHERE letta = 0')
    notifiche_non_lette = cursor.fetchone()['n']
    conn.close()

    return render_template(
        'admin_panel.html',
        admin_name=session['user']['name'],
        users=users,
        notifiche=notifiche,
        notifiche_non_lette=notifiche_non_lette
    )

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
        return jsonify({
            'ok': False,
            'errore': 'Nome, cognome ed email sono obbligatori'
        }), 400

    password_provvisoria = secrets.token_urlsafe(8)
    password_hash = generate_password_hash(password_provvisoria)

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''
            INSERT INTO users
            (email, password, name, cognome,
             orario_inizio, orario_pausa_inizio,
             orario_pausa_fine, orario_fine)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                email,
                password_hash,
                nome,
                cognome,
                orario_inizio,
                orario_pausa_inizio,
                orario_pausa_fine,
                orario_fine
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            'ok': False,
            'errore': 'Email già registrata'
        }), 409

    conn.close()

    msg = EmailMessage()
    msg['Subject'] = 'Password provvisoria per il tuo account'

    msg['From'] = 'christiancolleoni1@gmail.com'
    msg['To'] = email

    msg.set_content(f"""
Ciao {nome},

il tuo account è stato creato.

Email: {email}

Password provvisoria:
{password_provvisoria}

Ti consigliamo di cambiarla al primo accesso.
""")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login('christiancolleoni1@gmail.com', 'djxl pjvd gvqn irgc')
            smtp.send_message(msg)

    except Exception as e:
        return jsonify({
            'ok': False,
            'errore': f'Utente creato ma impossibile inviare l\'email: {str(e)}'
        }), 500

    return render_template(
        'admin_crea_ok.html',
        email=email,
        password=password_provvisoria
    )


@app.route('/admin/modifica/<int:user_id>', methods=['GET'])
def edit_user_page(user_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user is None:
        return jsonify({'ok': False, 'errore': 'Utente non trovato'}), 404

    return render_template('admin_modifica.html', user=user)


@app.route('/admin/modifica/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    nome = request.form.get('nome', '').strip()
    cognome = request.form.get('cognome', '').strip()
    email = request.form.get('email', '').strip().lower()
    orario_inizio = request.form.get('orario_inizio', '').strip()
    orario_pausa_inizio = request.form.get('orario_pausa_inizio', '').strip()
    orario_pausa_fine = request.form.get('orario_pausa_fine', '').strip()
    orario_fine = request.form.get('orario_fine', '').strip()

    if not nome or not cognome or not email:
        return jsonify({'ok': False, 'errore': 'Nome, cognome ed email sono obbligatori'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''UPDATE users
               SET name = ?, cognome = ?, email = ?, orario_inizio = ?,
                   orario_pausa_inizio = ?, orario_pausa_fine = ?, orario_fine = ?
               WHERE id = ?''',
            (nome, cognome, email, orario_inizio, orario_pausa_inizio,
             orario_pausa_fine, orario_fine, user_id)
        )
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'ok': False, 'errore': 'Utente non trovato'}), 404
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'ok': False, 'errore': 'Email già registrata da un altro utente'}), 409
    conn.close()

    return redirect(url_for('admin_panel'))


@app.route('/admin/elimina/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    eliminato = cursor.rowcount > 0
    conn.close()

    if not eliminato:
        return jsonify({'ok': False, 'errore': 'Utente non trovato'}), 404

    return redirect(url_for('admin_panel'))

@app.route('/admin/notifiche/segna_lette', methods=['POST'])
def segna_notifiche_lette():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifiche SET letta = 1 WHERE letta = 0')
    conn.commit()
    conn.close()

    return redirect(url_for('admin_panel'))


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
    is_admin = session.get('tipo_utente') == 'admin'
    return render_template('timbro.html', is_admin=is_admin)


@app.route('/timbro/azione', methods=['POST'])
def timbro_azione():
    if 'user' not in session:
        return jsonify({'ok': False, 'errore': 'Non autenticato'}), 401

    tipo = request.form.get('tipo', '').strip()
    if tipo not in ('entrata', 'pausa_inizio', 'pausa_fine', 'uscita'):
        return jsonify({'ok': False, 'errore': 'Tipo di timbratura non valido'}), 400
    if session.get('tipo_utente') == 'admin':
        return jsonify({'ok': True, 'registrata': False})

    user_id = session['user'].get('id')
    adesso = datetime.now()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO timbrature (user_id, tipo, creato_il) VALUES (?, ?, ?)',
        (user_id, tipo, adesso.isoformat())
    )
    conn.commit()

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    nome_completo = f"{user['name']} {user['cognome']}" if user else 'Un dipendente'
    etichette = {
        'entrata': "l'entrata",
        'pausa_inizio': "l'inizio pausa",
        'pausa_fine': "la fine pausa",
        'uscita': "l'uscita",
    }
    ora_str = adesso.strftime('%H:%M')
    messaggio = f"{nome_completo} ha timbrato {etichette[tipo]} alle {ora_str}"
    tipo_notifica = 'info'

    if tipo == 'entrata' and user and user['orario_inizio']:
        try:
            atteso = datetime.strptime(user['orario_inizio'], '%H:%M').time()
            atteso_dt = adesso.replace(hour=atteso.hour, minute=atteso.minute, second=0, microsecond=0)
            ritardo_minuti = (adesso - atteso_dt).total_seconds() / 60
            if ritardo_minuti > 10:
                messaggio += f" (in ritardo di {int(ritardo_minuti)} minuti)"
                tipo_notifica = 'alert'
        except ValueError:
            pass

    crea_notifica(messaggio, tipo=tipo_notifica, user_id=user_id, data_riferimento=adesso.date().isoformat())

    return jsonify({'ok': True, 'registrata': True})


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run('127.0.0.1', 5000, debug=True)