"""Tests for health score perception integration.

Verifies that _score_sentiment blends video perception signals
(engagement, confusion, disengagement) with insight-based sentiment.
"""

from src.memory.health_score import HealthScoreCalculator
from src.models.lead_memory import Sentiment


class FakeInsight:
    def __init__(self, sentiment: Sentiment):
        self.sentiment = sentiment


def test_score_sentiment_with_no_perception_data():
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.POSITIVE), FakeInsight(Sentiment.NEUTRAL)]
    score = calc._score_sentiment(insights)
    assert 0.5 < score <= 1.0


def test_score_sentiment_with_perception_data():
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.POSITIVE)]
    perception_data = {
        "engagement_score": 0.3,
        "confusion_events": 5,
        "disengagement_events": 2,
    }
    score = calc._score_sentiment(insights, perception_data=perception_data)
    pure_score = calc._score_sentiment(insights)
    assert score < pure_score


def test_score_sentiment_perception_high_engagement():
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.NEUTRAL)]
    perception_data = {
        "engagement_score": 0.95,
        "confusion_events": 0,
        "disengagement_events": 0,
    }
    score = calc._score_sentiment(insights, perception_data=perception_data)
    pure_score = calc._score_sentiment(insights)
    assert score >= pure_score
