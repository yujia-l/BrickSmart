"""Cross-encoder reranker — the single biggest lever on retrieval quality. Re-scores the shortlist from
hybrid search jointly against the query (query, chunk_text) and returns the best few. Embeddings stay
OpenAI; the reranker is a small separate model. Falls back to the hybrid (RRF) order if
sentence-transformers isn't installed, so it never breaks a run."""
from app.core.logging import get_logger

_log = get_logger("reranker")


class CrossEncoderReranker:
    name = "cross_encoder"

    def __init__(self, model="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model
        self._ce = None

    def _model(self):
        if self._ce is None:
            from sentence_transformers import CrossEncoder
            self._ce = CrossEncoder(self.model_name)
        return self._ce

    def rerank(self, query, hits, k):
        if not hits:
            return hits
        try:
            scores = self._model().predict([(query, h["content"]) for h in hits])
            order = sorted(range(len(hits)), key=lambda i: scores[i], reverse=True)
            out = []
            for i in order[:k]:
                h = dict(hits[i]); h["rerank_score"] = float(scores[i]); out.append(h)
            return out
        except Exception as e:
            _log.warning("cross-encoder unavailable (%s); keeping hybrid order", e)
            return hits[:k]


class NoOpReranker:
    name = "noop"
    def rerank(self, query, hits, k):
        return hits[:k]


def get_reranker(settings):
    if getattr(settings, "RERANKER", "cross_encoder") == "cross_encoder":
        return CrossEncoderReranker(getattr(settings, "RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    return NoOpReranker()
