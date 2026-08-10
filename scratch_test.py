from collections import defaultdict
import math

class SanitizedReview:
    def __init__(self, content, score=1, thumbs=0):
        self.sanitized_content = content
        self.score = score
        self.thumbs_up_count = thumbs
        self.is_negative = score < 3
        self.review_id = "test"

def test_assign():
    reviews = [
        SanitizedReview("The app is crashing on login"),
        SanitizedReview("Brokerage fees are too high"),
        SanitizedReview("Customer support did not respond to my email"),
        SanitizedReview("App performance is terrible"),
        SanitizedReview("General feedback is good"),
    ]
    themes = ["App Crash on Login", "High Brokerage Fees", "Customer Support", "App Performance", "General Feedback"]
    
    clusters_map = defaultdict(list)
    outliers = []
    
    theme_keywords = {t: set(t.lower().split()) for t in themes}
    print("Keywords:", theme_keywords)
    
    for r in reviews:
        content_lower = r.sanitized_content.lower()
        best_theme = None
        best_score = 0
        for theme, keywords in theme_keywords.items():
            score = sum(1 for k in keywords if k in content_lower)
            if score > best_score:
                best_score = score
                best_theme = theme
        
        if best_theme and best_score > 0:
            clusters_map[best_theme].append(r)
        else:
            outliers.append(r)
            
    print("clusters_map keys:", clusters_map.keys())
    for k, v in clusters_map.items():
        print(f"  {k}: {len(v)}")
    print("outliers:", len(outliers))
    
    # If all went to outliers, fallback
    if not clusters_map and reviews:
        clusters_map[themes[0]] = reviews
        outliers = []

    cluster_info_list = []
    c_id = 0
    for theme_name, member_reviews in clusters_map.items():
        if len(member_reviews) < 2:
            outliers.extend(member_reviews)
            continue
        c_id += 1
        
    print("Final clusters:", c_id)
    print("Final outliers:", len(outliers))

if __name__ == "__main__":
    test_assign()
