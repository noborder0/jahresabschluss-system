-- migrations/schema/001_create_tables.sql
-- Phase 1: Basic tables for import functionality

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Import batches table
CREATE TABLE import_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('BANK_XML', 'DATEV', 'PDF')),
    source_file VARCHAR(255) NOT NULL,
    bank_info JSONB,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Imported transactions table
CREATE TABLE imported_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID REFERENCES import_batches(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL,

    -- Common fields
    booking_date DATE,
    amount DECIMAL(15,2) NOT NULL,
    description TEXT,
    account_number VARCHAR(20),
    contra_account VARCHAR(20),
    account_name VARCHAR(100),

    -- Original data
    raw_data JSONB NOT NULL,

    -- Status
    processed BOOLEAN DEFAULT FALSE,
    matched_booking_id UUID,

    -- Metadata
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_unprocessed (processed, booking_date) WHERE processed = FALSE,
    INDEX idx_batch (batch_id),
    INDEX idx_booking_date (booking_date)
);

-- Documents table (for PDFs)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    file_data BYTEA NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    import_batch_id UUID REFERENCES import_batches(id) ON DELETE SET NULL,
    linked_booking_id UUID,

    INDEX idx_import_batch (import_batch_id)
);

-- Bookings table (final bookings)
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_date DATE NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    debit_account VARCHAR(10) NOT NULL,
    credit_account VARCHAR(10) NOT NULL,
    description TEXT,
    tax_key VARCHAR(5),

    -- Reference to import
    import_id UUID,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50),

    -- Indexes
    INDEX idx_booking_date (booking_date),
    INDEX idx_accounts (debit_account, credit_account)
);

-- Basic chart of accounts (minimal SKR04 subset for Phase 1)
CREATE TABLE chart_of_accounts (
    account_number VARCHAR(10) PRIMARY KEY,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20) CHECK (account_type IN ('asset', 'liability', 'expense', 'revenue'))
);

-- Insert basic accounts
INSERT INTO chart_of_accounts (account_number, account_name, account_type) VALUES
    ('1200', 'Bank', 'asset'),
    ('1400', 'Forderungen aus Lieferungen und Leistungen', 'asset'),
    ('1600', 'Verbindlichkeiten aus Lieferungen und Leistungen', 'liability'),
    ('1576', 'Abziehbare Vorsteuer 19%', 'asset'),
    ('1571', 'Abziehbare Vorsteuer 7%', 'asset'),
    ('4200', 'Raumkosten', 'expense'),
    ('4930', 'Bürobedarf', 'expense'),
    ('6200', 'Löhne und Gehälter', 'expense'),
    ('6805', 'Telefon', 'expense'),
    ('6815', 'Internetkosten', 'expense'),
    ('8400', 'Erlöse 19% USt', 'revenue');