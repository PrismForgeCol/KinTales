-- Run this in the Supabase SQL Editor to create the image generations tracking table

CREATE TABLE image_generations (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    prompt TEXT NOT NULL,
    character_id UUID, -- Optional, if you want to link it to the characters table
    user_id UUID, -- Links to auth.users
    status TEXT NOT NULL DEFAULT 'processing',
    runpod_job_id TEXT,
    image_url TEXT
);

-- Optional: If you want to enable Row Level Security (RLS)
-- ALTER TABLE image_generations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow public select on image_generations" ON image_generations FOR SELECT USING (true);
