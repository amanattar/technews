import re
from typing import Dict, Tuple, List
from django.conf import settings
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def calculate_priority_label(title: str, description: str, content: str = "") -> Tuple[str, Dict[str, str]]:
    """
    Calculate priority label based on keyword matching
    Returns: (priority_label, keyword_matches_dict)
    """
    keyword_priorities = getattr(settings, 'KEYWORD_PRIORITIES', {})
    
    # Combine all text for analysis
    full_text = f"{title} {description} {content}".lower()
    
    # Track matched keywords and their priorities
    keyword_matches = {}
    priority_weights = {'high': 3, 'medium': 2, 'low': 1}
    total_weight = 0
    high_priority_count = 0
    medium_priority_count = 0
    
    for keyword, priority in keyword_priorities.items():
        keyword_lower = keyword.lower()
        
        # Count occurrences (but cap at reasonable limit to avoid spam)
        count = min(full_text.count(keyword_lower), 3)
        
        if count > 0:
            # Apply positional weighting (title words worth more)
            title_matches = title.lower().count(keyword_lower)
            description_matches = description.lower().count(keyword_lower) if description else 0
            
            # Store the highest priority found for this keyword
            keyword_matches[keyword] = priority
            
            # Calculate weighted contribution
            weight_multiplier = 1
            if title_matches > 0:
                weight_multiplier = 2  # Title matches are more important
            elif description_matches > 0:
                weight_multiplier = 1.5  # Description matches are somewhat important
            
            weighted_contribution = priority_weights[priority] * weight_multiplier * count
            total_weight += weighted_contribution
            
            # Count priority levels
            if priority == 'high':
                high_priority_count += count
            elif priority == 'medium':
                medium_priority_count += count
    
    # Check for breaking news indicators
    breaking_indicators = ['breaking', 'urgent', 'exclusive', 'just in', 'developing']
    has_breaking = any(indicator in full_text for indicator in breaking_indicators)
    if has_breaking:
        keyword_matches['breaking_indicator'] = 'high'
        high_priority_count += 1
        total_weight += 6  # High bonus for breaking news
    
    # Determine final priority label
    if high_priority_count >= 2 or has_breaking:
        final_priority = 'high'
    elif high_priority_count >= 1 or medium_priority_count >= 3:
        final_priority = 'medium'
    elif medium_priority_count >= 1 or total_weight > 0:
        final_priority = 'low'
    else:
        final_priority = 'minimal'
    
    return final_priority, keyword_matches


# Keep backward compatibility with old function name
def calculate_priority_score(title: str, description: str, content: str = "") -> Tuple[float, Dict[str, float]]:
    """
    Legacy function for backward compatibility - converts priority labels to scores
    Returns: (numeric_score, keyword_matches_with_scores)
    """
    priority_label, keyword_matches = calculate_priority_label(title, description, content)
    
    # Convert priority label to numeric score for backward compatibility
    label_to_score = {
        'high': 20.0,
        'medium': 10.0, 
        'low': 5.0,
        'minimal': 1.0
    }
    
    # Convert keyword matches to scores
    priority_to_score = {'high': 5.0, 'medium': 3.0, 'low': 1.0}
    keyword_scores = {}
    for keyword, priority in keyword_matches.items():
        keyword_scores[keyword] = priority_to_score.get(priority, 1.0)
    
    return label_to_score.get(priority_label, 1.0), keyword_scores


def extract_keywords(text: str, min_length: int = 3) -> List[str]:
    """Extract meaningful keywords from text"""
    if not text:
        return []
    
    # Clean text
    text = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
    words = text.split()
    
    # Filter out common stop words and short words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'between', 'among', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
    }
    
    keywords = []
    for word in words:
        if len(word) >= min_length and word not in stop_words:
            keywords.append(word)
    
    # Return unique keywords, preserving order
    seen = set()
    unique_keywords = []
    for keyword in keywords:
        if keyword not in seen:
            seen.add(keyword)
            unique_keywords.append(keyword)
    
    return unique_keywords[:20]  # Limit to top 20 keywords


def calculate_recency_bonus(published_date, current_date) -> float:
    """Calculate bonus score based on article recency"""
    if not published_date:
        return 0.0
    
    time_diff = current_date - published_date
    hours_old = time_diff.total_seconds() / 3600
    
    # Recency bonus decreases over time
    if hours_old <= 1:
        return 15.0  # Very recent articles get high bonus
    elif hours_old <= 6:
        return 10.0  # Recent articles get good bonus
    elif hours_old <= 24:
        return 5.0   # Day-old articles get small bonus
    elif hours_old <= 168:  # 1 week
        return 2.0   # Week-old articles get tiny bonus
    else:
        return 0.0   # Older articles get no bonus


def detect_trending_topics(articles_queryset, time_window_hours: int = 24) -> List[Dict]:
    """Detect trending topics based on keyword frequency"""
    from datetime import timedelta
    from django.utils import timezone
    from collections import Counter
    
    cutoff_time = timezone.now() - timedelta(hours=time_window_hours)
    recent_articles = articles_queryset.filter(published_date__gte=cutoff_time)
    
    # Collect all keywords from recent articles
    all_keywords = []
    for article in recent_articles:
        if article.keyword_matches:
            all_keywords.extend(article.keyword_matches.keys())
    
    # Count keyword frequency
    keyword_counts = Counter(all_keywords)
    
    # Calculate trending score (frequency + recency)
    trending_topics = []
    for keyword, count in keyword_counts.most_common(20):
        if count >= 3:  # Minimum threshold for trending
            trending_topics.append({
                'keyword': keyword,
                'count': count,
                'trending_score': count * (24 / time_window_hours)  # Adjust for time window
            })
    
    return trending_topics


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    # Remove or replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = filename.strip('._')
    
    # Limit length
    if len(filename) > 100:
        filename = filename[:100]
    
    return filename or 'export'


def format_article_for_export(article) -> Dict:
    """Format article data for CSV/JSON export"""
    return {
        'title': article.title,
        'url': article.url,
        'source': article.source.name,
        'author': article.author,
        'published_date': article.published_date.isoformat(),
        'priority_score': article.priority_score,
        'final_score': article.get_final_score(),
        'description': article.description[:200] + '...' if len(article.description) > 200 else article.description,
        'tags': ', '.join([tag.name for tag in article.tags.all()]),
        'is_breaking': article.is_breaking,
        'is_trending': article.is_trending,
        'is_featured': article.is_featured,
        'keyword_matches': ', '.join(article.keyword_matches.keys()) if article.keyword_matches else '',
        'scraped_date': article.scraped_date.isoformat(),
    }


def validate_rss_url(url: str) -> Tuple[bool, str]:
    """Validate if URL is a valid RSS feed"""
    import feedparser
    import requests
    
    try:
        # Test URL accessibility with proper headers to avoid 403 errors
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.head(url, timeout=10, headers=headers)
        if response.status_code >= 400:
            # If HEAD request fails, try GET request
            response = requests.get(url, timeout=10, headers=headers)
            if response.status_code >= 400:
                # Provide specific error messages for common issues
                if response.status_code == 403:
                    return False, "Access denied (403). The website may be blocking automated requests. Try adding the source anyway and manually trigger a scrape."
                elif response.status_code == 404:
                    return False, "Feed not found (404). Please check the URL."
                else:
                    return False, f"URL returned status code {response.status_code}"
        
        # Test RSS parsing
        feed = feedparser.parse(url, request_headers=headers)
        
        if hasattr(feed, 'bozo') and feed.bozo:
            if feed.bozo_exception:
                return False, f"RSS parsing error: {feed.bozo_exception}"
        
        if not hasattr(feed, 'entries') or len(feed.entries) == 0:
            return False, "No entries found in RSS feed"
        
        return True, "Valid RSS feed"
        
    except requests.RequestException as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def get_source_health_status(source) -> Dict:
    """Get health status information for a source"""
    from datetime import timedelta
    from django.utils import timezone
    
    now = timezone.now()
    
    # Get recent logs
    recent_logs = source.logs.filter(
        scrape_date__gte=now - timedelta(days=7)
    ).order_by('-scrape_date')[:10]
    
    if not recent_logs:
        return {
            'status': 'unknown',
            'message': 'No recent scraping activity',
            'last_success': None,
            'success_rate': 0.0,
            'avg_articles_per_scrape': 0.0
        }
    
    successful_logs = [log for log in recent_logs if log.success]
    success_rate = len(successful_logs) / len(recent_logs) * 100
    
    last_success = successful_logs[0] if successful_logs else None
    
    # Calculate average articles per successful scrape
    avg_articles = 0.0
    if successful_logs:
        total_articles = sum(log.articles_found for log in successful_logs)
        avg_articles = total_articles / len(successful_logs)
    
    # Determine status
    if success_rate >= 90:
        status = 'healthy'
        message = 'Source is working well'
    elif success_rate >= 70:
        status = 'warning'
        message = 'Some recent failures detected'
    else:
        status = 'error'
        message = 'Frequent failures detected'
    
    # Check if source is overdue for scraping
    if source.last_scraped:
        time_since_scrape = now - source.last_scraped
        expected_interval = timedelta(minutes=source.scrape_frequency * 2)  # 2x buffer
        
        if time_since_scrape > expected_interval:
            status = 'warning'
            message = f'Overdue for scraping by {time_since_scrape}'
    
    return {
        'status': status,
        'message': message,
        'last_success': last_success.scrape_date if last_success else None,
        'success_rate': round(success_rate, 1),
        'avg_articles_per_scrape': round(avg_articles, 1),
        'recent_errors': [log.error_message for log in recent_logs if not log.success and log.error_message][:3]
    }


def generate_article_summary(title: str, content: str, description: str = "") -> str:
    """
    Generate a concise summary of an article using multiple methods.
    Falls back gracefully if external APIs are not available.
    """
    try:
        # Method 1: Try Gemini-2.5-flash API if configured
        gemini_summary = _generate_gemini_summary(title, content, description)
        if gemini_summary:
            return gemini_summary
    except Exception as e:
        logger.warning(f"Gemini summary generation failed: {e}")
    
    try:
        # Method 2: Try local extractive summarization
        extractive_summary = _generate_extractive_summary(title, content, description)
        if extractive_summary:
            return extractive_summary
    except Exception as e:
        logger.warning(f"Extractive summary generation failed: {e}")
    
    # Method 3: Fallback to simple truncated description/content
    return _generate_fallback_summary(title, content, description)


def _generate_gemini_summary(title: str, content: str, description: str = "") -> str:
    """
    Generate summary using Google Gemini API (requires API key in settings)
    """
    try:
        import google.generativeai as genai
        from django.conf import settings
        
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in settings")
            return ""
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Initialize the model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Prepare content for summarization
        full_text = f"Title: {title}\n\n"
        if description:
            full_text += f"Description: {description}\n\n"
        if content:
            # Limit content length to avoid token limits
            content_preview = content[:3000] + "..." if len(content) > 3000 else content
            full_text += f"Content: {content_preview}"
        
        # Create the prompt
        prompt = f"""You are a tech news summarizer. Create a concise, informative summary of this tech article in 2-3 sentences. Focus on key facts, impact, and relevance to the tech industry. Make it engaging and easy to understand.

Article to summarize:
{full_text}

Summary:"""
        
        # Generate the summary
        response = model.generate_content(prompt)
        
        if response.text:
            return response.text.strip()
        else:
            logger.warning("Gemini API returned empty response")
            return ""
        
    except ImportError:
        logger.error("google-generativeai package not installed. Install with: pip install google-generativeai")
        return ""
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return ""


def _generate_extractive_summary(title: str, content: str, description: str = "") -> str:
    """
    Generate summary using extractive summarization (sentence ranking)
    """
    try:
        from collections import Counter
        import re
        
        # Combine and clean text
        full_text = f"{description} {content}".strip()
        if not full_text:
            return description[:200] + "..." if len(description) > 200 else description
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', full_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        if len(sentences) <= 2:
            return full_text[:200] + "..." if len(full_text) > 200 else full_text
        
        # Score sentences based on keyword frequency and position
        word_freq = Counter()
        for sentence in sentences:
            words = re.findall(r'\b\w+\b', sentence.lower())
            word_freq.update(words)
        
        sentence_scores = {}
        for i, sentence in enumerate(sentences):
            words = re.findall(r'\b\w+\b', sentence.lower())
            score = sum(word_freq[word] for word in words)
            
            # Bonus for early sentences
            position_bonus = max(0, 10 - i)
            sentence_scores[sentence] = score + position_bonus
        
        # Select top 2-3 sentences
        top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)[:2]
        
        # Reorder by original position
        selected_sentences = []
        for sentence in sentences:
            if any(sentence == top[0] for top in top_sentences):
                selected_sentences.append(sentence)
        
        summary = '. '.join(selected_sentences).strip()
        if not summary.endswith('.'):
            summary += '.'
        
        return summary
        
    except Exception as e:
        logger.error(f"Extractive summarization error: {e}")
        return ""


def _generate_fallback_summary(title: str, content: str, description: str = "") -> str:
    """
    Fallback summary method - uses description or first part of content
    """
    if description and len(description) > 50:
        summary = description[:200]
        if len(description) > 200:
            summary += "..."
        return summary
    
    if content:
        # Clean HTML if present
        try:
            clean_content = BeautifulSoup(content, 'html.parser').get_text()
        except:
            clean_content = content
        
        # Get first meaningful paragraph
        paragraphs = [p.strip() for p in clean_content.split('\n') if len(p.strip()) > 50]
        if paragraphs:
            summary = paragraphs[0][:200]
            if len(paragraphs[0]) > 200:
                summary += "..."
            return summary
    
    return f"Summary for: {title}" if title else "No summary available."