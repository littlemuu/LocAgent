"""Opt-in fix: never present zero-similarity BM25 rows as matched evidence."""
import math
from experiments.cohort_preflight import body

def positive_nodes(rows):
    return [row for row in rows if math.isfinite(float(row.score)) and float(row.score)>0]

def backend(retriever,audit):
    class PositiveRetriever:
        stemmer=retriever.stemmer
        def retrieve(self,query):
            rows=retriever.retrieve(query);selected=positive_nodes(rows)
            audit.append({'stage':'score_filter','query':query,'raw_count':len(rows),
                          'positive_count':len(selected),'excluded_nonpositive_or_nonfinite':len(rows)-len(selected)})
            return selected
    return body.backend(PositiveRetriever(),audit)
