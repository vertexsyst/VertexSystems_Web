"""
=============================================================================
Project: Vertex Systems Web Backend
File: app.py
Last Updated: July 20, 2026

STATUS / NOTES:
- Local Python virtual environment (.venv) fully repaired and updated.
- Environment dependencies: Flask, flask-cors, pyodbc (see requirements.txt).
- Backend running on local Flask dev server (port 8000).
- Key features integrated: Security inputs, API endpoints, SQL database connections.

TODO / NEXT STEPS (Target: Early August):
1. Review persistent database connection strings and error-handling logic.
2. Address architectural and API layout questions (scheduled for Tuesday/August).
3. Test front-end integration (app.js, Dashboard.html) against live local endpoints.
=============================================================================
"""

# ==============================================================================
# SECTION 1: SYSTEM & STANDARD TOOLBOX IMPORTS
# ==============================================================================
import os          # Provides tools for file path manipulation and directory handling
import re          # Provides Regular Expression tools for strict input sanitization
import json        # Provides tools to read, parse, and write data in JSON format
import uuid        # Provides tools for generating unique identifiers (IDs)
import pyodbc      # <--- ADD THIS LINE! Restores your database connection driver

# --- WEB FRAMEWORK IMPORTS ---
from flask import Flask, jsonify, request  # RESTORES FLASK: Handles routing, JSON responses, and requests
from flask_cors import CORS                # RESTORES CORS: Authorizes cross-port browser fetches

# ==============================================================================
# SECTION 2: GLOBAL ENVIRONMENT CONFIGURATIONS
# ==============================================================================
# Make sure your connection string contains this exact pair:
# "DATABASE=VertexSecOps;"
app = Flask(__name__)
CORS(app) # 🔓 This single command explicitly authorizes cross-port browser fetches!

TEMPLATE_DIR = "./templates"
# Your database connections would sit here too
# ==================================================================================

# --- DATABASE CONFIGURATION ---
# Reads production settings from Environment Variables (Azure), with fallbacks to local SQLEXPRESS
DB_DRIVER = os.environ.get("DB_DRIVER", "{ODBC Driver 18 for SQL Server}")
DB_SERVER = os.environ.get("DB_SERVER", r".\SQLEXPRESS")
DB_NAME = os.environ.get("DB_NAME", "VertexSecOps")
DB_TRUSTED = os.environ.get("DB_TRUSTED", "yes")
DB_CERT = os.environ.get("DB_CERT", "yes")

# Dynamic Connection String built from environment or local defaults
CONN_STR = (
    f"Driver={DB_DRIVER};"
    f"Server={DB_SERVER};"
    f"Database={DB_NAME};"
    f"Trusted_Connection={DB_TRUSTED};"
    f"TrustServerCertificate={DB_CERT};"
    "Connection Timeout=30;"
)

# 📑 Ensure the function stitches the tuple array together with a clean semicolon map
def get_db_connection():
    return pyodbc.connect(CONN_STR)

# Establish the live persistence bridge to your SQL Server
conn = pyodbc.connect(CONN_STR)

# --- PAGE ROUTES (Serves HTML Front-End) ---
@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/dashboard')
def serve_dashboard():
    return app.send_static_file('Dashboard.html')

# 📥 PIPELINE 1: Inbound Ticket Consumer (POST)
@app.route('/api/tickets', methods=['POST'])
def create_ticket():
    data = request.get_json() or {}
    
    # 🔐 SERVER-SIDE VALIDATION & GENERATION
    raw_id = uuid.uuid4().hex[:8].upper() 
    secure_serial = f"VTX-2026-{raw_id}"
    
    name = data.get('name')
    email = data.get('email')
    message = data.get('message')
    
    try:
        # Initialize communication cursor
        cursor = conn.cursor()
        
        # 🔑 ALIGNED PERFECTLY WITH YOUR SSMS COLUMNS:
        cursor.execute(
            "INSERT INTO dbo.SecurityTickets (TicketSerial, ClientName, ClientEmail, MessageDetails) VALUES (?, ?, ?, ?)",
            (secure_serial, name, email, message)
        )
        conn.commit() # Lock transactions permanently into SQL Server
        cursor.close()
        
        print(f"[📡 BACKEND SUCCESS] Ticket {secure_serial} successfully committed to SQL Server.")
        return jsonify({"status": "SUCCESS", "serial": secure_serial}), 200

    except Exception as e:
        print(f"[❌ SYSTEM FAILURE] {str(e)}")
        return jsonify({"status": "SYS_ERR", "message": str(e)}), 500


# 📤 PIPELINE 2: Service Dashboard Feed (GET, PUT & DELETE)
@app.route('/api/dashboard/tickets', methods=['GET', 'PUT', 'DELETE'])
def handle_tickets():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
       # 🛰️ METHOD 1: READ FLOW (DYNAMIC MULTI-TENANT ISOLATION)
        if request.method == 'GET':
            # 🔍 Catch the "?client=" parameter from the browser URL (if passed)
            target_client = request.args.get('client') 
            
            # Base query structure
            query = """
                SELECT 
                    TicketID,       -- row[0]
                    ClientName,     -- row[1]
                    ClientEmail,    -- row[2]
                    MessageDetails, -- row[3]
                    TicketStatus,   -- row[4]
                    InternalNotes,  -- row[5]
                    AssignmentGroup,-- row[6]
                    Category,       -- row[7]
                    ClientID        -- row[8]
                FROM dbo.SecurityTickets 
            """
            
            # 🛡️ Dynamic SQL Construction based on identity parameter
            if target_client and target_client != 'ALL':
                query += " WHERE ClientID = ? ORDER BY TicketID DESC;"
                cursor.execute(query, (target_client,)) # Protective tuple parameter injection
            else:
                query += " ORDER BY TicketID DESC;"
                cursor.execute(query)
                
            rows = cursor.fetchall()
            
            tickets = []
            for row in rows:
                tickets.append({
                    "id": row[0],
                    "deviceName": row[1] if row[1] else 'Unknown Device',
                    "alertType": row[7] if row[7] else 'Security Alert',
                    "severity": "MEDIUM",
                    "riskScore": 50.0,
                    "timestamp": "Live Stream",
                    "status": row[4] if row[4] else 'NEW',
                    "notes": row[5] if row[5] else '',
                    "assignmentGroup": row[6] if row[6] else 'UNASSIGNED',
                    "tenantId": row[8] if row[8] else 'GLOBAL'
                })
            return jsonify(tickets)

        # 💾 METHOD 2: UPDATE FLOW
        elif request.method == 'PUT':
            data = request.get_json()
            ticket_id = data.get('id')
            new_status = data.get('status')
            new_notes = data.get('notes')

            if not ticket_id:
                return jsonify({"status": "ERROR", "message": "Missing Ticket ID"}), 400

            cursor.execute("""
                UPDATE dbo.SecurityTickets
                SET TicketStatus = ?, InternalNotes = ?
                WHERE TicketID = ?;
            """, (new_status, new_notes, ticket_id))
            
            conn.commit()
            return jsonify({"status": "SUCCESS", "message": f"Ticket {ticket_id} operational log committed."})

        # 💥 METHOD 3: PURGE FLOW
        elif request.method == 'DELETE':
            cursor.execute("DELETE FROM dbo.SecurityTickets;")
            conn.commit()
            return jsonify({"status": "SUCCESS", "message": "Tables successfully flashed."})

    except Exception as e:
        print(f"❌ Database Operations Failure: {e}")
        return jsonify({"error": "Internal infrastructure failure reading database storage."}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/api/dashboard/aging', methods=['GET'])
def get_aging_queue():
    """
    🚨 FETCH AGING OPERATIONAL QUEUE
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TicketSerial, ClientName, ClientEmail, MessageDetails FROM dbo.SecurityTickets ORDER BY TicketID ASC")
        rows = cursor.fetchall()
        
        queue = []
        for row in rows:
            queue.append({
                "serial": row[0],
                "name": row[1],
                "email": row[2],
                "message": row[3]
            })
            
        cursor.close()
        return jsonify(queue), 200
    except Exception as e:
        print(f"❌ Queue Fetch Database Failure: {e}")
        return jsonify({"error": "Internal infrastructure failure reading database storage."}), 500

    finally:
            cursor.close()
            conn.close()    

# ==============================================================================
# SECTION 3: THE ROUTES & LOGIC (The Core Engine)
# ==============================================================================
# This is where we handle incoming actions from the web browser.
# Instead of complex classes, Flask uses simple "routes" (@app.route).

@app.route('/api/preview', methods=['POST'])
def secure_preview():
    """
    [API HANDSHAKE ROUTINE]
    Listens for clicks from app.js and processes them safely.
    """
    try:
        data = request.get_json()
        client_id = data.get("client_id", "default_client")
        requested_template = data.get("template_name", "")
        
        # 🛡️ Input Validation / Sanitization
        clean_name = os.path.basename(requested_template)
        clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '', clean_name)
        
        # Whitelist format check
        _, ext = os.path.splitext(clean_name)
        if ext.lower() not in ['.html', '.json']:
            return jsonify({"status": "Error", "message": "Unauthorized format."}), 400

        # Success Response
        return jsonify({
            "status": "Success",
            "client_id": client_id,
            "template": clean_name,
            "render_url": f"/previews/{client_id}/{clean_name}"
        }), 200

    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500
    
# ==============================================================================
# SECTION 4: RUNTIME DRIVER (The Ignition Switch)
# ==============================================================================
if __name__ == "__main__":
    # You can explicitly set your host and port right here
    app.run(host="127.0.0.1", port=8000, debug=True)
# ===============================================================================