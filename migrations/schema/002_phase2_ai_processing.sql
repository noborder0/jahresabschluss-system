-- migrations/schema/002_phase2_ai_processing.sql
-- Phase 2: AI Processing Tables and Updates

-- Processing results table
CREATE TABLE IF NOT EXISTS processing_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    processing_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Extraction results
    extraction_status VARCHAR(20) CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed')),
    extraction_confidence DECIMAL(3,2),
    extracted_data JSONB,
    extraction_errors TEXT[],

    -- Matching results
    matching_status VARCHAR(20) CHECK (matching_status IN ('pending', 'completed', 'no_matches', 'failed')),
    matched_transaction_id UUID REFERENCES imported_transactions(id),
    match_confidence DECIMAL(3,2),
    match_details JSONB,

    -- Booking suggestion
    booking_suggestion JSONB,
    suggestion_confidence DECIMAL(3,2),
    auto_booked BOOLEAN DEFAULT FALSE,
    booking_id UUID REFERENCES bookings(id),

    -- Metadata
    ai_model_versions JSONB,
    processing_time_ms INTEGER,

    -- Indexes
    INDEX idx_document_processing (document_id),
    INDEX idx_processing_status (extraction_status, matching_status)
);

-- AI cache table for storing responses
CREATE TABLE IF NOT EXISTS ai_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    service VARCHAR(20) NOT NULL CHECK (service IN ('azure', 'claude')),
    request_hash VARCHAR(64) NOT NULL,
    response_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0,

    -- Indexes
    INDEX idx_cache_key (cache_key),
    INDEX idx_expires (expires_at)
);

-- Vendor mapping table for better matching
CREATE TABLE IF NOT EXISTS vendor_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vendor_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    common_account VARCHAR(10),
    vat_id VARCHAR(20),
    payment_terms_days INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_vendor_name (vendor_name),
    INDEX idx_normalized_name (normalized_name)
);

-- Processing queue for batch operations
CREATE TABLE IF NOT EXISTS processing_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Indexes
    INDEX idx_queue_status (status, priority DESC, created_at)
);

-- Add AI processing fields to documents table
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS ai_processed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS ai_processing_date TIMESTAMP,
ADD COLUMN IF NOT EXISTS document_type VARCHAR(20);

-- Add confidence scores to bookings
ALTER TABLE bookings
ADD COLUMN IF NOT EXISTS confidence_score DECIMAL(3,2),
ADD COLUMN IF NOT EXISTS is_auto_booked BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS ai_suggestion JSONB;

-- Add matching fields to imported_transactions
ALTER TABLE imported_transactions
ADD COLUMN IF NOT EXISTS potential_document_matches JSONB;

-- Statistics view for dashboard
CREATE OR REPLACE VIEW ai_processing_stats AS
SELECT
    COUNT(DISTINCT d.id) as total_documents,
    COUNT(DISTINCT CASE WHEN pr.extraction_status = 'completed' THEN d.id END) as extracted_documents,
    COUNT(DISTINCT CASE WHEN pr.matched_transaction_id IS NOT NULL THEN d.id END) as matched_documents,
    COUNT(DISTINCT CASE WHEN pr.auto_booked = TRUE THEN d.id END) as auto_booked_documents,
    AVG(pr.extraction_confidence) as avg_extraction_confidence,
    AVG(pr.match_confidence) as avg_match_confidence,
    AVG(pr.suggestion_confidence) as avg_suggestion_confidence,
    AVG(pr.processing_time_ms) as avg_processing_time_ms
FROM documents d
LEFT JOIN processing_results pr ON d.id = pr.document_id
WHERE d.upload_date >= CURRENT_DATE - INTERVAL '30 days';

-- Insert sample vendor mappings
INSERT INTO vendor_mappings (vendor_name, normalized_name, common_account) VALUES
    ('Amazon Web Services', 'aws', '6815'),
    ('Google Cloud Platform', 'google cloud', '6815'),
    ('Microsoft Azure', 'microsoft azure', '6815'),
    ('Telekom Deutschland GmbH', 'telekom', '6805'),
    ('Vodafone GmbH', 'vodafone', '6805')
ON CONFLICT DO NOTHING;

-- Create index for full-text search on documents
CREATE INDEX IF NOT EXISTS idx_documents_raw_text ON processing_results
USING gin(to_tsvector('german', extracted_data->>'raw_text'));

-- Function to clean up old cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_cache() RETURNS void AS $$
BEGIN
    DELETE FROM ai_cache WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;