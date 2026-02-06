-- US-904: Document Upload & Ingestion Pipeline
-- Tables for company document storage, processing tracking, and chunked content

CREATE TABLE company_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE NOT NULL,
    uploaded_by UUID REFERENCES auth.users(id) NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- pdf, docx, pptx, txt, md, csv, xlsx, image
    file_size_bytes BIGINT NOT NULL,
    storage_path TEXT NOT NULL,  -- Supabase Storage path
    processing_status TEXT DEFAULT 'uploaded',  -- uploaded, processing, complete, failed
    processing_progress FLOAT DEFAULT 0,  -- 0-100
    chunk_count INTEGER DEFAULT 0,
    entity_count INTEGER DEFAULT 0,
    quality_score FLOAT DEFAULT 0,  -- source quality: capabilities deck > generic report
    extracted_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES company_documents(id) ON DELETE CASCADE NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_type TEXT DEFAULT 'paragraph',  -- paragraph, table, header, list
    embedding vector(1536),  -- pgvector
    entities JSONB DEFAULT '[]',  -- extracted entities
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS
ALTER TABLE company_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

-- All company members can read documents
CREATE POLICY "company_docs_read" ON company_documents
    FOR SELECT TO authenticated USING (
        company_id IN (SELECT company_id FROM user_profiles WHERE id = auth.uid())
    );

-- Only uploader can delete
CREATE POLICY "company_docs_delete" ON company_documents
    FOR DELETE TO authenticated USING (uploaded_by = auth.uid());

-- Authenticated users can insert for their company
CREATE POLICY "company_docs_insert" ON company_documents
    FOR INSERT TO authenticated WITH CHECK (
        company_id IN (SELECT company_id FROM user_profiles WHERE id = auth.uid())
    );

-- Chunks follow document access
CREATE POLICY "chunks_read" ON document_chunks
    FOR SELECT TO authenticated USING (
        document_id IN (
            SELECT id FROM company_documents WHERE company_id IN (
                SELECT company_id FROM user_profiles WHERE id = auth.uid()
            )
        )
    );

-- Indexes
CREATE INDEX idx_doc_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_doc_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_company_docs_company ON company_documents(company_id);
CREATE INDEX idx_company_docs_status ON company_documents(processing_status);
