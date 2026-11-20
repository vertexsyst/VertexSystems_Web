-- Target your Vertex development database
USE VertexSecOps; -- (Adjust name if your DB name differs slightly)
GO

-- Inject the lifecycle tracking columns safely
ALTER TABLE dbo.SecurityTickets
ADD 
    TicketStatus VARCHAR(20) DEFAULT 'NEW',
    InternalNotes NVARCHAR(MAX) NULL;
GO

-- Update any existing records so they aren't blank
UPDATE dbo.SecurityTickets
SET TicketStatus = 'NEW'
WHERE TicketStatus IS NULL;
GO