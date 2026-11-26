"""The conversations Jarvis is tested on, taken from his real logs.

Each case is a short conversation. Each turn:
  say        what he says (as Whisper would type it, misheard words included)
  tool       the tool Jarvis should use: a name, or a list (any of them is fine), or "none" (no tool)
  not        tools he must NOT use for it (live runs check this)
  hide       tools that must not even be offered to the model (so it can't pick them)
  close      True if this should end the conversation, False if it must not
  answering  True if Jarvis just asked him a question (so his words are the answer)
  says_not   a regex the spoken reply must not match (live mode only)
Setup per case:
  screen     a page on his screen ("cbc" is a news article)
  last_doc   a slide deck he just made (for "make it prettier")
"""

CASES = [
    # ---------- briefs and the screen ----------
    {"id": "brief-article", "screen": "cbc", "turns": [
        {"say": "Can you brief this article for me?", "tool": "brief_document", "hide": ["web_search", "look_at_screen"],
         "says_not": r"(?i)link|paste|don't see"}]},
    {"id": "brief-misheard", "screen": "cbc", "turns": [
        {"say": "Can you breathe this off?", "tool": "brief_document"}]},
    {"id": "brief-write-me", "screen": "cbc", "turns": [
        {"say": "Could you write me a brief?", "tool": "brief_document"}]},
    {"id": "brief-of-the", "screen": "cbc", "turns": [
        {"say": "Can you give me a brief of the article on my screen?", "tool": "brief_document"}]},
    {"id": "screen-what-is-up", "screen": "cbc", "turns": [
        {"say": "What's on my screen right now?", "tool": "read_screen", "hide": ["look_at_screen", "web_search"]}]},
    {"id": "screen-read-off", "screen": "cbc", "turns": [
        {"say": "Can you read it off of my screen?", "tool": "read_screen", "hide": ["web_search"]}]},
    {"id": "screen-code", "screen": "cbc", "turns": [
        {"say": "Check the code of this page", "tool": "read_screen", "not": ["web_search"]}]},
    {"id": "screen-picture", "screen": "cbc", "turns": [
        {"say": "What's in this picture on my screen?", "tool": ["look_at_screen", "read_screen"]}]},
    {"id": "slides-on-article", "screen": "cbc", "turns": [
        {"say": "Can you make me a presentation on this article here?", "tool": "make_document",
         "hide": ["web_search"], "says_not": r"(?i)link|paste"}]},
    {"id": "slides-follow-up", "screen": "cbc", "turns": [
        {"say": "What's this article about?", "tool": "read_screen", "not": ["web_search"]},
        {"say": "Now make slides on it", "tool": "make_document", "hide": ["web_search"]}]},
    {"id": "quiz-on-screen", "screen": "cbc", "turns": [
        {"say": "Quiz me on what I have up", "tool": "quiz_me", "hide": ["web_search"]}]},
    {"id": "slides-no-topic", "turns": [
        {"say": "Can you make me a presentation?", "tool": "none", "not": ["make_document"],
         "says_not": r"(?i)your presentation\.pptx"}]},
    # ---------- documents ----------
    {"id": "restyle-prettier", "last_doc": True, "turns": [
        {"say": "Make it look prettier.", "tool": "restyle_document", "hide": ["make_document"]}]},
    {"id": "restyle-corporate", "last_doc": True, "turns": [
        {"say": "Make it a corporate.", "tool": "restyle_document", "hide": ["make_document"]}]},
    {"id": "restyle-pretty-up", "last_doc": True, "turns": [
        {"say": "Can you pretty up the slideshow?", "tool": "restyle_document", "hide": ["make_document"]}]},
    {"id": "new-corporate-deck", "last_doc": True, "turns": [
        {"say": "Make a corporate presentation about cyber security", "tool": "make_document",
         "not": ["restyle_document"]}]},
    {"id": "word-outline", "turns": [
        {"say": "Write me an outline for my essay on renewable energy as a Word doc",
         "tool": ["make_document", "make_file"]}]},
    {"id": "split-screen", "turns": [
        {"say": "Split the screen, have one side the dock, one side the slides.", "tool": "split_screen",
         "says_not": r"(?i)can't (?:physically )?split"}]},
    {"id": "split-screen-2", "turns": [
        {"say": "Put the article next to my essay", "tool": "split_screen"}]},
    # ---------- whiteboard and 3D ----------
    {"id": "whiteboard-led", "turns": [
        {"say": "Can you show me how to wire an LED to an Arduino?", "tool": "show_diagram"}]},
    {"id": "whiteboard-next", "turns": [
        {"say": "Show me how a voltage divider works", "tool": "show_diagram"},
        {"say": "Next step", "tool": "whiteboard_step"}]},
    {"id": "3d-arduino-case", "turns": [
        {"say": "Actually, can you build me a 3D model for the Arduino case?", "tool": "make_3d_model"}]},
    {"id": "3d-taller", "turns": [
        {"say": "Make me a phone stand", "tool": "make_3d_model"},
        {"say": "Make it 10 mm taller", "tool": "make_3d_model"}]},
    # ---------- music, YouTube, browsers ----------
    {"id": "youtube-play", "turns": [
        {"say": "Open YouTube and play never gonna give you up", "tool": ["open_website", "play_music"],
         "not": ["use_computer"]}]},
    {"id": "music-play", "turns": [
        {"say": "Play Blinding Lights", "tool": "play_music", "not": ["use_computer"]}]},
    {"id": "music-pause", "turns": [
        {"say": "Pause the music", "tool": "media"}]},
    {"id": "brave-open", "turns": [
        {"say": "Open Brave", "tool": ["open_app", "open_website"]}]},
    {"id": "brave-search", "turns": [
        {"say": "Pull up data breach news on Brave", "tool": ["open_website", "get_news", "web_search"]}]},
    {"id": "volume", "turns": [
        {"say": "Turn the volume down a bit", "tool": "set_volume"}]},
    # ---------- files ----------
    {"id": "find-file", "turns": [
        {"say": "Find my thermo notes", "tool": ["find_files", "read_file"]}]},
    {"id": "sort-downloads", "turns": [
        {"say": "Sort out my downloads folder", "tool": "organize_folder"}]},
    {"id": "undo", "turns": [
        {"say": "Undo that.", "tool": "undo_files"}]},
    {"id": "open-documents", "turns": [
        {"say": "Open my documents folder", "tool": ["open_folder", "open_file"]}]},
    # ---------- school ----------
    {"id": "canvas-due", "turns": [
        {"say": "What's due this week on Canvas?", "tool": "canvas_due"}]},
    {"id": "canvas-files", "turns": [
        {"say": "Download my class files from Canvas", "tool": "canvas_download"}]},
    {"id": "quiz-topic", "turns": [
        {"say": "Quiz me on thermodynamics", "tool": "quiz_me"}]},
    # ---------- reminders, time, calendar ----------
    {"id": "reminder", "turns": [
        {"say": "Remind me to call mom at 6 pm", "tool": "set_reminder"}]},
    {"id": "timer", "turns": [
        {"say": "Set a timer for 10 minutes", "tool": "set_timer"}]},
    {"id": "alarm", "turns": [
        {"say": "Wake me up at 7 tomorrow", "tool": "set_alarm"}]},
    {"id": "calendar", "turns": [
        {"say": "What's on my calendar tomorrow?", "tool": "get_calendar_events"}]},
    {"id": "weather", "turns": [
        {"say": "What's the weather like in Courtice?", "tool": "get_weather"}]},
    {"id": "remember", "turns": [
        {"say": "Remember that my exam is on Tuesday", "tool": "remember"}]},
    # ---------- phone ----------
    {"id": "phone-test", "turns": [
        {"say": "Can you test my phone notifications?", "tool": "test_phone_alerts"}]},
    {"id": "phone-test-2", "turns": [
        {"say": "Test my phone alerts", "tool": "test_phone_alerts"}]},
    # ---------- plain talk (no tool) ----------
    {"id": "chat-joke", "turns": [
        {"say": "Tell me a joke", "tool": "none"}]},
    {"id": "chat-explain", "turns": [
        {"say": "What's the difference between AC and DC?", "tool": ["none", "show_diagram"]}]},
    {"id": "maths", "turns": [
        {"say": "What's 15 percent of 240?", "tool": ["calculate", "none"]}]},
    # ---------- goodbyes and conversation flow ----------
    {"id": "bye-thats-everything", "turns": [
        {"say": "That's everything.", "close": True, "answering": True}]},
    {"id": "bye-its-okay", "turns": [
        {"say": "It's okay.", "close": True, "answering": True}]},
    {"id": "bye-thats-all", "turns": [
        {"say": "No, Jarvis, it's okay. That's all for now.", "close": True, "answering": True}]},
    {"id": "bye-cool-thanks", "turns": [
        {"say": "Cool, that's everything, thank you.", "close": True}]},
    {"id": "bye-see-ya", "turns": [
        {"say": "See ya.", "close": True}]},
    {"id": "not-bye-yes", "turns": [
        {"say": "Yes, go ahead.", "close": False, "answering": True}]},
    {"id": "not-bye-thanks-answer", "turns": [
        {"say": "Thanks, make it blue", "close": False, "answering": True}]},
    {"id": "not-bye-keep-going", "turns": [
        {"say": "No, no, just keep continuing building the 3D part.", "close": False, "answering": True}]},
    # ---------- his name mid-conversation ----------
    {"id": "name-front", "turns": [
        {"say": "Jarvis, and what about Friday?", "close": False, "addressed": True}]},
    {"id": "name-end", "turns": [
        {"say": "What do you think, Jarvis?", "close": False, "addressed": True}]},
    {"id": "name-misheard", "turns": [
        {"say": "Travis, set a timer for five minutes", "tool": "set_timer", "addressed": True}]},
    {"id": "name-other-person", "turns": [
        {"say": "Travis is coming over later", "addressed": False}]},
]
