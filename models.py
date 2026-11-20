"""
Vertex Systems - Command Center Database Models
File: models.py
Description: Defines SQLAlchemy ORM models for Multi-Tenant Organizations, 
             Managed Devices, and Real-Time Telemetry Logs.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_internal = db.Column(db.Boolean, default=False)  # True for Vertex Systems, False for Clients
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship to Devices belonging to this organization
    devices = db.relationship('Device', backref='organization', lazy=True)

class Device(db.Model):
    __tablename__ = 'devices'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    hostname = db.Column(db.String(100), unique=True, nullable=False)  # e.g., VS-WKST-01
    ip_address = db.Column(db.String(45), nullable=True)
    os_version = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='UNKNOWN')  # NOMINAL, WARNING, CRITICAL
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship to telemetry logs
    telemetry_logs = db.relationship('TelemetryLog', backref='device', lazy=True)

class TelemetryLog(db.Model):
    __tablename__ = 'telemetry_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    cpu_usage = db.Column(db.Float, nullable=True)
    mem_usage = db.Column(db.Float, nullable=True)
    disk_status = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class DirectoryUser(db.Model):
    __tablename__ = 'directory_users'
    
    id = db.Column(db.Integer, primary_key=True)
    entra_id = db.Column(db.String(100), unique=True, nullable=False)  # Azure Object ID (GUID)
    display_name = db.Column(db.String(150), nullable=True)
    user_principal_name = db.Column(db.String(150), unique=True, nullable=False) # e.g., Arya@...
    mail = db.Column(db.String(150), nullable=True)
    job_title = db.Column(db.String(100), nullable=True)
    last_synced = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Optional: Relationship to tickets if you want to link support blobs directly
    # SecurityTicket = db.relationship('SecurityTicket', backref='directory_user', lazy=True, cascade="all, delete-orphan")
 

class SecurityTicket(db.Model):
    __tablename__ = 'SecurityTickets'

    TicketID = db.Column(db.Integer, primary_key=True)
    TicketSerial = db.Column(db.String(50), nullable=True)
    ClientName = db.Column(db.String(150), nullable=True)
    ClientEmail = db.Column(db.String(150), nullable=True)
    MessageDetails = db.Column(db.Text, nullable=True)
    SubmissionTime = db.Column(db.DateTime, nullable=True)
    TicketStatus = db.Column(db.String(20), nullable=True)
    InternalNotes = db.Column(db.Text, nullable=True)
    AssignmentGroup = db.Column(db.String(100), nullable=True)
    Category = db.Column(db.String(100), nullable=True)
    ClientID = db.Column(db.String(50), nullable=True)

        # And inside your DirectoryUser model we defined earlier, we add:
    # tickets = db.relationship('Ticket', backref='directory_user', lazy=True, cascade="all, delete-orphan").......Modified OK.