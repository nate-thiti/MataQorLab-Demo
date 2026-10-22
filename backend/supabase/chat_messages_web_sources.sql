-- Persist external citations with assistant chat history.
-- JSONB is used because a response can contain a variable number of source objects.
ALTER TABLE public.chat_messages
ADD COLUMN IF NOT EXISTS web_sources jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.chat_messages
DROP CONSTRAINT IF EXISTS chat_messages_web_sources_is_array;

ALTER TABLE public.chat_messages
ADD CONSTRAINT chat_messages_web_sources_is_array
CHECK (jsonb_typeof(web_sources) = 'array');

COMMENT ON COLUMN public.chat_messages.web_sources IS
'External web citations shown with an assistant message.';
