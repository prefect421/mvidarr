"""
Thumbnail Generator - AI Selector Module
AI-powered intelligent thumbnail selection using computer vision and content analysis
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

try:
    import numpy as np
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    np = None

if TYPE_CHECKING:
    from PIL import Image as ImageType

# AI/ML imports
try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

from src.services.ai_content_analyzer import AnalysisType, get_ai_content_analyzer
from src.services.thumbnail_models import SmartThumbnailConfig, ThumbnailCandidate
from src.utils.logger import get_logger

logger = get_logger("mvidarr.thumbnail_ai_selector")


class AIThumbnailSelector:
    """AI-powered intelligent thumbnail selection using computer vision and content analysis"""

    def __init__(self):
        """Initialize AI thumbnail selector"""
        self.face_cascade = None
        self._load_face_detection()
        logger.info("🤖 AI Thumbnail Selector initialized")

    def _load_face_detection(self):
        """Load OpenCV face detection cascade"""
        if OPENCV_AVAILABLE:
            try:
                cascade_path = (
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
                if os.path.exists(cascade_path):
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)
                    logger.info("👤 Face detection loaded successfully")
                else:
                    logger.warning("⚠️ Face detection cascade not found")
            except Exception as e:
                logger.error(f"❌ Face detection loading failed: {e}")

    async def select_best_thumbnail_crop(
        self, image_path: Path, config: SmartThumbnailConfig
    ) -> ThumbnailCandidate:
        """
        Select the best crop region for thumbnail using AI analysis

        Args:
            image_path: Path to source image
            config: Smart thumbnail configuration

        Returns:
            Best thumbnail candidate with crop coordinates
        """
        try:
            if not PIL_AVAILABLE or not image_path.exists():
                raise ValueError(
                    f"Invalid image path or PIL not available: {image_path}"
                )

            # Load image
            image = Image.open(image_path)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Get AI content analysis
            ai_analysis = None
            if config.content_analysis:
                try:
                    analyzer = await get_ai_content_analyzer()
                    analysis_results = await analyzer.analyze_content(
                        str(image_path),
                        content_type=analyzer.ContentType.IMAGE,
                        analysis_types=[
                            AnalysisType.QUALITY_ASSESSMENT,
                            AnalysisType.COLOR_ANALYSIS,
                        ],
                    )
                    if analysis_results:
                        ai_analysis = analysis_results[0]  # Use first result
                except Exception as e:
                    logger.warning(f"⚠️ AI analysis failed, using basic selection: {e}")

            # Generate candidate crops
            candidates = await self._generate_thumbnail_candidates(
                image, config, ai_analysis
            )

            # Score candidates
            scored_candidates = []
            for candidate in candidates:
                score = await self._score_thumbnail_candidate(
                    image, candidate, config, ai_analysis
                )
                scored_candidates.append(score)

            # Select best candidate
            if scored_candidates:
                best_candidate = max(scored_candidates, key=lambda c: c.score)
                logger.info(
                    f"🎯 Selected best thumbnail crop with score: {best_candidate.score:.2f}"
                )
                return best_candidate
            else:
                # Fallback to center crop
                return self._create_fallback_candidate(image, config)

        except Exception as e:
            logger.error(f"❌ AI thumbnail selection failed: {e}")
            # Return center crop as fallback
            image = Image.open(image_path)
            return self._create_fallback_candidate(image, config)

    async def _generate_thumbnail_candidates(
        self, image: "Image.Image", config: SmartThumbnailConfig, ai_analysis=None
    ) -> List[ThumbnailCandidate]:
        """Generate potential thumbnail crop candidates"""
        candidates = []
        img_width, img_height = image.size
        target_ratio = config.width / config.height

        # Face detection candidates
        if config.face_detection and self.face_cascade and OPENCV_AVAILABLE:
            face_candidates = await self._generate_face_centered_candidates(
                image, config, target_ratio
            )
            candidates.extend(face_candidates)

        # Rule of thirds candidates
        if config.rule_of_thirds:
            thirds_candidates = self._generate_rule_of_thirds_candidates(
                img_width, img_height, config, target_ratio
            )
            candidates.extend(thirds_candidates)

        # Center and corner candidates
        center_candidates = self._generate_center_candidates(
            img_width, img_height, config, target_ratio
        )
        candidates.extend(center_candidates)

        # Content-aware candidates (if AI analysis available)
        if ai_analysis and config.content_analysis:
            content_candidates = await self._generate_content_aware_candidates(
                image, ai_analysis, config, target_ratio
            )
            candidates.extend(content_candidates)

        return candidates

    async def _generate_face_centered_candidates(
        self, image: "Image.Image", config: SmartThumbnailConfig, target_ratio: float
    ) -> List[ThumbnailCandidate]:
        """Generate candidates centered on detected faces"""
        candidates = []

        try:
            # Convert to OpenCV format for face detection
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )

            if len(faces) > 0:
                # Create candidates for each face
                for x, y, w, h in faces:
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2

                    # Calculate crop box centered on face
                    crop_box = self._calculate_crop_box(
                        face_center_x, face_center_y, image.size, config, target_ratio
                    )

                    if crop_box:
                        candidates.append(
                            ThumbnailCandidate(
                                crop_box=crop_box,
                                score=0.0,  # Will be scored later
                                has_faces=True,
                                face_count=len(faces),
                                quality_score=0.0,
                                composition_score=0.8,  # High composition score for face-centered
                                content_score=0.0,
                                reasons=["Face-centered crop"],
                            )
                        )

                logger.debug(f"👤 Generated {len(candidates)} face-centered candidates")

        except Exception as e:
            logger.error(f"❌ Face detection failed: {e}")

        return candidates

    def _generate_rule_of_thirds_candidates(
        self,
        img_width: int,
        img_height: int,
        config: SmartThumbnailConfig,
        target_ratio: float,
    ) -> List[ThumbnailCandidate]:
        """Generate candidates using rule of thirds composition"""
        candidates = []

        # Rule of thirds intersection points
        third_x1, third_x2 = img_width // 3, 2 * img_width // 3
        third_y1, third_y2 = img_height // 3, 2 * img_height // 3

        intersection_points = [
            (third_x1, third_y1),
            (third_x2, third_y1),
            (third_x1, third_y2),
            (third_x2, third_y2),
        ]

        for center_x, center_y in intersection_points:
            crop_box = self._calculate_crop_box(
                center_x, center_y, (img_width, img_height), config, target_ratio
            )

            if crop_box:
                candidates.append(
                    ThumbnailCandidate(
                        crop_box=crop_box,
                        score=0.0,
                        has_faces=False,
                        face_count=0,
                        quality_score=0.0,
                        composition_score=0.7,  # Good composition score for rule of thirds
                        content_score=0.0,
                        reasons=["Rule of thirds composition"],
                    )
                )

        return candidates

    def _generate_center_candidates(
        self,
        img_width: int,
        img_height: int,
        config: SmartThumbnailConfig,
        target_ratio: float,
    ) -> List[ThumbnailCandidate]:
        """Generate center-based candidates"""
        candidates = []

        # Perfect center
        center_x, center_y = img_width // 2, img_height // 2
        crop_box = self._calculate_crop_box(
            center_x, center_y, (img_width, img_height), config, target_ratio
        )

        if crop_box:
            candidates.append(
                ThumbnailCandidate(
                    crop_box=crop_box,
                    score=0.0,
                    has_faces=False,
                    face_count=0,
                    quality_score=0.0,
                    composition_score=0.5,  # Neutral composition score for center
                    content_score=0.0,
                    reasons=["Center crop"],
                )
            )

        # Slightly offset centers (to avoid perfect symmetry)
        offsets = [(0.1, 0.1), (-0.1, 0.1), (0.1, -0.1), (-0.1, -0.1)]
        for offset_x, offset_y in offsets:
            offset_center_x = int(center_x + offset_x * img_width * 0.1)
            offset_center_y = int(center_y + offset_y * img_height * 0.1)

            crop_box = self._calculate_crop_box(
                offset_center_x,
                offset_center_y,
                (img_width, img_height),
                config,
                target_ratio,
            )

            if crop_box:
                candidates.append(
                    ThumbnailCandidate(
                        crop_box=crop_box,
                        score=0.0,
                        has_faces=False,
                        face_count=0,
                        quality_score=0.0,
                        composition_score=0.4,
                        content_score=0.0,
                        reasons=["Offset center crop"],
                    )
                )

        return candidates

    async def _generate_content_aware_candidates(
        self,
        image: "Image.Image",
        ai_analysis,
        config: SmartThumbnailConfig,
        target_ratio: float,
    ) -> List[ThumbnailCandidate]:
        """Generate candidates based on AI content analysis"""
        candidates = []

        try:
            # Use AI analysis to identify interesting regions
            results = ai_analysis.results

            # If we have color analysis, focus on areas with dominant colors
            if "dominant_colors" in results:
                # This is a simplified approach - in reality, you'd analyze
                # color distribution and focus on regions with interesting colors
                img_width, img_height = image.size

                # Generate candidates in regions that might have interesting content
                # Based on the golden ratio
                golden_ratio = 1.618
                golden_x = int(img_width / golden_ratio)
                golden_y = int(img_height / golden_ratio)

                for center_x, center_y in [
                    (golden_x, golden_y),
                    (img_width - golden_x, golden_y),
                    (golden_x, img_height - golden_y),
                ]:
                    crop_box = self._calculate_crop_box(
                        center_x,
                        center_y,
                        (img_width, img_height),
                        config,
                        target_ratio,
                    )

                    if crop_box:
                        candidates.append(
                            ThumbnailCandidate(
                                crop_box=crop_box,
                                score=0.0,
                                has_faces=False,
                                face_count=0,
                                quality_score=0.0,
                                composition_score=0.6,
                                content_score=0.7,  # Higher content score for AI-guided
                                reasons=["AI content analysis guided"],
                            )
                        )

        except Exception as e:
            logger.error(f"❌ Content-aware candidate generation failed: {e}")

        return candidates

    def _calculate_crop_box(
        self,
        center_x: int,
        center_y: int,
        image_size: Tuple[int, int],
        config: SmartThumbnailConfig,
        target_ratio: float,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Calculate crop box given center point and target ratio"""
        img_width, img_height = image_size

        # Calculate crop dimensions maintaining aspect ratio
        if target_ratio > (img_width / img_height):
            # Width-constrained
            crop_width = min(img_width, int(img_height * target_ratio))
            crop_height = int(crop_width / target_ratio)
        else:
            # Height-constrained
            crop_height = min(img_height, int(img_width / target_ratio))
            crop_width = int(crop_height * target_ratio)

        # Calculate crop box coordinates
        half_width = crop_width // 2
        half_height = crop_height // 2

        left = max(0, min(center_x - half_width, img_width - crop_width))
        top = max(0, min(center_y - half_height, img_height - crop_height))
        right = left + crop_width
        bottom = top + crop_height

        # Validate crop box
        if right <= img_width and bottom <= img_height and left >= 0 and top >= 0:
            return (left, top, right, bottom)

        return None

    async def _score_thumbnail_candidate(
        self,
        image: "Image.Image",
        candidate: ThumbnailCandidate,
        config: SmartThumbnailConfig,
        ai_analysis=None,
    ) -> ThumbnailCandidate:
        """Score a thumbnail candidate based on multiple criteria"""

        try:
            # Extract crop region
            crop = image.crop(candidate.crop_box)

            # Quality scoring
            quality_score = await self._assess_crop_quality(crop)
            candidate.quality_score = quality_score

            # Face scoring
            face_score = 0.0
            if candidate.has_faces:
                face_score = config.face_priority * (1.0 + candidate.face_count * 0.1)

            # Edge avoidance scoring
            edge_score = 0.0
            if config.avoid_edges:
                edge_score = self._calculate_edge_avoidance_score(
                    candidate.crop_box, image.size
                )

            # Content scoring (if AI analysis available)
            content_score = candidate.content_score
            if ai_analysis and config.content_analysis:
                content_score *= ai_analysis.confidence

            # Calculate final score
            final_score = (
                quality_score * 0.3
                + face_score * 0.3
                + candidate.composition_score * 0.2
                + content_score * 0.1
                + edge_score * 0.1
            )

            candidate.score = final_score

            # Update reasons
            if quality_score > 0.8:
                candidate.reasons.append("High image quality")
            if face_score > 0.5:
                candidate.reasons.append("Contains faces")
            if edge_score > 0.7:
                candidate.reasons.append("Good positioning")

            return candidate

        except Exception as e:
            logger.error(f"❌ Candidate scoring failed: {e}")
            candidate.score = 0.0
            return candidate

    async def _assess_crop_quality(self, crop_image: "Image.Image") -> float:
        """Assess the quality of a crop region"""
        try:
            if not OPENCV_AVAILABLE or not np:
                return 0.5  # Default neutral score

            # Convert to OpenCV format
            cv_crop = cv2.cvtColor(np.array(crop_image), cv2.COLOR_RGB2BGR)
            gray_crop = cv2.cvtColor(cv_crop, cv2.COLOR_BGR2GRAY)

            # Calculate sharpness (Laplacian variance)
            sharpness = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
            normalized_sharpness = min(1.0, sharpness / 1000.0)

            # Calculate contrast (standard deviation)
            contrast = np.std(gray_crop) / 255.0

            # Calculate brightness balance
            brightness = np.mean(gray_crop) / 255.0
            brightness_balance = 1.0 - abs(brightness - 0.5) * 2

            # Combine quality metrics
            quality_score = (
                normalized_sharpness * 0.4 + contrast * 0.3 + brightness_balance * 0.3
            )

            return min(1.0, quality_score)

        except Exception as e:
            logger.error(f"❌ Quality assessment failed: {e}")
            return 0.5

    def _calculate_edge_avoidance_score(
        self, crop_box: Tuple[int, int, int, int], image_size: Tuple[int, int]
    ) -> float:
        """Calculate score based on distance from image edges"""
        left, top, right, bottom = crop_box
        img_width, img_height = image_size

        # Calculate distance from each edge (normalized)
        left_dist = left / img_width
        top_dist = top / img_height
        right_dist = (img_width - right) / img_width
        bottom_dist = (img_height - bottom) / img_height

        # Score based on minimum distance to any edge
        min_edge_dist = min(left_dist, top_dist, right_dist, bottom_dist)

        # Give higher scores to crops that are more centered
        return min_edge_dist * 2  # Scale to 0-1 range

    def _create_fallback_candidate(
        self, image: "Image.Image", config: SmartThumbnailConfig
    ) -> ThumbnailCandidate:
        """Create fallback center crop candidate"""
        img_width, img_height = image.size
        center_x, center_y = img_width // 2, img_height // 2
        target_ratio = config.width / config.height

        crop_box = self._calculate_crop_box(
            center_x, center_y, (img_width, img_height), config, target_ratio
        )

        if crop_box is None:
            # Ultimate fallback - entire image
            crop_box = (0, 0, img_width, img_height)

        return ThumbnailCandidate(
            crop_box=crop_box,
            score=0.5,
            has_faces=False,
            face_count=0,
            quality_score=0.5,
            composition_score=0.5,
            content_score=0.5,
            reasons=["Fallback center crop"],
        )
