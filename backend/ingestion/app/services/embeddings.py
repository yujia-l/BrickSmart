"""OpenAI embeddings (text-embedding-3-large, 3072-d). Swap these two functions to change embedder."""


def embed_texts(texts, settings):
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    out = []
    for i in range(0, len(texts), 100):
        batch = [t if t.strip() else " " for t in texts[i:i + 100]]
        out.extend(d.embedding for d in client.embeddings.create(model=settings.EMBED_MODEL, input=batch).data)
    return out


def embed_query(q, settings):
    return embed_texts([q], settings)[0]
