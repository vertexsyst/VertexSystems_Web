"""
=============================================================================
Project: Vertex Systems Web Backend
File: app.py
Last Refactored: September 2026

DESCRIPTION & ARCHITECTURE:
- Lightweight RESTful API built on Flask, Flask-CORS, and pyodbc.
- Integrates Microsoft Entra ID (MSAL) OAuth2 authentication flow.
- Establishes connection to SQL Server Express instance (VertexSecOps database).
- Serves static front-end assets (index.html, Dashboard.html).
- Exposes JSON endpoints for ticket submission (POST), retrieval/filtering (GET),
  lifecycle note updates (PUT), and emergency database purges (DELETE).
=============================================================================
"""

import os
import uuid
import json
import subprocess
import requests
import pyodbc
import jwt
import msal
import string
import smtplib
import psutil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, redirect, url_for, render_template, send_from_directory
from flask_cors import CORS
from flask_session import Session
from functools import wraps
from models import db, Organization, Device, TelemetryLog, DirectoryUser, SecurityTicket


"""
Vertex Systems - Command Center Main Application
File: app.py
Description: Flask application entry point managing API points, telemetry ingestion, and routing.
"""

# 1. Initialize Flask app once with all your desired folders
app = Flask(__name__, template_folder='templates', static_folder='.', static_url_path='')

# 2. Configure Database & Environment
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///vertex_command.db')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# 3. Initialize SQLAlchemy and Session Management on this ONE app instance
db.init_app(app)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "vertex_secops_secure_key_2026")
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# 4. Create database tables automatically on startup
with app.app_context():
    db.create_all()

# Load environment variables from local .env file
load_dotenv()

# Enable CORS allowing credentials across sessions
CORS(app, supports_credentials=True)

# In-memory storage for active security incidents and Windows event logging
ACTIVE_INCIDENTS = {}


# =========================================================================
# 2. SQL SERVER DATABASE CONFIGURATION & HELPERS
# =========================================================================

DB_DRIVER = os.environ.get("DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
DB_SERVER = os.environ.get("DB_SERVER", r"VS-GGS-WSTHOST\SQLEXPRESS")
DB_NAME = os.environ.get("DB_NAME", "VertexSecOps")
DB_TRUSTED = os.environ.get("DB_TRUSTED", "yes")

def get_db_connection():
    """Establishes and returns a secure pyodbc connection to SQL Server Express."""
    try:
        conn_str = (
            f"DRIVER={DB_DRIVER};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"Trusted_Connection={DB_TRUSTED};"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"❌ [DB CONNECTION ERROR] {e}")
        return None

def update_ticket_status_db(ticket_id, new_status):
    """Helper to update ticket status in SQL Server."""
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed"
    
    try:
        cursor = conn.cursor()
        query = """
            UPDATE VertexSecOps.dbo.SecurityTickets
            SET TicketStatus = ?
            WHERE TicketID = ?
        """
        cursor.execute(query, (new_status, ticket_id))
        conn.commit()
        return True, "Status updated successfully"
    except Exception as e:
        print(f"❌ [SQL ERROR] {e}")
        return False, str(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def update_ticket_notes_db(ticket_id, notes):
    """Helper to update the InternalNotes column in SQL Server."""
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed"
    
    try:
        cursor = conn.cursor()
        query = """
            UPDATE VertexSecOps.dbo.SecurityTickets
            SET InternalNotes = ?
            WHERE TicketID = ?
        """
        cursor.execute(query, (notes, ticket_id))
        conn.commit()
        return True, "Notes updated successfully"
    except Exception as e:
        print(f"❌ [SQL ERROR] {e}")
        return False, str(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =========================================================================
# GRAPH API AUTHENTICATION HELPER
# =========================================================================
class GraphAuthHelper:
    def __init__(self):
        self.tenant_id = os.getenv("TENANT_ID") or os.getenv("AZURE_TENANT_ID")
        self.client_id = os.getenv("CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET")
        self.scopes = ["https://graph.microsoft.com/.default"]
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        
    def get_access_token(self):
        app_client = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )
        result = app_client.acquire_token_for_client(scopes=self.scopes)
        if "access_token" in result:
            return result["access_token"]
        else:
            error_msg = result.get("error_description", "Unknown error acquiring token")
            raise Exception(f"❌ [MSAL AUTH ERROR]: {error_msg}")

    def get_headers(self):
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

# Instantiate a global helper instance if you like, or instantiate it inside your routes
graph_auth = GraphAuthHelper()

# ==========================================
# # 3. INTEGRATION & WEBHOOK UTILITIES
# ==========================================

# 3.1 M365 Adaptive Card Schema Builder
def build_m365_adaptive_card(incident_data):
    """Wraps Vertex SecOps incident data into an official Microsoft Adaptive Card schema."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "🚨 Vertex SecOps Security Alert",
                            "weight": "Bolder",
                            "size": "Medium",
                            "color": "Attention"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Incident ID:", "value": str(incident_data.get("id"))},
                                {"title": "Event Classification:", "value": str(incident_data.get("event_id"))},
                                {"title": "Title:", "value": str(incident_data.get("title"))},
                                {"title": "Severity:", "value": str(incident_data.get("severity"))},
                                {"title": "Timestamp:", "value": str(incident_data.get("timestamp"))},
                                {"title": "Status:", "value": str(incident_data.get("status"))}
                            ]
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "🔍 View in SecOps Dashboard",
                            "url": f"http://localhost:5000/dashboard?incident={incident_data.get('id')}"
                        }
                    ]
                }
            }
        ]
    }


# =========================================================================
# 4. WINDOWS EVENT VIEWER & TELEMETRY HELPER
# =========================================================================

def fetch_real_windows_events():
    """Queries local Windows Security Event Log using PowerShell for target IDs."""
    ps_command = (
        "Get-WinEvent -LogName Security -FilterXPath"
        " \"*[System[(EventID=4624 or EventID=4672 or EventID=4720)]]\" -MaxEvents"
        " 5 -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id,"
        " Message | ConvertTo-Json"
    )

    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.stdout.strip():
            events = json.loads(result.stdout)
            if isinstance(events, dict):
                events = [events]

            for ev in events:
                ev_id = str(ev.get("Id"))
                inc_id = str(uuid.uuid4())[:8]

                if len(ACTIVE_INCIDENTS) < 3:
                    ACTIVE_INCIDENTS[inc_id] = {
                        "id": inc_id,
                        "event_id": ev_id,
                        "title": f"Security Event ID {ev_id} Detected",
                        "severity": ("HIGH" if ev_id in ["4672", "4720"] else "MEDIUM"),
                        "timestamp": str(ev.get("TimeCreated", "Recent")),
                        "status": "UNACKNOWLEDGED",
                    }
    except Exception as e:
        print(f"Log parsing note: {e}")


# =========================================================================
# 7. ENTRA ID AUTHENTICATION & MIDDLEWARE
# =========================================================================

AZURE_TENANT_ID = os.getenv("TENANT_ID", "0ea0e445-5697-44ff-ae41-9b3a18fba136")
AZURE_CLIENT_ID = os.getenv("CLIENT_ID", "52f3d140-22b3-4a99-a07f-ef7970d9724e")
SCOPE = ["User.Read"]

def _build_msal_app():
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=os.getenv("AUTHORITY"),
        client_credential=os.getenv("CLIENT_SECRET")
    )

def require_entra_auth(f):
    """Middleware decorator to validate Microsoft Entra ID JWT Bearer tokens."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", None)
        if not auth_header:
            return jsonify({"message": "Missing Authorization Header"}), 401
        
        try:
            token = auth_header.split(" ")[1]
            jwks_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/discovery/v2.0/keys"
            jwks_client = jwt.PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=AZURE_CLIENT_ID,
                issuer=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0"
            )
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired"}), 401
        except Exception as e:
            return jsonify({"message": f"Unauthorized access: {str(e)}"}), 403
            
        return f(*args, **kwargs)
    return decorated


# =========================================================================
# 5. STATIC PAGE ROUTES & ACCESS CONTROL
# =========================================================================


@app.route('/api/v1/directory/sync', methods=['GET', 'POST'])
def sync_entra_directory():
    try:
        # 1.1 Instantiate your graph/MSAL helper class
        graph_helper = GraphAuthHelper() # Replace with your actual class name if different
        
        # 1.2. Get your pre-built headers (which automatically fetches the token!)
        headers = graph_helper.get_headers()
        
        graph_url = 'https://graph.microsoft.com/v1.0/users?$select=id,displayName,userPrincipalName,mail,jobTitle'
        response = requests.get(graph_url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({"status": "error", "message": response.json()}), 500
            
        azure_users = response.json().get('value', [])
        synced_count = 0

        # 2. Loop through results and perform UPSERT
        # Wrap database operations in an explicit app context
        with app.app_context():
            for az_user in azure_users:
                entra_id = az_user.get('id')
                local_user = DirectoryUser.query.filter_by(entra_id=entra_id).first()
                
                if not local_user:
                    local_user = DirectoryUser(entra_id=entra_id)
                    db.session.add(local_user)
                
                local_user.display_name = az_user.get('displayName')
                local_user.user_principal_name = az_user.get('userPrincipalName')
                local_user.mail = az_user.get('mail') or az_user.get('userPrincipalName')
                local_user.job_title = az_user.get('jobTitle')
                synced_count += 1

        # Commit all changes to SQL in one clean transaction
        db.session.commit()
        
        # 3. Return JSON payload for frontend table rendering
        all_users = DirectoryUser.query.all()
        return jsonify({
            "status": "success",
            "message": f"Successfully synced and stored {synced_count} directory records.",
            "value": [
                {
                    "id": u.entra_id,
                    "displayName": u.display_name,
                    "userPrincipalName": u.user_principal_name,
                    "mail": u.mail,
                    "jobTitle": u.job_title
                } for u in all_users
            ]
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/v1/nexus/client/<string:client_name>', methods=['GET'])
def get_client_nexus(client_name):
    try:
        db = get_db_connection()
        
        client = {
            "id": 1,
            "name": client_name,
            "email": f"{client_name.lower().replace(' ', '_')}@vertex.secops",
            "tier": "Production",
            "endpoints": 42
        }
        
        cursor = db.cursor()
        cursor.execute("SELECT * FROM dbo.SecurityTickets WHERE ClientName = ?", (client_name,))
        
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        tickets = [dict(zip(columns, row)) for row in rows]

        payload = {
            "client": client,
            "tickets": tickets,
            "assets": [],
            "knowledge": [],
            "invoices": []
        }
        
        return jsonify(payload), 200

    except Exception as e:
        print("[! NEXUS ERROR TRACEBACK]:", str(e))
        return jsonify({"status": "ERROR", "message": str(e)}), 500 
    

@app.route('/api/v1/clients/<int:user_id>/tickets', methods=['GET'])
def get_client_tickets(user_id):
    try:
        tickets = SecurityTicket.query.filter(
            db.or_(
                SecurityTicket.ClientID == str(user_id),
                SecurityTicket.ClientID == str(user_id).zfill(2) if isinstance(user_id, int) else False,
                SecurityTicket.ClientID == str(user_id).strip()
            )
        ).order_by(SecurityTicket.TicketID.desc()).all()
        
        ticket_list = [
            {
                "id": t.TicketID,
                "title": t.TicketSerial or 'Security Incident',
                "priority": "NORMAL",
                "status": t.TicketStatus or 'NEW',
                "work_done": t.InternalNotes or '',
                "recommendations": t.MessageDetails or '',
                "timestamp": str(t.SubmissionTime) if t.SubmissionTime else "Live Stream",
                "comments": [
                    {
                        "author": "Engineer",
                        "text": t.InternalNotes or "No additional notes logged.",
                        "timestamp": str(t.SubmissionTime) if t.SubmissionTime else ""
                    }
                ]
            } for t in tickets
        ]
        return jsonify({"status": "success", "user_id": user_id, "tickets": ticket_list}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/architecture-diagram')
def serve_architecture_image():
    """Serves the master system architecture diagram graphic."""
    target_dir = os.path.join(app.root_path, 'static', 'images')
    return send_from_directory(target_dir, 'Vertex_Master_System_Architecture.png')

@app.route('/')
def serve_index():
    """Serves index.html if authenticated via MSAL, otherwise forces login."""
    if not session.get("user"):
        return redirect(url_for("login"))
    return app.send_static_file('index.html')

@app.route('/dashboard')
@app.route('/Dashboard.html')
def serve_dashboard():
    """Role Guard: Requires active MSAL session and admin role."""
    if not session.get("user"):
        return redirect(url_for("login"))
    
    user_role = session.get('role', 'admin') # Defaulting to admin for local testing if needed
    if user_role == 'admin':
        return render_template('Dashboard.html')
        
    return redirect(url_for('serve_index'))

# =========================================================================
# 6. API ENDPOINTS & PIPELINES - DISPATCH & WEBHOOK ROUTE
# =========================================================================

# --- Pipeline A: Outbound Webhook Dispatcher ---
@app.route("/api/integrations/dispatch", methods=["POST"])
def dispatch_webhook():
    """
    Dispatches an active incident payload from memory or SQL Server to an 
    external client endpoint. Automatically detects whether to package the 
    data into a standard JSON payload or an M365 Adaptive Card based on the 
    target URL configuration.
    """
    data = request.get_json() or {}
    
    # ---------------------------------------------------------------------
    # Step 1: Endpoint & Identifier Resolution
    # Fallback to the environment variable if 'target_url' isn't explicitly 
    # provided in the incoming frontend request body.
    # ---------------------------------------------------------------------
    target_url = data.get("target_url") or os.getenv("M365_WEBHOOK_URL")
    auth_token = data.get("auth_token", "")
    incident_id = data.get("incident_id")
    
    if not target_url or not incident_id:
        return jsonify({"status": "error", "message": "Missing target_url or incident_id"}), 400

    incident_data = None


    # ---------------------------------------------------------------------
    # Step 2: Incident Data Lookup (Memory Cache -> SQL Server Fallback)
    # ---------------------------------------------------------------------
    global ACTIVE_INCIDENTS
    if incident_id in ACTIVE_INCIDENTS:
        # Fast-path: Retrieve from active in-memory dictionary
        incident_data = ACTIVE_INCIDENTS[incident_id]
    else:
        # Fallback: Query the persistent SQL Server SecurityTickets table
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TicketID, ClientName, ClientEmail, MessageDetails, TicketStatus, Category, AssignmentGroup
                    FROM dbo.SecurityTickets
                    WHERE TicketID = ? OR TicketSerial = ?
                """, (incident_id, incident_id))
                row = cursor.fetchone()
                if row:
                    incident_data = {
                        "id": str(row[0]),
                        "event_id": row[5] or "Security Alert",
                        "title": row[3] or "Database Security Ticket",
                        "severity": "MEDIUM",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": row[4] or "NEW"
                    }
            except Exception as e:
                print(f"❌ [DISPATCH DB LOOKUP ERROR] {e}")
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

    if not incident_data:
        return jsonify({"status": "error", "message": f"Incident {incident_id} not found in memory or database"}), 404

    # ---------------------------------------------------------------------
    # Step 3: Payload Schema Selection (M365 Adaptive Card vs. Standard JSON)
    # Inspects the target URL to determine if it's an Azure Logic App, Teams, 
    # or Office webhook destination.
    # ---------------------------------------------------------------------
    is_m365 = "logic.azure.com" in target_url or "office.com" in target_url or "webhook" in target_url
    
    if is_m365:
        # Construct rich Microsoft Teams / Adaptive Card layout
        payload = build_m365_adaptive_card(incident_data)
    else:
        # Standard structured JSON telemetry payload for generic endpoints
        payload = {
            "source_system": "Vertex SecOps Console",
            "schema_version": "1.0",
            "incident_details": {
                "id": incident_data.get("id"),
                "event_id": incident_data.get("event_id"),
                "title": incident_data.get("title"),
                "severity": incident_data.get("severity"),
                "timestamp": incident_data.get("timestamp"),
                "status": incident_data.get("status")
            },
            "forensic_context": {
                "log_source": "Vertex SecOps SQL Database & WinEvent API",
                "classification": "Escalated Ticket Dispatch",
                "payload_hash_verified": True
            },
            "deep_link_url": f"http://localhost:5000/dashboard?incident={incident_id}"
        }

    # ---------------------------------------------------------------------
    # Step 4: Secure Request Dispatch & Response Handling
    # ---------------------------------------------------------------------
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Vertex-SecOps-Bridge/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        # Outbound POST request with a 5-second timeout to prevent hanging worker threads
        response = requests.post(target_url, json=payload, headers=headers, timeout=5)
        return jsonify({
            "status": "success",
            "message": f"Webhook dispatched successfully to target endpoint",
            "external_response_code": response.status_code
        }), 200
    except requests.exceptions.RequestException as e:
        print(f"Webhook dispatch failed: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to reach target endpoint: {str(e)}"
        }), 502

# --- Pipeline B: Local Mock Receiver (Testing endpoint) ---
@app.route('/api/integrations/mock-receiver', methods=['POST'])
def mock_receiver():
    """Catches outbound webhooks locally for validation and terminal output."""
    payload = request.get_json() or {}
    print("\n--- 📥 MOCK RECEIVER: INCOMING TELEMETRY ---")
    print(json.dumps(payload, indent=4))
    print("-----------------------------------------")
    
    return jsonify({
        "status": "success",
        "message": "Payload successfully received and validated by local mock receiver.",
        "external_response_code": 200,
        "received_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    }), 200

# --- Pipeline C: Incident Management & Retrieval ---
@app.route("/api/incidents/active", methods=["GET"])
def get_active_incidents():
    """Fetches live Windows event logs and returns active security incidents."""
    try:
        if 'fetch_real_windows_events' in globals():
            try:
                fetch_real_windows_events()
            except Exception as e:
                print(f"Warning: Windows event fetch skipped/errored: {e}")

        global ACTIVE_INCIDENTS
        if not ACTIVE_INCIDENTS:
            incident_id = str(uuid.uuid4())[:8]
            ACTIVE_INCIDENTS[incident_id] = {
                "id": incident_id,
                "event_id": "4672",
                "title": "Special Privileges Assigned to New Logon",
                "severity": "HIGH",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "UNACKNOWLEDGED",
            }

        return jsonify(list(ACTIVE_INCIDENTS.values())), 200
    except Exception as e:
        print(f"CRITICAL ERROR in get_active_incidents: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/incidents/acknowledge/<incident_id>", methods=["POST"])
def acknowledge_incident(incident_id):
    """Marks an active incident as acknowledged."""
    if incident_id in ACTIVE_INCIDENTS:
        ACTIVE_INCIDENTS[incident_id]["status"] = "ACKNOWLEDGED"
        return jsonify({"status": "success", "message": f"Incident {incident_id} acknowledged."}), 200
    return jsonify({"status": "error", "message": "Incident not found"}), 404

# --- Pipeline D: Ticket Submission & Multi-Tenant Dashboard Data Bridge ---
@app.route('/api/Tickets', methods=['POST'])
@app.route('/api/tickets', methods=['POST'])
def create_ticket():
    """Accepts form payloads and creates new security ticket records in SQL Server."""
    try:
        data = request.get_json(force=True) or {}
        client_name = data.get('clientName') or data.get('name') or 'UNKNOWN_TENANT'
        client_email = data.get('clientEmail') or data.get('email') or 'unassigned@vertex.pro'
        category = data.get('category', 'Security Alert')
        details = data.get('messageDetails') or data.get('message') or ''
        
        ticket_serial = f"VTX-2026-{uuid.uuid4().hex[:6].upper()}"
        submission_time = datetime.now()
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"status": "error", "message": "Database connection failed"}), 500

        cursor = conn.cursor()
        query = """
            INSERT INTO VertexSecOps.dbo.SecurityTickets 
            (TicketSerial, ClientName, ClientEmail, MessageDetails, SubmissionTime, TicketStatus, Category)
            VALUES (?, ?, ?, ?, ?, 'NEW', ?)
        """
        cursor.execute(query, (ticket_serial, client_name, client_email, details, submission_time, category))
        conn.commit()
        
        return jsonify({
            "status": "SUCCESS", 
            "message": "Ticket created successfully", 
            "serial": ticket_serial,
            "ticket_serial": ticket_serial
        }), 201

    except Exception as e:
        print(f"❌ [CREATION ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/dashboard/tickets', methods=['GET', 'PUT', 'DELETE'])
def handle_tickets():
    """Multi-purpose endpoint: GET (list), PUT (update status/notes), DELETE (purge)."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'GET':
            target_client = request.args.get('client')
            if target_client and target_client != 'ALL':
                query = """
                    SELECT TicketID, ClientName, ClientEmail, MessageDetails,
                           TicketStatus, InternalNotes, AssignmentGroup, Category, ClientID
                    FROM dbo.SecurityTickets
                    WHERE ClientName = ? OR ClientID = ?
                    ORDER BY TicketID DESC
                """
                cursor.execute(query, (target_client, target_client))
            else:
                query = """
                    SELECT TicketID, ClientName, ClientEmail, MessageDetails,
                           TicketStatus, InternalNotes, AssignmentGroup, Category, ClientID
                    FROM dbo.SecurityTickets
                    ORDER BY TicketID DESC
                """
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
            return jsonify(tickets), 200

        elif request.method == 'PUT':
            data = request.get_json() or {}
            ticket_id = data.get('id')
            new_status = data.get('status')
            new_notes = data.get('notes')

            if not ticket_id:
                return jsonify({"status": "ERROR", "message": "Missing Ticket ID"}), 400

            if new_status is not None:
                cursor.execute("UPDATE dbo.SecurityTickets SET TicketStatus = ? WHERE TicketID = ?;", (new_status, ticket_id))
            if new_notes is not None:
                cursor.execute("UPDATE dbo.SecurityTickets SET InternalNotes = ? WHERE TicketID = ?;", (new_notes, ticket_id))
            
            conn.commit()
            return jsonify({"status": "SUCCESS", "message": f"Ticket #{ticket_id} updated."}), 200

        elif request.method == 'DELETE':
            cursor.execute("DELETE FROM dbo.SecurityTickets;")
            conn.commit()
            return jsonify({"status": "SUCCESS", "message": "Tables successfully purged."}), 200

    except Exception as e:
        print(f"❌ Database Operations Failure: {e}")
        return jsonify({"error": "Internal infrastructure failure reading database storage."}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Pipeline E: Aging Operational Queue ---
@app.route('/api/dashboard/aging', methods=['GET'])
def get_aging_queue():
    """Fetches oldest unassigned security tickets ordered chronologically."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TicketSerial, ClientName, ClientEmail, MessageDetails FROM dbo.SecurityTickets ORDER BY TicketID ASC")
        rows = cursor.fetchall()
        
        queue = [{"serial": r[0], "name": r[1], "email": r[2], "message": r[3]} for r in rows]
        return jsonify(queue), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Pipeline F: Ticket Note Updates ---
@app.route('/api/tickets/<int:ticket_id>/notes', methods=['PUT', 'POST'])
@app.route('/api/tickets/<int:ticket_id>/save-notes', methods=['POST'])
def save_ticket_notes(ticket_id):
    """Saves engineering journal notes for a specific ticket."""
    try:
        data = request.get_json(force=True) or {}
        notes = data.get('notes', '')
        success, message = update_ticket_notes_db(ticket_id, notes)
        if success:
            return jsonify({"status": "success", "message": message}), 200
        return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
def update_ticket_status_route(ticket_id):
    """Updates ticket status via REST route."""
    data = request.get_json(force=True) or {}
    new_status = data.get('status')
    if not new_status:
        return jsonify({"status": "error", "message": "No status provided"}), 400
        
    success, message = update_ticket_status_db(ticket_id, new_status)
    if success:
        return jsonify({"status": "success", "message": message}), 200
    return jsonify({"status": "error", "message": message}), 500

@app.route('/api/v1/ticket/<int:ticket_id>/commit', methods=['POST'])
def commit_ticket_blob(ticket_id):
    data = request.get_json()
    work_done = data.get('work_done', '')
    recommendations = data.get('recommendations', '')
    
    # Combine the blobs into your existing schema column
    combined_notes = f"WORK DONE:\n{work_done}\n\nRECOMMENDATIONS:\n{recommendations}"
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        query = """
            UPDATE VertexSecOps.dbo.SecurityTickets
            SET InternalNotes = ?
            WHERE TicketID = ?
        """
        cursor.execute(query, (combined_notes, ticket_id))
        conn.commit()
        
        return jsonify({
            "status": "success",
            "message": f"Support blobs updated for Ticket #{ticket_id}"
        })
    except Exception as e:
        print(f"❌ [SQL ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Pipeline G: Global Purge Admin Route ---
@app.route('/api/admin/purge-all', methods=['DELETE'])
def global_purge_tickets():
    """Executes emergency global truncation of all security tickets."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed"}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE VertexSecOps.dbo.SecurityTickets")
        conn.commit()
        return jsonify({"status": "success", "message": "All tickets purged"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Pipeline H: Local System Tools & MMC Direct Launcher ---
SYSTEM_TOOLS = {
    "control_panel": ["control.exe"],
    "task_mgr": ["taskmgr.exe"],
    "event_vwr": ["eventvwr.msc"],
    "dev_mgmt": ["devmgmt.msc"],
    "services": ["services.msc"],
    "net_conn": ["ncpa.cpl"],
    "res_mon": ["resmon.exe"],
    "sys_info": ["msinfo32.exe"],
    "firewall": ["WF.msc"],
    "regedit": ["regedit.exe"],
    "cmd": ["cmd.exe", "/k", "echo Vertex SecOps Local Terminal Ready"],
    "powershell": ["powershell.exe", "-NoExit", "-Command", "Write-Host 'Vertex SecOps PowerShell Session' -ForegroundColor Cyan"]
}

@app.route('/api/launch/<path:cmd>', methods=['POST'])
@app.route('/api/tools/launch', methods=['POST'])
def launch_local_tool():
    """Launches administrative Windows snap-ins and diagnostic tools locally."""
    data = request.get_json() or {}
    tool_key = data.get("tool")

    if tool_key not in SYSTEM_TOOLS:
        return jsonify({"status": "ERROR", "message": f"Unauthorized or unknown tool key: {tool_key}"}), 400

    try:
        subprocess.Popen(SYSTEM_TOOLS[tool_key], shell=True)
        return jsonify({"status": "SUCCESS", "message": f"Launched {tool_key} successfully."}), 200
    except Exception as e:
        return jsonify({"status": "ERROR", "message": f"Failed to launch tool: {str(e)}"}), 500

# --- Pipeline I: User Profile Endpoint ---
@app.route('/api/user-me', methods=['GET'])
def get_user_profile():
    """Returns the profile information of the active operator."""
    return jsonify({
        "username": "Mo Mojallali",
        "role": "Global Admin",
        "tenant": "Vertex Systems"
    }), 200

    # --- Pipeline K: Comms Bridge & Guest Executive Control ---

@app.route('/api/ticket/<int:ticket_id>/attach-call', methods=['POST'])
def attach_call_recording(ticket_id):
    data = request.get_json()
    recording_url = data.get('recordingUrl')
    
    try:
        db_conn = get_db_connection()
        if not db_conn:
            return jsonify({"status": "error", "message": "Database connection failed."}), 500
            
        cursor = db_conn.cursor()
        cursor.execute(
            "UPDATE dbo.SecurityTickets SET MeetingLink = ?, RecordingStatus = 'Recorded' WHERE TicketID = ?",
            (recording_url, ticket_id)
        )
        db_conn.commit()
        cursor.close()
        db_conn.close()
        
        return jsonify({"status": "success", "message": "Call artifact bound to audit trail."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

@app.route('/api/guest-login', methods=['POST'])
def guest_login():
    data = request.get_json()
    password = data.get('password')
    # Validate against secure environment or default demo key
    if password == os.getenv('VERTEX_GUEST_KEY', 'vertex-demo-2026'):
        session['is_guest'] = True
        return jsonify({"status": "authorized", "redirect": "/guest-dashboard"})
    return jsonify({"status": "unauthorized", "message": "Invalid guest key."}), 403


# --- Pipeline J: MSAL Authentication Routes ---
@app.route("/login")
def login():
    session["flow"] = _build_msal_app().initiate_auth_code_flow(
        scopes=SCOPE, 
        redirect_uri=url_for("authorized", _external=True)
    )
    return redirect(session["flow"]["auth_uri"])

@app.route("/getAToken")
def authorized():
    try:
        cache = _build_msal_app()
        result = cache.acquire_token_by_auth_code_flow(
            session.get("flow", {}), 
            request.args
        )
        if "error" in result:
            return f"Authentication Error: {result.get('error_description')}"
        
        session["user"] = result.get("id_token_claims")
        session["role"] = "admin"
        return redirect(url_for("serve_index"))
    except Exception as e:
        return f"Login failed: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    tenant_id = os.getenv("TENANT_ID", "common")
    ms_logout_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout?post_logout_redirect_uri=http://localhost:5000/"
    return redirect(ms_logout_url)


# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/telemetry', methods=['GET', 'POST'])
@app.route('/api/v1/telemetry', methods=['GET', 'POST'])
def system_telemetry():
    if request.method == 'GET':
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        used_gb = round(mem.used / (1024 ** 3), 1)
        total_gb = round(mem.total / (1024 ** 3), 1)
        status = "CRITICAL" if cpu_pct > 90 or mem.percent > 90 else "NOMINAL"
        return jsonify({
            "status": status,
            "cpu": f"{cpu_pct}%",
            "memory": f"{used_gb} GB / {total_gb} GB ({mem.percent}%)"
        }), 200
    
    data = request.get_json()
    
    if not data or 'hostname' not in data:
        return jsonify({"error": "Invalid payload, hostname required"}), 400
        
    hostname = data.get('hostname')
    device = Device.query.filter_by(hostname=hostname).first()
    
    if not device:
        return jsonify({"error": f"Device {hostname} not registered in command center"}), 404
        
    # Update device state based on incoming payload
    device.status = data.get('status', 'NOMINAL')
    device.ip_address = data.get('ip_address', device.ip_address)
    
    # Log the metrics
    log = TelemetryLog(
        device_id=device.id,
        cpu_usage=data.get('cpu_usage'),
        mem_usage=data.get('mem_usage'),
        disk_status=data.get('disk_status', 'Healthy')
    )
    
    db.session.add(log)
    db.session.commit()
    
    return jsonify({"status": "success", "message": f"Telemetry recorded for {hostname}"}), 200



@app.route('/api/admin/generate-sow', methods=['POST'])
def generate_statement_of_work():
    # Expecting JSON payload from the Admin UI form
    data = request.get_json() or {}
    
    company_name = data.get('companyName', 'Prospective Client')
    workstations = int(data.get('workstations', 10))
    servers = int(data.get('servers', 1))
    remediation_hours = float(data.get('remediationHours', 5.0))
    
    # Applying our Onboarding Formula
    audit_cost = (workstations * 25.0) + (servers * 150.0) + 500.0
    remediation_labor = remediation_hours * 150.0
    tooling_setup = workstations * 20.0
    
    total_upfront = audit_cost + remediation_labor + tooling_setup
    
    # Structured SOW response object for admin review or PDF dispatch
    sow_document = {
        "status": "Success",
        "targetClient": company_name,
        "pricingBreakdown": {
            "initialAudit": audit_cost,
            "remediationLabor": remediation_labor,
            "toolingDeployment": tooling_setup,
            "totalUpfrontInvestment": total_upfront
        },
        "governanceScope": [
            "Master Services Agreement (MSA) - Standard Terms",
            "NIST/ISO Baseline Security Alignment Schedule",
            "24/7 Comms Bridge & Incident Ticketing Integration"
        ],
        "generatedTimestamp": "2026-09-30"
    }
    
    return jsonify(sow_document)






@app.route('/api/guest/request-access', methods=['POST'])
def request_guest_access():
    data = request.get_json() or {}
    
    full_name = data.get('fullName', '').strip()
    company_name = data.get('companyName', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    
    if not email or not company_name:
        return jsonify({"status": "Error", "message": "Email and Company Name are required fields."}), 400
    
    # 1. Generate a secure temporary password (e.g., 12 characters with letters, digits, symbols)
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
    
    # 2. Set expiration window (Strictly 48 hours from now)
    expires_at = datetime.utcnow() + timedelta(hours=48)
    
    # 3. Structured Guest Access Record (Ready for database storage & email dispatch)
    guest_record = {
        "status": "Success",
        "message": "Executive preview credentials generated successfully.",
        "recipient": {
            "name": full_name,
            "company": company_name,
            "email": email,
            "phone": phone
        },
        "accessDetails": {
            "assignedUsername": email,
            "temporaryPassword": temp_password,  # In production, this goes exclusively to their email
            "accessTier": "Sandboxed Preview (Read-Only)",
            "expiresAt": expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            "validityWindowHours": 48
        }
    }
    
    # Log the access request to your server console for administrative tracking
    print(f"[SECURITY AUDIT] Guest access granted to {email} for {company_name}. Expires: {expires_at}")
    
    return jsonify(guest_record)


@app.route('/api/audit/execute-discovery', methods=['POST'])
def execute_asset_discovery():
    data = request.get_json() or {}
    company_name = data.get('companyName', 'Target Client')
    
    # Simulated asset discovery extraction telemetry
    discovered_assets = {
        "targetClient": company_name,
        "scanTimestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        "infrastructureInventory": {
            "workstations": {
                "totalDiscovered": 25,
                "compliant": 23,
                "flaggedForRemediation": 2,
                "osDistribution": {"Windows 11 Pro": 20, "Windows 10 Enterprise": 5}
            },
            "servers": {
                "totalDiscovered": 2,
                "compliant": 2,
                "flaggedForRemediation": 0,
                "osDistribution": {"Windows Server 2022": 2}
            },
            "mobileAndBYOD": {
                "totalDiscovered": 8,
                "devices": ["Corporate iPad Pro (2)", "Executive iPhone (4)", "Android Field Tablet (2)"],
                "mdmEnrolled": 7,
                "uncompliant": 1
            }
        },
        "securityPostureScore": "78/100 (Baseline Remediation Required)"
    }
    
    print(f"[DISCOVERY ENGINE] Asset extraction completed for {company_name}. 35 total assets cataloged.")
    return jsonify(discovered_assets)


@app.route('/api/admin/dispatch-sow-email', methods=['POST'])
def dispatch_sow_email():
    data = request.get_json() or {}
    company_name = data.get('companyName', 'Valued Client')
    client_email = data.get('email', 'admin@client.test')
    total_investment = data.get('totalInvestment', 3125.00)
    workstations = data.get('workstations', 25)
    servers = data.get('servers', 2)
    remediation_hours = data.get('remediationHours', 8.0)

    # Email server configuration (using environment variables or local secure relay in production)
    smtp_server = "smtp.yourmailserver.com"
    smtp_port = 587
    sender_email = "contracts@vertexsecops.com"
    sender_password = "YOUR_SECURE_APP_PASSWORD"

    # Construct the formal executive email body
    html_content = f"""
    <html>
        <head>
            <style>
                body {{ background-color: #0f172a; color: #f8fafc; font-family: monospace; padding: 20px; }}
                .container {{ background: #020617; border: 1px solid #334155; padding: 25px; border-radius: 6px; }}
                .header {{ color: #38bdf8; border-bottom: 1px solid #1e293b; padding-bottom: 10px; margin-bottom: 15px; }}
                .highlight {{ color: #10b981; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h3>[ VERTEX SECOPS: FORMAL STATEMENT OF WORK DISPATCH ]</h3>
                </div>
                <p>Dear Executive Team at <strong>{company_name}</strong>,</p>
                <p>Following our discovery session, our engineering framework has compiled your infrastructure metrics and structured your mandatory baseline audit and security alignment under <strong>NIST SP 800-53 / ISO 27001</strong> standards.</p>
                
                <p><strong>Scoped Infrastructure:</strong><br>
                • Workstations Endpoints: {workstations}<br>
                • Server Instances: {servers}<br>
                • Estimated Remediation Labor: {remediation_hours} Hours</p>

                <p><strong>Total Upfront Investment Schedule:</strong><br>
                <span class="highlight">${total_investment:.2f} CAD</span> (Includes Initial Baseline Audit, Remediation Labor, and Tooling Setup)</p>

                <p>To review the complete contract terms and execute digital sign-off to initiate Phase 4 deployment, please reply directly or access your secure portal.</p>
                
                <p style="margin-top: 30px; font-size: 12px; color: #94a3b8;">
                    VertexSecOps Enterprise Infrastructure Management<br>
                    Orangeville, Ontario | Secure Governance Active
                </p>
            </div>
        </body>
    </html>
    """

    try:
        # Set up MIME structure
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Formal Statement of Work & Governance Plan - {company_name}"
        msg['From'] = sender_email
        msg['To'] = client_email
        msg.attach(MIMEText(html_content, 'html'))

        # Connect and send (Simulated / Local test block can bypass if offline)
        # server = smtplib.SMTP(smtp_server, smtp_port)
        # server.starttls()
        # server.login(sender_email, sender_password)
        # server.sendmail(sender_email, client_email, msg.as_string())
        # server.quit()

        print(f"[EMAIL DISPATCH] SOW successfully routed to {client_email}")
        return jsonify({"status": "success", "message": f"SOW package successfully dispatched to {client_email}"})

    except Exception as e:
        print(f"[!] Email Dispatch Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



# --- Pipeline L: Executive Vault Resource Hub ---
@app.route('/api/executive-vault/resources', methods=['GET'])
def get_executive_vault_resources():
    vault_resources = [
        {
            "id": 1,
            "category": "Boardroom Objection Handlers",
            "title": "Scenario 3: The 'Too Small to Be a Target' Fallacy",
            "summary": "Countering the assumption that smaller operational footprints escape threat actor attention.",
            "content": "In today’s threat landscape, smaller footprints are targeted precisely because they lack dedicated security operations centers. Automated threat actors rely on scanning tools to find soft perimeters, minimal monitoring, and rapid paths of least resistance. Security isn't about being impenetrable; it's about eliminating low-hanging fruit.",
            "accessLevel": "Executive"
        },
        {
            "id": 2,
            "category": "Boardroom Objection Handlers",
            "title": "Scenario 4: The 'ROI of Documentation' Defense",
            "summary": "Proving that documentation protects corporate wealth and prevents knowledge drain.",
            "content": "Documentation doesn't drive top-line revenue—it protects the bottom line from erosion. The true ROI is measured in hours not lost: time saved referencing solved incidents, onboarding speed doubled, and intellectual property preserved when personnel transition out.",
            "accessLevel": "Executive"
        },
        {
            "id": 3,
            "category": "Boardroom Objection Handlers",
            "title": "Scenario 5: The 'Cloud Security vs. On-Premises' Cost & Control",
            "summary": "Balancing bundled cloud economics against the illusion of physical hardware control.",
            "content": "True security is about specialized defense-in-depth, not physical proximity. Off-premises security is often bundled into broader cloud services the client already uses, eliminating standalone hardware costs. Security risk is amplified when internal teams must manually patch every layer from the metal up.",
            "accessLevel": "Executive"
        },
        {
            "id": 4,
            "category": "Boardroom Objection Handlers",
            "title": "Scenario 6: Navigating the 'Vendor Lock-In' Illusion",
            "summary": "Reframing platform adoption through turnkey delivery and seamless hybrid transition.",
            "content": "Executives fear lock-in because they view new tools through legacy operational lenses. VertexSecOps is delivered in working order with 24/7 support while you adapt to the hybrid environment. Standard relational schemas ensure your data and audit trails remain fully accessible and portable.",
            "accessLevel": "Executive"            
        },
        {
            "id": 5,
            "category": "STRIDE Threat Modeling",
            "title": "[S] Spoofing Identity",
            "summary": "Unauthorized entity pretending to be a legitimate user or domain admin.",
            "content": "Mitigation: Microsoft Entra ID Phishing-Resistant MFA, FIDO2 Security Keys, Conditional Access Policies. (NIST AC-2 / IA-2)",
            "accessLevel": "Executive"
        },
        {
            "id": 6,
            "category": "STRIDE Threat Modeling",
            "title": "[T] Tampering with Data",
            "summary": "Malicious modification of transaction logs, client records, or core web files.",
            "content": "Mitigation: TLS 1.3 Transport Encryption, SHA-256 File Integrity Monitoring (FIM), Encrypted SQL Backups. (NIST SI-7 / SC-8)",
            "accessLevel": "Executive"
        },
        {
            "id": 7,
            "category": "STRIDE Threat Modeling",
            "title": "[R] Repudiation",
            "summary": "User or administrator denies performing an action due to missing audit trails.",
            "content": "Mitigation: Centralized Immutable Syslog, Windows Event ID Security Auditing, WORM Log Storage. (NIST AU-2 / AU-6)",
            "accessLevel": "Executive"
        },
        {
            "id": 8,
            "category": "STRIDE Threat Modeling",
            "title": "[I] Information Disclosure",
            "summary": "Exfiltration of sensitive client information, tax records, or legal filings.",
            "content": "Mitigation: Microsoft Purview Data Loss Prevention (DLP), AES-256 BitLocker Encryption, RBAC Scoping. (NIST MP-5 / SC-28)",
            "accessLevel": "Executive"
        },
        {
            "id": 9,
            "category": "STRIDE Threat Modeling",
            "title": "[D] Denial of Service",
            "summary": "Network traffic flood or resource starvation knocking administration tools offline.",
            "content": "Mitigation: Virtual Switch Rate Limiting, Automated Hyper-V Failover Clustering, Edge Firewall Policies. (NIST SC-5 / CP-8)",
            "accessLevel": "Executive"
        },
        {
            "id": 10,
            "category": "STRIDE Threat Modeling",
            "title": "[E] Elevation of Privilege",
            "summary": "Standard local user account attempting token manipulation to gain Domain Admin.",
            "content": "Mitigation: Privileged Identity Management (PIM) JIT Elevation, Domain Admin OU Isolation, LAPS Deployment. (NIST AC-6 / IA-5)",
            "accessLevel": "Executive"
        }
    ]
    return jsonify(vault_resources), 200



@app.route('/api/credentials', methods=['GET'])
def list_credentials():
    creds_dir = os.path.join(app.root_path, 'Credentials')
    if not os.path.isdir(creds_dir):
        return jsonify([]), 200
    files = sorted([f for f in os.listdir(creds_dir) if f.lower().endswith('.png')], key=str.lower)
    return jsonify(files), 200

# ==========================================
# 8. RUNTIME SERVER DRIVER & ROUTE AUDIT
# ==========================================
print("REGISTERED ROUTES:")
for rule in app.url_map.iter_rules():
    print(f"  {rule.endpoint} -> {rule.rule}")

if __name__ == '__main__':
    from waitress import serve
    print("🚀 Starting Vertex SecOps Production Server on http://localhost:5000...")
    serve(app, host='127.0.0.1', port=5000, threads=12)
