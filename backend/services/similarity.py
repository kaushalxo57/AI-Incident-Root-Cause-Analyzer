import re
import numpy as np
from typing import List, Dict, Any, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class LogClustering:
    # Regex rules to replace high-cardinality/dynamic variables
    IP_REGEX = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    UUID_REGEX = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    HEX_REGEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
    NUM_REGEX = re.compile(r"\b\d+\b")
    EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
    TIMESTAMP_REGEX = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")

    @classmethod
    def normalize_message(cls, message: str) -> str:
        """
        Replaces variables (IDs, IPs, timestamps, numbers) in log messages to normalize them.
        """
        msg = message
        msg = cls.TIMESTAMP_REGEX.sub("<TIMESTAMP>", msg)
        msg = cls.IP_REGEX.sub("<IP>", msg)
        msg = cls.UUID_REGEX.sub("<UUID>", msg)
        msg = cls.HEX_REGEX.sub("<HEX>", msg)
        msg = cls.EMAIL_REGEX.sub("<EMAIL>", msg)
        msg = cls.NUM_REGEX.sub("<NUM>", msg)
        # Collapse multiple spaces
        msg = re.sub(r"\s+", " ", msg)
        return msg.strip().lower()

    @classmethod
    def group_similar_logs(cls, logs: List[Dict[str, Any]], threshold: float = 0.75) -> List[Dict[str, Any]]:
        """
        Groups log events using TF-IDF and Cosine Similarity.
        Returns a list of cluster metadata and log items tagged with their cluster ID.
        """
        if not logs:
            return []

        # Step 1: Normalize all log messages
        normalized_msgs = [cls.normalize_message(log["message"]) for log in logs]
        
        # Step 2: Fit TF-IDF Vectorizer
        # If all messages are identical or empty after normalization, TF-IDF might throw an error. Handle safely.
        non_empty = [m for m in normalized_msgs if m.strip()]
        if not non_empty:
            # Fallback to single cluster
            for log in logs:
                log["cluster_id"] = 0
                log["normalized_message"] = "generic_log_event"
            return [{"cluster_id": 0, "template": "generic_log_event", "count": len(logs), "logs": logs}]

        try:
            # Use char-level and word-level features to handle system logs
            vectorizer = TfidfVectorizer(analyzer="word", min_df=1, stop_words=None, token_pattern=r"(?u)\b\w+\b|<[A-Z]+>")
            tfidf_matrix = vectorizer.fit_transform(normalized_msgs)
            
            # Step 3: Compute Cosine Similarity matrix
            sim_matrix = cosine_similarity(tfidf_matrix)
        except Exception:
            # Fallback to direct string matching if TF-IDF fails
            clusters = {}
            for i, log in enumerate(logs):
                norm = normalized_msgs[i]
                found = False
                for t, cid in clusters.items():
                    if t == norm:
                        log["cluster_id"] = cid
                        log["normalized_message"] = norm
                        found = True
                        break
                if not found:
                    cid = len(clusters)
                    clusters[norm] = cid
                    log["cluster_id"] = cid
                    log["normalized_message"] = norm
            
            grouped_clusters = []
            for t, cid in clusters.items():
                cluster_logs = [log for log in logs if log["cluster_id"] == cid]
                grouped_clusters.append({
                    "cluster_id": cid,
                    "template": t,
                    "count": len(cluster_logs),
                    "logs": cluster_logs
                })
            return grouped_clusters

        # Step 4: Clustering algorithm (Greedy single-linkage clustering)
        # Assign logs to clusters based on similarity threshold
        clusters: List[List[int]] = []  # List of list of log indices
        
        for i in range(len(logs)):
            assigned = False
            for c_idx, cluster in enumerate(clusters):
                # Compare current log to the first log in the cluster (cluster representative)
                rep_idx = cluster[0]
                similarity = sim_matrix[i, rep_idx]
                if similarity >= threshold:
                    cluster.append(i)
                    assigned = True
                    break
            if not assigned:
                clusters.append([i])

        # Step 5: Format cluster summaries
        grouped_clusters = []
        for c_idx, cluster_indices in enumerate(clusters):
            cluster_logs = [logs[idx] for idx in cluster_indices]
            
            # Tag the original log objects
            for idx in cluster_indices:
                logs[idx]["cluster_id"] = c_idx
                logs[idx]["normalized_message"] = normalized_msgs[idx]

            # Determine the template (most common normalized message in this cluster)
            cluster_norm_msgs = [normalized_msgs[idx] for idx in cluster_indices]
            template = max(set(cluster_norm_msgs), key=cluster_norm_msgs.count)

            grouped_clusters.append({
                "cluster_id": c_idx,
                "template": template,
                "count": len(cluster_logs),
                "logs": cluster_logs
            })

        return grouped_clusters
