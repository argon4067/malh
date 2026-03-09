-- Merge transcript_refine into transcript (MySQL 8+)
-- 1) Add target column on transcript
ALTER TABLE transcript
ADD COLUMN refined_text TEXT NULL;

-- 2) Backfill refined_text from transcript_refine.r_refined_text
UPDATE transcript t
JOIN transcript_refine tr
  ON tr.transcript_id = t.transcript_id
SET t.refined_text = tr.r_refined_text
WHERE tr.r_refined_text IS NOT NULL
  AND TRIM(tr.r_refined_text) <> '';

-- 3) Drop old table
DROP TABLE transcript_refine;
