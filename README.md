# get_to_know_me
A locally running assistant that records your interests and proposes discussion topics and interesting articles.

The program interacts with a locally running LLM served by ollama.
The data about the user is recorded in a text file, fully visible and editable by the user.
The user can ask to have some data corrected or removed.
The agent must propose articles from the internet that should be interesting for the user. Occasionnally, the agent must suggest content that is out of
the user's interest domains, to avoid the risk of echo chamber.
