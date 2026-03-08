import ollama
import json
import re
import requests
from bs4 import BeautifulSoup
from profile_manager import ProfileManager
from web_search import WebSearcher

def get_available_models():
    try:
        models = ollama.list()
        # Some versions of the ollama python client return models as a list directly or under 'models' key
        if getattr(models, 'models', None):
             return [m.model for m in models.models]
        elif isinstance(models, dict) and 'models' in models:
             return [m.get('name') or m.get('model') for m in models['models']]
        elif isinstance(models, list):
             # Try assuming it's a list of objects
             return [getattr(m, 'model', str(m)) for m in models]
        return []
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

class Assistant:
    def __init__(self, model_name):
        self.model_name = model_name

    def process_message(self, user_message, chat_history, current_profile, web_searcher):
        # 1. Analyze if profile needs update
        current_profile_str = json.dumps(current_profile, indent=4, ensure_ascii=False) if isinstance(current_profile, dict) else str(current_profile)
        
        profile_prompt = f"""Current profile:\n{current_profile_str}\n\nUser message: {user_message}
Based on the user message, update the profile. 
CRITICAL RULES:
1. Your output MUST be a valid JSON dictionary containing the user's profile.
2. The JSON keys should be top-level categories like "Name", "Age", "Gender", "City", "Family status", "Professional status", "Interests", etc. Feel free to add new keys if appropriate.
3. If the user states something that CONTRADICTS an existing fact (e.g., they say they aren't learning a language, but it's in the profile), you MUST REMOVE the old fact entirely. Do not just add a note saying they aren't learning it.
4. If they add new interests, append them to the "Interests" array.
5. Do NOT wrap your output in markdown code blocks (like ```json), output RAW JSON ONLY.
6. If NO changes are needed at all, output exactly "NO_UPDATE"."""
        
        try:
            response = ollama.generate(model=self.model_name, prompt=profile_prompt)
            new_profile_text = response['response'].strip()
        except Exception as e:
            print(f"Error calling ollama for profile update: {e}")
            new_profile_text = "NO_UPDATE"
        
        updated_profile = current_profile
        if new_profile_text != "NO_UPDATE" and "NO_UPDATE" not in new_profile_text:
            # Strip markdown code block fences if the LLM wrapped the JSON in them
            cleaned = new_profile_text.strip()
            if cleaned.startswith("```"):
                # Remove opening fence (e.g. ```json or ```)
                cleaned = re.sub(r'^```\w*\s*', '', cleaned)
                # Remove closing fence
                cleaned = re.sub(r'```\s*$', '', cleaned).strip()
            try:
                # Attempt to parse the LLM's raw text as JSON
                updated_profile = json.loads(cleaned)
            except json.JSONDecodeError:
                print(f"Failed to parse LLM profile output as JSON:\n{new_profile_text}")
                # Fallback to current if invalid
                updated_profile = current_profile

        # 2. Analyze if a web search is helpful (either in domain or out of domain)
        updated_profile_str = json.dumps(updated_profile, indent=4, ensure_ascii=False) if isinstance(updated_profile, dict) else str(updated_profile)
        search_prompt = f"""Current profile:\n{updated_profile_str}\n\nUser message: {user_message}
If you should suggest an article (either related to their interests, or deliberately outside their interests to avoid echo chamber), output a short text for a web search query.
If no search is needed, output exactly "NO_SEARCH"."""
        
        try:
            response = ollama.generate(model=self.model_name, prompt=search_prompt)
            search_query = response['response'].strip()
        except Exception as e:
            search_query = "NO_SEARCH"
        
        search_results_text = ""
        performed_search = False
        search_attempted = False
        if search_query != "NO_SEARCH" and "NO_SEARCH" not in search_query:
            search_attempted = True
            results = web_searcher.search_articles(search_query)
            if results:
                performed_search = True
                search_results_text = "Web Search Results (Use these to propose articles to the user):\n" + "\n".join([f"- {r['title']} ({r['link']}): {r['snippet']}" for r in results])
            else:
                search_results_text = "A web search was attempted but returned NO results. Do NOT suggest any URLs or links whatsoever in your response."

        # 3. Fetch content from any URLs the user shared in their message
        user_urls = re.findall(r'https?://[^\s)\]>"\']+', user_message)
        fetched_content_text = ""
        if user_urls:
            fetched_pages = []
            for url in user_urls[:3]:  # Limit to 3 URLs max
                clean_url = url.rstrip('.,;:!?')
                content = self._fetch_url_content(clean_url)
                if content:
                    fetched_pages.append(f"--- Content from {clean_url} ---\n{content}\n--- End of content ---")
            if fetched_pages:
                fetched_content_text = "\n\nThe user shared the following URLs. Here is the actual content fetched from those pages:\n" + "\n\n".join(fetched_pages)

        # 4. Generate final response
        system_prompt = f"""You are a friendly assistant that learns about the user's interests, updates their profile, and proposes discussion topics and interesting articles. 
The user profile is saved independently. Focus on responding to the user naturally. 
IMPORTANT: You MUST interact in the user's language. Detect the language of their message and respond in that same language.

If the User Profile is missing any of the following basic information: Name, Age, Gender, City, Family status, or Professional status, you should naturally and gently ask the user for one or two of these missing details in your response to get to know them better. Do not ask for all of them at once.

User Profile:
{updated_profile_str}

{search_results_text}
{fetched_content_text}

If you have web search results, incorporate them gracefully into your response and share the links.
Occasionnally suggest content that is out of the user's interest domains, to avoid the risk of echo chamber!
CRITICAL RULE: NEVER hallucinate URLs or links. You must ONLY share links that are explicitly provided in the "Web Search Results" above. If you want to discuss a topic but don't have a valid web search result with a link for it, you can discuss the topic but DO NOT invent a URL for it.
- Avant de suggérer un lien URL, vérifie qu'il est valide et accessible.
- Ne suggère aucun lien URL sauf si tu es certain qu'il fonctionne.
- Si tu ne peux pas trouver de lien URL pertinent et valide, ne suggère rien.
If the user shared a URL and you have fetched content from it above, use that content to answer their questions accurately. Do NOT pretend to have read content you haven't actually seen.
"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        try:
            final_response = ollama.chat(model=self.model_name, messages=messages)
            response_text = final_response['message']['content']
        except Exception as e:
            response_text = f"Error processing chat: {e}"
        
        # 4. Post-process: validate all URLs in the response and remove broken ones
        response_text = self._validate_urls_in_response(response_text)

        return {
            "response": response_text,
            "new_profile": updated_profile,
            "search_query": search_query if performed_search else None
        }
    def _fetch_url_content(self, url):
        """Fetch a web page and extract its readable text content."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            res = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            if res.status_code >= 400:
                print(f"Failed to fetch URL {url}: HTTP {res.status_code}")
                return None
            
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Remove script, style, and navigation elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                tag.decompose()
            
            # Extract text
            text = soup.get_text(separator='\n', strip=True)
            
            # Clean up excessive whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = '\n'.join(lines)
            
            # Truncate to avoid overwhelming the LLM context
            max_chars = 5000
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... [content truncated]"
            
            if len(text) < 50:
                print(f"URL {url} returned very little text content")
                return None
                
            print(f"Successfully fetched content from {url} ({len(text)} chars)")
            return text
        except Exception as e:
            print(f"Error fetching URL content from {url}: {e}")
            return None

    def _validate_urls_in_response(self, text):
        """Extract all URLs from the response, validate them, and remove broken ones.
        If any URLs were removed, use the LLM to rewrite the text so it reads naturally."""
        url_pattern = re.compile(r'https?://[^\s\)\]>"\\\']+', re.IGNORECASE)
        urls = url_pattern.findall(text)
        if not urls:
            return text
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        removed_any = False
        for url in urls:
            # Strip trailing punctuation that may have been captured
            clean_url = url.rstrip('.,;:!?')
            is_valid = False
            try:
                res = requests.get(clean_url, headers=headers, timeout=5, allow_redirects=True, stream=True)
                if res.status_code < 400:
                    # Check for soft 404s
                    chunk = next(res.iter_content(chunk_size=10240), b'').decode('utf-8', errors='ignore').lower()
                    res.close()
                    if not any(marker in chunk for marker in ["404 page not found", "<title>404", "page not found", "could not be found"]):
                        is_valid = True
                else:
                    res.close()
            except Exception:
                pass
            
            if not is_valid:
                removed_any = True
                # Remove the broken URL from the text
                # Handle markdown link format: [text](url)
                markdown_link_pattern = re.compile(r'\[([^\]]+)\]\(' + re.escape(clean_url) + r'\)')
                if markdown_link_pattern.search(text):
                    # Replace markdown link with just the link text
                    text = markdown_link_pattern.sub(r'\1', text)
                else:
                    # Replace bare URL with empty string
                    text = text.replace(clean_url, '')
                print(f"Removed invalid URL from response: {clean_url}")
        
        # If we removed any URLs, ask the LLM to rewrite the text so it reads naturally
        if removed_any:
            try:
                rewrite_prompt = f"""The following text had some broken URLs removed, leaving dangling references like "here is an article:" or "check out this link:" with nothing after them.
Rewrite the text so it reads naturally, removing any sentences or fragments that reference a link that is no longer there. Keep the rest of the text intact. Do NOT add any new URLs. Output ONLY the rewritten text, nothing else.

Text to rewrite:
{text}"""
                rewrite_response = ollama.generate(model=self.model_name, prompt=rewrite_prompt)
                text = rewrite_response['response'].strip()
            except Exception as e:
                print(f"Error rewriting text after URL removal: {e}")
                # If rewrite fails, return the text with URLs simply removed
        
        return text

    def generate_initial_greeting(self, current_profile):
        current_profile_str = json.dumps(current_profile, indent=4, ensure_ascii=False) if isinstance(current_profile, dict) else str(current_profile)
        
        if not current_profile or len(current_profile.keys()) == 0 or ("Uncategorized Notes" in current_profile and "None recorded yet" in current_profile["Uncategorized Notes"]):
            system_prompt = """You are a friendly assistant. The user just opened the chat. You know nothing about them yet. 
Your task is to initiate the conversation. Ask open questions to get to know their basic information like Name, Age, Gender, City, Family status, or Professional status, as well as their hobbies. 
Be concise and welcoming. If the user's system or browser language is not English, they might not reply in English, but you must start the conversation now. You can use English for this first message."""
        else:
            system_prompt = f"""You are a friendly assistant. Welcome the user back. Here is their profile:\n{current_profile_str}
Ask them what they'd like to talk about today based on their interests. Be concise.

CRITICAL INSTRUCTION: Analyze the language used in the profile above (e.g., are the keys or values mostly in French, English, etc.?). You MUST interact in that same language from this very start."""
            
        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "system", "content": system_prompt}])
            return response['message']['content']
        except Exception as e:
            if "None recorded yet" in current_profile:
                return "Hello! I'd love to get to know you better. What are your hobbies? Do you have family?"
            return "Welcome back! What are we discussing today?"
