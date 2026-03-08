import requests
import time
from duckduckgo_search import DDGS
from googlesearch import search as google_search

class WebSearcher:
    def __init__(self):
        self.ddgs = DDGS()

    def search_articles(self, query, max_results=3):
        # Try DuckDuckGo first, fall back to Google if rate-limited
        results = self._search_duckduckgo(query, max_results)
        if results is None:
            # DuckDuckGo failed (rate-limited), try Google
            print(f"DuckDuckGo failed, falling back to Google for: '{query}'")
            results = self._search_google(query, max_results)
        return results

    def _search_duckduckgo(self, query, max_results):
        """Search using DuckDuckGo. Returns list of results, or None if rate-limited."""
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                raw_results = list(self.ddgs.text(query, max_results=max_results * 2))
                return self._validate_results(raw_results, max_results, key_href='href', key_body='body')
            except Exception as e:
                error_str = str(e).lower()
                if "ratelimit" in error_str or "202" in error_str:
                    wait_time = (attempt + 1) * 5
                    print(f"DuckDuckGo rate-limited for '{query}', retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    self.ddgs = DDGS()
                    if attempt == max_retries - 1:
                        print(f"DuckDuckGo failed after {max_retries} retries for: '{query}'")
                        return None  # Signal to fall back
                else:
                    print(f"DuckDuckGo error for '{query}': {e}")
                    return None  # Signal to fall back
        return None

    def _search_google(self, query, max_results):
        """Search using Google as a fallback. Returns list of results."""
        results = []
        try:
            # google_search returns URLs directly
            urls = list(google_search(query, num_results=max_results * 2, lang="fr"))
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            
            for url in urls:
                if len(results) >= max_results:
                    break
                    
                try:
                    res = requests.get(url, headers=headers, timeout=3, allow_redirects=True, stream=True)
                    if res.status_code >= 400:
                        res.close()
                        continue
                    
                    chunk = next(res.iter_content(chunk_size=10240), b'').decode('utf-8', errors='ignore').lower()
                    res.close()
                    
                    if any(marker in chunk for marker in ["404 page not found", "<title>404", "page not found", "could not be found"]):
                        continue
                    
                    # Extract a title from the page
                    import re
                    title_match = re.search(r'<title[^>]*>(.*?)</title>', chunk)
                    title = title_match.group(1).strip() if title_match else url
                    
                    results.append({
                        "title": title,
                        "link": url,
                        "snippet": ""
                    })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Google search error for '{query}': {e}")
        
        return results

    def _validate_results(self, raw_results, max_results, key_href='href', key_body='body'):
        """Validate URLs from search results, filtering out broken links."""
        results = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        for r in raw_results:
            link = r.get(key_href, '')
            if not link:
                continue
            
            try:
                res = requests.get(link, headers=headers, timeout=3, allow_redirects=True, stream=True)
                if res.status_code >= 400:
                    res.close()
                    continue
                
                chunk = next(res.iter_content(chunk_size=10240), b'').decode('utf-8', errors='ignore').lower()
                res.close()
                
                if any(marker in chunk for marker in ["404 page not found", "<title>404", "page not found", "could not be found"]):
                    continue
            except requests.RequestException:
                continue
            except Exception:
                continue
            
            results.append({
                "title": r.get('title', ''),
                "link": link,
                "snippet": r.get(key_body, '')
            })
            
            if len(results) >= max_results:
                break
        
        return results
