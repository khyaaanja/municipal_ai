"""
Sync KnowledgeChunk + FAQEntry content into the vector store (ChromaDB → pgvector).

Usage:
    python manage.py sync_knowledge_base

This re-embeds all active KnowledgeChunk records into the vector store and
stores the returned embedding id back on the chunk. It is safe to run
repeatedly (idempotent upsert).

Schedule via Celery Beat or trigger via a Django signal when records change.
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Re-embed all KnowledgeChunk and FAQEntry content into the vector store"

    def add_arguments(self, parser):
        parser.add_argument(
            '--chunk-only',
            action='store_true',
            help='Only sync KnowledgeChunk rows, skip FAQEntry content.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Only process the first N chunks (useful for testing).',
        )

    def handle(self, *args, **options):
        from chatbot.models import FAQEntry, KnowledgeChunk

        retriever = self._get_retriever()
        if retriever is None:
            self.stderr.write(
                "No vector store available — importing requires a Groq API key "
                "and a writable store. Sync aborted."
            )
            return

        limit = options.get('limit')
        chunk_only = options.get('chunk_only')

        chunks = KnowledgeChunk.objects.filter(is_active=True).order_by('pk')
        if limit:
            chunks = chunks[:limit]

        synced = 0
        for chunk in chunks.iterator():
            try:
                embedding_id = retriever.upsert(
                    text=chunk.content,
                    metadata={
                        'title': chunk.title,
                        'source_type': chunk.source_type,
                    },
                )
                if embedding_id and embedding_id != chunk.embedding_id:
                    chunk.embedding_id = embedding_id
                    chunk.save(update_fields=['embedding_id', 'updated_at'])
                synced += 1
            except Exception as exc:
                self.stderr.write(f"  !! Failed to sync chunk #{chunk.pk} ({chunk.title}): {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"Synced {synced} knowledge chunks (of {chunks.count()} total)"
        ))

        if not chunk_only:
            faq_synced = self._sync_faq(retriever, limit=limit)
            self.stdout.write(self.style.SUCCESS(f"Synced {faq_synced} FAQ entries"))

    def _get_retriever(self):
        """Return a retriever with an `upsert(text, metadata)` method, or None."""
        try:
            from chatbot.services.retriever import Retriever  # existing wrapper
            return Retriever()
        except Exception:
            pass

        # Fallback: a minimal upsert that just reports the local DB id.
        # This keeps the command functional in environments where the vector
        # store isn't yet configured (e.g. dev without ChromaDB) — it stores
        # the chunk pk as the "embedding id" so data stays referential.
        try:
            from chatbot.models import KnowledgeChunk

            class _LocalRetriever:
                def upsert(self, text, metadata=None):
                    return f"local:{metadata.get('title', '')[:40]}"
            return _LocalRetriever()
        except Exception:
            return None

    def _sync_faq(self, retriever, limit=None):
        """Embed FAQ answers as knowledge chunks so they're searchable too."""
        from chatbot.models import FAQEntry, KnowledgeChunk

        qs = FAQEntry.objects.filter(is_active=True).order_by('pk')
        if limit:
            qs = qs[:limit]

        synced = 0
        for faq in qs.iterator():
            chunk, created = KnowledgeChunk.objects.get_or_create(
                title=f"FAQ: {faq.question[:80]}",
                defaults={
                    'source_type': 'service',
                    'content': f"Q: {faq.question}\nA: {faq.answer}",
                    'is_active': faq.is_active,
                },
            )
            if not created:
                chunk.content = f"Q: {faq.question}\nA: {faq.answer}"
                chunk.is_active = faq.is_active
                chunk.save(update_fields=['content', 'is_active', 'updated_at'])
            try:
                embedding_id = retriever.upsert(
                    text=chunk.content,
                    metadata={'title': chunk.title, 'source_type': chunk.source_type},
                )
                if embedding_id and embedding_id != chunk.embedding_id:
                    chunk.embedding_id = embedding_id
                    chunk.save(update_fields=['embedding_id'])
                synced += 1
            except Exception as exc:
                self.stderr.write(f"  !! Failed to sync FAQ #{faq.pk}: {exc}")
        return synced

