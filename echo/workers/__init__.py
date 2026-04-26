"""
Background workers — bus subscribers that turn raw events into persistent
state. Same role as Omi's `pusher/` and `utils/conversations/` workers,
collapsed in-process.

Importing this module registers ALL workers via their import side-effects.
Order doesn't matter — each submodule self-registers its bus subscriptions
at the bottom of the file.

  transcriber     audio.chunk            -> transcript.final
  persistence     transcript.final       -> SQLite + transcript.persisted
  embedder        transcript.persisted   -> ChromaDB upsert
                  memory.extracted       -> ChromaDB upsert
                  action_item.extracted  -> ChromaDB upsert
  post_processor  (cron) unprocessed transcripts -> Gemini -> memories +
                                                   action_items + summary
"""
from echo.workers import transcriber, persistence, embedder, post_processor  # noqa: F401

# Start the post-processor daemon on import. Idempotent.
post_processor.start()
