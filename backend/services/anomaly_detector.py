import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    def __init__(self, threshold_z: float = 2.0, window_minutes: int = 1):
        """
        threshold_z: Number of standard deviations above mean to trigger statistical anomaly.
        window_minutes: Size of the time bucket for aggregation.
        """
        self.threshold_z = threshold_z
        self.window_minutes = window_minutes

    def detect_anomalies(self, events: List[Dict[str, Any]], historical_baselines: Dict[str, Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        Processes log events, groups them into time buckets, and detects anomalies.
        Returns a list of detected anomalies.
        """
        if not events:
            return []

        # Convert to Pandas DataFrame for analysis
        df = pd.DataFrame(events)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Round timestamps to bucket intervals
        df["time_bucket"] = df["timestamp"].dt.round(f"{self.window_minutes}min")
        
        # Create columns for log level classification
        df["is_error"] = df["level"].isin(["WARNING", "ERROR", "CRITICAL"])
        df["is_critical"] = df["level"] == "CRITICAL"

        # Group by bucket and service
        grouped = df.groupby(["time_bucket", "service_name"]).agg(
            total_logs=("message", "count"),
            error_count=("is_error", "sum"),
            critical_count=("is_critical", "sum"),
            status_5xx_count=("status_code", lambda x: sum(1 for c in x if c is not None and 500 <= c < 600))
        ).reset_index()

        anomalies = []
        services = grouped["service_name"].unique()

        for service in services:
            service_df = grouped[grouped["service_name"] == service].copy()
            if len(service_df) == 0:
                continue

            # Sort chronologically
            service_df = service_df.sort_values("time_bucket")

            # Compute stats
            total_logs_arr = service_df["total_logs"].values
            error_count_arr = service_df["error_count"].values
            
            # Simple baselines
            mean_errors = np.mean(error_count_arr)
            std_errors = np.std(error_count_arr)
            
            mean_logs = np.mean(total_logs_arr)
            std_logs = np.std(total_logs_arr)

            # Apply Isolation Forest if we have enough data (at least 5 samples)
            use_ml = len(service_df) >= 5
            ml_anomalies = set()
            if use_ml:
                try:
                    # Features: total logs, errors, ratio of errors
                    features = service_df[["total_logs", "error_count"]].copy()
                    features["error_ratio"] = features["error_count"] / (features["total_logs"] + 1e-5)
                    
                    # Fit Isolation Forest (contamination represents expected ratio of anomalies)
                    clf = IsolationForest(contamination=0.1, random_state=42)
                    preds = clf.fit_predict(features)
                    
                    # Outliers are marked as -1
                    for idx, pred in zip(service_df.index, preds):
                        if pred == -1:
                            ml_anomalies.add(service_df.loc[idx, "time_bucket"])
                except Exception:
                    pass  # Fall back to statistical analysis

            # Statistical z-score detection
            for _, row in service_df.iterrows():
                bucket = row["time_bucket"]
                errs = row["error_count"]
                logs = row["total_logs"]
                crit_errs = row["critical_count"]
                err_5xx = row["status_5xx_count"]

                # Statistical thresholds
                is_anomaly = False
                reasons = []
                confidence_scores = []

                # Reason 1: Significant error count spike
                if std_errors > 0:
                    z_score_err = (errs - mean_errors) / std_errors
                    if z_score_err > self.threshold_z:
                        is_anomaly = True
                        reasons.append(f"Error count spike (Z-Score: {z_score_err:.2f})")
                        confidence_scores.append(min(0.95, 0.4 + 0.15 * z_score_err))
                elif errs > 0 and mean_errors == 0:
                    # First time seeing errors in the baseline
                    is_anomaly = True
                    reasons.append(f"First seen errors ({errs} errors in window)")
                    confidence_scores.append(0.80)

                # Reason 2: Severe traffic spike (DoS or loop)
                if std_logs > 0:
                    z_score_logs = (logs - mean_logs) / std_logs
                    if z_score_logs > self.threshold_z + 1.0: # require higher threshold for volume-only anomalies
                        is_anomaly = True
                        reasons.append(f"Log volume anomaly (Z-Score: {z_score_logs:.2f})")
                        confidence_scores.append(min(0.90, 0.3 + 0.12 * z_score_logs))

                # Reason 3: Any critical error or 5xx status codes
                if crit_errs > 0:
                    is_anomaly = True
                    reasons.append(f"{crit_errs} CRITICAL level errors detected")
                    confidence_scores.append(0.85)
                
                if err_5xx > 0:
                    is_anomaly = True
                    reasons.append(f"{err_5xx} HTTP 5xx responses detected")
                    confidence_scores.append(0.90)

                # Reason 4: ML model flagged it
                if bucket in ml_anomalies and (errs > mean_errors or logs > mean_logs):
                    is_anomaly = True
                    reasons.append("Flagged by Isolation Forest ML model")
                    confidence_scores.append(0.75)

                if is_anomaly:
                    # Overall confidence is the max of the reasons
                    confidence = max(confidence_scores) if confidence_scores else 0.50
                    
                    # Gather sample logs from this bucket & service for context
                    bucket_start = bucket - timedelta(minutes=self.window_minutes)
                    bucket_end = bucket + timedelta(minutes=self.window_minutes)
                    sample_logs_df = df[
                        (df["service_name"] == service) & 
                        (df["timestamp"] >= bucket_start) & 
                        (df["timestamp"] <= bucket_end)
                    ]
                    
                    # Pick top critical/error messages as samples
                    sample_errors = sample_logs_df[sample_logs_df["is_error"] == True]
                    if len(sample_errors) == 0:
                        sample_errors = sample_logs_df
                    
                    top_messages = sample_errors.head(3)["message"].tolist()

                    anomalies.append({
                        "timestamp": bucket.to_pydatetime(),
                        "service_name": service,
                        "reasons": reasons,
                        "confidence": float(confidence),
                        "metrics": {
                            "total_logs": int(logs),
                            "error_count": int(errs),
                            "mean_errors": float(mean_errors),
                            "std_errors": float(std_errors)
                        },
                        "sample_messages": top_messages
                    })

        return anomalies
