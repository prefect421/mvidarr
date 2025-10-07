"""
IMVDB Analytics Service for Issue #82
Implements historical data analysis for discovery patterns and performance insights.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, asc, desc, func
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Setting, User, Video, VideoStatus
from src.services.imvdb_discovery_service import imvdb_discovery_service
from src.services.imvdb_service import imvdb_service
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

logger = get_logger("mvidarr.imvdb_analytics")


class IMVDbAnalyticsService:
    """Service for analyzing IMVDB discovery patterns and performance"""

    def __init__(self):
        self.logger = logger

    @monitor_performance("imvdb_analytics.discovery_performance_analysis")
    def analyze_discovery_performance(self, days: int = 30) -> Dict[str, any]:
        """
        Analyze discovery performance over time

        Args:
            days: Number of days to analyze

        Returns:
            Discovery performance analysis
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with get_db() as session:
            # Get discovered videos in time period
            discovered_videos = (
                session.query(Video)
                .filter(
                    Video.source == "imvdb_discovery",
                    Video.discovered_date >= cutoff_date,
                )
                .all()
            )

            # Get artists with recent discovery activity
            active_artists = (
                session.query(Artist)
                .filter(Artist.last_discovery >= cutoff_date, Artist.monitored == True)
                .all()
            )

            analysis = {
                "time_period": {
                    "start_date": cutoff_date.isoformat(),
                    "end_date": datetime.utcnow().isoformat(),
                    "days_analyzed": days,
                },
                "overall_metrics": {
                    "total_videos_discovered": len(discovered_videos),
                    "active_monitored_artists": len(active_artists),
                    "discovery_rate": len(discovered_videos) / max(days, 1),
                    "average_quality_score": 0.0,
                },
                "temporal_patterns": self._analyze_temporal_patterns(
                    discovered_videos, days
                ),
                "artist_performance": self._analyze_artist_discovery_performance(
                    discovered_videos, active_artists
                ),
                "quality_trends": self._analyze_quality_trends(discovered_videos),
                "source_effectiveness": self._analyze_source_effectiveness(
                    discovered_videos
                ),
                "recommendations": [],
            }

            # Calculate average quality score
            if discovered_videos:
                quality_scores = []
                for video in discovered_videos:
                    if video.imvdb_metadata:
                        try:
                            quality_analysis = imvdb_service.analyze_video_quality(
                                video.imvdb_metadata
                            )
                            quality_scores.append(
                                quality_analysis.get("overall_score", 0)
                            )
                        except Exception:
                            quality_scores.append(0)

                if quality_scores:
                    analysis["overall_metrics"]["average_quality_score"] = sum(
                        quality_scores
                    ) / len(quality_scores)

            # Generate recommendations based on analysis
            analysis["recommendations"] = self._generate_discovery_recommendations(
                analysis
            )

            return analysis

    def _analyze_temporal_patterns(
        self, videos: List[Video], days: int
    ) -> Dict[str, any]:
        """Analyze discovery patterns over time"""
        patterns = {
            "daily_discovery": {},
            "weekly_trends": {},
            "peak_discovery_times": [],
            "discovery_velocity": [],
        }

        if not videos:
            return patterns

        # Group by day
        daily_counts = defaultdict(int)
        for video in videos:
            if video.discovered_date:
                day_key = video.discovered_date.strftime("%Y-%m-%d")
                daily_counts[day_key] += 1

        patterns["daily_discovery"] = dict(sorted(daily_counts.items()))

        # Weekly aggregation
        weekly_counts = defaultdict(int)
        for video in videos:
            if video.discovered_date:
                # Get week start (Monday)
                week_start = video.discovered_date - timedelta(
                    days=video.discovered_date.weekday()
                )
                week_key = week_start.strftime("%Y-W%W")
                weekly_counts[week_key] += 1

        patterns["weekly_trends"] = dict(sorted(weekly_counts.items()))

        # Calculate discovery velocity (videos discovered per week)
        if len(weekly_counts) > 1:
            weekly_values = list(weekly_counts.values())
            for i in range(1, len(weekly_values)):
                velocity = weekly_values[i] - weekly_values[i - 1]
                patterns["discovery_velocity"].append(
                    {"week": list(weekly_counts.keys())[i], "velocity": velocity}
                )

        return patterns

    def _analyze_artist_discovery_performance(
        self, videos: List[Video], artists: List[Artist]
    ) -> Dict[str, any]:
        """Analyze which artists are most productive for discovery"""
        performance = {
            "top_performing_artists": [],
            "discovery_distribution": {},
            "artist_metrics": {},
        }

        # Count discoveries per artist
        artist_discovery_counts = defaultdict(int)
        artist_quality_scores = defaultdict(list)

        for video in videos:
            if video.artist_id:
                artist_discovery_counts[video.artist_id] += 1

                # Get quality score if available
                if video.imvdb_metadata:
                    try:
                        quality_analysis = imvdb_service.analyze_video_quality(
                            video.imvdb_metadata
                        )
                        artist_quality_scores[video.artist_id].append(
                            quality_analysis.get("overall_score", 0)
                        )
                    except Exception:
                        pass

        # Create performance metrics for each artist
        for artist in artists:
            discoveries = artist_discovery_counts.get(artist.id, 0)
            quality_scores = artist_quality_scores.get(artist.id, [])
            avg_quality = (
                sum(quality_scores) / len(quality_scores) if quality_scores else 0
            )

            performance["artist_metrics"][artist.name] = {
                "discoveries_count": discoveries,
                "average_quality": avg_quality,
                "auto_download_enabled": artist.auto_download,
                "last_discovery": (
                    artist.last_discovery.isoformat() if artist.last_discovery else None
                ),
            }

        # Sort artists by discovery performance
        sorted_artists = sorted(
            performance["artist_metrics"].items(),
            key=lambda x: (x[1]["discoveries_count"], x[1]["average_quality"]),
            reverse=True,
        )

        performance["top_performing_artists"] = sorted_artists[:10]

        # Discovery distribution
        discovery_ranges = {"0": 0, "1-2": 0, "3-5": 0, "6-10": 0, "10+": 0}
        for count in artist_discovery_counts.values():
            if count == 0:
                discovery_ranges["0"] += 1
            elif count <= 2:
                discovery_ranges["1-2"] += 1
            elif count <= 5:
                discovery_ranges["3-5"] += 1
            elif count <= 10:
                discovery_ranges["6-10"] += 1
            else:
                discovery_ranges["10+"] += 1

        performance["discovery_distribution"] = discovery_ranges

        return performance

    def _analyze_quality_trends(self, videos: List[Video]) -> Dict[str, any]:
        """Analyze quality trends over time"""
        trends = {
            "quality_over_time": [],
            "quality_distribution": {"high": 0, "medium": 0, "low": 0},
            "quality_by_genre": {},
            "quality_improvement_rate": 0.0,
        }

        if not videos:
            return trends

        # Quality over time
        quality_by_date = []
        for video in videos:
            if video.discovered_date and video.imvdb_metadata:
                try:
                    quality_analysis = imvdb_service.analyze_video_quality(
                        video.imvdb_metadata
                    )
                    quality_score = quality_analysis.get("overall_score", 0)

                    quality_by_date.append(
                        {
                            "date": video.discovered_date.strftime("%Y-%m-%d"),
                            "quality_score": quality_score,
                        }
                    )

                    # Quality distribution
                    if quality_score >= 70:
                        trends["quality_distribution"]["high"] += 1
                    elif quality_score >= 40:
                        trends["quality_distribution"]["medium"] += 1
                    else:
                        trends["quality_distribution"]["low"] += 1

                    # Quality by genre
                    if video.video_metadata and video.video_metadata.get("genre"):
                        genre = video.video_metadata["genre"]
                        if genre not in trends["quality_by_genre"]:
                            trends["quality_by_genre"][genre] = []
                        trends["quality_by_genre"][genre].append(quality_score)

                except Exception:
                    quality_by_date.append(
                        {
                            "date": video.discovered_date.strftime("%Y-%m-%d"),
                            "quality_score": 0,
                        }
                    )

        trends["quality_over_time"] = sorted(quality_by_date, key=lambda x: x["date"])

        # Calculate average quality by genre
        for genre in trends["quality_by_genre"]:
            scores = trends["quality_by_genre"][genre]
            trends["quality_by_genre"][genre] = {
                "average_quality": sum(scores) / len(scores),
                "video_count": len(scores),
            }

        # Calculate quality improvement rate
        if len(trends["quality_over_time"]) >= 2:
            first_half = trends["quality_over_time"][
                : len(trends["quality_over_time"]) // 2
            ]
            second_half = trends["quality_over_time"][
                len(trends["quality_over_time"]) // 2 :
            ]

            first_avg = sum(item["quality_score"] for item in first_half) / len(
                first_half
            )
            second_avg = sum(item["quality_score"] for item in second_half) / len(
                second_half
            )

            trends["quality_improvement_rate"] = (
                ((second_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0
            )

        return trends

    def _analyze_source_effectiveness(self, videos: List[Video]) -> Dict[str, any]:
        """Analyze effectiveness of different discovery sources and patterns"""
        effectiveness = {
            "metadata_completeness_impact": {},
            "year_distribution_effectiveness": {},
            "director_presence_impact": {},
            "thumbnail_availability_impact": {},
        }

        metadata_complete = 0
        metadata_incomplete = 0
        director_present = 0
        director_absent = 0
        thumbnail_present = 0
        thumbnail_absent = 0
        year_distribution = defaultdict(int)

        for video in videos:
            # Metadata completeness
            if (
                video.video_metadata and len(video.video_metadata) >= 3
            ):  # Reasonable completeness threshold
                metadata_complete += 1
            else:
                metadata_incomplete += 1

            # Director presence
            if video.video_metadata and video.video_metadata.get("directors"):
                director_present += 1
            else:
                director_absent += 1

            # Thumbnail availability
            if video.thumbnail_url:
                thumbnail_present += 1
            else:
                thumbnail_absent += 1

            # Year distribution
            if video.year:
                decade = (video.year // 10) * 10
                year_distribution[f"{decade}s"] += 1

        total_videos = len(videos)
        if total_videos > 0:
            effectiveness["metadata_completeness_impact"] = {
                "complete": {
                    "count": metadata_complete,
                    "percentage": (metadata_complete / total_videos) * 100,
                },
                "incomplete": {
                    "count": metadata_incomplete,
                    "percentage": (metadata_incomplete / total_videos) * 100,
                },
            }

            effectiveness["director_presence_impact"] = {
                "with_directors": {
                    "count": director_present,
                    "percentage": (director_present / total_videos) * 100,
                },
                "without_directors": {
                    "count": director_absent,
                    "percentage": (director_absent / total_videos) * 100,
                },
            }

            effectiveness["thumbnail_availability_impact"] = {
                "with_thumbnails": {
                    "count": thumbnail_present,
                    "percentage": (thumbnail_present / total_videos) * 100,
                },
                "without_thumbnails": {
                    "count": thumbnail_absent,
                    "percentage": (thumbnail_absent / total_videos) * 100,
                },
            }

            effectiveness["year_distribution_effectiveness"] = dict(
                sorted(year_distribution.items())
            )

        return effectiveness

    def _generate_discovery_recommendations(
        self, analysis: Dict[str, any]
    ) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        # Check discovery rate
        discovery_rate = analysis["overall_metrics"]["discovery_rate"]
        if discovery_rate < 1.0:  # Less than 1 video per day
            recommendations.append(
                "Discovery rate is low. Consider expanding monitored artist list or adjusting discovery frequency."
            )
        elif discovery_rate > 10.0:  # More than 10 videos per day
            recommendations.append(
                "High discovery rate detected. Consider implementing stricter quality filters to improve relevance."
            )

        # Check quality trends
        avg_quality = analysis["overall_metrics"]["average_quality_score"]
        if avg_quality < 50:
            recommendations.append(
                "Average quality score is below optimal. Consider raising minimum quality thresholds for discoveries."
            )
        elif avg_quality > 80:
            recommendations.append(
                "Excellent quality filtering detected. Current discovery settings are performing well."
            )

        # Check artist performance distribution
        artist_metrics = analysis["artist_performance"]["artist_metrics"]
        low_performing_artists = sum(
            1
            for metrics in artist_metrics.values()
            if metrics["discoveries_count"] == 0
        )
        total_artists = len(artist_metrics)

        if total_artists > 0 and (low_performing_artists / total_artists) > 0.5:
            recommendations.append(
                "Over 50% of monitored artists have no recent discoveries. Review artist monitoring list for inactive or irrelevant artists."
            )

        # Check quality improvement
        quality_trends = analysis.get("quality_trends", {})
        improvement_rate = quality_trends.get("quality_improvement_rate", 0)
        if improvement_rate < -10:
            recommendations.append(
                "Quality scores are declining. Review discovery algorithms and quality filters."
            )
        elif improvement_rate > 10:
            recommendations.append(
                "Quality scores are improving. Current optimization strategies are effective."
            )

        # Check source effectiveness
        source_effectiveness = analysis.get("source_effectiveness", {})
        metadata_complete = (
            source_effectiveness.get("metadata_completeness_impact", {})
            .get("complete", {})
            .get("percentage", 0)
        )
        if metadata_complete < 60:
            recommendations.append(
                "Low metadata completeness detected. Consider prioritizing sources with richer metadata."
            )

        if not recommendations:
            recommendations.append(
                "Discovery performance is within optimal ranges. Continue current strategy."
            )

        return recommendations

    @monitor_performance("imvdb_analytics.generate_discovery_report")
    def generate_comprehensive_discovery_report(self, days: int = 30) -> Dict[str, any]:
        """
        Generate a comprehensive discovery analysis report

        Args:
            days: Number of days to analyze

        Returns:
            Comprehensive discovery report
        """
        # Combine all analysis methods
        performance_analysis = self.analyze_discovery_performance(days)
        discovery_stats = imvdb_discovery_service.get_discovery_statistics()
        quality_patterns = imvdb_discovery_service.get_quality_discovery_patterns()

        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "analysis_period": days,
                "report_type": "comprehensive_discovery_analysis",
            },
            "executive_summary": self._generate_executive_summary(
                performance_analysis, discovery_stats
            ),
            "performance_analysis": performance_analysis,
            "discovery_statistics": discovery_stats,
            "quality_patterns": quality_patterns,
            "strategic_recommendations": self._generate_strategic_recommendations(
                performance_analysis, discovery_stats, quality_patterns
            ),
        }

        return report

    def _generate_executive_summary(
        self, performance: Dict, stats: Dict
    ) -> Dict[str, any]:
        """Generate executive summary of discovery performance"""
        return {
            "key_metrics": {
                "total_videos_discovered": performance["overall_metrics"][
                    "total_videos_discovered"
                ],
                "average_quality_score": round(
                    performance["overall_metrics"]["average_quality_score"], 1
                ),
                "active_monitored_artists": performance["overall_metrics"][
                    "active_monitored_artists"
                ],
                "discovery_rate_per_day": round(
                    performance["overall_metrics"]["discovery_rate"], 2
                ),
            },
            "performance_indicators": {
                "discovery_rate_status": (
                    "optimal"
                    if 1 <= performance["overall_metrics"]["discovery_rate"] <= 5
                    else "needs_attention"
                ),
                "quality_status": (
                    "excellent"
                    if performance["overall_metrics"]["average_quality_score"] >= 70
                    else (
                        "good"
                        if performance["overall_metrics"]["average_quality_score"] >= 50
                        else "needs_improvement"
                    )
                ),
                "artist_utilization": (
                    "high"
                    if performance["overall_metrics"]["active_monitored_artists"]
                    >= stats.get("total_monitored_artists", 0) * 0.7
                    else "moderate"
                ),
            },
        }

    def _generate_strategic_recommendations(
        self, performance: Dict, stats: Dict, patterns: Dict
    ) -> List[Dict[str, str]]:
        """Generate strategic recommendations for discovery optimization"""
        recommendations = []

        # Analyze patterns and provide strategic guidance
        total_discovered = patterns.get("total_discovered", 0)
        high_quality_count = patterns.get("quality_distribution", {}).get(
            "high_quality", 0
        )

        if total_discovered > 0:
            high_quality_ratio = high_quality_count / total_discovered

            if high_quality_ratio < 0.3:
                recommendations.append(
                    {
                        "category": "Quality Optimization",
                        "priority": "High",
                        "recommendation": "Implement stricter quality filtering - less than 30% of discoveries meet high quality standards.",
                        "action": "Increase minimum quality score threshold and enhance metadata requirements.",
                    }
                )
            elif high_quality_ratio > 0.7:
                recommendations.append(
                    {
                        "category": "Discovery Expansion",
                        "priority": "Medium",
                        "recommendation": "Quality filtering is excellent - consider expanding discovery scope.",
                        "action": "Add more monitored artists or reduce quality thresholds slightly to increase discovery volume.",
                    }
                )

        # Artist performance recommendations
        top_artists = performance.get("artist_performance", {}).get(
            "top_performing_artists", []
        )
        if len(top_artists) < 5:
            recommendations.append(
                {
                    "category": "Artist Management",
                    "priority": "High",
                    "recommendation": "Limited high-performing artists detected.",
                    "action": "Review and expand monitored artist list, focusing on artists with consistent IMVDB presence.",
                }
            )

        return recommendations


# Global service instance
imvdb_analytics_service = IMVDbAnalyticsService()
